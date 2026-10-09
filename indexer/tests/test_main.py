import json

import pytest
from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser

import main
from main import _build_points, _load_markdown_files


def test_build_points_preserves_document_and_section_metadata():
    document_metadata = {
        "content_type": "career_timeline",
        "domains": ["experience"],
        "topics": ["employment history"],
        "temporal": True,
        "sensitivity": "standard",
    }
    document = Document(
        text="# Experience\n## Backend Engineer\nBuilt services.",
        metadata={"source": "experience.md", "document_metadata": document_metadata},
    )
    nodes = MarkdownNodeParser().get_nodes_from_documents([document])

    points = _build_points(nodes, [[0.1] * 384 for _ in nodes])
    payload = points[-1].payload

    assert payload["source"] == "experience.md"
    assert payload["document_metadata"] == document_metadata
    assert "Backend Engineer" in payload["section_path"]
    assert payload["section_headings"] == ["Backend Engineer"]


def test_build_points_rejects_embedding_count_mismatch():
    with pytest.raises(ValueError, match="embedding count"):
        _build_points([object()], [])


def test_load_markdown_files_skips_json_and_readme(tmp_path, monkeypatch):
    (tmp_path / "notes.md").write_text("# Notes\n\nHello.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Skip\n", encoding="utf-8")
    (tmp_path / "gaps.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "metadata.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "documents": {
                    "notes.md": {
                        "content_type": "profile",
                        "domains": ["identity"],
                        "topics": ["summary"],
                        "temporal": False,
                        "sensitivity": "standard",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)

    docs = _load_markdown_files()

    assert [doc.metadata["source"] for doc in docs] == ["notes.md"]
