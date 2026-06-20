"""Contract checks for user-facing model and local-agent documentation."""

from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_development_provenance_names_all_three_coding_tools():
    tool_names = ("GitHub Copilot", "OpenAI Codex", "Claude Code")

    for relative_path in ("README.md", "CONTENT_PROVENANCE.md"):
        content = _read(relative_path)
        for tool_name in tool_names:
            assert tool_name in content


def test_readme_documents_runtime_model_defaults_and_overrides():
    readme = _read("README.md")
    ai_review = _read("src/invoice_sorter/ai_review.py")
    expected = (
        ("deepseek-r1:8b", "OLLAMA_MODEL"),
        ("deepseek-r1:8b", "OLLAMA_ADVICE_MODEL"),
        ("qwen3-coder:30b", "OLLAMA_REPORT_MODEL"),
        ("granite4:tiny-h", "OLLAMA_CHAT_MODEL"),
    )

    for model, environment_variable in expected:
        assert f'os.environ.get("{environment_variable}", "{model}")' in ai_review
        assert f"`{environment_variable}`" in readme
        assert f"`{model}`" in readme


def test_agent_endpoint_documentation_matches_implemented_routes():
    service = _read("src/invoice_sorter/agent_service.py")
    architecture = _read("ARCHITECTURE.md")
    provenance = _read("CONTENT_PROVENANCE.md")
    endpoints = (
        "/api/health",
        "/api/document-advice",
        "/api/document-chat",
        "/api/executive-report",
        "/api/executive-report-stream",
    )

    for endpoint in endpoints:
        assert endpoint in service
        assert endpoint in architecture
        assert endpoint in provenance


def test_drawio_architecture_contains_static_and_dynamic_pages():
    relative_path = "docs/invoice_sorter_architecture.drawio"
    root = ElementTree.parse(ROOT / relative_path).getroot()
    page_names = {diagram.attrib["name"] for diagram in root.findall("diagram")}

    assert page_names == {"Static Structure", "Dynamic Flow"}
    assert relative_path in _read("README.md")
    assert relative_path in _read("ARCHITECTURE.md")
