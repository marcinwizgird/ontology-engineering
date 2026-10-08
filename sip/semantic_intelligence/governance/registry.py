"""Users, groups, projects, bindings, ACLs and the policy decision point.

Ported from Semantic Turkey 15.1.3:

* ``Project`` / ``ProjectManager.createProject`` — model type, lexicalization
  model, base URI, default namespace, validation + history switches;
* ``ProjectACL`` — access levels ``R ⊂ RW`` (+ ``EXT``) for *consumers* (other
  projects), a universal ``*`` level and lock levels ``W``/``R``/``NO``, with the
  exact ``resolveAccessibility`` / ``resolveLocking`` rules;
* ``ProjectUserBinding`` — roles, group, languages per (user, project);
* ``STAuthorizationEvaluator.isAuthorized`` — the decision algorithm, step for
  step (see :meth:`PolicyDecisionPoint.authorize`).

Additions the platform needs and Semantic Turkey did not have:

* machine principals carry an ``on_behalf_of`` human and can never exercise
  ``V`` — the PDP strips it before the algebra runs (QR-SEC-02);
* a per-project **AI policy** (may content be sent to an LLM, which agents are
  enabled, budget) checked by the agent runtime on every model call (QR-SEC-03).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from ..core.principal import Principal
from .capabilities import CapabilitySet, Decision, parse_capability, role_grants

__all__ = ["ModelType", "Lexicalization", "AccessLevel", "LockLevel", "ProjectACL",
           "AiPolicy", "ProjectConfig", "Binding", "Group", "Registry",
           "PolicyDecisionPoint", "AuthorizationError"]


class AuthorizationError(PermissionError):
    pass


class ModelType(str, Enum):
    RDFS = "http://www.w3.org/2000/01/rdf-schema"
    OWL = "http://www.w3.org/2002/07/owl"
    SKOS = "http://www.w3.org/2004/02/skos/core"
    ONTOLEX = "http://www.w3.org/ns/lemon/ontolex"


class Lexicalization(str, Enum):
    RDFS = "http://www.w3.org/2000/01/rdf-schema"
    SKOS = "http://www.w3.org/2004/02/skos/core"
    SKOSXL = "http://www.w3.org/2008/05/skos-xl"
    ONTOLEX = "http://www.w3.org/ns/lemon/ontolex"


class AccessLevel(str, Enum):
    R = "R"
    RW = "RW"
    EXT = "EXT"


class LockLevel(str, Enum):
    W = "W"
    R = "R"
    NO = "NO"


def resolve_accessibility(requested: AccessLevel, allowed: AccessLevel) -> bool:
    """``AccessLevel.isAcceptedBy``: ``req == allowed || allowed == RW``."""
    return requested == allowed or allowed == AccessLevel.RW


def resolve_locking(requested: LockLevel, allowed: LockLevel) -> bool:
    """``LockLevel.isAcceptedBy``: ``req == allowed || req == NO || allowed == R``."""
    return requested == allowed or requested == LockLevel.NO or allowed == LockLevel.R


@dataclass
class ProjectACL:
    """``acl.acl = "SYSTEM:RW,otherProject:R,*:R"``; default ``{SYSTEM: RW}``."""

    entries: dict[str, AccessLevel] = field(default_factory=lambda: {"SYSTEM": AccessLevel.RW})
    universal: AccessLevel | None = None
    lock_level: LockLevel = LockLevel.R

    def is_accessible_from(self, consumer: str, access: AccessLevel,
                           lock: LockLevel = LockLevel.NO) -> bool:
        entry = self.entries.get(consumer)
        ok = entry is not None and resolve_accessibility(access, entry)
        if not ok and self.universal is not None:
            ok = resolve_accessibility(access, self.universal)
        return ok and resolve_locking(lock, self.lock_level)


@dataclass
class AiPolicy:
    """Per-project AI-use policy (new in SIP)."""

    llm_allowed: bool = True
    enabled_agents: tuple[str, ...] = ("*",)
    max_tokens_per_run: int = 200_000
    max_steps_per_run: int = 50
    inference_geo: str | None = None

    def agent_enabled(self, agent: str) -> bool:
        return "*" in self.enabled_agents or agent in self.enabled_agents


@dataclass
class ProjectConfig:
    name: str
    base_uri: str
    model: ModelType = ModelType.OWL
    lexicalization: Lexicalization = Lexicalization.RDFS
    default_namespace: str = ""
    languages: tuple[str, ...] = ("en",)
    validation_enabled: bool = False
    history_enabled: bool = True
    read_only: bool = False
    acl: ProjectACL = field(default_factory=ProjectACL)
    ai_policy: AiPolicy = field(default_factory=AiPolicy)
    description: str = ""

    def __post_init__(self) -> None:
        if not self.default_namespace:
            b = self.base_uri
            self.default_namespace = b if b.endswith(("#", "/")) else b + "#"
        if self.validation_enabled and not self.history_enabled:
            # Semantic Turkey refuses this combination: validation needs the support repo.
            raise ValueError("validation requires history to be enabled")


@dataclass
class Binding:
    """``ProjectUserBinding`` — roles, group, languages for (principal, project)."""

    principal: str
    project: str
    roles: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    group: str | None = None


@dataclass
class Group:
    """``UsersGroup`` + ``ProjectGroupBinding.ownedSchemes``."""

    name: str
    owned_schemes: dict[str, set[str]] = field(default_factory=dict)  # project -> schemes
    limited: dict[str, bool] = field(default_factory=dict)            # project -> subjectToGroupLimitations


class Registry:
    """In-memory registry of principals, groups, projects and bindings.

    ``to_graph``/persistence is deliberately not here: governance state is small and
    is serialised by ``platform.Platform.export_governance`` (RDF, "everything's
    RDF") so that a restore brings back who-may-do-what together with content.
    """

    def __init__(self) -> None:
        self.principals: dict[str, Principal] = {}
        self.projects: dict[str, ProjectConfig] = {}
        self.bindings: dict[tuple[str, str], Binding] = {}
        self.groups: dict[str, Group] = {}
        self.custom_roles: dict[str, tuple[str, ...]] = {}
        self.superusers: set[str] = set()

    # -- principals ------------------------------------------------------- #
    def add_principal(self, p: Principal, *, superuser: bool = False) -> Principal:
        if p.is_machine and p.on_behalf_of is None and p.id != "system":
            raise ValueError(f"machine principal {p.id!r} needs on_behalf_of (FR-GOV-03)")
        self.principals[p.id] = p
        if superuser:
            self.superusers.add(p.id)
        return p

    def principal(self, pid: str) -> Principal:
        try:
            return self.principals[pid]
        except KeyError:
            raise KeyError(f"unknown principal {pid!r}") from None

    # -- projects --------------------------------------------------------- #
    def add_project(self, cfg: ProjectConfig) -> ProjectConfig:
        if cfg.name in self.projects:
            raise ValueError(f"project {cfg.name!r} exists")
        self.projects[cfg.name] = cfg
        return cfg

    def bind(self, principal: str, project: str, roles: Iterable[str],
             languages: Iterable[str] = (), group: str | None = None) -> Binding:
        self.principal(principal)
        if project not in self.projects:
            raise KeyError(f"unknown project {project!r}")
        for r in roles:
            if r not in self.custom_roles:
                role_grants(r)  # raises on an unknown role
        b = Binding(principal, project, tuple(roles), tuple(languages), group)
        self.bindings[(principal, project)] = b
        return b

    def binding(self, principal: str, project: str) -> Binding | None:
        return self.bindings.get((principal, project))

    def define_role(self, name: str, capabilities: Iterable[str]) -> None:
        caps = tuple(capabilities)
        for c in caps:
            parse_capability(c)
        self.custom_roles[name] = caps

    def grants(self, principal: str, project: str) -> CapabilitySet:
        b = self.binding(principal, project)
        if b is None:
            return CapabilitySet()
        exprs: list[str] = []
        std = [r for r in b.roles if r not in self.custom_roles]
        out = role_grants(*std) if std else CapabilitySet()
        for r in b.roles:
            if r in self.custom_roles:
                exprs.extend(self.custom_roles[r])
        return out | CapabilitySet.parse(exprs) if exprs else out


_LANG_RE = re.compile(r"^[A-Za-z]{1,8}(-[A-Za-z0-9]{1,8})*$")


class PolicyDecisionPoint:
    """``STAuthorizationEvaluator.isAuthorized`` with the SIP machine rule."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.audit: list[tuple[str, str, str, bool, str]] = []

    def authorize(self, principal: Principal, project: str, capability: str,
                  crudv: str, *, languages: Iterable[str] = (),
                  consumer: str = "SYSTEM", writes_outside_main: bool = False) -> Decision:
        """Semantic Turkey's order of checks:

        1. no actor → deny;
        2. project ACL for the consumer (``R`` or ``RW`` from the requested letters);
        3. read-only project → deny C/U/D on ``rdf`` (everyone, admins included);
        4. admin → allow (machines are never admins here);
        5. machine → strip ``V`` (deny any request containing it);
        6. OR across the binding's roles of the capability algebra;
        7. every requested language must be in the binding **and** in the project
           languages (case-insensitive);
        8. writing outside the main graph additionally needs ``rdf(graph) U``.
        """
        cfg = self.registry.projects.get(project)
        goal = f"{capability}:{crudv}"

        def done(ok: bool, why: str) -> Decision:
            self.audit.append((principal.id if principal else "-", project, goal, ok, why))
            return Decision(ok, why)

        if principal is None or not principal.id:
            return done(False, "no authenticated subject")
        if cfg is None:
            return done(False, f"unknown project {project!r}")
        access = AccessLevel.RW if any(c != "R" for c in crudv) else AccessLevel.R
        if not cfg.acl.is_accessible_from(consumer, access):
            return done(False, f"ACL denies {consumer} {access.value}")
        if cfg.read_only and capability.startswith("rdf") and set(crudv) & set("CUD"):
            return done(False, "project is read-only")
        if principal.is_admin and not principal.is_machine:
            return done(True, "administrator")
        if principal.is_machine and "V" in crudv:
            return done(False, "machine principals never validate (QR-SEC-02)")
        grants = self.registry.grants(principal.id, project)
        req = parse_capability(f'capability({capability}, "{crudv}")')
        if not grants.satisfies(req.topic, req.ops):
            return done(False, f"no role grants {capability} {crudv}")
        langs = [l for l in languages if l and l != "null"]
        if langs:
            b = self.registry.binding(principal.id, project)
            assigned = {l.lower() for l in (b.languages if b else ())}
            proj = {l.lower() for l in cfg.languages}
            for l in langs:
                if not _LANG_RE.match(l):
                    return done(False, f"invalid language tag {l!r}")
                if assigned and l.lower() not in assigned:
                    return done(False, f"binding restricts languages to {sorted(assigned)}")
                if l.lower() not in proj:
                    return done(False, f"{l!r} is not a project language {sorted(proj)}")
        if writes_outside_main and access == AccessLevel.RW and capability.startswith("rdf"):
            if not grants.satisfies(parse_capability('capability(rdf(graph), "U")').topic, "U"):
                return done(False, "writing outside the main graph needs rdf(graph) U")
        return done(True, f"granted {capability} {crudv}")

    def require(self, *args, **kw) -> None:
        d = self.authorize(*args, **kw)
        if not d:
            raise AuthorizationError(d.reason)

    def scheme_ownership(self, principal: Principal, project: str, schemes: Iterable[str],
                         mode: str = "all") -> bool:
        """``ProjectGroupBindingsManager.hasUserOwnershipOfSchemes``: true for machines,
        admins, users with no group or not subject to group limitations."""
        if principal.is_machine or principal.is_admin:
            return True
        b = self.registry.binding(principal.id, project)
        if b is None or b.group is None:
            return True
        g = self.registry.groups.get(b.group)
        if g is None or not g.limited.get(project, False):
            return True
        owned = g.owned_schemes.get(project, set())
        if not owned:
            return False
        req = set(schemes)
        return req <= owned if mode == "all" else bool(req & owned)
