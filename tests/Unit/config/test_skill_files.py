import pytest

from config.skill_files import normalize_skill_file_entries, normalize_skill_file_map


def test_normalize_skill_file_map_converts_paths_to_posix_keys() -> None:
    assert normalize_skill_file_map({"references\\query.md": "Use exact queries."}, context="Skill files") == {
        "references/query.md": "Use exact queries."
    }


def test_normalize_skill_file_map_rejects_duplicate_paths_after_normalization() -> None:
    with pytest.raises(ValueError, match="Skill files contain duplicate path after normalization: references/query.md"):
        normalize_skill_file_map(
            {
                "references\\query.md": "Windows-shaped key.",
                "references/query.md": "POSIX-shaped key.",
            },
            context="Skill files",
        )


def test_normalize_skill_file_entries_rejects_duplicate_paths_after_normalization() -> None:
    with pytest.raises(ValueError, match="Local Skill files contain duplicate path after normalization: references/query.md"):
        normalize_skill_file_entries(
            [
                ("references\\query.md", "Windows-shaped key."),
                ("references/query.md", "POSIX-shaped key."),
            ],
            context="Local Skill files",
        )


def test_normalize_skill_file_map_rejects_non_string_content() -> None:
    with pytest.raises(ValueError, match="Skill files content must be a string: references/query.md"):
        normalize_skill_file_map({"references/query.md": {"text": "Use exact queries."}}, context="Skill files")


def test_normalize_skill_file_map_rejects_non_string_paths() -> None:
    with pytest.raises(ValueError, match="Skill files path must be a string"):
        normalize_skill_file_map({123: "Use exact queries."}, context="Skill files")


@pytest.mark.parametrize("path", ["", " ", "references//query.md"])
def test_normalize_skill_file_map_rejects_blank_or_empty_segment_paths(path: str) -> None:
    with pytest.raises(ValueError, match="Skill files path must be a relative file path"):
        normalize_skill_file_map({path: "Use exact queries."}, context="Skill files")


@pytest.mark.parametrize("path", ["/references/query.md", "references/../secret.md", "./references/query.md"])
def test_normalize_skill_file_map_rejects_paths_outside_package(path: str) -> None:
    with pytest.raises(ValueError, match="Skill files path must stay inside the Skill package"):
        normalize_skill_file_map({path: "Use exact queries."}, context="Skill files")
