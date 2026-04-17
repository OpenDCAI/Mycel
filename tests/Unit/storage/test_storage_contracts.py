import inspect

from storage.contracts import LeaseRepo


def test_lease_repo_protocol_docstring_describes_lower_runtime_bridge() -> None:
    doc = inspect.getdoc(LeaseRepo)

    assert doc is not None
    assert "lower sandbox runtime bridge" in doc.lower()
    assert "Sandbox lease CRUD" not in doc
