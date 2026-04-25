import pytest

from config.skill_document import parse_skill_document, skill_description, skill_version, strip_skill_frontmatter


def test_parse_skill_document_reads_frontmatter_and_body() -> None:
    document = parse_skill_document(
        "---\nname: Query Helper\ndescription: Use precise query terms\nversion: 1.2.3\n---\nBody\n",
        label="Test Skill",
    )

    assert document.name == "Query Helper"
    assert document.frontmatter["description"] == "Use precise query terms"
    assert document.body == "Body\n"
    assert skill_description(document, required=True) == "Use precise query terms"
    assert skill_version(document) == "1.2.3"


def test_parse_skill_document_requires_frontmatter_name() -> None:
    with pytest.raises(ValueError, match="Test Skill frontmatter must include name"):
        parse_skill_document("---\ndescription: Missing\n---\nBody", label="Test Skill")


def test_strip_skill_frontmatter_returns_body() -> None:
    assert strip_skill_frontmatter("---\nname: Query Helper\n---\nUse exact terms.") == "Use exact terms."
