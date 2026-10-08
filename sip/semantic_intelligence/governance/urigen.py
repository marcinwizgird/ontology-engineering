"""IRI minting — Semantic Turkey's template URI generator and Protégé's entity factory.

**Semantic Turkey** (``NativeTemplateBasedURIGenerator`` → CODA
``TemplateBasedRandomIdGenerator``): one template per *xRole*; defaults
``concept = c_${rand()}``, ``xLabel = xl_${lexicalForm.language}_${rand()}``,
``xNote = xNote_${rand()}``, ``fallback = ${xRole}_${rand()}``. ``${…}`` values
are whitespace→``_`` and URL-escaped; ``$${…}`` are inserted raw. ``rand(CODE[,n])``
codes: DATETIMEMS, UUID, TRUNCUUID4/8/12, DIGIT, XDIGIT, ALNUM (default
TRUNCUUID8). A candidate already used anywhere in the dataset is retried, five
attempts, then an error ("template lacks a random part?").

**Protégé** (``CustomOWLEntityFactory`` + ``EntityCreationPreferences``): either
*name as fragment* (spaces → ``_``) under the active ontology IRI with a ``#``
separator, or *auto-ID* (default prefix ``<type>_`` + UUID; iterative and
pronounceable generators also exist), optionally creating an ``rdfs:label`` from
the typed name. Protégé's iterative generator silently truncates digits beyond
the configured width; this port raises instead.
"""

from __future__ import annotations

import re
import secrets
import string
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Mapping
from urllib.parse import quote

from rdflib import Literal, URIRef

RAND_RE = re.compile(r"rand\((?P<code>DATETIMEMS|UUID|TRUNCUUID4|TRUNCUUID8|TRUNCUUID12|"
                     r"DIGIT|XDIGIT|ALNUM)?(?:\s*,\s*(?P<len>[1-9]\d*))?\)")
_PH_RE = re.compile(r"([a-zA-Z]+)(?:\[([1-9]*\d)\])?(?:\.([a-zA-Z]+))?")

DEFAULT_TEMPLATES = {
    "concept": "c_${rand()}",
    "xLabel": "xl_${lexicalForm.language}_${rand()}",
    "xNote": "xNote_${rand()}",
    "fallback": "${xRole}_${rand()}",
}


def random_part(code: str | None, length: int | None, default_code: str = "TRUNCUUID8",
                default_len: int = 8) -> str:
    code = code or default_code
    n = length or default_len
    if code == "DATETIMEMS":
        return str(int(time.time() * 1000))
    u = str(uuid.uuid4())
    if code == "UUID":
        return u
    if code == "TRUNCUUID4":
        return u[:4]
    if code == "TRUNCUUID8":
        return u[:8]
    if code == "TRUNCUUID12":
        return u[:13]
    alphabet = {"DIGIT": string.digits, "XDIGIT": "0123456789abcdef",
                "ALNUM": string.digits + string.ascii_lowercase}[code]
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _attr(value, attr: str | None) -> str:
    if attr is None:
        return str(value)
    if attr == "language":
        return (value.language if isinstance(value, Literal) else None) or "null"
    if attr == "datatype":
        return str(getattr(value, "datatype", "") or "")
    if attr == "label":
        return str(value)
    if attr in ("localName", "namespace"):
        s = str(value)
        cut = max(s.rfind("#"), s.rfind("/"))
        return s[cut + 1:] if attr == "localName" else s[:cut + 1]
    raise ValueError(f"unsupported placeholder attribute .{attr}")


@dataclass
class TemplateURIGenerator:
    namespace: str
    templates: dict[str, str] = field(default_factory=dict)
    rand_code: str = "TRUNCUUID8"
    rand_len: int = 8
    max_attempts: int = 5

    def generate(self, x_role: str, args: Mapping[str, object],
                 exists: Callable[[URIRef], bool]) -> URIRef:
        x_role = x_role or "res"
        for _ in range(self.max_attempts):
            tpl = (self.templates.get(x_role) or DEFAULT_TEMPLATES.get(x_role)
                   or self.templates.get("fallback") or DEFAULT_TEMPLATES["fallback"])
            iri = URIRef(self.namespace + self._expand(tpl, x_role, args))
            if not exists(iri):
                return iri
        raise ValueError(f"exceeded {self.max_attempts} attempts generating an IRI for "
                         f"{x_role!r}: does the template lack a random part?")

    def _expand(self, tpl: str, x_role: str, args: Mapping[str, object]) -> str:
        out = []
        while tpl:
            if tpl.startswith("$${") or tpl.startswith("${"):
                raw = tpl.startswith("$${")
                start = 3 if raw else 2
                end = tpl.find("}")
                if end < 0:
                    raise ValueError("missing closing brace in URI template")
                ph = tpl[start:end]
                m = RAND_RE.fullmatch(ph)
                if m:
                    val = random_part(m.group("code"), int(m.group("len")) if m.group("len")
                                      else None, self.rand_code, self.rand_len)
                elif ph == "xRole":
                    val = x_role
                else:
                    pm = _PH_RE.fullmatch(ph)
                    if not pm or pm.group(1) not in args:
                        raise ValueError(f'placeholder "{ph}" not present')
                    val = _attr(args[pm.group(1)], pm.group(3))
                if not raw:
                    val = quote(re.sub(r"\s+", "_", val.strip()), safe="-._~!$&'()*+,;=:@")
                out.append(val)
                tpl = tpl[end + 1:]
            else:
                nxt = re.search(r"\$\$?\{", tpl)
                cut = nxt.start() if nxt else len(tpl)
                out.append(tpl[:cut])
                tpl = tpl[cut:]
        return "".join(out)


@dataclass
class EntityCreationPreferences:
    """Protégé *Preferences ▸ New entities*."""

    base: str
    separator: str = "#"
    mode: str = "fragment"           # "fragment" | "auto-id"
    auto_id_prefix: str = "{type}_"
    auto_id: str = "uuid"            # "uuid" | "iterative"
    iterative_start: int = 1
    iterative_digits: int = 6
    create_label: bool = True
    label_language: str | None = "en"
    _counter: int = field(default=0, init=False, repr=False)

    def mint(self, name: str, entity_type: str, exists: Callable[[URIRef], bool]) -> URIRef:
        base = self.base.rstrip("#/") + self.separator
        if self.mode == "fragment":
            frag = re.sub(r"\s+", "_", name.strip())
            if not frag:
                raise ValueError("empty entity name")
            iri = URIRef(base + quote(frag, safe="-._~()'!*:@,;"))
            if exists(iri):
                raise ValueError(f"an entity named {iri} already exists")
            return iri
        prefix = self.auto_id_prefix.replace("{type}", entity_type)
        for _ in range(10_000):
            if self.auto_id == "uuid":
                local = prefix + str(uuid.uuid4())
            else:
                n = self.iterative_start + self._counter
                self._counter += 1
                if len(str(n)) > self.iterative_digits:
                    raise ValueError(f"iterative id {n} exceeds {self.iterative_digits} digits")
                local = prefix + str(n).zfill(self.iterative_digits)
            iri = URIRef(base + local)
            if not exists(iri):
                return iri
        raise ValueError("could not mint a fresh IRI")
