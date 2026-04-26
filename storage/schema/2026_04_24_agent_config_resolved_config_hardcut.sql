create extension if not exists pgcrypto;

create schema if not exists agent;
create schema if not exists library;

drop table if exists agent.agent_skills cascade;
drop table if exists agent.skills cascade;

create table if not exists library.skills (
    id text not null,
    owner_user_id text not null,
    name text not null,
    description text not null,
    package_id text,
    source_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (owner_user_id, id),
    unique (owner_user_id, name)
);

create table if not exists library.skill_packages (
    id text primary key,
    owner_user_id text not null,
    skill_id text not null,
    version text not null,
    hash text not null,
    manifest_json jsonb not null default '{}'::jsonb,
    skill_md text not null,
    files_json jsonb not null default '{}'::jsonb,
    source_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (owner_user_id, skill_id, hash),
    foreign key (owner_user_id, skill_id)
        references library.skills(owner_user_id, id)
        on delete cascade
);

alter table library.skills
    drop constraint if exists skills_package_fk,
    add constraint skills_package_fk
        foreign key (package_id)
        references library.skill_packages(id);

alter table if exists library.skills
    alter column description drop default;

alter table if exists library.skill_packages
    alter column version drop default;

create table if not exists agent.skill_bindings (
    id uuid primary key default gen_random_uuid(),
    agent_config_id text not null,
    skill_id text not null,
    package_id text not null
        references library.skill_packages(id),
    enabled boolean not null default true,
    created_at timestamptz not null default now(),
    unique (agent_config_id, skill_id)
);

grant usage on schema agent, library to service_role, authenticated, anon;
revoke all on library.skills, library.skill_packages from anon, authenticated;
grant select, insert, update, delete on library.skills, library.skill_packages to service_role;

alter table if exists agent.agent_configs
    add column if not exists owner_user_id text,
    add column if not exists agent_user_id text,
    add column if not exists runtime_json jsonb not null default '{}'::jsonb,
    add column if not exists compact_json jsonb not null default '{}'::jsonb,
    add column if not exists meta_json jsonb not null default '{}'::jsonb,
    add column if not exists mcp_json jsonb not null default '[]'::jsonb;

alter table if exists agent.agent_rules
    add column if not exists name text,
    add column if not exists enabled boolean not null default true;

alter table if exists agent.agent_sub_agents
    add column if not exists enabled boolean not null default true;

alter table if exists agent.agent_rules
    drop constraint if exists agent_rules_agent_config_id_fkey,
    add constraint agent_rules_agent_config_id_fkey
        foreign key (agent_config_id) references agent.agent_configs(id) on delete cascade;

alter table if exists agent.agent_sub_agents
    drop constraint if exists agent_sub_agents_agent_config_id_fkey,
    add constraint agent_sub_agents_agent_config_id_fkey
        foreign key (agent_config_id) references agent.agent_configs(id) on delete cascade;

alter table if exists agent.skill_bindings
    drop constraint if exists skill_bindings_agent_config_id_fkey,
    add constraint skill_bindings_agent_config_id_fkey
        foreign key (agent_config_id) references agent.agent_configs(id) on delete cascade;

do $$
begin
    if exists (
        select 1
        from agent.agent_configs
        where owner_user_id is null
           or btrim(owner_user_id) = ''
           or agent_user_id is null
           or btrim(agent_user_id) = ''
           or name is null
           or btrim(name) = ''
           or version is null
           or btrim(version) = ''
    ) then
        raise exception 'agent.agent_configs contains blank root identity before hard cut';
    end if;

    alter table agent.agent_configs
        drop constraint if exists agent_configs_owner_user_id_required_ck,
        add constraint agent_configs_owner_user_id_required_ck
            check (owner_user_id is not null and btrim(owner_user_id) <> ''),
        drop constraint if exists agent_configs_agent_user_id_required_ck,
        add constraint agent_configs_agent_user_id_required_ck
            check (agent_user_id is not null and btrim(agent_user_id) <> ''),
        drop constraint if exists agent_configs_name_required_ck,
        add constraint agent_configs_name_required_ck
            check (name is not null and btrim(name) <> ''),
        drop constraint if exists agent_configs_version_required_ck,
        add constraint agent_configs_version_required_ck
            check (version is not null and btrim(version) <> '');

    if exists (
        select 1
        from agent.agent_rules
        group by agent_config_id, name
        having count(*) > 1
    ) then
        raise exception 'agent.agent_rules contains duplicate (agent_config_id, name) rows before hard cut';
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conname = 'agent_rules_config_name_uq'
          and conrelid = 'agent.agent_rules'::regclass
    ) then
        alter table agent.agent_rules
            add constraint agent_rules_config_name_uq unique (agent_config_id, name);
    end if;

    if exists (
        select 1
        from agent.agent_sub_agents
        group by agent_config_id, name
        having count(*) > 1
    ) then
        raise exception 'agent.agent_sub_agents contains duplicate (agent_config_id, name) rows before hard cut';
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conname = 'agent_sub_agents_config_name_uq'
          and conrelid = 'agent.agent_sub_agents'::regclass
    ) then
        alter table agent.agent_sub_agents
            add constraint agent_sub_agents_config_name_uq unique (agent_config_id, name);
    end if;
end $$;

do $$
begin
    if exists (
        select 1
        from library.skills
        where description is null
           or btrim(description) = ''
    ) then
        raise exception 'library.skills.description must be present before hard cut';
    end if;

    alter table library.skills
        drop constraint if exists skills_description_required_ck,
        add constraint skills_description_required_ck
            check (description is not null and btrim(description) <> '');

    if exists (
        select 1
        from library.skills
        where jsonb_typeof(source_json) <> 'object'
    ) then
        raise exception 'library.skills.source_json must be a JSON object before hard cut';
    end if;
    if exists (
        select 1
        from library.skill_packages
        where version is null
           or btrim(version) = ''
    ) then
        raise exception 'library.skill_packages.version must be present before hard cut';
    end if;

    alter table library.skill_packages
        drop constraint if exists skill_packages_version_required_ck,
        add constraint skill_packages_version_required_ck
            check (version is not null and btrim(version) <> '');

    if exists (
        select 1
        from library.skill_packages
        where jsonb_typeof(manifest_json) <> 'object'
    ) then
        raise exception 'library.skill_packages.manifest_json must be a JSON object before hard cut';
    end if;
    if exists (
        select 1
        from library.skill_packages
        where jsonb_typeof(files_json) <> 'object'
    ) then
        raise exception 'library.skill_packages.files_json must be a JSON object before hard cut';
    end if;
    if exists (
        select 1
        from library.skill_packages package
        cross join lateral jsonb_each(package.files_json) as file(path, content)
        where jsonb_typeof(file.content) <> 'string'
    ) then
        raise exception 'library.skill_packages.files_json values must be strings before hard cut';
    end if;
    if exists (
        select 1
        from library.skill_packages package
        cross join lateral jsonb_each(package.files_json) as file(path, content)
        where btrim(file.path) = ''
           or file.path like '/%'
           or file.path like '%//%'
           or file.path like './%'
           or file.path like '%/./%'
           or file.path like '../%'
           or file.path like '%/../%'
           or position(chr(92) in file.path) > 0
    ) then
        raise exception 'library.skill_packages.files_json keys must be package-relative paths before hard cut';
    end if;
    if exists (
        select 1
        from library.skill_packages
        where jsonb_typeof(source_json) <> 'object'
    ) then
        raise exception 'library.skill_packages.source_json must be a JSON object before hard cut';
    end if;
    if exists (
        select 1
        from agent.agent_configs
        where jsonb_typeof(tools_json) <> 'array'
    ) then
        raise exception 'agent.agent_configs.tools_json must be a JSON array before hard cut';
    end if;
    if exists (
        select 1
        from agent.agent_configs
        where jsonb_typeof(runtime_json) <> 'object'
    ) then
        raise exception 'agent.agent_configs.runtime_json must be a JSON object before hard cut';
    end if;
    if exists (
        select 1
        from agent.agent_configs
        where jsonb_typeof(compact_json) <> 'object'
    ) then
        raise exception 'agent.agent_configs.compact_json must be a JSON object before hard cut';
    end if;
    if exists (
        select 1
        from agent.agent_configs
        where jsonb_typeof(meta_json) <> 'object'
    ) then
        raise exception 'agent.agent_configs.meta_json must be a JSON object before hard cut';
    end if;
    if exists (
        select 1
        from agent.agent_configs
        where jsonb_typeof(mcp_json) <> 'array'
    ) then
        raise exception 'agent.agent_configs.mcp_json must be a JSON array before hard cut';
    end if;
end $$;

create or replace function agent.save_agent_config(payload jsonb)
returns void
language plpgsql
as $$
declare
    config_id text := payload->>'id';
    owner_id text := payload->>'owner_user_id';
    child jsonb;
    child_skill_id text;
    child_package_id text;
begin
    if config_id is null or btrim(config_id) = '' then
        raise exception 'agent_config.id is required';
    end if;
    if owner_id is null or btrim(owner_id) = '' then
        raise exception 'agent_config.owner_user_id is required';
    end if;
    if payload->>'agent_user_id' is null or btrim(payload->>'agent_user_id') = '' then
        raise exception 'agent_config.agent_user_id is required';
    end if;
    if payload->>'name' is null or btrim(payload->>'name') = '' then
        raise exception 'agent_config.name is required';
    end if;
    if payload->>'version' is null or btrim(payload->>'version') = '' then
        raise exception 'agent_config.version is required';
    end if;
    if jsonb_typeof(coalesce(payload->'tools', '["*"]'::jsonb)) <> 'array' then
        raise exception 'agent_config.tools must be a JSON array';
    end if;
    if jsonb_typeof(coalesce(payload->'runtime_settings', '{}'::jsonb)) <> 'object' then
        raise exception 'agent_config.runtime_settings must be a JSON object';
    end if;
    if jsonb_typeof(coalesce(payload->'compact', '{}'::jsonb)) <> 'object' then
        raise exception 'agent_config.compact must be a JSON object';
    end if;
    if jsonb_typeof(coalesce(payload->'meta', '{}'::jsonb)) <> 'object' then
        raise exception 'agent_config.meta must be a JSON object';
    end if;
    if jsonb_typeof(coalesce(payload->'skills', '[]'::jsonb)) <> 'array' then
        raise exception 'agent_config.skills must be a JSON array';
    end if;
    if jsonb_typeof(coalesce(payload->'rules', '[]'::jsonb)) <> 'array' then
        raise exception 'agent_config.rules must be a JSON array';
    end if;
    if jsonb_typeof(coalesce(payload->'sub_agents', '[]'::jsonb)) <> 'array' then
        raise exception 'agent_config.sub_agents must be a JSON array';
    end if;
    if jsonb_typeof(coalesce(payload->'mcp_servers', '[]'::jsonb)) <> 'array' then
        raise exception 'agent_config.mcp_servers must be a JSON array';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'skills', '[]'::jsonb)) as skill_item(value)
        where skill_item.value ? 'disabled'
    ) then
        raise exception 'agent_config.skills child state must use enabled';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'mcp_servers', '[]'::jsonb)) as mcp_item(value)
        where mcp_item.value ? 'disabled'
    ) then
        raise exception 'agent_config.mcp_servers child state must use enabled';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'skills', '[]'::jsonb)) as skill_item(value)
        where skill_item.value ? 'enabled'
          and jsonb_typeof(skill_item.value->'enabled') <> 'boolean'
    ) then
        raise exception 'agent_config.skills child.enabled must be a JSON boolean';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'rules', '[]'::jsonb)) as rule_item(value)
        where rule_item.value ? 'enabled'
          and jsonb_typeof(rule_item.value->'enabled') <> 'boolean'
    ) then
        raise exception 'agent_config.rules child.enabled must be a JSON boolean';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'sub_agents', '[]'::jsonb)) as sub_agent_item(value)
        where sub_agent_item.value ? 'enabled'
          and jsonb_typeof(sub_agent_item.value->'enabled') <> 'boolean'
    ) then
        raise exception 'agent_config.sub_agents child.enabled must be a JSON boolean';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'mcp_servers', '[]'::jsonb)) as mcp_item(value)
        where mcp_item.value ? 'enabled'
          and jsonb_typeof(mcp_item.value->'enabled') <> 'boolean'
    ) then
        raise exception 'agent_config.mcp_servers child.enabled must be a JSON boolean';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'rules', '[]'::jsonb)) as rule_item(value)
        where btrim(coalesce(rule_item.value->>'name', '')) = ''
    ) then
        raise exception 'agent_config.rules child.name is required';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'sub_agents', '[]'::jsonb)) as sub_agent_item(value)
        where btrim(coalesce(sub_agent_item.value->>'name', '')) = ''
    ) then
        raise exception 'agent_config.sub_agents child.name is required';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'mcp_servers', '[]'::jsonb)) as mcp_item(value)
        where btrim(coalesce(mcp_item.value->>'name', '')) = ''
    ) then
        raise exception 'agent_config.mcp_servers child.name is required';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'sub_agents', '[]'::jsonb)) as sub_agent_item(value)
        where sub_agent_item.value ? 'tools'
          and jsonb_typeof(sub_agent_item.value->'tools') <> 'array'
    ) then
        raise exception 'agent_config.sub_agents child.tools must be a JSON array';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'mcp_servers', '[]'::jsonb)) as mcp_item(value)
        where mcp_item.value ? 'args'
          and jsonb_typeof(mcp_item.value->'args') <> 'array'
    ) then
        raise exception 'agent_config.mcp_servers child.args must be a JSON array';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'mcp_servers', '[]'::jsonb)) as mcp_item(value)
        where mcp_item.value ? 'env'
          and jsonb_typeof(mcp_item.value->'env') <> 'object'
    ) then
        raise exception 'agent_config.mcp_servers child.env must be a JSON object';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'rules', '[]'::jsonb)) as rule_item(value)
        group by rule_item.value->>'name'
        having count(*) > 1
    ) then
        raise exception 'agent_config.rules contains duplicate name';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'sub_agents', '[]'::jsonb)) as sub_agent_item(value)
        group by sub_agent_item.value->>'name'
        having count(*) > 1
    ) then
        raise exception 'agent_config.sub_agents contains duplicate name';
    end if;
    if exists (
        select 1
        from jsonb_array_elements(coalesce(payload->'mcp_servers', '[]'::jsonb)) as mcp_item(value)
        group by mcp_item.value->>'name'
        having count(*) > 1
    ) then
        raise exception 'agent_config.mcp_servers contains duplicate name';
    end if;

    insert into agent.agent_configs (
        id,
        owner_user_id,
        agent_user_id,
        name,
        description,
        model,
        tools_json,
        system_prompt,
        status,
        version,
        runtime_json,
        compact_json,
        meta_json,
        mcp_json
    )
    values (
        config_id,
        payload->>'owner_user_id',
        payload->>'agent_user_id',
        payload->>'name',
        coalesce(payload->>'description', ''),
        payload->>'model',
        coalesce(payload->'tools', '["*"]'::jsonb),
        coalesce(payload->>'system_prompt', ''),
        coalesce(payload->>'status', 'draft'),
        payload->>'version',
        coalesce(payload->'runtime_settings', '{}'::jsonb),
        coalesce(payload->'compact', '{}'::jsonb),
        coalesce(payload->'meta', '{}'::jsonb),
        coalesce(payload->'mcp_servers', '[]'::jsonb)
    )
    on conflict (id) do update set
        owner_user_id = excluded.owner_user_id,
        agent_user_id = excluded.agent_user_id,
        name = excluded.name,
        description = excluded.description,
        model = excluded.model,
        tools_json = excluded.tools_json,
        system_prompt = excluded.system_prompt,
        status = excluded.status,
        version = excluded.version,
        runtime_json = excluded.runtime_json,
        compact_json = excluded.compact_json,
        meta_json = excluded.meta_json,
        mcp_json = excluded.mcp_json;

    delete from agent.skill_bindings where agent_config_id = config_id;
    delete from agent.agent_rules where agent_config_id = config_id;
    delete from agent.agent_sub_agents where agent_config_id = config_id;

    for child in select * from jsonb_array_elements(coalesce(payload->'skills', '[]'::jsonb)) loop
        child_skill_id := nullif(child->>'skill_id', '');
        child_package_id := nullif(child->>'package_id', '');
        if child_skill_id is null then
            raise exception 'agent_config.skills child.skill_id is required';
        end if;
        if child_package_id is null then
            raise exception 'agent_config.skills child.package_id is required';
        end if;
        if child_skill_id is not null and not exists (
            select 1
            from library.skills
            where owner_user_id = owner_id
              and id = child_skill_id
        ) then
            raise exception 'agent_skill.skill_id does not belong to owner: %', child_skill_id;
        end if;
        if child_package_id is not null and not exists (
            select 1
            from library.skill_packages
            where owner_user_id = owner_id
              and id = child_package_id
              and (child_skill_id is null or skill_id = child_skill_id)
        ) then
            raise exception 'agent_skill.package_id does not belong to owner: %', child_package_id;
        end if;

        insert into agent.skill_bindings (id, agent_config_id, skill_id, package_id, enabled)
        values (coalesce(nullif(child->>'id', '')::uuid, gen_random_uuid()), config_id, child_skill_id, child_package_id, coalesce((child->>'enabled')::boolean, true));
    end loop;

    for child in select * from jsonb_array_elements(coalesce(payload->'rules', '[]'::jsonb)) loop
        insert into agent.agent_rules (id, agent_config_id, filename, name, content, enabled)
        values (
            coalesce(nullif(child->>'id', ''), gen_random_uuid()::text),
            config_id,
            child->>'name',
            child->>'name',
            coalesce(child->>'content', ''),
            coalesce((child->>'enabled')::boolean, true)
        );
    end loop;

    for child in select * from jsonb_array_elements(coalesce(payload->'sub_agents', '[]'::jsonb)) loop
        insert into agent.agent_sub_agents (
            id, agent_config_id, name, description, model, tools_json, system_prompt, enabled
        )
        values (
            coalesce(nullif(child->>'id', ''), gen_random_uuid()::text),
            config_id,
            child->>'name',
            coalesce(child->>'description', ''),
            child->>'model',
            coalesce(child->'tools', '[]'::jsonb),
            coalesce(child->>'system_prompt', ''),
            coalesce((child->>'enabled')::boolean, true)
        );
    end loop;
end;
$$;

revoke all on function agent.save_agent_config(jsonb) from public, anon, authenticated;
grant execute on function agent.save_agent_config(jsonb) to service_role;

revoke all on table
    agent.agent_configs,
    agent.skill_bindings,
    agent.agent_rules,
    agent.agent_sub_agents
from anon, authenticated;

grant select, insert, update, delete on table
    agent.agent_configs,
    agent.skill_bindings,
    agent.agent_rules,
    agent.agent_sub_agents
to service_role;

notify pgrst, 'reload schema';
