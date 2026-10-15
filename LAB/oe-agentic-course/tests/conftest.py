import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def chapter_path(name: str) -> str:
    """Put one chapter folder on sys.path (its modules import each other by name)."""
    path = str(next(ROOT.glob(f"chapters/{name}*")))
    if path not in sys.path:
        sys.path.insert(0, path)
    return path
