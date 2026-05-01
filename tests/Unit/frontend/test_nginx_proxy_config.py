from pathlib import Path


def test_frontend_api_proxy_forwards_websocket_upgrade() -> None:
    config = Path("frontend/app/nginx.conf").read_text(encoding="utf-8")

    assert "map $http_upgrade $connection_upgrade" in config
    assert "proxy_http_version 1.1;" in config
    assert "proxy_set_header Upgrade $http_upgrade;" in config
    assert "proxy_set_header Connection $connection_upgrade;" in config
