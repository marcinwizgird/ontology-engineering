"""Generate vkg-artifacts/fiben-mappings.r2rml.ttl from vkg-artifacts/mapping-spec.yaml.

The YAML spec is the source of truth; the Turtle is a build output and is not edited by
hand. The generator validates the spec's structure (unknown entities, prefixes or fields)
and applies its conventions: one subject template per entity, quoted identifiers, and
`filter` maps rendered as rr:sqlQuery views. Semantic conformance against the database
metadata and the TBox is tools/check_mappings.py.

    python tools/build_mappings.py           # write the Turtle
    python tools/build_mappings.py --check   # exit 1 if the Turtle is out of date
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ARTIFACTS = Path(__file__).resolve().parents[1] / "vkg-artifacts"
SPEC = ARTIFACTS / "mapping-spec.yaml"
OUTPUT = ARTIFACTS / "fiben-mappings.r2rml.ttl"

HEADER = ("# Generated from mapping-spec.yaml by tools/build_mappings.py. Do not edit by hand:\n"
          "# change the spec, then run `python tools/build_mappings.py`.\n")

_MAP_FIELDS = {"id", "table", "subject", "subject_column", "class", "filter", "properties"}
_PROP_FIELDS = {"predicate", "column", "datatype", "ref"}


class SpecError(ValueError):
    pass


def load(path: Path = SPEC) -> dict:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    validate(spec)
    return spec


def validate(spec: dict) -> None:
    """Structural checks; every problem is reported at once."""
    errors: list[str] = []
    prefixes, entities = spec.get("prefixes", {}), spec.get("entities", {})
    for key in ("base_iri", "schema", "prefixes", "entities", "maps"):
        if key not in spec:
            errors.append(f"missing top-level key '{key}'")

    def curie(where: str, value) -> None:
        if not isinstance(value, str) or ":" not in value:
            errors.append(f"{where}: '{value}' is not a prefixed name")
        elif value.split(":", 1)[0] not in prefixes:
            errors.append(f"{where}: unknown prefix in '{value}'")

    paths = [e.get("path") for e in entities.values()]
    if len(paths) != len(set(paths)):
        errors.append("entities: two entities share an IRI path")
    for name, e in entities.items():
        for k in ("path", "table", "key"):
            if k not in e:
                errors.append(f"entity '{name}': missing '{k}'")

    ids = [m.get("id") for m in spec.get("maps", [])]
    for dup in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"map id '{dup}' is used more than once")
    for m in spec.get("maps", []):
        where = f"map '{m.get('id', '?')}'"
        if extra := set(m) - _MAP_FIELDS:
            errors.append(f"{where}: unknown fields {sorted(extra)}")
        for k in ("id", "table", "subject"):
            if k not in m:
                errors.append(f"{where}: missing '{k}'")
        if m.get("subject") not in entities:
            errors.append(f"{where}: unknown subject entity '{m.get('subject')}'")
        if "class" in m:
            curie(where, m["class"])
        if not m.get("class") and not m.get("properties"):
            errors.append(f"{where}: produces no triples (no class and no properties)")
        for i, p in enumerate(m.get("properties", []), 1):
            pw = f"{where} property {i}"
            if extra := set(p) - _PROP_FIELDS:
                errors.append(f"{pw}: unknown fields {sorted(extra)}")
            curie(pw, p.get("predicate"))
            if "ref" in p:
                if p["ref"] not in entities:
                    errors.append(f"{pw}: unknown ref entity '{p['ref']}'")
                if "datatype" in p:
                    errors.append(f"{pw}: a ref produces an IRI and takes no datatype")
            elif "column" not in p:
                errors.append(f"{pw}: needs 'column' (literal) or 'ref' (link)")
            if "datatype" in p:
                curie(pw, p["datatype"])
    if errors:
        raise SpecError("mapping spec is invalid:\n  " + "\n  ".join(errors))


def _q(name: str) -> str:
    return f'"{name}"'


def _lit(s: str) -> str:
    """A Turtle string literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _template(spec: dict, entity: str, column: str | None = None) -> str:
    e = spec["entities"][entity]
    return f'{spec["base_iri"]}{e["path"]}/{{{_q(column or e["key"])}}}'


def _columns_used(spec: dict, m: dict) -> list[str]:
    cols = [m.get("subject_column") or spec["entities"][m["subject"]]["key"]]
    for p in m.get("properties", []):
        cols.append(p.get("column") or spec["entities"][p["ref"]]["key"])
    return list(dict.fromkeys(cols))


def _logical_table(spec: dict, m: dict) -> str:
    table = f'{_q(spec["schema"])}.{_q(m["table"])}'
    if not m.get("filter"):
        return f"rr:tableName {_lit(table)}"
    cols = ", ".join(_q(c) for c in _columns_used(spec, m))
    where = " AND ".join(f"{_q(c)} = '{str(v).replace(chr(39), chr(39) * 2)}'"
                         for c, v in m["filter"].items())
    return f"rr:sqlQuery {_lit(f'SELECT {cols} FROM {table} WHERE {where}')}"


def render(spec: dict) -> str:
    out = [HEADER]
    out += [f"@prefix {p}: <{iri}> ." for p, iri in spec["prefixes"].items()]
    for m in spec["maps"]:
        lines = [f"<#{m['id']}> a rr:TriplesMap ;",
                 f"    rr:logicalTable [ {_logical_table(spec, m)} ] ;"]
        subject = f"rr:template {_lit(_template(spec, m['subject'], m.get('subject_column')))}"
        if m.get("class"):
            subject += f" ; rr:class {m['class']}"
        lines.append(f"    rr:subjectMap [ {subject} ] ;")
        for p in m.get("properties", []):
            if "ref" in p:
                om = f"rr:template {_lit(_template(spec, p['ref'], p.get('column')))}"
            else:
                om = f"rr:column {_lit(_q(p['column']))}"
                if p.get("datatype"):
                    om += f" ; rr:datatype {p['datatype']}"
            lines.append(f"    rr:predicateObjectMap [ rr:predicate {p['predicate']} ; "
                         f"rr:objectMap [ {om} ] ] ;")
        lines[-1] = lines[-1][:-2] + " ."
        out += ["", *lines]
    return "\n".join(out) + "\n"


def is_current(spec_path: Path = SPEC, output: Path = OUTPUT) -> bool:
    """True when the committed Turtle equals a fresh build (line endings ignored)."""
    if not output.exists():
        return False
    committed = output.read_text(encoding="utf-8").replace("\r\n", "\n")
    return committed == render(load(spec_path))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="fail if the Turtle is out of date")
    args = ap.parse_args(argv)
    try:
        spec = load()
    except SpecError as e:
        print(e, file=sys.stderr)
        return 1
    if args.check:
        if is_current():
            print(f"{OUTPUT.name} is up to date")
            return 0
        print(f"{OUTPUT.name} is out of date: run `python tools/build_mappings.py`",
              file=sys.stderr)
        return 1
    OUTPUT.write_text(render(spec), encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ARTIFACTS.parent)} ({len(spec['maps'])} triples maps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
