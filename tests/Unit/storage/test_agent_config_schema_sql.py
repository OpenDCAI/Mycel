from pathlib import Path


def test_agent_config_schema_rejects_skill_id_outside_owner() -> None:
    sql = Path("storage/schema/2026_04_24_agent_config_resolved_config_hardcut.sql").read_text(encoding="utf-8")

    assert "agent_skill.skill_id does not belong to owner" in sql
    assert "from agent.skills" in sql
    assert "owner_user_id = owner_id" in sql


def test_agent_config_schema_rejects_duplicate_child_names_inside_rpc() -> None:
    sql = Path("storage/schema/2026_04_24_agent_config_resolved_config_hardcut.sql").read_text(encoding="utf-8")

    assert "agent_config.name is required" in sql
    assert "agent_config.skills must be a JSON array" in sql
    assert "agent_config.rules must be a JSON array" in sql
    assert "agent_config.sub_agents must be a JSON array" in sql
    assert "agent_config.skills child.name is required" in sql
    assert "agent_config.rules child.name is required" in sql
    assert "agent_config.sub_agents child.name is required" in sql
    assert "agent_config.mcp_servers child.name is required" in sql
    assert "agent_config.skills contains duplicate name" in sql
    assert "agent_config.rules contains duplicate name" in sql
    assert "agent_config.sub_agents contains duplicate name" in sql
    assert "agent_config.mcp_servers contains duplicate name" in sql
    assert "jsonb_array_elements(coalesce(payload->'mcp_servers'" in sql
    assert "as mcp_item(value)" in sql
    assert "group by child->>'name'" not in sql


def test_agent_config_schema_constrains_named_child_tables() -> None:
    sql = Path("storage/schema/2026_04_24_agent_config_resolved_config_hardcut.sql").read_text(encoding="utf-8")

    assert "agent_rules_config_name_uq" in sql
    assert "agent_sub_agents_config_name_uq" in sql
    assert "agent.agent_rules contains duplicate (agent_config_id, name) rows before hard cut" in sql
    assert "agent.agent_sub_agents contains duplicate (agent_config_id, name) rows before hard cut" in sql


def test_agent_config_schema_constrains_root_identity_fields() -> None:
    sql = Path("storage/schema/2026_04_24_agent_config_resolved_config_hardcut.sql").read_text(encoding="utf-8")

    assert "agent_configs_owner_user_id_required_ck" in sql
    assert "agent_configs_agent_user_id_required_ck" in sql
    assert "agent_configs_name_required_ck" in sql
    assert "check (owner_user_id is not null and btrim(owner_user_id) <> '')" in sql
    assert "check (agent_user_id is not null and btrim(agent_user_id) <> '')" in sql
    assert "check (name is not null and btrim(name) <> '')" in sql
    assert "agent.agent_configs contains blank root identity before hard cut" in sql
