from config.models_schema import ModelsConfig, ProviderConfig


def test_provider_qualified_model_id_resolves_provider_and_model_name():
    config = ModelsConfig(providers={"openai": ProviderConfig(api_key="key", base_url="https://proxy.example")})

    model_name, overrides = config.resolve_model("openai:gpt-5.4")

    assert model_name == "gpt-5.4"
    assert overrides == {"model_provider": "openai"}


def test_user_credential_source_does_not_fallback_to_platform_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "platform-key")
    config = ModelsConfig(providers={"openai": ProviderConfig(credential_source="user")})

    assert config.resolve_api_key("openai") is None


def test_platform_credential_source_reads_provider_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "platform-key")
    config = ModelsConfig(providers={"openai": ProviderConfig(credential_source="platform", api_key="stale-user-key")})

    assert config.resolve_api_key("openai") == "platform-key"
