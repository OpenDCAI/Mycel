"""
Leon 配置管理模块
"""

import os
from pathlib import Path


class ConfigManager:
    """管理 Leon 的配置"""

    def __init__(self):
        self.config_dir = Path.home() / ".leon"
        self.config_file = self.config_dir / "config.env"
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> str | None:
        """获取配置值"""
        if not self.config_file.exists():
            return None

        for line in self.config_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip()
        return None

    def set(self, key: str, value: str):
        """设置配置值"""
        config = {}

        if self.config_file.exists():
            for line in self.config_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()

        config[key] = value

        with self.config_file.open("w") as f:
            for k, v in config.items():
                f.write(f"{k}={v}\n")

    def list_all(self) -> dict[str, str]:
        """列出所有配置"""
        config = {}
        if self.config_file.exists():
            for line in self.config_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
        return config

    def load_to_env(self):
        """加载配置到环境变量"""
        for key, value in self.list_all().items():
            if key not in os.environ:
                # 规范化 OPENAI_BASE_URL：确保包含 /v1
                if key == "OPENAI_BASE_URL" and value:
                    value = normalize_base_url(value)
                os.environ[key] = value


def normalize_base_url(url: str) -> str:
    """
    规范化 OpenAI 兼容 API 的 base_url

    OpenAI SDK 会在 base_url 后直接拼接 /chat/completions，
    所以 base_url 必须以 /v1 结尾。

    Examples:
        https://api.openai.com -> https://api.openai.com/v1
        https://yunwu.ai -> https://yunwu.ai/v1
        https://yunwu.ai/v1 -> https://yunwu.ai/v1 (不变)
        https://example.com/api/v1 -> https://example.com/api/v1 (不变)
    """
    if not url:
        return url

    url = url.rstrip("/")

    # 如果已经以 /v1 结尾，不处理
    if url.endswith("/v1"):
        return url

    # 如果包含 /v1/ 在中间（如 /v1/engines），不处理
    if "/v1/" in url:
        return url

    # 否则补全 /v1
    return f"{url}/v1"


