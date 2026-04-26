from backend.web.models.panel import CreateResourceRequest


def test_create_resource_request_allows_skill_content_without_name() -> None:
    request = CreateResourceRequest.model_validate({"content": "---\nname: Skill\n---\nBody"})

    assert request.name == ""
    assert request.content == "---\nname: Skill\n---\nBody"
