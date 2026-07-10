import json

import pytest

from metadata import (
    MetadataError,
    build_section_path,
    extract_section_path,
    load_document_metadata,
)


def _write_manifest(tmp_path, documents, schema_version=1):
    (tmp_path / "metadata.json").write_text(
        json.dumps({"schema_version": schema_version, "documents": documents}),
        encoding="utf-8",
    )


def _metadata():
    return {
        "content_type": "profile",
        "domains": ["identity"],
        "topics": ["summary"],
        "temporal": False,
        "sensitivity": "standard",
    }


def test_load_document_metadata(tmp_path):
    _write_manifest(tmp_path, {"profile.md": _metadata()})

    result = load_document_metadata(tmp_path, {"profile.md"})

    assert result["profile.md"]["content_type"] == "profile"


def test_manifest_requires_exact_markdown_coverage(tmp_path):
    _write_manifest(tmp_path, {"old.md": _metadata()})

    with pytest.raises(MetadataError, match="missing metadata for: profile.md"):
        load_document_metadata(tmp_path, {"profile.md"})


def test_manifest_validates_list_values(tmp_path):
    metadata = _metadata()
    metadata["topics"] = []
    _write_manifest(tmp_path, {"profile.md": metadata})

    with pytest.raises(MetadataError, match="topics must contain non-empty strings"):
        load_document_metadata(tmp_path, {"profile.md"})


def test_extract_section_path():
    text = "# **Experience**\nIntro\n## Backend Engineer\nDetails"

    assert extract_section_path(text) == ["Experience", "Backend Engineer"]


def test_build_section_path_combines_ancestors_and_leaf_heading():
    assert build_section_path("/Experience/", "## Backend Engineer\nDetails") == (
        "/Experience/Backend Engineer"
    )
