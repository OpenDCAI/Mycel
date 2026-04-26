Integration tests in this directory must exercise real integration boundaries without mocks,
fakes, or monkeypatch replacement of collaborators.

Mocked router shells and narrow contract probes belong under `tests/Unit/`.
