import pytest
from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser

from main import _build_points


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
