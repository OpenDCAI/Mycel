"""Tests for model config enrichment (based_on + context_limit)."""

import importlib

import pytest
from pydantic import ValidationError

from config.models_schema import ActiveModel, CustomModelConfig, ModelsConfig, ModelSpec, PoolConfig
from core.runtime.middleware.monitor import cost as cost_module
from core.runtime.middleware.monitor.cost import fetch_openrouter_pricing, get_model_context_limit
from core.runtime.middleware.monitor.middleware import MonitorMiddleware

# Ensure OpenRouter cache is populated (same as MonitorMiddleware.__init__)
fetch_openrouter_pricing()
SONNET_LIMIT = get_model_context_limit("claude-sonnet-4.5")
DEFAULT_LIMIT = 128000


class TestModelSpecFields:
    """ModelSpec 和 ActiveModel 支持 based_on + context_limit 字段"""

    def test_model_spec_accepts_based_on_and_context_limit(self):
        spec = ModelSpec(model="Alice", based_on="claude-sonnet-4.5", context_limit=32768)
        assert spec.based_on == "claude-sonnet-4.5"
        assert spec.context_limit == 32768

    def test_model_spec_defaults_none(self):
        spec = ModelSpec(model="Alice")
        assert spec.based_on is None
        assert spec.context_limit is None

    def test_active_model_accepts_based_on_and_context_limit(self):
        active = ActiveModel(model="Alice", based_on="claude-sonnet-4.5", context_limit=32768)
        assert active.based_on == "claude-sonnet-4.5"
        assert active.context_limit == 32768

    def test_context_limit_rejects_zero_or_negative(self):
        with pytest.raises(ValidationError):
            ModelSpec(model="x", context_limit=0)
        with pytest.raises(ValidationError):
            ModelSpec(model="x", context_limit=-1)


class TestResolveModelOverrides:
    """resolve_model 把 based_on/context_limit 放入 overrides"""

    def test_virtual_model_passes_based_on(self):
        config = ModelsConfig(mapping={"leon:custom": ModelSpec(model="Alice", based_on="claude-sonnet-4.5")})
        name, overrides = config.resolve_model("leon:custom")
        assert name == "Alice"
        assert overrides["based_on"] == "claude-sonnet-4.5"

    def test_virtual_model_passes_context_limit(self):
        config = ModelsConfig(mapping={"leon:custom": ModelSpec(model="Alice", context_limit=32768)})
        name, overrides = config.resolve_model("leon:custom")
        assert overrides["context_limit"] == 32768

    def test_non_virtual_model_passes_active_overrides(self):
        config = ModelsConfig(active=ActiveModel(model="Alice", based_on="claude-sonnet-4.5", context_limit=32768))
        name, overrides = config.resolve_model("Alice")
        assert name == "Alice"
        assert overrides["based_on"] == "claude-sonnet-4.5"
        assert overrides["context_limit"] == 32768

    def test_non_virtual_no_active_returns_empty(self):
        config = ModelsConfig()
        name, overrides = config.resolve_model("Alice")
        assert name == "Alice"
        assert overrides == {}

    def test_non_virtual_active_no_based_on_no_context_returns_empty(self):
        config = ModelsConfig(active=ActiveModel(model="Alice"))
        name, overrides = config.resolve_model("Alice")
        assert overrides == {}

    def test_virtual_model_inherits_custom_config(self):
        """虚拟模型映射到自定义模型时，继承 custom_config"""
        config = ModelsConfig(
            mapping={"leon:medium": ModelSpec(model="Day53")},
            pool=PoolConfig(
                custom=["Day53"],
                custom_config={"Day53": CustomModelConfig(based_on="deepseek-chat", context_limit=65536)},
            ),
        )
        name, overrides = config.resolve_model("leon:medium")
        assert name == "Day53"
        assert overrides["based_on"] == "deepseek-chat"
        assert overrides["context_limit"] == 65536

    def test_virtual_model_mapping_overrides_custom_config(self):
        """mapping 级别的 based_on/context_limit 优先于 custom_config"""
        config = ModelsConfig(
            mapping={"leon:medium": ModelSpec(model="Day53", based_on="gpt-4o", context_limit=128000)},
            pool=PoolConfig(
                custom_config={"Day53": CustomModelConfig(based_on="deepseek-chat", context_limit=65536)},
            ),
        )
        name, overrides = config.resolve_model("leon:medium")
        assert overrides["based_on"] == "gpt-4o"
        assert overrides["context_limit"] == 128000


class TestMonitorUpdateModel:
    """update_model 用 based_on 查找 pricing 和 context_limit"""

    def test_update_model_with_based_on(self):
        mw = MonitorMiddleware(model_name="claude-sonnet-4.5")
        mw.update_model("Alice", overrides={"based_on": "claude-sonnet-4.5"})
        assert mw._context_monitor.context_limit == SONNET_LIMIT

    def test_update_model_with_explicit_context_limit(self):
        mw = MonitorMiddleware(model_name="claude-sonnet-4.5")
        mw.update_model(
            "Alice",
            overrides={
                "based_on": "claude-sonnet-4.5",
                "context_limit": 32768,
            },
        )
        assert mw._context_monitor.context_limit == 32768

    def test_update_model_no_overrides_uses_model_name(self):
        mw = MonitorMiddleware(model_name="claude-sonnet-4.5")
        mw.update_model("claude-sonnet-4.5")
        assert mw._context_monitor.context_limit == SONNET_LIMIT

    def test_update_model_unknown_no_based_on_gets_default(self):
        mw = MonitorMiddleware(model_name="claude-sonnet-4.5")
        mw.update_model("totally-unknown-model")
        assert mw._context_monitor.context_limit == DEFAULT_LIMIT

    def test_update_model_based_on_affects_cost_calculator(self):
        mw = MonitorMiddleware(model_name="claude-sonnet-4.5")
        mw.update_model("Alice", overrides={"based_on": "claude-sonnet-4.5"})
        assert mw._token_monitor.cost_calculator.costs != {}

    def test_empty_cached_pricing_falls_back_to_bundled_models(self, monkeypatch: pytest.MonkeyPatch):
        importlib.reload(cost_module)

        monkeypatch.setattr(
            cost_module,
            "_load_cache",
            lambda: (
                {},
                {"claude-sonnet-4.5": SONNET_LIMIT},
                {"claude-sonnet-4.5": "anthropic"},
            ),
        )
        monkeypatch.setattr(cost_module, "_fetch_from_openrouter", lambda: None)

        prices = cost_module.fetch_openrouter_pricing()

        assert prices.get("claude-sonnet-4.5") is not None
        assert cost_module.CostCalculator("claude-sonnet-4.5").costs != {}


class TestThreeLevelPriority:
    """Level 1 用户配置 > Level 2 OpenRouter > Level 3 Bundled"""

    def test_user_context_limit_overrides_lookup(self):
        mw = MonitorMiddleware(model_name="claude-sonnet-4.5")
        mw.update_model(
            "Alice",
            overrides={
                "based_on": "claude-sonnet-4.5",
                "context_limit": 32768,
            },
        )
        assert mw._context_monitor.context_limit == 32768

    def test_based_on_lookup_overrides_default(self):
        mw = MonitorMiddleware(model_name="gpt-4o")
        mw.update_model("MyModel", overrides={"based_on": "claude-sonnet-4.5"})
        assert mw._context_monitor.context_limit == SONNET_LIMIT

    def test_no_based_on_no_user_config_falls_to_default(self):
        mw = MonitorMiddleware(model_name="gpt-4o")
        mw.update_model("totally-unknown")
        assert mw._context_monitor.context_limit == DEFAULT_LIMIT
