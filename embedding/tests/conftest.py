"""Mock fastembed/uvicorn so tests can import main without installing them.

fastembed is imported at module level in main.py — must be mocked before import.
uvicorn is only used in __name__ == "__main__" but is imported at module level.
"""

import sys


class _MockVector:
    """Mimics a fastembed embedding vector with .tolist()."""
    def tolist(self):
        return [0.1] * 384


class _MockEmbedder:
    """Mimics fastembed.TextEmbedding."""
    def __init__(self, **kw):
        pass

    def embed(self, inputs):
        return [_MockVector() for _ in inputs]


# Inject mocks before any test imports main
if "fastembed" not in sys.modules:
    fastembed = type(sys)("fastembed")
    fastembed.TextEmbedding = _MockEmbedder
    sys.modules["fastembed"] = fastembed

if "uvicorn" not in sys.modules:
    sys.modules["uvicorn"] = type(sys)("uvicorn")
