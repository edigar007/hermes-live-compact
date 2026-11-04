"""Test fixtures.

The engine imports two Hermes modules (``agent.context_compressor``,
``agent.model_metadata``). Prefer a real Hermes tree; otherwise fall back to the tiny stub
in ``tests/_hermes_stub`` so the suite also runs hermetically (CI, no network).

    "$HERMES_HOME/hermes-agent/venv/bin/python" -m pytest tests -q     # real Hermes
    python -m pytest tests -q                                          # stub backend
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUB = Path(__file__).resolve().parent / "_hermes_stub"
_BACKEND = None


def _ensure_hermes_importable() -> str:
    """Make ``agent.*`` importable and report which backend was used."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    try:
        import agent
        # Hermes modules import siblings (hermes_yaml, utils) as top-level names.
        root = Path(agent.__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        _BACKEND = "hermes"
    except Exception:
        if not (STUB / "agent" / "context_compressor.py").is_file():
            raise RuntimeError(
                "Neither Hermes nor the test stub is importable. Run with Hermes' venv "
                "python, or set HERMES_HOME to your Hermes home."
            )
        sys.path.insert(0, str(STUB))
        _BACKEND = "stub"
    return _BACKEND


@pytest.fixture()
def lc(tmp_path):
    """A freshly imported engine whose runtime dirs point at tmp_path."""
    _ensure_hermes_importable()
    # Execute the entry file directly instead of going through importlib's spec loader:
    # the entry is ``__init__.py``, and a spec for it makes pytest try to re-import a
    # module literally named "__init__".
    entry = ROOT / "__init__.py"
    module = types.ModuleType("live_compact")
    module.__file__ = str(entry)
    exec(compile(entry.read_text(encoding="utf-8"), str(entry), "exec"), module.__dict__)
    module.SHADOW_DIR = tmp_path / "shadow"
    module.LOG_PATH = tmp_path / "debug.jsonl"
    return module


@pytest.fixture()
def backend():
    """'hermes' or 'stub' — which agent.* backend this run uses."""
    return _ensure_hermes_importable()
