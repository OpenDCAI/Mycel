from pathlib import Path


def test_staging_deploy_verifies_public_openapi_not_private_monitor_routes() -> None:
    workflow = Path(".github/workflows/deploy-staging.yml").read_text(encoding="utf-8")

    assert "Verify staging OpenAPI contract" in workflow
    assert "https://app.staging.mycel.nextmind.space/openapi.json" in workflow
    assert ".openapi" in workflow
    assert "/api/monitor/sandbox-configs" not in workflow
    assert "/api/monitor/sandboxes" not in workflow
