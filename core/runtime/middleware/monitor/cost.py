"""模型成本计算

定价来源优先级：
1. OpenRouter API（启动时拉取，缓存到 ~/.leon/pricing_cache.json，24h TTL）
2. 本地 models.json（OpenRouter /models 原始快照，随代码发布，离线兜底）
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from config.user_paths import preferred_existing_user_home_path, user_home_path

# 定价数据（运行时填充）
_pricing_data: dict[str, dict[str, Decimal]] = {}
_context_limits: dict[str, int] = {}  # model_name → context_length
_model_providers: dict[str, str] = {}  # model_name → provider (e.g. "anthropic", "openai")
_initialized = False

# 路径
_BUNDLED_PATH = Path(__file__).parent / "models.json"
_CACHE_PATH = user_home_path("pricing_cache.json")
_CACHE_TTL = 86400  # 24 小时

M = Decimal("1000000")
_PER_TOKEN_TO_PER_M = Decimal("1000000")


def _parse_openrouter_model(model: dict[str, Any]) -> tuple[str, dict[str, Decimal] | None, int, str] | None:
    """从 OpenRouter 模型数据中提取定价、上下文窗口和 provider

    OpenRouter pricing 字段是 per-token（字符串），转换为 per-1M-tokens（Decimal）。
    模型 ID 格式为 "provider/model-name"，提取两部分。
    costs 为 None 表示免费模型（pricing 为 0），但 context_length 和 provider 仍会返回。
    """
    model_id = model.get("id", "")
    if not model_id or "/" not in model_id:
        return None
    context_length = model.get("context_length", 0) or 0

    provider = model_id.split("/", 1)[0]
    short_name = model_id.split("/", 1)[1]

    pricing = model.get("pricing") or {}
    prompt_price = pricing.get("prompt", "0")
    completion_price = pricing.get("completion", "0")

    if prompt_price == "0" and completion_price == "0":
        return short_name, None, context_length, provider

    try:
        input_per_m = Decimal(prompt_price) * _PER_TOKEN_TO_PER_M
        output_per_m = Decimal(completion_price) * _PER_TOKEN_TO_PER_M
    except Exception:
        return short_name, None, context_length, provider

    cache_read_per_m = _parse_cache_price(pricing.get("input_cache_read"))
    cache_write_per_m = _parse_cache_price(pricing.get("input_cache_write"))

    # 仅在 OpenRouter 未明确提供时推断（不覆盖明确值）
    if not cache_read_per_m or not cache_write_per_m:
        cache_read_per_m, cache_write_per_m = _infer_cache_prices(provider, input_per_m, cache_read_per_m, cache_write_per_m)

    costs: dict[str, Decimal] = {
        "input": input_per_m,
        "output": output_per_m,
    }
    if cache_read_per_m:
        costs["cache_read"] = cache_read_per_m
    if cache_write_per_m:
        costs["cache_write"] = cache_write_per_m

    return short_name, costs, context_length, provider


def _parse_cache_price(price_str: str | None) -> Decimal:
    """解析缓存价格字符串"""
    if not price_str:
        return Decimal("0")
    try:
        return Decimal(price_str) * _PER_TOKEN_TO_PER_M
    except Exception:
        return Decimal("0")


def _infer_cache_prices(provider: str, input_per_m: Decimal, cache_read: Decimal, cache_write: Decimal) -> tuple[Decimal, Decimal]:
    """根据 provider 推断缓存价格"""
    cache_rules = {
        "anthropic": (Decimal("0.1"), Decimal("1.25")),
        "openai": (Decimal("0.5"), Decimal("1.0")),
        "": (Decimal("0.5"), Decimal("1.0")),
        "deepseek": (Decimal("0.1"), Decimal("1.0")),
    }

    read_multiplier, write_multiplier = cache_rules.get(provider, (Decimal("0.5"), Decimal("1.0")))

    if not cache_read:
        cache_read = input_per_m * read_multiplier
    if not cache_write:
        cache_write = input_per_m * write_multiplier

    return cache_read, cache_write


def _load_cache() -> tuple[dict[str, dict[str, str]], dict[str, int], dict[str, str]] | None:
    """从磁盘缓存加载定价数据、上下文窗口大小和 provider 映射"""
    cache_path = preferred_existing_user_home_path("pricing_cache.json")
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text())
        if time.time() - data.get("timestamp", 0) > _CACHE_TTL:
            return None
        models = data.get("models", {})
        ctx = data.get("context_limits", {})
        provs = data.get("providers", {})
        return models, ctx, provs
    except Exception:
        return None


def _save_cache(models: dict[str, dict[str, str]], context_limits: dict[str, int], providers: dict[str, str]) -> None:
    """保存定价数据、上下文窗口大小和 provider 映射到磁盘缓存"""
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {"timestamp": time.time(), "models": models, "context_limits": context_limits, "providers": providers}
        _CACHE_PATH.write_text(json.dumps(data))
    except Exception:
        pass


def _deserialize_costs(raw: dict[str, dict[str, str]]) -> dict[str, dict[str, Decimal]]:
    """将缓存中的字符串值转为 Decimal"""
    result = {}
    for model_name, costs in raw.items():
        try:
            result[model_name] = {k: Decimal(v) for k, v in costs.items()}
        except Exception:
            continue
    return result


def _serialize_costs(costs: dict[str, dict[str, Decimal]]) -> dict[str, dict[str, str]]:
    """将 Decimal 值转为字符串用于缓存"""
    return {model: {k: str(v) for k, v in c.items()} for model, c in costs.items()}


def fetch_openrouter_pricing() -> dict[str, dict[str, Decimal]]:
    """加载定价数据：API 缓存 → OpenRouter API → bundled 文件

    同步调用（启动时一次性），超时 5 秒。
    同时加载上下文窗口大小和 provider 映射数据。
    """
    global _pricing_data, _context_limits, _model_providers, _initialized

    if _initialized:
        return _pricing_data

    cached = _load_cache()
    if cached:
        models_raw, ctx, provs = cached
        _pricing_data = _deserialize_costs(models_raw)
        _context_limits = ctx
        _model_providers = provs
        _initialized = True
        return _pricing_data

    _pricing_data = _fetch_from_openrouter() or _load_bundled()
    _initialized = True
    return _pricing_data


def _fetch_from_openrouter() -> dict[str, dict[str, Decimal]] | None:
    """从 OpenRouter API 拉取定价数据、上下文窗口大小和 provider 映射"""
    global _context_limits, _model_providers
    try:
        import urllib.request

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"User-Agent": "leon-agent/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        result: dict[str, dict[str, Decimal]] = {}
        ctx_result: dict[str, int] = {}
        prov_result: dict[str, str] = {}
        for model in data.get("data", []):
            parsed = _parse_openrouter_model(model)
            if parsed:
                name, costs, ctx_len, provider = parsed
                if name not in result:
                    if costs is not None:
                        result[name] = costs
                    if ctx_len > 0:
                        ctx_result[name] = ctx_len
                    if provider:
                        prov_result[name] = provider

        if result:
            _context_limits = ctx_result
            _model_providers = prov_result
            _save_cache(_serialize_costs(result), ctx_result, prov_result)
            return result
    except Exception:
        pass

    return None


def _load_bundled() -> dict[str, dict[str, Decimal]]:
    """从随代码发布的 models.json（OpenRouter 原始快照）加载"""
    global _context_limits, _model_providers
    if not _BUNDLED_PATH.exists():
        return {}
    try:
        data = json.loads(_BUNDLED_PATH.read_text())
        result: dict[str, dict[str, Decimal]] = {}
        ctx_result: dict[str, int] = {}
        prov_result: dict[str, str] = {}
        for model in data.get("data", []):
            parsed = _parse_openrouter_model(model)
            if parsed:
                name, costs, ctx_len, provider = parsed
                if name not in result:
                    if costs is not None:
                        result[name] = costs
                    if ctx_len > 0:
                        ctx_result[name] = ctx_len
                    if provider:
                        prov_result[name] = provider
        _context_limits = ctx_result
        _model_providers = prov_result
        _save_cache(_serialize_costs(result), ctx_result, prov_result)
        return result
    except Exception:
        return {}


def get_model_providers() -> dict[str, str]:
    """返回 model_name → provider 映射（需先调用 fetch_openrouter_pricing）"""
    return _model_providers


_DEFAULT_CONTEXT_LIMIT = 128000


def get_model_context_limit(model_name: str) -> int:
    """查询模型的上下文窗口大小，来源为 OpenRouter 数据（models.json 或实时 API）。

    查找优先级：精确匹配 → 规范化名称匹配 → 默认值 128000。
    不使用前缀匹配，因为不同变体的上下文窗口可能完全不同（如 gpt-5 vs gpt-5-turbo）。
    """
    normalized = CostCalculator._normalize_model_name(model_name)

    for name in (model_name, normalized):
        if name in _context_limits:
            return _context_limits[name]

    return _DEFAULT_CONTEXT_LIMIT


class CostCalculator:
    """基于模型单价表计算 token 成本

    查找优先级：精确匹配 → 前缀匹配 → 空（不计费）
    """

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.costs = self._resolve_costs(model_name)

    def _resolve_costs(self, model_name: str) -> dict[str, Decimal]:
        """解析模型单价"""
        if model_name in _pricing_data:
            return _pricing_data[model_name]

        normalized = self._normalize_model_name(model_name)
        if normalized != model_name and normalized in _pricing_data:
            return _pricing_data[normalized]

        for key in sorted(_pricing_data.keys(), key=len, reverse=True):
            if model_name.startswith(key):
                return _pricing_data[key]

        return {}

    @staticmethod
    def _normalize_model_name(name: str) -> str:
        """规范化模型名：去日期后缀，版本号横杠转点号

        claude-sonnet-4-5-20250929 → claude-sonnet-4.5
        claude-haiku-4-5-20251001 → claude-haiku-4.5
        claude-opus-4-1-20250805 → claude-opus-4.1
        """
        import re

        name = re.sub(r"-\d{8}$", "", name)
        name = re.sub(r"-(\d+)-(\d+)$", r"-\1.\2", name)
        return name

    def calculate(self, tokens: dict) -> dict:
        """返回各项成本（USD）

        Args:
            tokens: dict with keys input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens
        Returns:
            {"total": Decimal, "breakdown": {...}}
        """
        if not self.costs:
            return {"total": Decimal("0"), "breakdown": {}}

        breakdown = {
            "input": self.costs.get("input", Decimal("0")) * Decimal(str(tokens.get("input_tokens", 0))) / M,
            "output": self.costs.get("output", Decimal("0")) * Decimal(str(tokens.get("output_tokens", 0))) / M,
            "cache_read": self.costs.get("cache_read", Decimal("0")) * Decimal(str(tokens.get("cache_read_tokens", 0))) / M,
            "cache_write": self.costs.get("cache_write", Decimal("0")) * Decimal(str(tokens.get("cache_write_tokens", 0))) / M,
        }
        return {"total": sum(breakdown.values()), "breakdown": breakdown}
