from config.models_schema import ModelsConfig, ProviderConfig


def test_provider_qualified_model_id_resolves_provider_and_model_name():
    config = ModelsConfig(providers={"openai": ProviderConfig(api_key="key", base_url="https://proxy.example")})

    model_name, overrides = config.resolve_model("openai:gpt-5.4")

    assert model_name == "gpt-5.4"
    assert overrides == {"model_provider": "openai"}
