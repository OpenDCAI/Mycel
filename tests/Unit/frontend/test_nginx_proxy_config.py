from pathlib import Path


def test_frontend_api_proxy_forwards_websocket_upgrade() -> None:
    config = Path("frontend/app/nginx.conf").read_text(encoding="utf-8")

    assert "map $http_upgrade $connection_upgrade" in config
    assert "proxy_http_version 1.1;" in config
    assert "proxy_set_header Upgrade $http_upgrade;" in config
    assert "proxy_set_header Connection $connection_upgrade;" in config


def test_frontend_openapi_probe_is_backend_route_not_spa_fallback() -> None:
    config = Path("frontend/app/nginx.conf").read_text(encoding="utf-8")

    assert "location = /openapi.json" in config
    openapi_location = config.split("location = /openapi.json", 1)[1].split("location", 1)[0]
    assert "proxy_pass http://backend:8900" in openapi_location
    assert "try_files" not in openapi_location
