"""Tests for identity loading."""

import pytest
from pathlib import Path
from app.core.identity import get_identity, _load_identity


def test_get_identity_returns_dict():
    result = get_identity()
    assert result["full_name"] == "Test User"
    assert result["job_title"] == "Test Engineer"
    assert isinstance(result, dict)


def test_load_identity_missing_file(tmp_path, monkeypatch):
    """_load_identity raises FileNotFoundError when identity.json is missing."""
    monkeypatch.setattr(
        "app.core.identity._IDENTITY_PATH",
        tmp_path / "nonexistent.json",
    )
    with pytest.raises(FileNotFoundError, match="Identity data not found"):
        _load_identity()
