from typing import Literal

BumpType = Literal["major", "minor", "patch"]


def bump_semver(version: str, bump_type: BumpType) -> str:
    major, minor, patch = (int(part) for part in version.split("."))
    if bump_type == "major":
        return f"{major + 1}.0.0"
    if bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"
