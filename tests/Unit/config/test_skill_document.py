import pytest

from config.skill_document import parse_skill_document


def test_parse_skill_document_reads_frontmatter_fields_and_body() -> None:
    document = parse_skill_document(
        "---\nname: Query Helper\ndescription: Use precise query terms\nversion: 1.2.3\n---\nBody\n",
        label="Test Skill",
    )

    assert document.name == "Query Helper"
    assert document.description == "Use precise query terms"
    assert document.version == "1.2.3"
    assert document.body == "Body\n"


def test_parse_skill_document_requires_frontmatter_name() -> None:
    with pytest.raises(ValueError, match="Test Skill frontmatter must include name"):
        parse_skill_document("---\ndescription: Missing\n---\nBody", label="Test Skill")


def test_parse_skill_document_can_require_description() -> None:
    with pytest.raises(ValueError, match="Test Skill frontmatter must include description"):
        parse_skill_document("---\nname: Query Helper\n---\nBody", label="Test Skill", require_description=True)


def test_parse_skill_document_can_require_version() -> None:
    with pytest.raises(ValueError, match="Test Skill frontmatter must include version"):
        parse_skill_document("---\nname: Query Helper\n---\nBody", label="Test Skill", require_version=True)
