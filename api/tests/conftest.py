"""Shared test fixtures.

IMPORTANT: DATA_DIR must be set before any test imports app.core.identity.
identity.py calls _load_identity() at module import time, so this env var
must be in place before the first import.
"""

import os
from pathlib import Path

os.environ["DATA_DIR"] = str(Path(__file__).parent / "data")
