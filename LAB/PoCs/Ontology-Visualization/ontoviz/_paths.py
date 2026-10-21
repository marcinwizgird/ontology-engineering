"""Repository paths, and ``sip/`` on ``sys.path`` so ``semantic_intelligence`` imports."""

import sys
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
REPO = POC.parents[2]
SIP = REPO / "sip"
FIBO = REPO / "Ontology Repository" / "FIBO" / "fibo"
DATA = POC / "data"
ARTIFACTS = POC / "artifacts"
WEB = POC / "web"

if str(SIP) not in sys.path:
    sys.path.insert(0, str(SIP))
