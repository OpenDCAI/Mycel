import re
from pathlib import Path


def test_agent_config_schema_uses_library_package_storage() -> None:
    sql = Path("storage/schema/2026_04_24_agent_config_resolved_config_hardcut.sql").read_text(encoding="utf-8")

    assert "create schema if not exists library" in sql
    assert "create table if not exists library.skills" in sql
    assert "create table if not exists library.skill_packages" in sql
    assert "create table if not exists agent.skill_bindings" in sql
    assert "description text not null default ''" not in sql
    assert "skills_description_required_ck" in sql
    assert "drop table if exists agent.agent_skills cascade" in sql
    assert "drop table if exists agent.skills cascade" in sql
    assert "skill_md text not null" in sql
    assert "version text not null default" not in sql
    assert "files_json jsonb not null default '{}'::jsonb" in sql
    assert "manifest_json jsonb not null default '{}'::jsonb" in sql
    assert "artifact_uri" not in sql
    assert "references library.skill_packages(id)" in sql
    assert "agent_config.skills child.skill_id is required" in sql
    assert "agent_config.skills child.package_id is required" in sql
    assert "agent_skill.package_id does not belong to owner" in sql
    assert "from library.skill_packages" in sql
    assert "insert into agent.skill_bindings" in sql
    assert "insert into agent.agent_skills" not in sql
    assert "agent.agent_skills.content" not in sql
    assert "agent.agent_skills.files_json" not in sql


def test_agent_skill_binding_package_fk_does_not_silently_delete_agent_selection() -> None:
    sql = Path("storage/schema/2026_04_24_agent_config_resolved_config_hardcut.sql").read_text(encoding="utf-8")

    binding_table = re.search(
        r"create table if not exists agent\.skill_bindings \((?P<body>.*?)\);",
        sql,
        flags=re.DOTALL,
    )
    assert binding_table is not None
    body = binding_table.group("body")
    assert "references library.skill_packages(id)" in body
    assert "on delete cascade" not in body.lower()


def test_agent_config_schema_rejects_duplicate_child_names_inside_rpc() -> None:
    sql = Path("storage/schema/2026_04_24_agent_config_resolved_config_hardcut.sql").read_text(encoding="utf-8")

    assert "agent_config.name is required" in sql
    assert "agent_config.version is required" in sql
    assert "coalesce(payload->>'version', '0.1.0')" not in sql
    assert "agent_config.tools must be a JSON array" in sql
    assert "agent_config.runtime_settings must be a JSON object" in sql
    assert "agent_config.compact must be a JSON object" in sql
    assert "agent_config.meta must be a JSON object" in sql
    assert "agent_config.skills must be a JSON array" in sql
    assert "agent_config.rules must be a JSON array" in sql
    assert "agent_config.sub_agents must be a JSON array" in sql
    assert "agent_config.mcp_servers must be a JSON array" in sql
    assert "agent_config.skills child.name is required" not in sql
    assert "agent_config.rules child.name is required" in sql
    assert "agent_config.sub_agents child.name is required" in sql
    assert "agent_config.mcp_servers child.name is required" in sql
    assert "agent_config.sub_agents child.tools must be a JSON array" in sql
    assert "agent_config.mcp_servers child.args must be a JSON array" in sql
    assert "agent_config.mcp_servers child.env must be a JSON object" in sql
    assert "agent_config.skills contains duplicate name" not in sql
    assert "agent_config.rules contains duplicate name" in sql
    assert "agent_config.sub_agents contains duplicate name" in sql
    assert "agent_config.mcp_servers contains duplicate name" in sql
    assert "jsonb_array_elements(coalesce(payload->'mcp_servers'" in sql
    assert "as mcp_item(value)" in sql
    assert "group by child->>'name'" not in sql


def test_agent_config_schema_requires_enabled_direction_for_skill_and_mcp_state() -> None:
    sql = Path("storage/schema/2026_04_24_agent_config_resolved_config_hardcut.sql").read_text(encoding="utf-8")

    assert "agent_config.skills child state must use enabled" in sql
    assert "agent_config.mcp_servers child state must use enabled" in sql
    assert "agent_config.skills child.enabled must be a JSON boolean" in sql
    assert "agent_config.rules child.enabled must be a JSON boolean" in sql
    assert "agent_config.sub_agents child.enabled must be a JSON boolean" in sql
    assert "agent_config.mcp_servers child.enabled must be a JSON boolean" in sql
    assert "skill_item.value ? 'disabled'" in sql
    assert "mcp_item.value ? 'disabled'" in sql


def test_agent_config_schema_does_not_convert_object_mcp_json() -> None:
    sql = Path("storage/schema/2026_04_24_agent_config_resolved_config_hardcut.sql").read_text(encoding="utf-8")

    assert "agent.agent_configs.mcp_json must be a JSON array before hard cut" in sql
    assert "alter column mcp_json set default '[]'::jsonb" in sql
    assert "agent_configs_mcp_json_array_ck" in sql
    assert "check (jsonb_typeof(mcp_json) = 'array')" in sql
    assert "jsonb_typeof(mcp_json) not in ('array', 'object')" not in sql
    assert "jsonb_each(c.mcp_json)" not in sql
    assert "(item.value - 'disabled')" not in sql


def test_agent_config_schema_constrains_named_child_tables() -> None:
    sql = Path("storage/schema/2026_04_24_agent_config_resolved_config_hardcut.sql").read_text(encoding="utf-8")

    assert "agent_rules_config_name_uq" in sql
    assert "agent_sub_agents_config_name_uq" in sql
    assert "agent.agent_rules contains duplicate (agent_config_id, name) rows before hard cut" in sql
    assert "agent.agent_sub_agents contains duplicate (agent_config_id, name) rows before hard cut" in sql


def test_agent_config_schema_constrains_root_identity_fields() -> None:
    sql = Path("storage/schema/2026_04_24_agent_config_resolved_config_hardcut.sql").read_text(encoding="utf-8")

    assert "library.skills.source_json must be a JSON object before hard cut" in sql
    assert "library.skills.description must be present before hard cut" in sql
    assert "library.skill_packages.manifest_json must be a JSON object before hard cut" in sql
    assert "library.skill_packages.version must be present before hard cut" in sql
    assert "library.skill_packages.files_json must be a JSON object before hard cut" in sql
    assert "library.skill_packages.files_json values must be strings before hard cut" in sql
    assert "library.skill_packages.files_json keys must be package-relative paths before hard cut" in sql
    assert "library.skill_packages.source_json must be a JSON object before hard cut" in sql
    assert "skills_source_json_object_ck" in sql
    assert "skill_packages_manifest_json_object_ck" in sql
    assert "skill_packages_files_json_object_ck" in sql
    assert "skill_packages_source_json_object_ck" in sql
    assert "agent.agent_configs.tools_json must be a JSON array before hard cut" in sql
    assert "agent.agent_configs.runtime_json must be a JSON object before hard cut" in sql
    assert "agent.agent_configs.compact_json must be a JSON object before hard cut" in sql
    assert "agent.agent_configs.meta_json must be a JSON object before hard cut" in sql
    assert "agent_configs_tools_json_array_ck" in sql
    assert "agent_configs_runtime_json_object_ck" in sql
    assert "agent_configs_compact_json_object_ck" in sql
    assert "agent_configs_meta_json_object_ck" in sql
    assert "agent_configs_owner_user_id_required_ck" in sql
    assert "agent_configs_agent_user_id_required_ck" in sql
    assert "agent_configs_name_required_ck" in sql
    assert "agent_configs_version_required_ck" in sql
    assert "check (owner_user_id is not null and btrim(owner_user_id) <> '')" in sql
    assert "check (agent_user_id is not null and btrim(agent_user_id) <> '')" in sql
    assert "check (name is not null and btrim(name) <> '')" in sql
    assert "check (version is not null and btrim(version) <> '')" in sql
    assert "agent.agent_configs contains blank root identity before hard cut" in sql
