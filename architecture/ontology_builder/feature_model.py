"""Ontology Builder — feature model.

Machine-readable record of the **feature extraction** from the three reference
ontology-editing platforms, and of how each extracted feature maps onto the
**Ontology Engineering Capability Model**
(``ontology_engineering_capabilities.capability_model``).

Sources (all read from source, not from marketing pages):

* **VocBench 3** — ``bitbucket.org/art-uniroma2/vocbench3`` (Angular front end for
  the *Semantic Turkey* RDF platform). The Angular ``src/app/services/*.ts`` layer
  is a 1:1 mirror of the Semantic Turkey HTTP API: **60 service classes, 781
  distinct server operations**. ``src/app/utils/AuthorizationEvaluator.ts`` holds
  the complete authorization policy (**330 guarded actions** over 7 capability
  areas). ``src/app/models/Plugins.ts`` holds the **15 extension points**.
  *(The Semantic Turkey server repo itself is not publicly clonable — it requires
  Bitbucket credentials — so the server contract was recovered from its client.)*
* **WebProtégé** — ``github.com/protegeproject/webprotege`` plus the microservice
  repos (``webprotege-authorization-service``, ``-backend-service``, ``-gwt-ui``,
  ``-robot-service``, ``-event-history-service``, ``-gh-*``). **145 action
  handlers**, **53 built-in capabilities**, **15 built-in roles**.
* **Protégé Desktop** — ``github.com/protegeproject/protege``. **24 OSGi extension
  points**, **7 workspace tabs**, **51 view components**, **132 menu actions**
  (from ``protege-editor-{core,owl}/src/main/resources/plugin.xml``).

This module defines data + accessors only; document generation lives in
``build_docs.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Reference vocabularies
# --------------------------------------------------------------------------- #

#: Delivery layers of the Ontology Builder.
LAYERS: tuple[str, ...] = ("store", "backend", "agent", "ui")

#: RFC-2119 priority for the Ontology Builder implementation.
PRIORITIES: tuple[str, ...] = ("MUST", "SHOULD", "MAY")

#: Roadmap phases (see ROADMAP.md).
PHASES: dict[str, str] = {
    "P0": "Governance Core — projects, RBAC, named-graph layout over Fuseki",
    "P1": "Change Spine — triple-level change tracking, staging, validation, undo",
    "P2": "Authoring Core — resource view, OWL + SKOS editing, trees & lists",
    "P3": "Quality Gate — reasoning, SHACL, ICV, competency-question tests",
    "P4": "Extension & IO Framework — loaders, lifters, transformers, deployers, exporters",
    "P5": "Collaboration & Release — issues, comments, watches, versions, time machine",
    "P6": "Alignment & Metadata — EDOAL mappings, alignment validation, DCAT/VoID registry",
    "P7": "Agentic Layer — the ontology-engineering agents over the whole surface",
    "P8": "Scale-out — federation, observability, multi-tenant hardening",
}


@dataclass(frozen=True)
class SourceTool:
    """One of the three reference platforms we extracted features from."""

    id: str
    name: str
    repo: str
    stack: str
    licence: str
    notes: str


SOURCE_TOOLS: list[SourceTool] = [
    SourceTool(
        "VB3", "VocBench 3 / Semantic Turkey",
        "bitbucket.org/art-uniroma2/vocbench3 (+ semanticturkey, auth-walled)",
        "Angular 1x SPA · Java 11 · Spring + OSGi (Apache Karaf) · RDF4J · "
        "file-based project/user store · tuProlog + jsprolog authorization",
        "BSD-3 / academic (Univ. Roma Tor Vergata, EU Publications Office)",
        "The reference implementation for *controlled collaborative editing*: "
        "multi-project, RBAC-with-validation, triple-level history, staging graphs.",
    ),
    SourceTool(
        "WP", "WebProtégé",
        "github.com/protegeproject/webprotege (+ ~15 microservice repos)",
        "GWT 2.8 client (MVP) · Java servlets · Dagger 2 · MongoDB · Lucene · "
        "OWL API 4.5 · migrating to Spring Boot microservices + Keycloak + RabbitMQ",
        "BSD-2",
        "The reference implementation for *web-scale project sharing*: "
        "capability/role authorization, axiom-level revision history, "
        "declarative forms, perspectives/portlets, watches and threaded comments.",
    ),
    SourceTool(
        "PD", "Protégé Desktop",
        "github.com/protegeproject/protege",
        "Java Swing · OSGi (Equinox/Felix) · OWL API · HermiT/ELK/Pellet/FaCT++",
        "BSD-2",
        "The reference implementation for *deep OWL authoring*: Manchester-syntax "
        "class expression editing, DL reasoning with explanations, refactoring "
        "operations, and a 24-extension-point plugin architecture.",
    ),
]

SOURCE_TOOL_BY_ID = {t.id: t for t in SOURCE_TOOLS}


@dataclass(frozen=True)
class FeatureArea:
    """A coherent slice of Ontology Builder functionality."""

    id: str
    name: str
    description: str
    #: Owning backend package under ``ontology_builder/``.
    package: str


FEATURE_AREAS: list[FeatureArea] = [
    FeatureArea("PRJ", "Project & Workspace Management",
                "The project as the unit of work, configuration, isolation and access.",
                "ontology_builder.projects"),
    FeatureArea("GOV", "Governance, Identity & Access Control",
                "Users, groups, roles, capabilities, project bindings and ACLs.",
                "ontology_builder.governance"),
    FeatureArea("CHG", "Change Tracking, History & Validation",
                "Triple-level change capture, staged commits, accept/reject workflow, undo.",
                "ontology_builder.changes"),
    FeatureArea("VER", "Versioning, Snapshots & Time Travel",
                "Version dumps, tagged snapshots, per-resource time machine, revert.",
                "ontology_builder.versions"),
    FeatureArea("STO", "Storage & Repository Management",
                "Fuseki datasets, named-graph layout, repository configuration, backups.",
                "ontology_builder.store"),
    FeatureArea("EDT", "OWL / RDFS Authoring",
                "Classes, properties, individuals, datatypes, axioms, Manchester syntax.",
                "ontology_builder.authoring.owl"),
    FeatureArea("SKO", "SKOS / Thesaurus Authoring",
                "Concepts, schemes, collections, SKOS-XL labels, notes.",
                "ontology_builder.authoring.skos"),
    FeatureArea("LEX", "Lexicon & Terminology Authoring",
                "OntoLex-Lemon lexicons, lexical entries/forms/senses, terminologist view.",
                "ontology_builder.authoring.ontolex"),
    FeatureArea("BRW", "Browsing, Resource View & Navigation",
                "Trees, lists, the predicate-object resource view, graph view, perspectives.",
                "ontology_builder.browse"),
    FeatureArea("SRCH", "Search & Lookup",
                "Lexical, prefix, advanced and custom search; path-from-root; entity lookup.",
                "ontology_builder.search"),
    FeatureArea("FRM", "Custom Forms & Custom Views",
                "Declarative, data-driven creation/visualisation forms bound to OWL properties.",
                "ontology_builder.forms"),
    FeatureArea("RSN", "Reasoning & Explanation",
                "Consistency, classification, materialisation, entailment justification.",
                "ontology_builder.reasoning"),
    FeatureArea("QLT", "Quality, Constraints & Testing",
                "SHACL, integrity-constraint validation, metrics, competency-question tests.",
                "ontology_builder.quality"),
    FeatureArea("IO", "Import, Export, Transform & Deploy",
                "Loaders, lifters, RDF transformers, reformatting exporters, deployers.",
                "ontology_builder.io"),
    FeatureArea("MAP", "Alignment, Mapping & Reconciliation",
                "EDOAL alignments, alignment validation, mapping projection, remote matchers.",
                "ontology_builder.alignment"),
    FeatureArea("MDR", "Metadata, Catalogs & Publishing",
                "Namespaces/imports, DCAT/VoID/ADMS/LIME metadata, dataset catalogs, docs.",
                "ontology_builder.metadata"),
    FeatureArea("SPQ", "SPARQL & Programmatic Access",
                "Guarded query/update endpoint, stored & parameterised queries, exports.",
                "ontology_builder.sparql"),
    FeatureArea("COL", "Collaboration & Notification",
                "Issues, threaded comments, watches, notification digests, tags.",
                "ontology_builder.collaboration"),
    FeatureArea("EXT", "Extension & Configuration Framework",
                "Extension points, scoped settings/configurations, plugin registry.",
                "ontology_builder.extensions"),
    FeatureArea("S2R", "Structured-Source Lifting",
                "Spreadsheet/DB → RDF lifting with a declarative projection language.",
                "ontology_builder.lifting"),
    FeatureArea("AGT", "Agentic Layer",
                "LLM agents that plan, author, review and explain over the whole surface.",
                "ontology_builder.agents"),
    FeatureArea("UIX", "UI Shell & Client",
                "React application shell, layout persistence, permission-aware rendering.",
                "ontology_builder_ui (React/TypeScript)"),
]

FEATURE_AREA_BY_ID = {a.id: a for a in FEATURE_AREAS}


@dataclass(frozen=True)
class Feature:
    """One extracted, portable feature of the Ontology Builder."""

    id: str
    name: str
    area: str
    description: str
    #: Where it came from, e.g. ``("VB3:Projects.createProject", "WP:CreateNewProject")``.
    evidence: tuple[str, ...]
    #: Capability ids from ``ontology_engineering_capabilities``.
    capabilities: tuple[str, ...]
    layers: tuple[str, ...]
    phase: str
    priority: str
    #: Python module (or React module) that will own it.
    target: str
    #: Existing code in this repo that should be reused rather than rewritten.
    reuse: tuple[str, ...] = ()
    #: Ontology Builder feature ids this one needs.
    depends_on: tuple[str, ...] = ()
    notes: str = ""


# --------------------------------------------------------------------------- #
# The features
# --------------------------------------------------------------------------- #
F = Feature  # brevity

FEATURES: list[Feature] = [
    # ===================== PRJ · Project & Workspace ======================== #
    F("OB.PRJ.01", "Project registry & lifecycle", "PRJ",
      "Create, list, open, close, delete and describe projects; a project is the "
      "unit of configuration, access control, history and release.",
      ("VB3:Projects.createProject/deleteProject/listProjects/accessProject/"
       "disconnectFromProject (52 ops in Projects service)",
       "WP:CreateNewProjectActionHandler, LoadProjectActionHandler, "
       "GetAvailableProjectsWithPermissionActionHandler, MoveProjectsToTrash"),
      ("B.SG.2", "B.SE.3", "T.OO.1"), ("backend", "ui"), "P0", "MUST",
      "ontology_builder.projects.registry",
      reuse=("src/Ontology Modeler/ontology_modeler/config.py",),
      notes="VB3 `Project` carries name, baseURI, defaultNamespace, model, "
            "lexicalizationModel, open, visibility, readOnly, history/validation/"
            "blacklisting/undo/shacl/trivialInference flags, facets, labels."),
    F("OB.PRJ.02", "Semantic model & lexicalization model declaration", "PRJ",
      "Each project declares a core model (OWL | SKOS | SKOS-XL | OntoLex) and an "
      "independent lexicalization model (RDFS | SKOS | SKOS-XL | OntoLex); the UI, "
      "the tree set and the validation rules follow from the pair.",
      ("VB3:Project.model + Project.lexicalizationModel; §4.1.3 of the SWJ paper",),
      ("T.DA.2", "T.DA.6", "T.AC.5"), ("backend", "ui"), "P0", "MUST",
      "ontology_builder.projects.model_profile",
      depends_on=("OB.PRJ.01",),
      notes="This is the single most load-bearing modelling decision VocBench "
            "makes and the reason it can host OWL, SKOS and lexicons in one tool."),
    F("OB.PRJ.03", "Project settings & scoped configuration", "PRJ",
      "Per-project settings with defaults, editable while the project is closed, "
      "some requiring a repository restart.",
      ("VB3:Projects.setProjectProperty/getProjectPropertyMap, Settings service (17 ops)",
       "WP:GetProjectSettings/SetProjectSettings (displayName, description, "
       "defaultLanguage, displayNameSettings, slack/webhook integration)"),
      ("B.SG.3", "T.OO.2"), ("backend", "ui"), "P0", "MUST",
      "ontology_builder.projects.settings", depends_on=("OB.PRJ.01", "OB.EXT.02")),
    F("OB.PRJ.04", "Project access control list & lock levels", "PRJ",
      "A project grants other projects (consumers) an access level (R | RW | EXT) "
      "and holds a lock level (R | W | NO); a universal ACL level applies to all "
      "consumers. Enables permission-by-delegation for cross-project alignment.",
      ("VB3:Projects.getAccessStatus/updateAccessLevel/updateLockLevel/"
       "updateUniversalAccessLevel; models/Project.ts AccessLevel, LockLevel",),
      ("B.SG.2", "B.SG.5", "T.AC.4"), ("backend", "ui"), "P0", "MUST",
      "ontology_builder.projects.acl", depends_on=("OB.PRJ.01",),
      notes="Prerequisite for OB.MAP.* — you cannot align to another project's "
            "content without an ACL grant."),
    F("OB.PRJ.05", "Project visibility & open-at-startup policy", "PRJ",
      "PUBLIC | AUTHORIZED | PRISTINE visibility, plus per-project and global "
      "open-at-startup and read-only switches.",
      ("VB3:Projects.setVisibility/setOpenAtStartup/setReadOnly; ProjectVisibility",),
      ("B.SG.2", "B.SG.5"), ("backend", "ui"), "P0", "SHOULD",
      "ontology_builder.projects.registry", depends_on=("OB.PRJ.01",)),
    F("OB.PRJ.06", "Project facets & faceted project browser", "PRJ",
      "Six built-in facets (model, lexicalization, history, validation, category, "
      "organization) plus an administrator-defined custom facet schema; projects "
      "are browsable as a flat list or grouped by facet, with a facet index.",
      ("VB3:Projects.getProjectFacets/setProjectFacets/getCustomProjectFacetsSchema/"
       "createFacetIndex; models/Project.ts ProjectFacets, ProjectViewMode",),
      ("B.SG.1", "B.CT.2"), ("backend", "ui"), "P0", "SHOULD",
      "ontology_builder.projects.facets", depends_on=("OB.PRJ.01",),
      notes="The mechanism that makes a 100-project portfolio navigable — the "
            "portfolio-management face of B.SG.1."),
    F("OB.PRJ.07", "Project templates", "PRJ",
      "Named, reusable project creation templates capturing model, storage, "
      "rendering and URI-generation choices.",
      ("VB3:ProjectTemplates.createTemplate/listTemplates/updateTemplate",),
      ("B.SG.3", "B.CT.2"), ("backend", "ui"), "P0", "SHOULD",
      "ontology_builder.projects.templates", depends_on=("OB.PRJ.01", "OB.PRJ.03")),
    F("OB.PRJ.08", "Multilingual project labels & descriptions", "PRJ",
      "Projects are never renamed (the name is an identifier); a per-language "
      "label/description map provides the display name.",
      ("VB3:Projects.setProjectLabels; Project.getLabel()",),
      ("T.AC.5",), ("backend", "ui"), "P0", "SHOULD",
      "ontology_builder.projects.registry", depends_on=("OB.PRJ.01",)),
    F("OB.PRJ.09", "Project trash & soft delete", "PRJ",
      "Move projects to trash and restore them, distinct from hard delete.",
      ("WP:MoveProjectsToTrashActionHandler, RemoveProjectsFromTrashActionHandler",),
      ("B.SG.5", "T.OO.2"), ("backend", "ui"), "P0", "SHOULD",
      "ontology_builder.projects.registry", depends_on=("OB.PRJ.01",)),
    F("OB.PRJ.10", "Project dashboard & portfolio metrics", "PRJ",
      "Per-project health card: triple counts, open validations, failing tests, "
      "last release, steward, maturity level.",
      ("VB3:Projects.getProjectInfo + ICV counts", "WP:GetProjectDetails/GetProjectInfo"),
      ("B.VP.2", "T.QV.3"), ("backend", "ui"), "P5", "SHOULD",
      "ontology_builder.projects.dashboard",
      depends_on=("OB.PRJ.01", "OB.QLT.05")),

    # ===================== GOV · Governance & Access ======================== #
    F("OB.GOV.01", "User accounts & registration lifecycle", "GOV",
      "Registration, activation (NEW | INACTIVE | ACTIVE), profile fields, "
      "password reset/force, e-mail verification, avatar, affiliation, "
      "language proficiencies, and a configurable custom-field schema.",
      ("VB3:Users service (31 ops), models/User.ts UserForm/UserFormCustomField",
       "WP:CreateUserAccountActionHandler, ResetPasswordActionHandler, "
       "ChangePasswordActionHandler, GetUserIdsActionHandler"),
      ("B.SG.2", "B.CT.1"), ("backend", "ui"), "P0", "MUST",
      "ontology_builder.governance.users",
      notes="`languageProficiencies` is what makes language-restricted "
            "lexicographer roles enforceable (OB.GOV.06)."),
    F("OB.GOV.02", "Capability expression language", "GOV",
      "A first-class permission grammar `auth(<area>(<subject>[,<scope>]), \"<CRUDV>\")` "
      "over areas rdf | pm | rbac | um | cform | customService | invokableReporter | "
      "sys, with C·R·U·D plus **V (validate)**. Evaluated identically on server and "
      "client so the UI hides what the user may not do.",
      ("VB3:utils/AuthorizationEvaluator.ts — 330 guarded actions; areas: "
       "rdf(155) pm(17) cform(12) sys(7) invokableReporter(7) customService(7) rbac(2)",
       "WP:BuiltInCapability — 53 flat capabilities (coarser, no CRUD algebra)"),
      ("B.SG.2", "B.SG.3", "B.SG.5", "T.AC.4"), ("backend", "ui"), "P0", "MUST",
      "ontology_builder.governance.capabilities",
      notes="**The single most valuable thing to port.** VocBench's algebra is "
            "strictly more expressive than WebProtégé's flat enum; adopt VB3's "
            "grammar and seed it with WP's 53 capability names where they fit."),
    F("OB.GOV.03", "Role definitions & role editor", "GOV",
      "System-level and project-level roles, each a set of capability expressions. "
      "Factory roles are immutable; user-defined roles are created per project via "
      "a wizard, cloned, exported and imported.",
      ("VB3:Administration.createRole/cloneRole/addCapabilityToRole/"
       "updateCapabilityForRole/listCapabilities/listRoles; models/User.ts Role, RoleLevel",
       "WP:BuiltInRole (15 roles, parent-inheriting), ProjectRoleDefinitionsManager, "
       "SetProjectRoleDefinitionsHandler"),
      ("B.SG.2", "B.SG.3"), ("backend", "ui"), "P0", "MUST",
      "ontology_builder.governance.roles", depends_on=("OB.GOV.02",)),
    F("OB.GOV.04", "Default role set", "GOV",
      "Ship the eight VocBench roles — Administrator (system), Project Manager, "
      "Ontology Editor, Thesaurus Editor, Lexicographer, Mapper, Validator, "
      "RDF Geek, Lurker — reconciled with WebProtégé's CanView / CanComment / "
      "CanEdit / CanManage ladder.",
      ("VB3:§4.2 of the SWJ paper; roles_adm documentation",
       "WP:BuiltInRole PROJECT_VIEWER→OBJECT_COMMENTER→PROJECT_EDITOR→PROJECT_MANAGER, "
       "ISSUE_VIEWER→…→ISSUE_MANAGER, SYSTEM_ADMIN/USER_ADMIN"),
      ("B.SG.2",), ("backend",), "P0", "MUST",
      "ontology_builder.governance.roles", depends_on=("OB.GOV.03",)),
    F("OB.GOV.05", "Role inheritance", "GOV",
      "Roles compose from parent roles so the capability set is derived, not "
      "duplicated (WebProtégé's model; VocBench roles are flat).",
      ("WP:BuiltInRole(parents, actions), BuiltInRoleOracle",),
      ("B.SG.2",), ("backend",), "P0", "SHOULD",
      "ontology_builder.governance.roles", depends_on=("OB.GOV.03",),
      notes="Take this from WebProtégé — it is the one place its model beats VB3's."),
    F("OB.GOV.06", "Project–user binding with language & group limitation", "GOV",
      "Binds a user to a project with roles, an owning group, a `groupLimitations` "
      "flag and a set of permitted languages — the enforcement point for "
      "'this terminologist may only edit French'.",
      ("VB3:models/User.ts ProjectUserBinding; Administration.getProjectUserBinding/"
       "addRolesToUser/updateLanguagesOfUserInProject/removeUserFromProject",),
      ("B.SG.2", "T.AC.5"), ("backend", "ui"), "P0", "MUST",
      "ontology_builder.governance.bindings",
      depends_on=("OB.GOV.01", "OB.GOV.03")),
    F("OB.GOV.07", "User groups & group-scoped ownership", "GOV",
      "Groups with IRI identity and metadata; a project–group binding owns a set of "
      "SKOS schemes, so a group's editors are confined to their own branch.",
      ("VB3:UsersGroups service (15 ops), ProjectGroupBinding.ownedSchemes",),
      ("B.SG.2", "B.CT.2"), ("backend", "ui"), "P0", "SHOULD",
      "ontology_builder.governance.groups", depends_on=("OB.GOV.06",)),
    F("OB.GOV.08", "Sharing settings (per-person grants)", "GOV",
      "Ad-hoc sharing of a project with named people at VIEW | COMMENT | EDIT | "
      "MANAGE, plus a link-sharing default — the low-ceremony complement to roles.",
      ("WP:ProjectSharingSettings, SharingSetting, SharingPermission, "
       "GetProjectSharingSettings/SetProjectSharingSettings",),
      ("B.SG.2", "B.VP.3"), ("backend", "ui"), "P0", "MUST",
      "ontology_builder.governance.sharing", depends_on=("OB.GOV.06",)),
    F("OB.GOV.09", "Authentication & identity federation", "GOV",
      "Local accounts plus OIDC/SAML; token-derived roles.",
      ("VB3:Auth.login/logout, oauth2.service.ts, SamlLevel",
       "WP:webprotege-keycloak, JwtRolesExtractor, TokenValidator, "
       "webprotege-user-management-service (AD/Keycloak wrapper)"),
      ("B.SG.5", "T.AC.4"), ("backend", "ui"), "P0", "MUST",
      "ontology_builder.governance.auth"),
    F("OB.GOV.10", "Authorization decision service", "GOV",
      "A single `authorize(subject, capability, resource) -> bool` service used by "
      "every endpoint via a decorator, with a cached client-side twin that drives "
      "UI affordances. Emits a permissions-changed event on role/binding change.",
      ("VB3:AuthorizationEvaluator (tuProlog server-side / jsprolog client-side, "
       "with an authCache keyed by goal)",
       "WP:AccessManager, ApplicationPermissionValidator, ProjectPermissionValidator, "
       "GetAuthorizationStatusHandler, PermissionsChangedEvent"),
      ("B.SG.2", "B.SG.5", "T.AC.4"), ("backend", "agent", "ui"), "P0", "MUST",
      "ontology_builder.governance.pdp",
      depends_on=("OB.GOV.02", "OB.GOV.03", "OB.GOV.06"),
      notes="Agents are subjects too: every agent action must go through this PDP "
            "with its own service identity, never with the user's ambient rights."),
    F("OB.GOV.11", "Declarative service authorization annotations", "GOV",
      "Endpoints declare their required capability, read/write intent and "
      "preconditions declaratively; the capability catalogue is *derived* from the "
      "endpoint registry, so a new service cannot ship unguarded.",
      ("VB3:§4.15 'Declarative Service Implementation' — Java annotations for "
       "read/write access, required capabilities, parameter preconditions",),
      ("B.SG.3", "T.OO.3"), ("backend",), "P0", "MUST",
      "ontology_builder.governance.decorators", depends_on=("OB.GOV.10",),
      notes="In Python: a `@guarded(capability=..., writes=True)` decorator plus a "
            "test that fails the build if any router endpoint lacks one."),
    F("OB.GOV.12", "Machine / service accounts", "GOV",
      "Non-human principals with their own roles and client IDs — the mechanism "
      "that lets agents and CI hold least-privilege identities.",
      ("VB3:Machines service (9 ops) — createMachine, updateMachineRoles, "
       "updateMachineClientID, setAdmin",),
      ("B.SG.5", "T.OO.3", "T.AC.6"), ("backend",), "P0", "MUST",
      "ontology_builder.governance.machines",
      depends_on=("OB.GOV.03",),
      notes="Foundational for the agentic layer — see OB.AGT.09."),
    F("OB.GOV.13", "Permission rebuild & audit", "GOV",
      "Recompute the materialised permission table from role definitions and "
      "bindings; expose an audit view of who can do what where.",
      ("WP:RebuildPermissionsActionHandler, RebuildPermissions CLI, "
       "ProjectPermissionsManager",
       "VB3:Administration.getProjectUserBindings, ACL matrix inspection"),
      ("B.SG.2", "B.SG.5"), ("backend", "ui"), "P0", "SHOULD",
      "ontology_builder.governance.pdp", depends_on=("OB.GOV.10",)),

    # ===================== CHG · Change spine =============================== #
    F("OB.CHG.01", "Triple-level change interception", "CHG",
      "Every write, including raw SPARQL Update, is intercepted at the triple level "
      "and recorded as an add/remove set — not as a predefined operation type. This "
      "is what makes history complete rather than best-effort.",
      ("VB3:§4.3 — RDF4J SAIL extension capturing effectively-modified triples into "
       "a separate *support repository*",
       "WP:webprotege-revision-manager — axiom-level change lists"),
      ("T.OO.2", "B.SG.2", "B.SG.5"), ("store", "backend"), "P1", "MUST",
      "ontology_builder.changes.tracker",
      reuse=("src/Ontology Modeler/ontology_modeler/diff.py (GraphSynchronizer)",),
      notes="Fuseki has no SAIL. Implement as a write-path wrapper: every mutation "
            "goes through a `ChangeSet` object that computes the delta and applies "
            "it in one SPARQL Update transaction alongside the provenance write."),
    F("OB.CHG.02", "Commit provenance (the five Ws)", "CHG",
      "Each commit records actor, operation, operation parameters, start/end time, "
      "and the created/modified/deleted resources, stored as RDF.",
      ("VB3:models/History.ts CommitInfo{commit,user,operation,operationParameters,"
       "startTime,endTime,created,modified,deleted}; History service",
       "WP:GetRevisionSummaries, GetRevisions, RevisionSummary"),
      ("B.SG.5", "T.OO.2", "T.RI.4"), ("store", "backend"), "P1", "MUST",
      "ontology_builder.changes.provenance", depends_on=("OB.CHG.01",)),
    F("OB.CHG.03", "History browser with delta view", "CHG",
      "Paged, filterable commit list (by actor, operation, time range, resource) "
      "with a per-commit additions/removals delta, truncation-aware.",
      ("VB3:History.getCommits/getCommitSummary/getCommitDelta/getTimeOfOrigin; "
       "CommitDelta{additions,removals,additionsTruncated,removalsTruncated}",
       "WP:ProjectHistoryPortletPresenter, GetProjectChanges, GetWatchedEntityChanges"),
      ("T.OO.2", "B.SG.2"), ("backend", "ui"), "P1", "MUST",
      "ontology_builder.changes.history", depends_on=("OB.CHG.02",)),
    F("OB.CHG.04", "Staging graphs & the validation workflow", "CHG",
      "When validation is enabled, edits land in `staging-add` / `staging-delete` "
      "named graphs rather than the main graph. A user holding **V** accepts (making "
      "effects permanent) or rejects (erasing them, leaving no history trace). "
      "There is no `status` property — the workflow *is* the graph layout.",
      ("VB3:§4.4; Validation service — accept, reject, getStagedCommitSummary, "
       "getCurrentUserStagedCommitSummary, rejectCurrentUserCommit",),
      ("B.SG.2", "B.SG.5", "T.QV.1", "T.OO.2"), ("store", "backend", "ui"),
      "P1", "MUST",
      "ontology_builder.changes.validation",
      depends_on=("OB.CHG.01", "OB.GOV.02"),
      notes="**The keystone governance feature.** Maps cleanly onto Fuseki named "
            "graphs: <g>, <g#staging-add>, <g#staging-delete>. Read paths union "
            "main+staging and tag each triple's provenance so the UI can render "
            "proposed content distinctly."),
    F("OB.CHG.05", "Undo", "CHG",
      "Per-user undo of the last operation, independent of the validation workflow.",
      ("VB3:Undo.undo; Projects.setUndoEnabled/isUndoEnabled",
       "PD:EditMenu Undo/Redo (OWL API change-list based)"),
      ("T.OO.2",), ("backend", "ui"), "P1", "SHOULD",
      "ontology_builder.changes.undo", depends_on=("OB.CHG.01",)),
    F("OB.CHG.06", "Revert a revision", "CHG",
      "Reverse-apply a historical commit onto the head.",
      ("WP:RevertRevisionActionHandler; BuiltInCapability.REVERT_CHANGES",),
      ("T.OO.2",), ("backend", "ui"), "P1", "SHOULD",
      "ontology_builder.changes.history", depends_on=("OB.CHG.03",)),
    F("OB.CHG.07", "Blacklisting of rejected changes", "CHG",
      "Remember rejected proposals so a re-proposal warns the editor. Requires "
      "validation to be enabled.",
      ("VB3:Projects.setBlacklistingEnabled; §4.4 'future directions' now shipped",),
      ("B.SG.5", "T.QV.3"), ("backend", "ui"), "P1", "MAY",
      "ontology_builder.changes.validation", depends_on=("OB.CHG.04",)),
    F("OB.CHG.08", "Change-set safety guard", "CHG",
      "Before any write is applied, verify that the merged graph is a superset-"
      "preserving transformation of the base for everything the editing surface "
      "never saw — never re-serialise a lossy projection over the canonical graph.",
      ("Local invariant established in `playground/service.py::guard`",),
      ("T.QV.1", "B.SG.5"), ("backend",), "P1", "MUST",
      "ontology_builder.changes.guard",
      reuse=("src/Ontology Modeler/ontology_modeler/playground/service.py",
             "src/Ontology Modeler/ontology_modeler/playground/merge.py",
             "src/Ontology Modeler/ontology_modeler/diff.py"),
      notes="Already built and live-verified against the 133k-triple Fuseki "
            "dataset; lift it verbatim into the Builder."),

    # ===================== VER · Versioning ================================= #
    F("OB.VER.01", "Tagged version snapshots", "VER",
      "Create a named, timestamped dump of a project's repository; list, load and "
      "delete versions; create an editable fork from a version.",
      ("VB3:Versions service (20 ops) — createVersionDump, createEditableFork, "
       "loadVersionDumpIntoRepository, closeVersion, deleteVersion",),
      ("T.OO.2", "T.OO.1"), ("backend", "ui"), "P5", "MUST",
      "ontology_builder.versions.snapshots", depends_on=("OB.STO.01",)),
    F("OB.VER.02", "Time machine (per-resource and global)", "VER",
      "Switch the whole UI to a past version, or inspect one resource's state at a "
      "chosen point in time inside the resource view.",
      ("VB3:§4.9; ResourceView.getResourceViewAtTime; resource-view/time-machine/",
       "WP:GetRevision — download the ontology at any revision"),
      ("T.OO.2", "T.AC.2"), ("backend", "ui"), "P5", "SHOULD",
      "ontology_builder.versions.timemachine",
      depends_on=("OB.VER.01", "OB.CHG.02")),
    F("OB.VER.03", "Release packaging & deployment", "VER",
      "Publish a version through a deployer chain (file, triplestore, SFTP, object "
      "store) with a stored, reusable deployment configuration.",
      ("VB3:Versions.createVersionDumpUsingDeployer/storeDeploymentConfiguration; "
       "Download.deleteDistribution",),
      ("T.OO.2", "T.OO.3", "T.AC.3"), ("backend", "ui"), "P5", "SHOULD",
      "ontology_builder.versions.release", depends_on=("OB.VER.01", "OB.IO.05")),
    F("OB.VER.04", "SKOS/ontology diffing between versions", "VER",
      "Run a pluggable diffing service between two versions and store the report.",
      ("VB3:Diffing service (11 ops) — runDiffing, storeTaskResult, "
       "getDiffingServices, addDiffingService",),
      ("T.OO.2", "T.QV.3"), ("backend", "ui"), "P5", "SHOULD",
      "ontology_builder.versions.diffing", depends_on=("OB.VER.01",)),
    F("OB.VER.05", "Deprecation as a first-class state", "VER",
      "`owl:deprecated` rather than a bespoke status vocabulary; deprecating is an "
      "ordinary edit and therefore validatable.",
      ("VB3:Resources.setDeprecated; §4.4",
       "PD:'Deprecate...' menu action on class/property/individual/annotation "
       "hierarchies; 'Merge into...' as the paired refactor"),
      ("T.OO.2", "B.SG.3"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.owl.deprecation", depends_on=("OB.CHG.04",)),

    # ===================== STO · Storage ==================================== #
    F("OB.STO.01", "Fuseki dataset & named-graph layout", "STO",
      "The canonical store. One Fuseki dataset per environment; per project a "
      "reserved namespace of named graphs: main, imports, staging-add, "
      "staging-delete, inferred closure, mappings, metadata, support/history.",
      ("VB3:core + support repository split (models/Project.ts ProjectRepository)",
       "Local: infra/fuseki, ontology_modeler.fuseki.FusekiClient"),
      ("T.OO.1", "T.IA.2"), ("store", "backend"), "P0", "MUST",
      "ontology_builder.store.layout",
      reuse=("src/Ontology Modeler/ontology_modeler/fuseki.py",
             "architecture/technical architecture/deploy/fuseki/config-tdb2.ttl"),
      notes="Fuseki/TDB2 is single-writer — the write path must serialise through "
            "one coordinator per dataset (TR.SK.* in the technical requirements)."),
    F("OB.STO.02", "Support store for governance metadata", "STO",
      "Users, projects, roles, bindings, settings, commit provenance and staging "
      "metadata are themselves RDF, in a separate graph space ('Everything's RDF').",
      ("VB3:R15 'Everything's RDF' — VB2's relational DB removed; support repository",),
      ("T.OO.1", "B.SG.2"), ("store", "backend"), "P0", "MUST",
      "ontology_builder.store.support", depends_on=("OB.STO.01",),
      notes="Deliberately follows VocBench over WebProtégé (MongoDB): keeping "
            "governance in RDF means governance is itself queryable and auditable "
            "with SPARQL, and versionable by the same machinery."),
    F("OB.STO.03", "Repository configuration & remote stores", "STO",
      "Declarative store configuration templates, credentials management, remote "
      "repository registration and restart.",
      ("VB3:TripleStore service (14 ops), Repositories service, "
       "RepositoryImplConfigurer extension point, RepositoryAccessType",),
      ("T.OO.1", "T.OO.4"), ("backend", "ui"), "P4", "SHOULD",
      "ontology_builder.store.repositories", depends_on=("OB.STO.01", "OB.EXT.01")),
    F("OB.STO.04", "Derived property-graph projection", "STO",
      "Keep FalkorDB in step with Fuseki as a *derived* projection for fast "
      "neighbourhood, similarity and path queries — never as a source of truth.",
      ("Local: ontology_modeler.lpg (extract→transform→embed→load); "
       "architecture/ontology_assistant governing store-split principle",),
      ("T.AC.1", "T.AC.2", "T.IA.4"), ("store", "backend"), "P7", "SHOULD",
      "ontology_builder.store.projection",
      reuse=("src/Ontology Modeler/ontology_modeler/lpg/",),
      depends_on=("OB.STO.01",)),
    F("OB.STO.05", "Data preloading & bulk ingest", "STO",
      "Preload a project from a URL or a catalog entry at creation time, with a "
      "profiling pass and warnings.",
      ("VB3:Projects.preloadDataFromURL/preloadDataFromCatalog, "
       "PreloadedDataSummary, PreloadWarning; Administration.setPreloadProfilerThreshold",),
      ("T.OO.1", "T.IA.3"), ("backend", "ui"), "P4", "SHOULD",
      "ontology_builder.store.preload", depends_on=("OB.STO.01", "OB.IO.01")),
    F("OB.STO.06", "Managed backup & restore", "STO",
      "Scheduled TDB2 backup, point-in-time restore, and a documented RPO/RTO.",
      ("WP:WebProtégé back-up instructions; "
       "local: architecture/technical architecture TR.SK.* requirements",),
      ("T.OO.1", "T.OO.5"), ("store",), "P0", "MUST",
      "ontology_builder.store.backup", depends_on=("OB.STO.01",)),

    # ===================== EDT · OWL authoring ============================== #
    F("OB.EDT.01", "Class authoring & taxonomy", "EDT",
      "Create/delete classes, add/remove superclasses, subclass navigation, "
      "instance counts.",
      ("VB3:Classes service (17 ops) — createClass, addSuperCls, getSubClasses, "
       "getNumberOfInstances",
       "WP:CreateClassesActionHandler, DeleteEntitiesActionHandler, GetClassFrame",
       "PD:Add subclass/sibling/subclasses, Duplicate class, Convert to "
       "primitive/defined class"),
      ("T.DA.1", "T.DA.2"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.owl.classes", depends_on=("OB.CHG.01",)),
    F("OB.EDT.02", "Class expression axioms", "EDT",
      "unionOf / intersectionOf / oneOf / complementOf, general class axioms, "
      "covering axioms, disjointness (pairwise and set), equivalence.",
      ("VB3:Classes.addUnionOf/addIntersectionOf/addOneOf + removeX",
       "PD:'Make primitive siblings disjoint', 'Add covering axiom', 'Split/"
       "Amalgamate disjoint classes', General class axioms view"),
      ("T.DA.2", "T.RI.1"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.owl.axioms", depends_on=("OB.EDT.01",)),
    F("OB.EDT.03", "Manchester-syntax rendering of class expressions", "EDT",
      "Render any anonymous class expression as a readable Manchester-syntax "
      "string (`classifies some Role`) instead of a blank node. Read-only: a "
      "recursive walk over the restriction structure, no grammar required.",
      ("VB3:§4.6 — Manchester syntax for visualisation of class descriptions",
       "WP:GetManchesterSyntaxFrame",
       "PD:'Manchester syntax rendering' view; the Description view"),
      ("T.DA.2", "T.AC.2"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.manchester.render",
      notes="Measured on the local FIBO corpus (297 files, 3,190 classes): "
            "**6,388 owl:Restriction nodes** — about two anonymous expressions "
            "per named class. Without this, the majority of FIBO's semantic "
            "content renders as blank nodes and the tool is unusable against "
            "the primary corpus. ~150 lines, no dependency."),
    F("OB.EDT.14", "Manchester-syntax parsing & completion", "EDT",
      "Parse a typed Manchester-syntax expression into OWL axioms, with "
      "validation, precedence handling, structured parse errors and "
      "autocompletion — the free-text class-expression editor.",
      ("VB3:ManchesterHandler service (7 ops) — checkExpression, "
       "createRestriction, updateExpression, checkDatatypeExpression; "
       "widget/codemirror/manchester-editor",
       "WP:mansyntax/ManchesterSyntaxFrameParser wraps OWL API's "
       "ManchesterOWLSyntaxFramesParser in 6 lines; "
       "CheckManchesterSyntaxFrame, GetManchesterSyntaxFrameCompletions",
       "PD:class expression editor with syntax checking"),
      ("T.DA.2",), ("backend", "ui"), "P6", "SHOULD",
      "ontology_builder.authoring.manchester.parse",
      depends_on=("OB.EDT.03", "OB.EXT.05"),
      notes="Delivered by delegating to the OWL API through the sidecar "
            "(OB.EXT.05) rather than by writing a grammar. The decisive "
            "detail is error handling: OWL API's `ParserException` exposes "
            "line, column, current token and `isClassNameExpected()` / "
            "`isObjectPropertyNameExpected()` / … — so **completion falls out "
            "of the parser for free**, which is the expensive half to build by "
            "hand. Still deferred to P6: measured, 91.2% of FIBO restrictions "
            "have a named filler and are covered by OB.EDT.15 without any "
            "parser."),
    F("OB.EDT.15", "Structured restriction builder", "EDT",
      "A three-part form — property · quantifier (some/only/value/min/max/"
      "exactly) · filler — that composes a restriction without free-text "
      "syntax, with a live Manchester-syntax preview.",
      ("PD:the restriction-creation dialogs in the class Description view",
       "VB3:ManchesterHandler.createRestriction is the server side of this"),
      ("T.DA.2", "T.AC.2"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.owl.restrictions",
      depends_on=("OB.EDT.03",),
      notes="Covers the 91.2% of FIBO-shaped restrictions that have a named "
            "filler, and is far more usable than free text for non-logicians. "
            "This is what makes OB.EDT.14 deferrable rather than missing."),
    F("OB.EDT.04", "Property authoring (object/data/annotation)", "EDT",
      "Create/delete properties across all four kinds; sub/super/equivalent/"
      "disjoint/inverse; domains and ranges; property chains; characteristics "
      "(functional, transitive, symmetric, reflexive…); data ranges.",
      ("VB3:Properties service (35 ops)",
       "WP:CreateObjectProperties/CreateDataProperties/CreateAnnotationProperties, "
       "GetObjectPropertyFrame/GetDataPropertyFrame/GetAnnotationPropertyFrame",
       "PD:Domains and ranges view, Characteristics view, property hierarchies"),
      ("T.DA.2",), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.owl.properties", depends_on=("OB.CHG.01",)),
    F("OB.EDT.05", "Individual authoring & property assertions", "EDT",
      "Create/delete individuals, add/remove types, edit property assertions, "
      "make-all-different.",
      ("VB3:Individuals service, Classes.createInstance/deleteInstance",
       "WP:CreateNamedIndividuals, GetNamedIndividualFrame, GetIndividuals",
       "PD:Property assertions view, 'Make all individuals different'"),
      ("T.DA.2", "T.IA.4"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.owl.individuals", depends_on=("OB.EDT.01",)),
    F("OB.EDT.06", "Datatype authoring & facet restrictions", "EDT",
      "Declare datatypes; enumeration, facet and Manchester restrictions; the "
      "OWL 2 datatype map.",
      ("VB3:Datatypes service (11 ops) — setDatatypeFacetsRestriction, "
       "setDatatypeEnumerationRestrictions, getOWL2DatatypeMap",
       "WP:CreateDatatype/DeleteDatatype capabilities",
       "PD:Datatypes view"),
      ("T.DA.2",), ("backend", "ui"), "P2", "SHOULD",
      "ontology_builder.authoring.owl.datatypes", depends_on=("OB.EDT.03",)),
    F("OB.EDT.07", "Generic triple-level editing (RDF observability)", "EDT",
      "Any resource, including reified and blank-node structures, is inspectable "
      "and editable in full — the high-level forms never become a ceiling.",
      ("VB3:R10 'Full Editing Capability'; Resources service (16 ops) — "
       "getOutgoingTriples, updateResourceTriplesDescription, updateTriplePredicate, "
       "removePredicateObject; resource-view/triple-editor",),
      ("T.DA.2", "B.SG.3"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.triples", depends_on=("OB.CHG.01",),
      notes="Explicitly the thing the Microsoft Ontology-Playground surface could "
            "not do — it saw only ~18–23% of a FIBO module. Non-negotiable here."),
    F("OB.EDT.08", "URI generation strategy", "EDT",
      "Pluggable IRI minting: label-derived, UUID, OBO-style numeric with per-user "
      "ranges, prefix/suffix settings, whitespace treatment, conditional prefixes.",
      ("VB3:URIGenerator extension point; Projects.updateURIGeneratorConfiguration",
       "WP:EntityCrudKit — UuidSuffixKit, SuppliedNameSuffixKit, OBOIdSuffixKit, "
       "EntityCrudKitPrefixSettings, ConditionalIriPrefix, UserIdRange, "
       "WhiteSpaceTreatment, IRIPrefixUpdateStrategy"),
      ("T.DA.2", "B.SG.3", "T.IA.4"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.urigen", depends_on=("OB.EXT.01",),
      notes="WebProtégé's crud-kit model is richer than VB3's here — port it, and "
            "expose it through VB3's extension-point mechanism."),
    F("OB.EDT.09", "Rendering engine (display of resources)", "EDT",
      "Pluggable computation of a resource's display string from labels in the "
      "user's language preference order, with a URI/qname toggle.",
      ("VB3:RenderingEngine extension point; Projects.updateRenderingEngineConfiguration",
       "WP:DisplayNameSettings, DictionaryLanguage, GetEntityRendering, "
       "GetEntityHtmlRendering",
       "PD:'Render by entity IRI short name / prefixed name / rdfs:label / "
       "annotation property / custom rendering'"),
      ("T.AC.5", "T.AC.2"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.rendering", depends_on=("OB.EXT.01",)),
    F("OB.EDT.10", "Refactoring operations", "EDT",
      "Rename entity (single and bulk), change ontology IRI, replace base URI, "
      "merge entities, move axioms between ontologies, split/amalgamate subclass "
      "axioms, convert IRIs to labels, SKOS↔SKOS-XL conversion.",
      ("VB3:Refactor service (7 ops) — changeResourceURI, replaceBaseURI, "
       "SKOStoSKOSXL, SKOSXLtoSKOS, migrateDefaultGraphToBaseURIGraph, "
       "spawnNewConceptFromLabel",
       "WP:ChangeEntityIRI, MergeEntities, MoveHierarchyNode, MoveToParent",
       "PD:Refactor menu — 14 operations including 'Copy/move/delete axioms', "
       "'Merge ontologies', 'Rename multiple entities'"),
      ("T.DA.2", "T.IA.2", "T.OO.2"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.refactor", depends_on=("OB.CHG.01",),
      notes="Protégé Desktop is the richest source here by a wide margin."),
    F("OB.EDT.11", "Bulk / mass editing", "EDT",
      "Apply an annotation or axiom edit across a selected set of entities in one "
      "reviewable transaction.",
      ("WP:bulkop package (3 handlers), BuiltInCapability.BULK_EDIT_ANNOTATIONS, "
       "EditAnnotationValuesActionHandler",
       "VB3:R6 'Under-the-hood data access/modification' via SPARQL Update"),
      ("T.DA.2", "T.OO.3"), ("backend", "ui"), "P2", "SHOULD",
      "ontology_builder.authoring.bulk",
      depends_on=("OB.EDT.07", "OB.CHG.04")),
    F("OB.EDT.12", "Ontology header, prefixes & imports", "EDT",
      "Edit ontology annotations, prefix declarations, base URI/default namespace, "
      "and the import closure (from web, local project, mirror, catalog).",
      ("VB3:Metadata service (23 ops) — addFromWeb/addFromLocalProject/addFromMirror, "
       "getImports, removeImport, setNSPrefixMapping, setDefaultNamespace",
       "WP:GetOntologyAnnotations/SetOntologyAnnotations, "
       "GetProjectPrefixDeclarations/SetProjectPrefixDeclarations",
       "PD:Ontology header, Ontology prefixes, Imported ontologies views; "
       "'Edit ontology catalog file...'"),
      ("T.IA.2", "T.DA.3", "T.AC.3"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.metadata.imports",
      reuse=("src/Ontology Modeler/ontology_modeler/structure.py",)),
    F("OB.EDT.13", "Ontology mirror / offline import cache", "EDT",
      "Cache imported ontologies locally so builds are reproducible and offline.",
      ("VB3:OntManager service — getOntologyMirror, updateOntologyMirrorEntry",
       "PD:'Loaded ontology sources...', XML catalog"),
      ("T.DA.3", "T.IA.2", "T.OO.3"), ("backend",), "P4", "SHOULD",
      "ontology_builder.metadata.mirror", depends_on=("OB.EDT.12",)),

    # ===================== SKO · SKOS ======================================= #
    F("OB.SKO.01", "Concept & scheme authoring", "SKO",
      "Create/delete concepts and schemes, broader/narrower, top concepts, "
      "concept-to-scheme membership (incl. bulk), scheme emptiness checks.",
      ("VB3:SKOS service (42 ops) — createConcept, addBroaderConcept, addTopConcept, "
       "addMultipleConceptsToScheme, getSchemesMatrixPerConcept",),
      ("T.DA.6", "B.SE.4"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.skos.concepts", depends_on=("OB.CHG.01",)),
    F("OB.SKO.02", "Collections & ordered collections", "SKO",
      "skos:Collection and skos:OrderedCollection with position-aware membership.",
      ("VB3:SKOS.createCollection, addFirstToOrderedCollection, "
       "addInPositionToOrderedCollection, getNestedCollections",),
      ("T.DA.6",), ("backend", "ui"), "P2", "SHOULD",
      "ontology_builder.authoring.skos.collections", depends_on=("OB.SKO.01",)),
    F("OB.SKO.03", "Labels, notes and SKOS-XL reified labels", "SKO",
      "pref/alt/hidden labels per language; documentation notes with sub-property "
      "qualification; SKOS-XL literal forms with their own identity and relations.",
      ("VB3:SKOS.setPrefLabel/addAltLabel/addNote/updateNoteProperty; "
       "SKOSXL service (12 ops) — altToPrefLabel, changeLabelInfo",),
      ("T.DA.6", "T.AC.5", "B.SE.4"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.authoring.skos.labels", depends_on=("OB.SKO.01",)),
    F("OB.SKO.04", "Sub-property-qualified hierarchical relations", "SKO",
      "When asserting broader/narrower or a lexicalization, allow choosing a "
      "sub-property (e.g. XKOS meronymy) so specialised semantics survive.",
      ("VB3:§4.1.2 and Fig. 4 — predicate-object presentation qualifies the predicate",),
      ("T.DA.5", "T.DA.6"), ("backend", "ui"), "P2", "SHOULD",
      "ontology_builder.authoring.skos.concepts", depends_on=("OB.SKO.01",)),
    F("OB.SKO.05", "Terminologist view", "SKO",
      "A label-centric editing surface for domain terminologists, per language, "
      "hiding the RDF entirely.",
      ("VB3:resource-view/term-view — language-box, language-term, language-definition",),
      ("B.SE.4", "T.AC.5", "B.VP.3"), ("ui", "backend"), "P2", "SHOULD",
      "ontology_builder_ui/features/termView", depends_on=("OB.SKO.03", "OB.GOV.06")),

    # ===================== LEX · Lexicons =================================== #
    F("OB.LEX.01", "OntoLex-Lemon lexicon authoring", "LEX",
      "Lexicons, lexical entries, forms, senses, canonical forms, references, "
      "conceptualizations, lexico-semantic relations, translation sets.",
      ("VB3:OntoLexLemon service (46 ops)",),
      ("T.DA.6", "T.AC.5"), ("backend", "ui"), "P6", "MAY",
      "ontology_builder.authoring.ontolex", depends_on=("OB.PRJ.02",),
      notes="Include only if multilingual lexical resources are in scope; it is "
            "the largest single service in VocBench and the least reused outside "
            "terminology organisations."),
    F("OB.LEX.02", "Lexicographer view & alphabetic indexing", "LEX",
      "Scalable browsing of huge flat entry lists via single/double-character "
      "indexes, and a dedicated lexicographer editing surface.",
      ("VB3:LexicographerView service; "
       "OntoLexLemon.getLexicalEntriesByAlphabeticIndex/countLexicalEntriesBy…",),
      ("T.AC.5", "T.AC.2"), ("ui", "backend"), "P6", "MAY",
      "ontology_builder_ui/features/lexicographerView", depends_on=("OB.LEX.01",)),

    # ===================== BRW · Browsing =================================== #
    F("OB.BRW.01", "Model-driven structure panels", "BRW",
      "The left-hand navigator adapts to the project's model: class tree + instance "
      "list + property tree + datatype list for OWL; concept tree, scheme list and "
      "collection tree added for SKOS; lexicon and lexical-entry panels for OntoLex.",
      ("VB3:§4.1.1; structures/trees/{class,concept,property,collection,custom}, "
       "structures/lists/{instance,scheme,lexicon,datatype,lexical-entry}",
       "PD:7 workspace tabs — Active ontology, Entities, Classes, Object "
       "properties, Data properties, Annotation properties, Individuals by class"),
      ("T.AC.2", "T.DA.1"), ("ui", "backend"), "P2", "MUST",
      "ontology_builder_ui/features/structures", depends_on=("OB.PRJ.02",)),
    F("OB.BRW.02", "Paged, lazily-expanded hierarchies", "BRW",
      "Trees fetch roots then children on demand with server-side paging; lists "
      "page and index. Required for 100k-concept thesauri.",
      ("VB3:R5 'Data Scalability'; Classes.getSubClasses, SKOS.getNarrowerConcepts, "
       "Search.getPathFromRoot",
       "WP:GetHierarchyRoots, GetEntityHierarchyChildren, GetHierarchyPathsToRoot, "
       "GetHierarchySiblings, GetIndividualsPageContainingIndividual"),
      ("T.AC.2", "T.OO.1"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.browse.hierarchy", depends_on=("OB.BRW.01",)),
    F("OB.BRW.03", "The resource view", "BRW",
      "One universal predicate-object editor for *any* resource, organised into "
      "~30 typed sections (types, lexicalizations, broaders, classaxioms, domains, "
      "ranges, imports, notes, members, …), each with its own CRUD authorization.",
      ("VB3:§4.1.2; models/ResourceView.ts ResViewSection — 30 sections; "
       "AuthorizationEvaluator.sectionEvaluationMap maps every (section, CRUD) pair "
       "to a capability goal",
       "WP:frame package (12 handlers) — GetClassFrame, GetObjectPropertyFrame, …"),
      ("T.DA.2", "T.AC.2", "B.SG.2"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.browse.resource_view",
      depends_on=("OB.EDT.07", "OB.GOV.10"),
      notes="The centre of gravity of the whole editing UI. Its per-section CRUD "
            "authorization map is what makes fine-grained governance visible."),
    F("OB.BRW.04", "Inferred vs asserted rendering", "BRW",
      "Inferred triples are rendered distinctly and can be toggled in and out of "
      "every view.",
      ("VB3:§4.6 and Fig. 10 — lighter colour for inferred, eye-icon toggle",
       "PD:'Class hierarchy (inferred)', 'Individuals by type (inferred)', "
       "'Direct instances (inferred)', Classification results view"),
      ("T.RI.2", "T.RI.4", "T.AC.2"), ("backend", "ui"), "P3", "MUST",
      "ontology_builder.browse.resource_view", depends_on=("OB.RSN.02",)),
    F("OB.BRW.05", "Graph view", "BRW",
      "Interactive model/data/UML graph exploration with incremental expansion.",
      ("VB3:Graph service — getGraphModel, expandGraphModelNode, "
       "expandSub/SuperResources; graph/impl/{data,model,uml}-graph",
       "WP:viz package (4 handlers) — GetEntityGraph, SetEntityGraphActiveFilters, "
       "GetUserProjectEntityGraphCriteria",
       "PD:OWLViz / OntoGraf plugins"),
      ("T.AC.2",), ("backend", "ui"), "P5", "SHOULD",
      "ontology_builder.browse.graph",
      reuse=("src/Ontology Converter/ontology_to_lpg.py",)),
    F("OB.BRW.06", "Custom trees", "BRW",
      "Define a navigable tree over arbitrary properties (not just rdfs:subClassOf "
      "or skos:broader) with a SPARQL-backed roots/children contract.",
      ("VB3:CustomTrees service — getRoots, getChildrenResources; structures/trees/custom",),
      ("T.AC.2", "T.DA.5"), ("backend", "ui"), "P4", "SHOULD",
      "ontology_builder.browse.custom_trees", depends_on=("OB.BRW.02",)),
    F("OB.BRW.07", "Perspectives, portlets & saved layouts", "BRW",
      "The workspace is a user- and role-configurable arrangement of view "
      "components; layouts are savable, resettable and shippable as project "
      "defaults.",
      ("WP:perspective package (7 handlers) — GetPerspectives, GetPerspectiveLayout, "
       "SetPerspectiveLayout, ResetPerspectives, SAVE_DEFAULT_PROJECT_LAYOUT; "
       "wiki 'Portlets'",
       "PD:Window menu — Views, Tabs, 'Create new tab...', 'Export/Import tab', "
       "'Store current layout'; 51 registered view components"),
      ("T.AC.2", "B.VP.3"), ("ui", "backend"), "P5", "SHOULD",
      "ontology_builder_ui/shell/perspectives", depends_on=("OB.UIX.01",),
      notes="WebProtégé and Protégé Desktop agree on this; VocBench does not have "
            "it. It is the mechanism that lets one product serve ontologists, "
            "terminologists and reviewers without three products."),
    F("OB.BRW.08", "Resource-view section customisation", "BRW",
      "Per-project and per-user control over which sections appear, in what order, "
      "with filters — a template editor.",
      ("VB3:preferences/res-view-section-customization, res-view-template-editor, "
       "section-filter-editor",),
      ("T.AC.2", "B.VP.3"), ("ui", "backend"), "P5", "SHOULD",
      "ontology_builder_ui/features/resourceView/customization",
      depends_on=("OB.BRW.03",)),

    # ===================== SRCH · Search ==================================== #
    F("OB.SRCH.01", "Resource search (lexical, prefix, regex, language-scoped)", "SRCH",
      "Search over labels and IRIs with mode, language, scheme and role filters; "
      "search within instances of a class; path-from-root for reveal-in-tree.",
      ("VB3:Search service (12 ops) — searchResource, searchPrefix, advancedSearch, "
       "searchInstancesOfClass, getPathFromRoot, searchStringList, searchURIList",
       "WP:PerformEntitySearchActionHandler, LookupEntitiesActionHandler, "
       "GetMatchingEntitiesActionHandler, webprotege-server-lucene"),
      ("T.AC.1", "T.AC.2"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.search.engine",
      notes="Fuseki's `text:query` (Lucene) index is the analogue of VB3's "
            "GraphDB-specific `SearchStrategy` extension point; declare it in the "
            "TDB2 assembler, and keep a SPARQL-FILTER fallback."),
    F("OB.SRCH.02", "Custom search & search settings", "SRCH",
      "Project-defined parameterised search services with generated input forms; "
      "stored per-user/per-project search preferences.",
      ("VB3:Search.customSearch/getCustomSearchForm/storeCustomSearchSettings",
       "WP:GetSearchSettings/SetSearchSettings, webprotege-criteria "
       "('extensible criteria API for selecting entities')"),
      ("T.AC.1", "T.DA.5"), ("backend", "ui"), "P4", "SHOULD",
      "ontology_builder.search.custom",
      depends_on=("OB.SRCH.01", "OB.EXT.02")),
    F("OB.SRCH.03", "Pluggable search strategy", "SRCH",
      "The search implementation is an extension point so a store-specific "
      "full-text index can replace the portable SPARQL implementation.",
      ("VB3:SearchStrategy extension point (§3.2)",),
      ("T.AC.1", "T.OO.4"), ("backend",), "P4", "SHOULD",
      "ontology_builder.search.strategies", depends_on=("OB.EXT.01",)),

    # ===================== FRM · Forms ====================================== #
    F("OB.FRM.01", "Declarative custom forms", "FRM",
      "Data-driven definition of what is prompted when a resource of a given type "
      "is created or viewed, transforming input into arbitrary RDF — so complex "
      "design patterns are enterable by non-modellers.",
      ("VB3:CustomForms service (24 ops) — createCustomForm, createFormCollection, "
       "addFormsMapping, getCustomFormRepresentation, removeReifiedResource; "
       "forms are PEARL templates executed by CODA (§4.1.5)",
       "WP:form package (11 handlers) — FormDescriptor, FormFieldDescriptor, "
       "FormControlDescriptor (Text/Choice/Grid/SubForm/Collection), "
       "EntityFormChangeListGenerator, GetEntityForm, SetEntityFormsData, "
       "CopyFormDescriptorsFromProject"),
      ("T.DA.5", "B.SE.1", "B.VP.3"), ("backend", "ui"), "P4", "MUST",
      "ontology_builder.forms",
      notes="Two designs to choose between. WebProtégé's is a typed JSON descriptor "
            "tree with an explicit change generator — far easier to port to "
            "Python/React. VocBench's is more expressive (arbitrary RDF via PEARL) "
            "but drags in the CODA runtime. **Recommendation: adopt WebProtégé's "
            "descriptor model, add a SPARQL-CONSTRUCT escape hatch for the cases "
            "PEARL would have covered.**"),
    F("OB.FRM.02", "Form collections & type mappings", "FRM",
      "Bind a form (or a collection of forms) to a class/type so it fires on "
      "creation of any instance of that type; import/export forms between projects.",
      ("VB3:CustomForms.addFormsMapping/getFormCollection/isFormLinkedToCollection",
       "WP:GetProjectFormDescriptors/SetProjectFormDescriptors, "
       "CopyFormDescriptorsFromProject, FormsManagerPresenter"),
      ("T.DA.5", "B.SG.3"), ("backend", "ui"), "P4", "MUST",
      "ontology_builder.forms.binding", depends_on=("OB.FRM.01",)),
    F("OB.FRM.03", "Custom views (SPARQL-backed value widgets)", "FRM",
      "Render a predicate's values through a custom widget — map, chart, table, "
      "vector — driven by a stored query and an association to a property.",
      ("VB3:CustomViews service (17 ops) — createCustomView, addAssociation, "
       "updateSparqlBasedData, updateDynamicVectorData; custom-views/editors/views; "
       "widget/leaflet-map, widget/charts",),
      ("T.AC.2", "T.DA.5"), ("backend", "ui"), "P6", "SHOULD",
      "ontology_builder.forms.custom_views", depends_on=("OB.FRM.01", "OB.SPQ.02")),
    F("OB.FRM.04", "Form validation & broken-form detection", "FRM",
      "Validate a form definition, infer its annotations, and report forms broken "
      "by ontology change.",
      ("VB3:CustomForms.validatePearl/inferPearlAnnotations/getBrokenCustomForms; "
       "CODA.validatePearl",),
      ("T.QV.1", "T.QV.3"), ("backend", "ui"), "P4", "SHOULD",
      "ontology_builder.forms.validation", depends_on=("OB.FRM.01",)),

    # ===================== RSN · Reasoning ================================== #
    F("OB.RSN.01", "Consistency & classification", "RSN",
      "Run a reasoner over the project's imports closure; report unsatisfiable "
      "classes and the inferred hierarchy.",
      ("PD:inference_reasonerfactory extension point, Reasoner menu, HermiT built in, "
       "Pellet/FaCT++/ELK as plugins; 'Classification results' view; DL metrics view",
       "VB3:§4.6 — reasoning delegated to the store (RDF4J RDFS or GraphDB "
       "OWL2-RL/QL rulesets); ICV.listConsistencyViolations"),
      ("T.RI.1", "T.QV.1"), ("backend", "ui"), "P3", "MUST",
      "ontology_builder.reasoning.engine",
      reuse=("src/Ontology Enricher/src/patterns.py",),
      notes="Python options: owlrl (OWL 2 RL, pure Python, already used in "
            "chapter04) and Fuseki's own inference cover P3 in-process. True DL "
            "classification has no Python implementation at all, so it arrives "
            "in P6 through the sidecar (OB.EXT.05) behind the same "
            "`ReasonerBackend` interface."),
    F("OB.RSN.02", "Materialised inference in a dedicated graph", "RSN",
      "Entailments are computed into a separate `inferred` named graph with a "
      "freshness stamp, never mixed into the asserted graph.",
      ("VB3:store-level total materialisation; explicit/inferred distinction",
       "Local: src/Ontology Enricher output/inferred_closure.ttl; "
       "playground-fuseki-workbench P4 design"),
      ("T.RI.2", "T.OO.1"), ("store", "backend"), "P3", "MUST",
      "ontology_builder.reasoning.materialize",
      depends_on=("OB.RSN.01", "OB.STO.01")),
    F("OB.RSN.03", "Explanation & justification", "RSN",
      "Human-readable justification for an inferred axiom or an inconsistency.",
      ("PD:`explanation` and `inconsistentOntologyExplanation` extension points, "
       "`explanationpreferencespanel`",
       "VB3:ICV.explain; §4.6 notes VB3 *cannot* justify because RDF4J offers no "
       "mechanism — an explicit gap this design closes"),
      ("T.RI.4", "B.SG.5", "T.AC.6"), ("backend", "agent", "ui"), "P3", "SHOULD",
      "ontology_builder.reasoning.explain", depends_on=("OB.RSN.02",),
      notes="Protégé Desktop is the only one of the three that does this well. "
            "It is also the highest-value input to the agentic layer — an agent "
            "that can quote a justification is an agent that can be trusted. "
            "Two tiers: rule-provenance tracking under OWL 2 RL in P3 "
            "(in-process, owlrl), and true DL justifications via the sidecar "
            "(OB.EXT.05) in P6. Always show which profile produced an "
            "explanation — see decision O6."),
    F("OB.RSN.04", "Rule management (SHACL-AF / SWRL)", "RSN",
      "Author and execute domain rules that augment the ontology.",
      ("WP:'Rules' view is present in Protégé Desktop; WebProtégé supports SWRL "
       "rule editing (per the VB3 comparison, §6.3)",
       "PD:Rules view (SWRLTab)",
       "Local: src/Ontology Enricher catalog/reasoning_patterns.yaml"),
      ("T.RI.3", "T.DA.5"), ("backend", "ui"), "P3", "SHOULD",
      "ontology_builder.reasoning.rules",
      reuse=("src/Ontology Enricher/catalog/reasoning_patterns.yaml",)),
    F("OB.RSN.05", "Trivial inference toggle", "RSN",
      "Cheap automatic materialisation of symmetric/inverse assertions at write "
      "time, switchable per project.",
      ("VB3:Projects.setTrivialInferenceEnabled/isTrivialInferenceEnabled",),
      ("T.RI.2",), ("backend",), "P3", "MAY",
      "ontology_builder.reasoning.trivial", depends_on=("OB.CHG.01",)),

    # ===================== QLT · Quality ==================================== #
    F("OB.QLT.01", "SHACL validation", "QLT",
      "Load shapes into a shapes graph, validate on demand and on commit, extract "
      "custom forms from shapes.",
      ("VB3:SHACL service — batchValidation, clearShapes, extractCFfromShapesGraph; "
       "Projects.setSHACLValidationEnabled",),
      ("T.QV.1", "T.RI.3", "B.SG.3"), ("backend", "ui"), "P3", "MUST",
      "ontology_builder.quality.shacl",
      notes="pySHACL covers this in Python with no sidecar."),
    F("OB.QLT.02", "Integrity constraint validation (ICV) with interactive fixes", "QLT",
      "A catalogue of ~30 model-specific anomaly checks — dangling concepts, cyclic "
      "hierarchies, hierarchical redundancy, multiple prefLabels in a language, "
      "overlapped labels, no-scheme concepts, top concepts with broaders, extra "
      "spaces in labels, invalid URIs, broken alignments, missing definitions — "
      "**each with a one-click remediation**.",
      ("VB3:ICV service (38 ops); src/app/icv/ has one component per check",),
      ("T.QV.1", "T.QV.3", "B.SG.3"), ("backend", "ui"), "P3", "MUST",
      "ontology_builder.quality.icv",
      notes="The interactive *fix* is the differentiator — a validation report "
            "nobody can act on is not a quality capability. Also the single "
            "best-shaped target for agent automation (OB.AGT.04)."),
    F("OB.QLT.03", "Competency-question test suite", "QLT",
      "Executable tests that assert the ontology answers its competency questions; "
      "run on every change.",
      ("Local: capability T.QV.2 has no equivalent in any of the three tools — "
       "this is an addition, drawn from architecture/ontology_assistant/EVALUATION.md",),
      ("T.QV.2", "B.SE.2", "T.OO.3"), ("backend", "agent", "ui"), "P3", "MUST",
      "ontology_builder.quality.cq_tests",
      reuse=("architecture/ontology_assistant/EVALUATION.md",),
      notes="**Gap in all three reference tools.** None of VocBench, WebProtégé or "
            "Protégé manages competency questions as first-class testable artifacts. "
            "This is where the Ontology Builder can be better than what it merges."),
    F("OB.QLT.04", "Quality metrics", "QLT",
      "Structural and semantic metrics — DL expressivity, axiom counts, "
      "coverage, cohesion, label completeness per language.",
      ("PD:'Ontology metrics' view, 'DL metrics' view",
       "VB3:LIME/VoID statistical metadata computation (§4.12)"),
      ("T.QV.3", "B.VP.2"), ("backend", "ui"), "P3", "SHOULD",
      "ontology_builder.quality.metrics",
      reuse=("src/Ontology Modeler/ontology_modeler/structure.py",)),
    F("OB.QLT.05", "Quality gate on commit", "QLT",
      "A configurable policy that blocks (or routes to validation) a commit that "
      "breaks reasoning, SHACL, ICV or a CQ test.",
      ("Composition of VB3's validation workflow with WP's revision model — "
       "not present as such in either",),
      ("T.OO.3", "T.QV.1", "B.SG.3", "B.SG.5"), ("backend",), "P3", "MUST",
      "ontology_builder.quality.gate",
      depends_on=("OB.CHG.04", "OB.QLT.01", "OB.QLT.02", "OB.QLT.03")),
    F("OB.QLT.06", "Invokable reporters", "QLT",
      "User-defined report definitions composed of sections, compiled on demand "
      "into HTML/Markdown — the reporting counterpart of custom services.",
      ("VB3:InvokableReporters service (11 ops) — createInvokableReporter, "
       "addSectionToReporter, compileReport",),
      ("T.QV.3", "B.VP.2", "T.AC.3"), ("backend", "ui"), "P6", "SHOULD",
      "ontology_builder.quality.reporters", depends_on=("OB.SPQ.02",)),

    # ===================== IO · Import/Export =============================== #
    F("OB.IO.01", "Data loading with format detection", "IO",
      "Load RDF from file, URL, mirror or another project; detect the parser from "
      "filename/content; report supported formats.",
      ("VB3:InputOutput service — getSupportedFormats, getParserFormatForFileName, "
       "clearData; StreamTargetingLoader / RepositoryTargetingLoader extension points",
       "WP:UPLOAD_PROJECT, MergeUploadedProject, NewOntologyMergeAdd, "
       "ExistingOntologyMergeAdd, webprotege-ontology-processing-service"),
      ("T.IA.3", "T.OO.1"), ("backend", "ui"), "P4", "MUST",
      "ontology_builder.io.load",
      reuse=("src/Ontology Modeler/ontology_modeler/upload.py",)),
    F("OB.IO.02", "RDF lifters (non-RDF → RDF)", "IO",
      "Pluggable lifting of non-RDF sources into RDF at load time.",
      ("VB3:RDFLifter extension point",),
      ("T.IA.3", "T.DA.4"), ("backend",), "P4", "SHOULD",
      "ontology_builder.io.lifters", depends_on=("OB.EXT.01",)),
    F("OB.IO.03", "RDF transformer chains", "IO",
      "An ordered chain of destructive transformations applied to a *copy* of the "
      "data on export (e.g. SKOS-XL → plain SKOS, filter by namespace). Chains and "
      "individual component configurations are stored and reusable across projects.",
      ("VB3:§4.7; RDFTransformer extension point; Export service",),
      ("T.IA.1", "T.AC.3", "T.OO.2"), ("backend", "ui"), "P4", "MUST",
      "ontology_builder.io.transformers", depends_on=("OB.EXT.01", "OB.EXT.02")),
    F("OB.IO.04", "Reformatting exporters", "IO",
      "Pluggable serializers beyond the RDF syntaxes (e.g. Zthes, spreadsheet, "
      "SKOS-flavoured CSV).",
      ("VB3:ReformattingExporter extension point; Export.getOutputFormats",),
      ("T.AC.3",), ("backend",), "P4", "SHOULD",
      "ontology_builder.io.exporters", depends_on=("OB.EXT.01",)),
    F("OB.IO.05", "Deployers", "IO",
      "Pluggable destinations for exported data — file, triplestore, SFTP, object "
      "store, catalog — with stored configurations.",
      ("VB3:StreamSourcedDeployer / RepositorySourcedDeployer extension points; "
       "§4.7 example deploys RDF/XML to SFTP",),
      ("T.AC.3", "T.OO.3", "T.AC.4"), ("backend", "ui"), "P4", "SHOULD",
      "ontology_builder.io.deployers", depends_on=("OB.EXT.01",)),
    F("OB.IO.06", "Export named-graph selection & filtering", "IO",
      "Choose which named graphs to export (main only, with imports, with "
      "inferences, with staging) — the export surface makes the graph layout "
      "explicit to users.",
      ("VB3:Export.getNamedGraphs/export; config/dataManagement/exportData/filter-graphs",),
      ("T.AC.3", "T.IA.2"), ("backend", "ui"), "P4", "MUST",
      "ontology_builder.io.export", depends_on=("OB.STO.01",)),
    F("OB.IO.07", "Download at any revision", "IO",
      "Produce a serialisation of the project as of any revision, not only tagged "
      "snapshots.",
      ("WP:GetRevision, webprotege-snapshot-generator-service; noted in the VB3 "
       "paper (§6.3) as WebProtégé's unique advantage",),
      ("T.OO.2", "T.AC.3"), ("backend",), "P5", "SHOULD",
      "ontology_builder.io.export", depends_on=("OB.CHG.02", "OB.VER.01")),
    F("OB.IO.08", "Documentation generation & publishing", "IO",
      "Generate human-readable ontology documentation and publish it per release.",
      ("Local capability T.AC.3; tool candidates already listed in "
       "architecture/ARCHITECTURE.md (Widoco, pyLODE, Ontospy)",
       "VB3:no equivalent; WP:no equivalent"),
      ("T.AC.3", "B.VP.3"), ("backend",), "P5", "SHOULD",
      "ontology_builder.io.docs", depends_on=("OB.VER.03",),
      notes="Second gap common to all three reference tools."),

    # ===================== MAP · Alignment ================================== #
    F("OB.MAP.01", "Interactive cross-project alignment", "MAP",
      "Browse another project (subject to its ACL), search it by label, and assert "
      "a mapping from the resource view.",
      ("VB3:Alignment service (18 ops) — searchResources, addAlignment, getMappings, "
       "getSuggestedProperties, changeMappingProperty",),
      ("T.IA.1", "B.CT.3"), ("backend", "ui"), "P6", "MUST",
      "ontology_builder.alignment.interactive",
      depends_on=("OB.PRJ.04",),
      reuse=("src/Ontology Enricher/mappings/hbim_to_fibo_mappings.ttl",)),
    F("OB.MAP.02", "Alignment validation workflow", "MAP",
      "Load an alignment file (INRIA Alignment API model), review cell by cell, "
      "accept/reject individually or in bulk (all above/under a threshold), then "
      "project accepted cells onto real mapping properties — owl:equivalentClass "
      "for classes, skos:exactMatch/closeMatch for concepts.",
      ("VB3:§4.10; Alignment.acceptAlignment/rejectAlignment/acceptAllAbove/"
       "rejectAllUnder/applyValidation/listCells",),
      ("T.IA.1", "T.QV.4", "B.SG.2"), ("backend", "ui"), "P6", "MUST",
      "ontology_builder.alignment.validation", depends_on=("OB.MAP.01",)),
    F("OB.MAP.03", "EDOAL expressive alignments", "MAP",
      "First-class alignment *projects* holding correspondences with relation, "
      "measure, mapping property, comments and status — mappings that are richer "
      "than a single triple.",
      ("VB3:EDOAL service (17 ops) — createAlignment, createCorrespondence, "
       "setLeftEntity/setRightEntity/setRelation/setMeasure, "
       "updateCorrespondenceStatus, addCorrespondenceComment",),
      ("T.IA.1", "T.IA.2"), ("backend", "ui"), "P6", "SHOULD",
      "ontology_builder.alignment.edoal", depends_on=("OB.MAP.01",)),
    F("OB.MAP.04", "Remote matcher services", "MAP",
      "Register external alignment systems, discover their matchers, run matching "
      "tasks asynchronously and fetch results.",
      ("VB3:RemoteAlignmentServices (15 ops) — addRemoteAlignmentService, "
       "searchMatchers, createTask, listTasks, fetchAlignment",),
      ("T.IA.1", "B.CT.3", "T.AC.6"), ("backend", "agent"), "P6", "SHOULD",
      "ontology_builder.alignment.remote", depends_on=("OB.MAP.02", "OB.EXT.01"),
      notes="The natural insertion point for an LLM/embedding matcher as just "
            "another registered matcher — see OB.AGT.05."),
    F("OB.MAP.05", "Matching-problem profiling (MAPLE)", "MAP",
      "Profile two datasets' metadata to choose matchers and supporting resources "
      "automatically before matching.",
      ("VB3:MAPLE service — profileProject, profileMatchingProblemBetweenProjects, "
       "profileMediationProblem, checkProjectMetadataAvailability",),
      ("T.IA.1", "T.IA.3"), ("backend", "agent"), "P6", "MAY",
      "ontology_builder.alignment.profiling", depends_on=("OB.MDR.02",)),
    F("OB.MAP.06", "Mappings in a dedicated named graph", "MAP",
      "All cross-ontology mappings are written to a separate mapping graph, never "
      "into the source ontologies.",
      ("Local invariant from the playground-fuseki workbench design",),
      ("T.IA.1", "T.IA.2", "T.OO.1"), ("store", "backend"), "P6", "MUST",
      "ontology_builder.alignment.storage", depends_on=("OB.STO.01",)),

    # ===================== MDR · Metadata =================================== #
    F("OB.MDR.01", "Dataset metadata authoring & export", "MDR",
      "Describe the dataset with DCAT / DCAT-AP / ADMS / VoID / LIME, including "
      "computed statistical and lexicalization metadata, and export it alongside "
      "the data.",
      ("VB3:§4.12; DatasetMetadata service; DatasetMetadataExporter extension point",),
      ("T.AC.3", "B.SE.3", "B.CT.3"), ("backend", "ui"), "P6", "SHOULD",
      "ontology_builder.metadata.dataset", depends_on=("OB.EXT.01",)),
    F("OB.MDR.02", "Metadata registry (dataset catalogue)", "MDR",
      "A registry of known datasets — catalog records, versions, distributions, "
      "SPARQL endpoints, lexicalization sets, linksets, dereferenceability, "
      "abstractions — usable to discover and import ontologies.",
      ("VB3:MetadataRegistry service (37 ops)",),
      ("B.CT.3", "T.DA.3", "T.IA.1"), ("backend", "ui"), "P6", "SHOULD",
      "ontology_builder.metadata.registry",
      reuse=("Ontology Repository/FIBO/",)),
    F("OB.MDR.03", "External dataset catalog connectors", "MDR",
      "Pluggable connectors to public catalogs (LOV, BioPortal, EU vocabularies) "
      "for search-and-import.",
      ("VB3:DatasetCatalogs service; DatasetCatalogConnector extension point",
       "WP:BioPortal term-linking facility (noted in VB3 §6.3)"),
      ("T.DA.3", "B.CT.3"), ("backend", "ui"), "P6", "SHOULD",
      "ontology_builder.metadata.catalogs", depends_on=("OB.EXT.01",)),
    F("OB.MDR.04", "Resource metadata patterns", "MDR",
      "Declarative patterns that stamp provenance/administrative metadata "
      "(creator, created, modified, status) onto resources on create/update, "
      "with a shareable pattern library.",
      ("VB3:ResourceMetadata service (13 ops) — createPattern, addAssociation, "
       "importPatternFromLibrary, storePatternInLibrary",),
      ("B.SG.5", "T.OO.2", "T.DA.5"), ("backend", "ui"), "P4", "SHOULD",
      "ontology_builder.metadata.patterns", depends_on=("OB.CHG.02",)),
    F("OB.MDR.05", "Entity tags", "MDR",
      "Colour-coded project-defined tags applied to entities manually or by "
      "criteria, usable as review/triage state.",
      ("WP:tag package (4 handlers) — GetProjectTags, SetProjectTags, "
       "GetEntityTags, UpdateEntityTags; EDIT_PROJECT_TAGS / EDIT_ENTITY_TAGS "
       "capabilities; webprotege-criteria",),
      ("B.SG.2", "T.QV.3", "B.VP.3"), ("backend", "ui"), "P5", "SHOULD",
      "ontology_builder.metadata.tags", depends_on=("OB.PRJ.03",),
      notes="Cheap, and the practical mechanism for editorial workflow states "
            "('needs definition', 'awaiting SME', 'FIBO-aligned')."),

    # ===================== SPQ · SPARQL ===================================== #
    F("OB.SPQ.01", "SPARQL query & update console", "SPQ",
      "A YASGUI-class editor with prefix autocompletion, live schema feeding, "
      "result download in tabular and RDF formats, and federation endpoint "
      "suggestion — with update guarded by capability and routed through change "
      "tracking.",
      ("VB3:§4.8; SPARQL service — evaluateQuery, executeUpdate, "
       "suggestEndpointsForFederation; widget/codemirror",),
      ("T.AC.1", "T.OO.4", "B.SG.2"), ("backend", "ui"), "P2", "MUST",
      "ontology_builder.sparql.console",
      reuse=("src/Ontology Modeler/ontology_modeler/fuseki.py",),
      depends_on=("OB.CHG.01", "OB.GOV.10"),
      notes="`executeUpdate` must not bypass OB.CHG.01 — that is precisely the "
            "'under-the-hood modification with complete history' requirement (R6+R9)."),
    F("OB.SPQ.02", "Stored & shared queries", "SPQ",
      "Save a query at system/project/user scope, share it across projects, "
      "parameterise it, and pipe its graph results through a transformer chain.",
      ("VB3:§4.8 stored queries; sparql/query-parameterization; "
       "Configurations service (7 ops) provides the storage substrate",),
      ("T.AC.1", "B.CT.2", "T.DA.5"), ("backend", "ui"), "P4", "SHOULD",
      "ontology_builder.sparql.stored", depends_on=("OB.SPQ.01", "OB.EXT.02")),
    F("OB.SPQ.03", "Custom services (declarative SPARQL-backed APIs)", "SPQ",
      "Define named operations backed by parameterised SPARQL, exposed as first-"
      "class API endpoints with generated forms and their own capabilities.",
      ("VB3:CustomServices service (12 ops) — createCustomService, "
       "addOperationToCustomService, getOperationForms, reloadCustomServices; "
       "Services service exposes the service/operation registry",),
      ("T.AC.4", "T.DA.5", "B.SG.2"), ("backend", "ui"), "P6", "SHOULD",
      "ontology_builder.sparql.custom_services",
      depends_on=("OB.SPQ.02", "OB.GOV.11"),
      notes="This is how a governed, ontology-driven data API is built without "
            "writing backend code — the direct realisation of T.AC.4."),
    F("OB.SPQ.04", "Typed programmatic API for agents & CI", "SPQ",
      "Every backend operation is a typed function with an HTTP twin, so agents, "
      "notebooks and pipelines call the same contract the UI does.",
      ("Local convention (bottomup_ontology.tools, ontology_assistant TOOL_CATALOG)",
       "WP:webprotege-backend-api, Jersey REST endpoints"),
      ("T.AC.4", "T.OO.3", "T.AC.6"), ("backend", "agent"), "P0", "MUST",
      "ontology_builder.api",
      notes="Establish in P0, not later — it is expensive to retrofit and it is "
            "the substrate the whole agent layer stands on."),

    # ===================== COL · Collaboration ============================== #
    F("OB.COL.01", "Issue tracking bound to resources", "COL",
      "Create and list issues, assign them to resources, and see per-resource "
      "pending items inside the resource view — either natively or via a connector "
      "to an existing tracker.",
      ("VB3:§4.11; Collaboration service (16 ops) with a JIRA implementation of the "
       "CollaborationBackend extension point",
       "WP:issues package (3 handlers), ISSUE_* capabilities and roles, "
       "webprotege-gh-issues-service (GitHub Issues connector)"),
      ("B.SE.1", "B.SE.3", "B.CT.2"), ("backend", "ui"), "P5", "MUST",
      "ontology_builder.collaboration.issues", depends_on=("OB.EXT.01",),
      notes="Both reference tools converged on *connect to the tracker the "
            "organisation already uses* rather than building one. Do the same: "
            "ship a `CollaborationBackend` extension point with GitHub and Jira "
            "implementations, and a minimal built-in fallback."),
    F("OB.COL.02", "Threaded comments on entities", "COL",
      "Discussion threads attached to entities, with a resolved/open status.",
      ("WP:EditComment, GetCommentedEntities, VIEW/CREATE/EDIT_OWN/EDIT_ANY/"
       "SET_OBJECT_COMMENT_STATUS capabilities",
       "VB3:EDOAL correspondence comments; otherwise delegated to the tracker"),
      ("B.SE.1", "B.CT.2"), ("backend", "ui"), "P5", "MUST",
      "ontology_builder.collaboration.comments", depends_on=("OB.GOV.10",)),
    F("OB.COL.03", "Watches & notification digests", "COL",
      "Watch a resource or a whole branch; receive changes in-app or as a scheduled "
      "e-mail digest, with time-zone-aware scheduling and per-user preferences.",
      ("VB3:Notifications service (11 ops) — startWatching, listWatching, "
       "scheduleNotificationDigest, getAvailableTimeZoneIds",
       "WP:watches package (4 handlers), AddWatch/RemoveWatch/SetEntityWatches/"
       "GetWatchedEntityChanges, WATCH_CHANGES capability"),
      ("B.SE.1", "B.CT.2", "B.VP.3"), ("backend", "ui"), "P5", "MUST",
      "ontology_builder.collaboration.watches", depends_on=("OB.CHG.03",)),
    F("OB.COL.04", "Outbound integrations (Slack / webhooks)", "COL",
      "Per-project Slack and webhook targets fired on project events.",
      ("WP:ProjectSettings.getSlackIntegrationSettings/getWebhookSettings",),
      ("B.VP.3", "T.OO.5"), ("backend",), "P5", "SHOULD",
      "ontology_builder.collaboration.integrations", depends_on=("OB.PRJ.03",)),
    F("OB.COL.05", "Git repository synchronisation", "COL",
      "Two-way sync between a project and a Git repository, tracking axiom-level "
      "changes across commit history — so ontology CI/CD works with ordinary "
      "developer tooling.",
      ("WP:webprotege-gh-history-service ('cloning ontology files in GitHub "
       "repositories to WebProtege by tracking axiom-level changes across Git "
       "commit history'), webprotege-gh-integration-service, "
       "github-commit-navigator-library",
       "VB3:§6.2 discusses VoCol's Git-based approach as an alternative"),
      ("T.OO.3", "T.OO.2", "B.CT.2"), ("backend",), "P8", "SHOULD",
      "ontology_builder.collaboration.git",
      depends_on=("OB.CHG.02", "OB.VER.01"),
      notes="WebProtégé's newest microservices are all about this. It is the "
            "bridge from T.OO.2 (versioning) to T.OO.3 (OntoOps CI/CD)."),

    # ===================== EXT · Extension framework ======================== #
    F("OB.EXT.01", "Extension-point registry", "EXT",
      "A general `component` abstraction — identifiable, configurable, scoped — "
      "and a registry of extension points that third parties implement. Ship the "
      "VocBench set: CollaborationBackend, DatasetCatalogConnector, "
      "DatasetMetadataExporter, RDFLifter, RDFTransformer, ReformattingExporter, "
      "RenderingEngine, RepositoryImplConfigurer, RepositorySourcedDeployer, "
      "RepositoryTargetingLoader, SearchStrategy, StreamSourcedDeployer, "
      "StreamTargetingLoader, URIGenerator — plus Reasoner and Matcher.",
      ("VB3:§3.2; models/Plugins.ts ExtensionPointID (15 points), "
       "ExtensionFactory/ConfigurableExtensionFactory; Extensions service",
       "PD:24 OSGi extension points — EditorKitFactory, ViewComponent, "
       "WorkspaceTab, inference_reasonerfactory, searchmanager, explanation, "
       "entity_renderer, OntologyLoader, OntologyRepositoryFactory, "
       "moveaxiomskit, preferencespanel, …"),
      ("B.SG.3", "T.OO.3", "B.CT.3"), ("backend",), "P2", "MUST",
      "ontology_builder.extensions.registry",
      notes="In Python: entry-point groups (`ontology_builder.extensions.*`) plus "
            "a Pydantic-typed configuration schema per factory. This is the "
            "architectural decision that determines whether the Builder can grow "
            "without forking — take VocBench's design wholesale."),
    F("OB.EXT.02", "Scoped settings & stored configurations", "EXT",
      "Settings and configurations exist at SYSTEM, PROJECT, USER, PROJECT_USER, "
      "PROJECT_GROUP and FACTORY scope with defaults cascading down; any "
      "extension's configuration can be stored, named, shared and reused.",
      ("VB3:models/Plugins.ts Scope enum; Settings service (17 ops) with "
       "getSettingsDefault/storePUSettingProjectDefault/getSettingsScopes; "
       "Configurations service (7 ops)",),
      ("B.SG.3", "B.CT.2"), ("backend", "ui"), "P0", "MUST",
      "ontology_builder.extensions.settings",
      notes="Needed in P0 because project settings, rendering and URI generation "
            "all sit on it."),
    F("OB.EXT.03", "Auto-generated configuration UI", "EXT",
      "Settings schemas render themselves as forms in the client, so a new "
      "extension needs no front-end work.",
      ("VB3:§3.2 — 'the user interface is informed by the extension point mechanism "
       "and supports extensions with automatically built forms'; "
       "widget/settings-renderer, widget/extension-configurator",),
      ("B.SG.3", "T.AC.2"), ("ui",), "P4", "MUST",
      "ontology_builder_ui/components/SettingsRenderer",
      depends_on=("OB.EXT.02",),
      notes="Pydantic/JSON-Schema → React form generator. This is what keeps the "
            "React layer from becoming the bottleneck on backend extensibility."),
    F("OB.EXT.04", "UI extension slots", "EXT",
      "Named slots in the React shell (structure tabs, resource-view sections, "
      "value renderers, tools menu) that plugins register into at runtime.",
      ("PD:ViewComponent / WorkspaceTab / EditorKitMenuAction extension points — "
       "the capability VocBench explicitly lacks ('provisioning of arbitrary "
       "extensions for the user interface … is still missing in VB3, due to "
       "limitations of the Angular technology', §6.3)",),
      ("T.AC.2", "B.CT.3"), ("ui",), "P8", "SHOULD",
      "ontology_builder_ui/shell/slots", depends_on=("OB.BRW.07",),
      notes="React module federation makes this practical in a way Angular did "
            "not for VocBench — a place where the merged product can beat both "
            "predecessors."),

    # ===================== S2R · Structured-source lifting ================== #
    F("OB.EXT.05", "OWL API sidecar service", "EXT",
      "A single stateless JVM service, behind HTTP and behind Python "
      "interfaces, giving the platform the Java OWL tooling that has no Python "
      "equivalent: Manchester-syntax parsing/rendering/completion (OWL API), "
      "DL classification and justifications (HermiT / ELK + OWL Explanation), "
      "and optionally ROBOT for release operations.",
      ("WP:webprotege-robot-service — 'Spring Boot service wrapping ROBOT for "
       "programmatic ontology processing and manipulation in WebProtege'; the "
       "precedent for reaching Java OWL tooling from a service architecture",
       "PD:the `inference_reasonerfactory`, `explanation` and "
       "`inconsistentOntologyExplanation` extension points — note that Protege "
       "core ships only NoOpReasoner; HermiT arrives via protege-distribution"),
      ("T.RI.1", "T.RI.4", "T.DA.2", "T.OO.3"), ("backend",), "P6", "SHOULD",
      "ontology_builder.sidecar (Python client) + services/owl-sidecar (Java)",
      depends_on=("OB.RSN.01",),
      notes="Justified by serving **two** unrelated gaps at once, not one. "
            "Pin the OWL API version explicitly — WebProtege is on 4.5.13, "
            "Protege Desktop on 4.5.29, and 5.x has incompatible packages. "
            "Costs to accept: a JVM in the deployment, cold start, a "
            "serialization boundary on a keystroke-latency path, and the "
            "entity-resolution round trip (solve with a per-project name->IRI "
            "dictionary cached in the sidecar and invalidated by change "
            "events, as WebProtege does with DictionaryManager)."),
    F("OB.S2R.01", "Spreadsheet & database lifting", "S2R",
      "Load a sheet or a JDBC/SQL source, inspect headers, map each header to a "
      "node/graph application, preview generated triples, then commit them.",
      ("VB3:Sheet2RDF service (31 ops) — getSheetHeaders, updateSubjectHeader, "
       "addAdvancedGraphApplicationToHeader, getTriplesPreview, addTriples, "
       "uploadDBInfo, getSupportedDBDrivers",
       "WP:csv package — ImportCSVFileActionHandler, GetCSVGridActionHandler; "
       "cellfie-plugin for Protégé Desktop"),
      ("T.DA.4", "T.IA.3", "B.SE.1"), ("backend", "ui"), "P6", "SHOULD",
      "ontology_builder.lifting.sheet",
      reuse=("bottomup_ontology/",),
      notes="All three tools have a version of this; VocBench's is by far the "
            "most complete. It is also the natural landing zone for the existing "
            "`bottomup_ontology` pipeline (T.DA.4)."),
    F("OB.S2R.02", "Text-to-ontology bottom-up pipeline", "S2R",
      "Text cleaning → pre-processing → term extraction → relation extraction → "
      "axiom finding → human-in-the-loop → evaluation, producing candidate classes, "
      "properties and constraints.",
      ("Local: bottomup_ontology/ (Keet Ch.7 Fig. 7.7) — already implemented as a "
       "networkx DiGraph of agent-callable steps",
       "VB3:CODA is designed for exactly this but 'has not yet been exploited "
       "inside VB3' (§3.4) — an explicit gap this design fills"),
      ("T.DA.4", "B.SE.1", "T.QV.4"), ("backend", "agent"), "P7", "SHOULD",
      "ontology_builder.lifting.text",
      reuse=("bottomup_ontology/",),
      depends_on=("OB.CHG.04",),
      notes="Its output must land in the staging graphs, never the main graph — "
            "candidate axioms are proposals by construction."),

    # ===================== AGT · Agentic layer ============================== #
    F("OB.AGT.01", "Agent tool surface over the typed API", "AGT",
      "Every backend operation is exposed as a typed, individually testable agent "
      "tool with declared read/write intent and required capability.",
      ("Local convention: bottomup_ontology/tools.py ToolRegistry + tool_specs; "
       "architecture/ontology_assistant/TOOL_CATALOG.md",),
      ("T.AC.6", "T.OO.3"), ("agent", "backend"), "P7", "MUST",
      "ontology_builder.agents.tools",
      reuse=("bottomup_ontology/tools.py",
             "architecture/ontology_assistant/TOOL_CATALOG.md"),
      depends_on=("OB.SPQ.04", "OB.GOV.11")),
    F("OB.AGT.02", "Ontology Assistant (read-only comprehension agent)", "AGT",
      "Answers questions about what the ontology asserts, with citations, using "
      "the Falkor-proposes / Fuseki-proves retrieval funnel and a grounding critic.",
      ("Local: architecture/ontology_assistant/ (full functional design, P0–P5)",),
      ("T.AC.6", "T.AC.2", "B.SE.1"), ("agent",), "P7", "MUST",
      "ontology_builder.agents.assistant",
      reuse=("architecture/ontology_assistant/",),
      depends_on=("OB.STO.04", "OB.SPQ.04")),
    F("OB.AGT.03", "Authoring copilot (proposal-only)", "AGT",
      "Drafts classes, properties, labels, definitions and axioms from a natural-"
      "language brief or a competency question — writing exclusively into the "
      "staging graphs so every suggestion is a human-validatable proposal.",
      ("Composition: VB3's staging/validation workflow (§4.4) + WP's forms + "
       "the local Enricher pipeline",
       "Local: src/Ontology Enricher/src/enricher.py"),
      ("T.AC.6", "T.DA.1", "T.DA.2", "B.SE.1"), ("agent",), "P7", "MUST",
      "ontology_builder.agents.copilot",
      reuse=("src/Ontology Enricher/src/enricher.py",),
      depends_on=("OB.CHG.04", "OB.AGT.01"),
      notes="**The governance keystone applied to AI.** Because the validation "
            "workflow already exists, an LLM is just another editor whose work "
            "requires the V capability to land. No new trust model is needed."),
    F("OB.AGT.04", "Quality remediation agent", "AGT",
      "Runs the ICV/SHACL/CQ suite, clusters violations, proposes the interactive "
      "fixes ICV already defines, and opens issues for the ones needing a human.",
      ("VB3:ICV's 38 checks each already carry a remediation operation — the agent "
       "chooses and batches them",),
      ("T.QV.1", "T.QV.3", "T.AC.6"), ("agent",), "P7", "SHOULD",
      "ontology_builder.agents.quality",
      depends_on=("OB.QLT.02", "OB.AGT.03")),
    F("OB.AGT.05", "Alignment agent", "AGT",
      "Registers as a matcher behind the existing remote-alignment interface, "
      "proposes candidate correspondences with confidence, and feeds them into the "
      "alignment validation queue.",
      ("VB3:RemoteAlignmentServices + alignment validation give the agent a "
       "ready-made review workflow",
       "Local: src/Ontology Enricher/mappings/"),
      ("T.IA.1", "T.AC.6", "T.IA.4"), ("agent",), "P7", "SHOULD",
      "ontology_builder.agents.aligner",
      depends_on=("OB.MAP.02", "OB.MAP.04")),
    F("OB.AGT.06", "Competency-question agent", "AGT",
      "Elicits and maintains competency questions from stakeholder text, "
      "synthesises SPARQL tests from them, and reports coverage.",
      ("Local: architecture/ontology_assistant TOOL_CATALOG `synthesize_cqs`, "
       "EVALUATION.md gold set",),
      ("B.SE.2", "T.QV.2", "T.AC.6"), ("agent",), "P7", "MUST",
      "ontology_builder.agents.cq",
      depends_on=("OB.QLT.03", "OB.AGT.02")),
    F("OB.AGT.07", "Governance & stewardship agent", "AGT",
      "Watches the validation queue and the change history; surfaces stale "
      "proposals, unassigned stewardship, policy drift and capability-model "
      "maturity gaps against the EKGF target level.",
      ("Composition of VB3 history/validation with the local capability model",
       "Local: ontology_engineering_capabilities/"),
      ("B.SG.2", "B.SG.5", "B.VP.2"), ("agent",), "P7", "SHOULD",
      "ontology_builder.agents.steward",
      reuse=("ontology_engineering_capabilities/",),
      depends_on=("OB.CHG.03", "OB.PRJ.10")),
    F("OB.AGT.08", "Agent evaluation harness", "AGT",
      "A gold set of competency questions, retrieval and faithfulness metrics, and "
      "a regression harness run in CI for every agent.",
      ("Local: architecture/ontology_assistant/EVALUATION.md",),
      ("T.QV.4", "T.AC.6", "B.VP.2"), ("agent",), "P7", "MUST",
      "ontology_builder.agents.eval",
      reuse=("architecture/ontology_assistant/EVALUATION.md",)),
    F("OB.AGT.09", "Least-privilege agent identities & audit", "AGT",
      "Each agent is a machine account with an explicit role; every agent write is "
      "attributed to it in the commit provenance and is subject to validation.",
      ("VB3:Machines service + ProjectUserBinding + commit provenance combine to "
       "give this for free once agents are modelled as principals",),
      ("B.SG.5", "B.SG.2", "T.AC.6"), ("agent", "backend"), "P7", "MUST",
      "ontology_builder.agents.identity",
      depends_on=("OB.GOV.12", "OB.CHG.02"),
      notes="Non-negotiable. An agent that writes with a human's ambient "
            "credentials makes the audit trail a lie."),

    # ===================== UIX · React client =============================== #
    F("OB.UIX.01", "React application shell", "UIX",
      "Routing, project context, session, language preference, theming and a "
      "resizable multi-pane layout.",
      ("VB3:app/ shell with resizable-layout, VBContext, config bar",
       "WP:GWT MVP shell with places/activities"),
      ("T.AC.2",), ("ui",), "P2", "MUST",
      "ontology_builder_ui/shell"),
    F("OB.UIX.02", "Permission-aware rendering", "UIX",
      "The client evaluates the same capability expressions as the server so "
      "controls are hidden or disabled rather than failing on click.",
      ("VB3:AuthorizationEvaluator runs in the browser via jsprolog with a goal "
       "cache; §4.2 'very dynamic UIs automatically modeled on users' capabilities, "
       "with no redundancy in the code'",),
      ("B.SG.2", "T.AC.2"), ("ui",), "P2", "MUST",
      "ontology_builder_ui/auth", depends_on=("OB.GOV.10",),
      notes="Ship the policy to the client as data (the evaluated capability set "
            "for the current user+project), not as a re-implementation of the "
            "engine — that removes VB3's dual-Prolog duplication."),
    F("OB.UIX.03", "Typed API client generated from the backend", "UIX",
      "OpenAPI → TypeScript client so the 700-odd operations stay in sync with "
      "zero hand-written service classes.",
      ("VB3:60 hand-written Angular service classes mirroring the server — the "
       "maintenance cost this avoids",),
      ("T.AC.4", "T.OO.3"), ("ui", "backend"), "P2", "MUST",
      "ontology_builder_ui/api", depends_on=("OB.SPQ.04",),
      notes="A direct lesson from reading VocBench's source: do not repeat the "
            "hand-mirrored service layer."),
    F("OB.UIX.04", "Virtualised trees & lists", "UIX",
      "Windowed rendering with incremental fetch, so 100k-node structures stay "
      "responsive.",
      ("VB3:R5 Data Scalability; alphabetic indexing for flat lists",),
      ("T.AC.2",), ("ui",), "P2", "MUST",
      "ontology_builder_ui/components/Tree", depends_on=("OB.BRW.02",)),
    F("OB.UIX.05", "Editor widgets", "UIX",
      "Manchester-syntax editor, Turtle/N-Triples editor, SPARQL editor, "
      "language-tagged literal editor, typed-literal input, resource picker, "
      "datatype/date pickers.",
      ("VB3:widget/codemirror/{manchester,turtle,ntriple,pearl,json,html,mustache}-"
       "editor, widget/pickers/*, lang-string-editor, typed-literal-input",),
      ("T.DA.2", "T.AC.5"), ("ui",), "P2", "MUST",
      "ontology_builder_ui/components/editors",
      depends_on=("OB.EDT.03", "OB.SPQ.01")),
    F("OB.UIX.06", "Localisation of the application itself", "UIX",
      "The UI is translated, independently of the data's languages.",
      ("VB3:src/assets/l10n/",),
      ("T.AC.5", "B.VP.3"), ("ui",), "P5", "SHOULD",
      "ontology_builder_ui/i18n"),
    F("OB.UIX.07", "Branding & content customisation", "UIX",
      "Configurable home page, navbar brand, footer — so a deployment can be "
      "presented as the organisation's own ontology portal.",
      ("VB3:CustomContent service — setHomeContent, setNavbarBrandContent, "
       "setFooterContent",),
      ("B.VP.3",), ("ui", "backend"), "P5", "MAY",
      "ontology_builder_ui/shell/branding"),
]

FEATURE_BY_ID = {f.id: f for f in FEATURES}


# --------------------------------------------------------------------------- #
# Accessors
# --------------------------------------------------------------------------- #
def features_in_area(area_id: str) -> list[Feature]:
    return [f for f in FEATURES if f.area == area_id]


def features_in_phase(phase: str) -> list[Feature]:
    return [f for f in FEATURES if f.phase == phase]


def features_for_capability(capability_id: str) -> list[Feature]:
    return [f for f in FEATURES if capability_id in f.capabilities]


def features_from_source(source_id: str) -> list[Feature]:
    """Features with at least one piece of evidence from ``source_id`` (VB3/WP/PD)."""
    prefix = source_id + ":"
    return [f for f in FEATURES if any(e.startswith(prefix) for e in f.evidence)]


def covered_capabilities() -> set[str]:
    return {c for f in FEATURES for c in f.capabilities}


def validate_model(known_capability_ids: set[str] | None = None) -> list[str]:
    """Return integrity problems (empty == consistent)."""
    problems: list[str] = []
    ids = set(FEATURE_BY_ID)
    if len(ids) != len(FEATURES):
        problems.append("duplicate feature ids")
    for f in FEATURES:
        if f.area not in FEATURE_AREA_BY_ID:
            problems.append(f"{f.id}: unknown area {f.area!r}")
        if f.phase not in PHASES:
            problems.append(f"{f.id}: unknown phase {f.phase!r}")
        if f.priority not in PRIORITIES:
            problems.append(f"{f.id}: bad priority {f.priority!r}")
        for lyr in f.layers:
            if lyr not in LAYERS:
                problems.append(f"{f.id}: bad layer {lyr!r}")
        if not f.capabilities:
            problems.append(f"{f.id}: maps to no capability")
        for d in f.depends_on:
            if d not in ids:
                problems.append(f"{f.id}.depends_on -> unknown {d!r}")
        if not f.evidence:
            problems.append(f"{f.id}: no evidence")
        if known_capability_ids is not None:
            for c in f.capabilities:
                if c not in known_capability_ids:
                    problems.append(f"{f.id}: unknown capability {c!r}")
    # dependency phase ordering
    order = list(PHASES)
    for f in FEATURES:
        for d in f.depends_on:
            dep = FEATURE_BY_ID.get(d)
            if dep and order.index(dep.phase) > order.index(f.phase):
                problems.append(
                    f"{f.id} ({f.phase}) depends on {d} scheduled later ({dep.phase})")
    return problems


if __name__ == "__main__":  # pragma: no cover
    try:
        from ontology_engineering_capabilities.capability_model import CAPABILITY_BY_ID
        known = set(CAPABILITY_BY_ID)
    except Exception:  # pragma: no cover
        known = None
    problems = validate_model(known)
    print(f"source tools  : {len(SOURCE_TOOLS)}")
    print(f"feature areas : {len(FEATURE_AREAS)}")
    print(f"features      : {len(FEATURES)}")
    print(f"capabilities  : {len(covered_capabilities())} covered")
    print(f"problems      : {len(problems)}")
    for p in problems:
        print("  -", p)
