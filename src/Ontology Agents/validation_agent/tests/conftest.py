import re
import warnings
from pathlib import Path

import pytest

from validation_agent.engine import pipeline
from validation_agent.workspace import ValidationWorkspace

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLES = Path(__file__).resolve().parent.parent / "samples"

warnings.filterwarnings("ignore", message=".*does not look like a valid URI.*")


def run_file(path: Path, policy: str = "registry-default-v1", declared: str | None = None,
             shapes: Path | None = None) -> ValidationWorkspace:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^# declared: (\S+)", text, re.MULTILINE)
    declared = declared or (m.group(1) if m else None)
    m = re.search(r"^# shapes: (\S+)", text, re.MULTILINE)
    if shapes is None and m:
        shapes = path.parent / m.group(1)
    ws = ValidationWorkspace.from_path(path, declared_level=declared, policy=policy,
                                       shapes_path=shapes)
    return pipeline.run(ws)


@pytest.fixture(scope="session")
def rail_ws():
    return run_file(SAMPLES / "rail.ttl", declared="formal-ontology",
                    shapes=SAMPLES / "rail_shapes.ttl")
