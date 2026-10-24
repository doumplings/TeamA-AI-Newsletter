"""AI Newsletter Web API.

The API shares the team's PostgreSQL schema with the collector: both use the root
``models.py`` (mirrors ``schema.sql``). The repository root is put on the import
path here so ``import models`` and ``import collector`` work when uvicorn runs from api/.
"""
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
