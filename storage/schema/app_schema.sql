-- Mycel app runtime schema baseline.
-- Provenance: generated from the 2026-05-07 production/full Mycel app-owned schema dump
-- stored out of repo at ~/share/ops/mycel-schema-diff-20260507T032824Z/prod-mycel-schemas.sql.
-- This file is the executable current-runtime baseline for empty app databases.
-- It is not a local-only schema fork; local deploy profiles must use this same baseline.
-- Review note: production/live shape is evidence, not design perfection. Known design/live
-- drift is tracked in notes/2026-05-07-schema-init-truth-inventory.html and
-- mycel-db-design/program/doc/core/schema-init-executable-path-inventory-2026-05-07.md.

--
-- PostgreSQL database dump
--

-- Dumped from database version 15.8
-- Dumped by pg_dump version 15.8

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: agent; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA agent;


--
-- Name: chat; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA chat;


--
-- Name: container; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA container;


--
-- Name: identity; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA identity;


--
-- Name: library; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA library;


--
-- Name: observability; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA observability;


--
-- Name: save_agent_config(jsonb); Type: FUNCTION; Schema: agent; Owner: -
--

CREATE FUNCTION agent.save_agent_config(payload jsonb) RETURNS void
    LANGUAGE plpgsql
    AS $$
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


--
-- Name: increment_chat_message_seq(text); Type: FUNCTION; Schema: chat; Owner: -
--

CREATE FUNCTION chat.increment_chat_message_seq(p_chat_id text) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE v_seq bigint;
BEGIN
    UPDATE chat.chats SET next_message_seq = next_message_seq + 1
    WHERE id = p_chat_id
    RETURNING next_message_seq INTO v_seq;
    IF v_seq IS NULL THEN
        RAISE EXCEPTION 'chat not found: %', p_chat_id;
    END IF;
    RETURN v_seq;
END;
$$;


--
-- Name: increment_user_thread_seq(text); Type: FUNCTION; Schema: identity; Owner: -
--

CREATE FUNCTION identity.increment_user_thread_seq(p_user_id text) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE v_seq bigint;
BEGIN
    UPDATE identity.users SET next_thread_seq = next_thread_seq + 1
    WHERE id = p_user_id
    RETURNING next_thread_seq INTO v_seq;
    IF v_seq IS NULL THEN
        RAISE EXCEPTION 'user not found: %', p_user_id;
    END IF;
    RETURN v_seq;
END;
$$;


--
-- Name: next_mycel_id(); Type: FUNCTION; Schema: identity; Owner: -
--

CREATE FUNCTION identity.next_mycel_id() RETURNS integer
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'identity', 'public'
    AS $$
  select nextval('identity.mycel_id_seq')::integer
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agent_configs; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.agent_configs (
    id text NOT NULL,
    agent_user_id text NOT NULL,
    owner_user_id text NOT NULL,
    name text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    model text,
    tools_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    system_prompt text DEFAULT ''::text NOT NULL,
    mcp_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    runtime_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    version text DEFAULT '0.1.0'::text NOT NULL,
    meta_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    compact_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT agent_configs_agent_user_id_required_ck CHECK (((agent_user_id IS NOT NULL) AND (btrim(agent_user_id) <> ''::text))),
    CONSTRAINT agent_configs_compact_json_object_ck CHECK ((jsonb_typeof(compact_json) = 'object'::text)),
    CONSTRAINT agent_configs_mcp_json_array_ck CHECK ((jsonb_typeof(mcp_json) = 'array'::text)),
    CONSTRAINT agent_configs_meta_json_object_ck CHECK ((jsonb_typeof(meta_json) = 'object'::text)),
    CONSTRAINT agent_configs_name_required_ck CHECK (((name IS NOT NULL) AND (btrim(name) <> ''::text))),
    CONSTRAINT agent_configs_owner_user_id_required_ck CHECK (((owner_user_id IS NOT NULL) AND (btrim(owner_user_id) <> ''::text))),
    CONSTRAINT agent_configs_runtime_json_object_ck CHECK ((jsonb_typeof(runtime_json) = 'object'::text)),
    CONSTRAINT agent_configs_status_chk CHECK ((status = ANY (ARRAY['draft'::text, 'active'::text, 'inactive'::text]))),
    CONSTRAINT agent_configs_tools_json_array_ck CHECK ((jsonb_typeof(tools_json) = 'array'::text)),
    CONSTRAINT agent_configs_version_required_ck CHECK (((version IS NOT NULL) AND (btrim(version) <> ''::text)))
);


--
-- Name: agent_rules; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.agent_rules (
    id text NOT NULL,
    agent_config_id text NOT NULL,
    filename text NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    name text,
    enabled boolean DEFAULT true NOT NULL
);


--
-- Name: agent_sub_agents; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.agent_sub_agents (
    id text NOT NULL,
    agent_config_id text NOT NULL,
    name text NOT NULL,
    description text,
    model text,
    tools_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    system_prompt text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    enabled boolean DEFAULT true NOT NULL
);


--
-- Name: checkpoint_blobs; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.checkpoint_blobs (
    thread_id text NOT NULL,
    checkpoint_ns text DEFAULT ''::text NOT NULL,
    channel text NOT NULL,
    version text NOT NULL,
    type text NOT NULL,
    blob bytea
);


--
-- Name: checkpoint_migrations; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.checkpoint_migrations (
    v integer NOT NULL
);


--
-- Name: checkpoint_writes; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.checkpoint_writes (
    thread_id text NOT NULL,
    checkpoint_ns text DEFAULT ''::text NOT NULL,
    checkpoint_id text NOT NULL,
    task_id text NOT NULL,
    idx integer NOT NULL,
    channel text NOT NULL,
    type text,
    blob bytea NOT NULL,
    task_path text DEFAULT ''::text NOT NULL
);


--
-- Name: checkpoints; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.checkpoints (
    thread_id text NOT NULL,
    checkpoint_ns text DEFAULT ''::text NOT NULL,
    checkpoint_id text NOT NULL,
    parent_checkpoint_id text,
    type text,
    checkpoint jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: file_operations; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.file_operations (
    id text NOT NULL,
    thread_id text NOT NULL,
    checkpoint_id text NOT NULL,
    "timestamp" double precision NOT NULL,
    operation_type text NOT NULL,
    file_path text NOT NULL,
    before_content text,
    after_content text NOT NULL,
    changes jsonb,
    status text DEFAULT 'applied'::text
);


--
-- Name: message_queue; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.message_queue (
    id bigint NOT NULL,
    thread_id text NOT NULL,
    content text NOT NULL,
    notification_type text DEFAULT 'steer'::text NOT NULL,
    source text,
    sender_user_id text,
    sender_name text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: message_queue_id_seq; Type: SEQUENCE; Schema: agent; Owner: -
--

CREATE SEQUENCE agent.message_queue_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: message_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: agent; Owner: -
--

ALTER SEQUENCE agent.message_queue_id_seq OWNED BY agent.message_queue.id;


--
-- Name: run_events; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.run_events (
    seq bigint NOT NULL,
    thread_id text NOT NULL,
    run_id text NOT NULL,
    event_type text NOT NULL,
    data text NOT NULL,
    message_id text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: run_events_seq_seq; Type: SEQUENCE; Schema: agent; Owner: -
--

CREATE SEQUENCE agent.run_events_seq_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: run_events_seq_seq; Type: SEQUENCE OWNED BY; Schema: agent; Owner: -
--

ALTER SEQUENCE agent.run_events_seq_seq OWNED BY agent.run_events.seq;


--
-- Name: schedule_runs; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.schedule_runs (
    id text NOT NULL,
    schedule_id text NOT NULL,
    owner_user_id text NOT NULL,
    agent_user_id text NOT NULL,
    thread_id text,
    status text DEFAULT 'queued'::text NOT NULL,
    triggered_by text NOT NULL,
    scheduled_for timestamp with time zone,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    input_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    output_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT schedule_runs_status_chk CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'succeeded'::text, 'failed'::text, 'cancelled'::text]))),
    CONSTRAINT schedule_runs_triggered_by_chk CHECK ((triggered_by = ANY (ARRAY['scheduler'::text, 'manual'::text])))
);


--
-- Name: schedules; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.schedules (
    id text NOT NULL,
    owner_user_id text NOT NULL,
    agent_user_id text NOT NULL,
    target_thread_id text,
    create_thread_on_run boolean DEFAULT false NOT NULL,
    cron_expression text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    instruction_template text NOT NULL,
    timezone text DEFAULT 'UTC'::text NOT NULL,
    last_run_at timestamp with time zone,
    next_run_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT schedules_cron_expression_chk CHECK ((btrim(cron_expression) <> ''::text)),
    CONSTRAINT schedules_instruction_template_chk CHECK ((btrim(instruction_template) <> ''::text)),
    CONSTRAINT schedules_target_chk CHECK (((target_thread_id IS NOT NULL) OR create_thread_on_run)),
    CONSTRAINT schedules_timezone_chk CHECK ((btrim(timezone) <> ''::text))
);


--
-- Name: skill_bindings; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.skill_bindings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    agent_config_id text NOT NULL,
    skill_id text NOT NULL,
    package_id text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: summaries; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.summaries (
    summary_id text NOT NULL,
    thread_id text DEFAULT ''::text NOT NULL,
    summary_text text DEFAULT ''::text NOT NULL,
    compact_up_to_index integer DEFAULT 0 NOT NULL,
    compacted_at integer DEFAULT 0 NOT NULL,
    is_split_turn boolean DEFAULT false,
    split_turn_prefix text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: thread_tasks; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.thread_tasks (
    thread_id text NOT NULL,
    task_id text NOT NULL,
    subject text NOT NULL,
    description text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    active_form text,
    owner text,
    blocks jsonb DEFAULT '[]'::jsonb NOT NULL,
    blocked_by jsonb DEFAULT '[]'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT thread_tasks_status_chk CHECK ((status = ANY (ARRAY['pending'::text, 'in_progress'::text, 'completed'::text])))
);


--
-- Name: threads; Type: TABLE; Schema: agent; Owner: -
--

CREATE TABLE agent.threads (
    id text NOT NULL,
    agent_user_id text NOT NULL,
    owner_user_id text NOT NULL,
    current_workspace_id text,
    model text,
    cwd text,
    status text DEFAULT 'active'::text NOT NULL,
    run_status text DEFAULT 'idle'::text NOT NULL,
    is_main boolean DEFAULT false NOT NULL,
    branch_index integer DEFAULT 0 NOT NULL,
    last_active_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    sandbox_type text NOT NULL,
    CONSTRAINT threads_run_status_chk CHECK ((run_status = ANY (ARRAY['idle'::text, 'running'::text, 'paused'::text, 'error'::text]))),
    CONSTRAINT threads_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'archived'::text])))
);


--
-- Name: chat_members; Type: TABLE; Schema: chat; Owner: -
--

CREATE TABLE chat.chat_members (
    chat_id text NOT NULL,
    user_id text NOT NULL,
    role text DEFAULT 'member'::text NOT NULL,
    joined_at double precision NOT NULL,
    last_read_seq bigint DEFAULT 0 NOT NULL,
    muted integer DEFAULT 0 NOT NULL,
    mute_until double precision,
    version integer DEFAULT 0 NOT NULL
);


--
-- Name: chats; Type: TABLE; Schema: chat; Owner: -
--

CREATE TABLE chat.chats (
    id text NOT NULL,
    type text NOT NULL,
    title text,
    status text DEFAULT 'active'::text NOT NULL,
    created_by_user_id text NOT NULL,
    next_message_seq bigint DEFAULT 0 NOT NULL,
    created_at double precision NOT NULL,
    updated_at double precision,
    CONSTRAINT chats_type_check CHECK ((type = ANY (ARRAY['direct'::text, 'group'::text])))
);


--
-- Name: contacts; Type: TABLE; Schema: chat; Owner: -
--

CREATE TABLE chat.contacts (
    source_user_id text NOT NULL,
    target_user_id text NOT NULL,
    kind text DEFAULT 'normal'::text NOT NULL,
    state text DEFAULT 'active'::text NOT NULL,
    muted integer DEFAULT 0 NOT NULL,
    blocked integer DEFAULT 0 NOT NULL,
    snapshot_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at double precision NOT NULL,
    updated_at double precision,
    version integer DEFAULT 0 NOT NULL
);


--
-- Name: join_requests; Type: TABLE; Schema: chat; Owner: -
--

CREATE TABLE chat.join_requests (
    id text NOT NULL,
    chat_id text NOT NULL,
    requester_user_id text NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    message text,
    decided_by_user_id text,
    decided_at double precision,
    created_at double precision NOT NULL,
    updated_at double precision,
    CONSTRAINT join_requests_state_check CHECK ((state = ANY (ARRAY['pending'::text, 'approved'::text, 'rejected'::text])))
);


--
-- Name: messages; Type: TABLE; Schema: chat; Owner: -
--

CREATE TABLE chat.messages (
    id text NOT NULL,
    chat_id text NOT NULL,
    seq bigint NOT NULL,
    sender_user_id text NOT NULL,
    content text NOT NULL,
    content_type text DEFAULT 'text/plain'::text NOT NULL,
    message_type text DEFAULT 'text'::text NOT NULL,
    signal text,
    mentions_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    reply_to_message_id text,
    ai_metadata_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at double precision NOT NULL,
    delivered_at double precision,
    edited_at double precision,
    retracted_at double precision,
    deleted_at double precision,
    delivery_scope text DEFAULT 'broadcast'::text NOT NULL,
    addressed_to_user_ids_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    CONSTRAINT messages_delivery_scope_check CHECK ((delivery_scope = ANY (ARRAY['broadcast'::text, 'addressed'::text])))
);


--
-- Name: relationships; Type: TABLE; Schema: chat; Owner: -
--

CREATE TABLE chat.relationships (
    user_low text NOT NULL,
    user_high text NOT NULL,
    kind text NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    initiator_user_id text NOT NULL,
    created_at double precision NOT NULL,
    updated_at double precision,
    version integer DEFAULT 0 NOT NULL,
    message text,
    CONSTRAINT relationships_check CHECK ((user_low <> user_high))
);


--
-- Name: tasks; Type: TABLE; Schema: chat; Owner: -
--

CREATE TABLE chat.tasks (
    chat_id text NOT NULL,
    task_id text NOT NULL,
    subject text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    active_form text,
    owner_user_id text,
    blocks_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    blocked_by_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    metadata_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at double precision NOT NULL,
    updated_at double precision
);


--
-- Name: workflow_events; Type: TABLE; Schema: chat; Owner: -
--

CREATE TABLE chat.workflow_events (
    chat_id text NOT NULL,
    event_id text NOT NULL,
    kind text NOT NULL,
    state text DEFAULT 'open'::text NOT NULL,
    resource_refs_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    requested_by_user_id text,
    decision_states_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    rationales_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    final_state_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at double precision NOT NULL,
    updated_at double precision,
    settled_at double precision
);


--
-- Name: workflow_state; Type: TABLE; Schema: chat; Owner: -
--

CREATE TABLE chat.workflow_state (
    chat_id text NOT NULL,
    kind text NOT NULL,
    state text DEFAULT 'active'::text NOT NULL,
    config_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_by_user_id text,
    created_at double precision NOT NULL,
    updated_at double precision
);


--
-- Name: abstract_terminals; Type: TABLE; Schema: container; Owner: -
--

CREATE TABLE container.abstract_terminals (
    terminal_id text NOT NULL,
    thread_id text NOT NULL,
    sandbox_runtime_id text NOT NULL,
    cwd text NOT NULL,
    env_delta_json text DEFAULT '{}'::text NOT NULL,
    state_version integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: chat_sessions; Type: TABLE; Schema: container; Owner: -
--

CREATE TABLE container.chat_sessions (
    chat_session_id text NOT NULL,
    thread_id text NOT NULL,
    terminal_id text NOT NULL,
    sandbox_runtime_id text NOT NULL,
    runtime_id text,
    status text DEFAULT 'active'::text NOT NULL,
    idle_ttl_sec integer NOT NULL,
    max_duration_sec integer NOT NULL,
    budget_json text,
    started_at timestamp with time zone NOT NULL,
    last_active_at timestamp with time zone NOT NULL,
    ended_at timestamp with time zone,
    close_reason text
);


--
-- Name: resource_snapshots; Type: TABLE; Schema: container; Owner: -
--

CREATE TABLE container.resource_snapshots (
    sandbox_id text NOT NULL,
    owner_user_id text NOT NULL,
    provider_name text NOT NULL,
    observed_state text NOT NULL,
    probe_mode text NOT NULL,
    cpu_used double precision,
    cpu_limit double precision,
    memory_used_mb double precision,
    memory_total_mb double precision,
    disk_used_gb double precision,
    disk_total_gb double precision,
    network_rx_kbps double precision,
    network_tx_kbps double precision,
    probe_error text,
    collected_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT resource_snapshots_observed_state_chk CHECK ((observed_state = ANY (ARRAY['running'::text, 'stopped'::text, 'detached'::text, 'error'::text]))),
    CONSTRAINT resource_snapshots_probe_mode_chk CHECK ((probe_mode = ANY (ARRAY['running_runtime'::text, 'non_running_sdk'::text])))
);


--
-- Name: sandbox_recipes; Type: TABLE; Schema: container; Owner: -
--

CREATE TABLE container.sandbox_recipes (
    owner_user_id text NOT NULL,
    recipe_id text NOT NULL,
    kind text NOT NULL,
    provider_type text NOT NULL,
    data_json text NOT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL
);


--
-- Name: sandboxes; Type: TABLE; Schema: container; Owner: -
--

CREATE TABLE container.sandboxes (
    id text NOT NULL,
    owner_user_id text NOT NULL,
    provider_name text NOT NULL,
    provider_env_id text,
    sandbox_template_id text,
    desired_state text NOT NULL,
    observed_state text NOT NULL,
    status text NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    last_error text,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: terminal_command_chunks; Type: TABLE; Schema: container; Owner: -
--

CREATE TABLE container.terminal_command_chunks (
    chunk_id bigint NOT NULL,
    command_id text NOT NULL,
    stream text NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT terminal_command_chunks_stream_check CHECK ((stream = ANY (ARRAY['stdout'::text, 'stderr'::text])))
);


--
-- Name: terminal_command_chunks_chunk_id_seq; Type: SEQUENCE; Schema: container; Owner: -
--

CREATE SEQUENCE container.terminal_command_chunks_chunk_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: terminal_command_chunks_chunk_id_seq; Type: SEQUENCE OWNED BY; Schema: container; Owner: -
--

ALTER SEQUENCE container.terminal_command_chunks_chunk_id_seq OWNED BY container.terminal_command_chunks.chunk_id;


--
-- Name: terminal_commands; Type: TABLE; Schema: container; Owner: -
--

CREATE TABLE container.terminal_commands (
    command_id text NOT NULL,
    terminal_id text NOT NULL,
    chat_session_id text,
    command_line text NOT NULL,
    cwd text NOT NULL,
    status text NOT NULL,
    stdout text DEFAULT ''::text NOT NULL,
    stderr text DEFAULT ''::text NOT NULL,
    exit_code integer,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone
);


--
-- Name: thread_terminal_pointers; Type: TABLE; Schema: container; Owner: -
--

CREATE TABLE container.thread_terminal_pointers (
    thread_id text NOT NULL,
    active_terminal_id text NOT NULL,
    default_terminal_id text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: workspaces; Type: TABLE; Schema: container; Owner: -
--

CREATE TABLE container.workspaces (
    id text NOT NULL,
    sandbox_id text NOT NULL,
    owner_user_id text NOT NULL,
    workspace_path text NOT NULL,
    name text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: invite_codes; Type: TABLE; Schema: identity; Owner: -
--

CREATE TABLE identity.invite_codes (
    code text NOT NULL,
    created_by text,
    used_by text,
    used_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: mycel_id_seq; Type: SEQUENCE; Schema: identity; Owner: -
--

CREATE SEQUENCE identity.mycel_id_seq
    START WITH 10000
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_settings; Type: TABLE; Schema: identity; Owner: -
--

CREATE TABLE identity.user_settings (
    user_id text NOT NULL,
    default_workspace text,
    recent_workspaces jsonb DEFAULT '[]'::jsonb,
    default_model text DEFAULT 'leon:large'::text,
    updated_at timestamp with time zone DEFAULT now(),
    models_config jsonb,
    observation_config jsonb,
    sandbox_configs jsonb,
    account_resource_limits jsonb
);


--
-- Name: users; Type: TABLE; Schema: identity; Owner: -
--

CREATE TABLE identity.users (
    id text NOT NULL,
    type text NOT NULL,
    display_name text NOT NULL,
    avatar text,
    bio text,
    owner_user_id text,
    agent_config_id text,
    next_thread_seq bigint DEFAULT 0 NOT NULL,
    created_at double precision NOT NULL,
    updated_at double precision,
    email text,
    mycel_id integer,
    created_by_user_id text,
    is_guest boolean DEFAULT false NOT NULL,
    CONSTRAINT users_type_check CHECK ((type = ANY (ARRAY['human'::text, 'agent'::text, 'external'::text])))
);


--
-- Name: skill_packages; Type: TABLE; Schema: library; Owner: -
--

CREATE TABLE library.skill_packages (
    id text NOT NULL,
    owner_user_id text NOT NULL,
    skill_id text NOT NULL,
    version text NOT NULL,
    hash text NOT NULL,
    manifest_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    skill_md text NOT NULL,
    files_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT skill_packages_files_json_object_ck CHECK ((jsonb_typeof(files_json) = 'object'::text)),
    CONSTRAINT skill_packages_hash_format_ck CHECK ((hash ~~ 'sha256:%'::text)),
    CONSTRAINT skill_packages_id_not_hash_ck CHECK ((id <> SUBSTRING(hash FROM 8))),
    CONSTRAINT skill_packages_manifest_json_object_ck CHECK ((jsonb_typeof(manifest_json) = 'object'::text)),
    CONSTRAINT skill_packages_source_json_object_ck CHECK ((jsonb_typeof(source_json) = 'object'::text)),
    CONSTRAINT skill_packages_version_required_ck CHECK (((version IS NOT NULL) AND (btrim(version) <> ''::text)))
);


--
-- Name: skills; Type: TABLE; Schema: library; Owner: -
--

CREATE TABLE library.skills (
    id text NOT NULL,
    owner_user_id text NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    package_id text,
    source_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT skills_description_required_ck CHECK (((description IS NOT NULL) AND (btrim(description) <> ''::text))),
    CONSTRAINT skills_source_json_object_ck CHECK ((jsonb_typeof(source_json) = 'object'::text))
);


--
-- Name: eval_llm_calls; Type: TABLE; Schema: observability; Owner: -
--

CREATE TABLE observability.eval_llm_calls (
    id text NOT NULL,
    run_id text NOT NULL,
    parent_run_id text,
    duration_ms double precision DEFAULT 0,
    input_tokens integer DEFAULT 0,
    output_tokens integer DEFAULT 0,
    total_tokens integer DEFAULT 0,
    cost_usd double precision DEFAULT 0,
    model_name text DEFAULT ''::text
);


--
-- Name: eval_metrics; Type: TABLE; Schema: observability; Owner: -
--

CREATE TABLE observability.eval_metrics (
    id text NOT NULL,
    run_id text NOT NULL,
    tier text NOT NULL,
    "timestamp" text,
    metrics_json text
);


--
-- Name: eval_runs; Type: TABLE; Schema: observability; Owner: -
--

CREATE TABLE observability.eval_runs (
    id text NOT NULL,
    thread_id text NOT NULL,
    started_at text,
    finished_at text,
    user_message text,
    final_response text,
    status text DEFAULT 'completed'::text,
    run_tree_json text,
    trajectory_json text
);


--
-- Name: eval_tool_calls; Type: TABLE; Schema: observability; Owner: -
--

CREATE TABLE observability.eval_tool_calls (
    id text NOT NULL,
    run_id text NOT NULL,
    parent_run_id text,
    tool_name text NOT NULL,
    tool_call_id text DEFAULT ''::text,
    duration_ms double precision DEFAULT 0,
    success boolean DEFAULT true,
    error text,
    args_summary text DEFAULT ''::text,
    result_summary text DEFAULT ''::text
);


--
-- Name: evaluation_batch_runs; Type: TABLE; Schema: observability; Owner: -
--

CREATE TABLE observability.evaluation_batch_runs (
    batch_run_id text NOT NULL,
    batch_id text NOT NULL,
    item_key text NOT NULL,
    scenario_id text NOT NULL,
    status text NOT NULL,
    thread_id text,
    eval_run_id text,
    started_at text,
    finished_at text,
    summary_json jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: evaluation_batches; Type: TABLE; Schema: observability; Owner: -
--

CREATE TABLE observability.evaluation_batches (
    batch_id text NOT NULL,
    kind text NOT NULL,
    submitted_by_user_id text NOT NULL,
    agent_user_id text NOT NULL,
    config_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text NOT NULL,
    created_at text,
    updated_at text,
    summary_json jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: monitor_operations; Type: TABLE; Schema: observability; Owner: -
--

CREATE TABLE observability.monitor_operations (
    operation_id text NOT NULL,
    kind text NOT NULL,
    target_type text NOT NULL,
    target_id text NOT NULL,
    status text NOT NULL,
    requested_at text NOT NULL,
    updated_at text NOT NULL,
    payload_json text NOT NULL
);


--
-- Name: provider_events; Type: TABLE; Schema: observability; Owner: -
--

CREATE TABLE observability.provider_events (
    event_id bigint NOT NULL,
    provider_name text NOT NULL,
    instance_id text NOT NULL,
    event_type text NOT NULL,
    payload_json text,
    created_at timestamp with time zone NOT NULL,
    matched_sandbox_id text,
    matched_runtime_handle text
);


--
-- Name: provider_events_event_id_seq; Type: SEQUENCE; Schema: observability; Owner: -
--

CREATE SEQUENCE observability.provider_events_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provider_events_event_id_seq; Type: SEQUENCE OWNED BY; Schema: observability; Owner: -
--

ALTER SEQUENCE observability.provider_events_event_id_seq OWNED BY observability.provider_events.event_id;


--
-- Name: message_queue id; Type: DEFAULT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.message_queue ALTER COLUMN id SET DEFAULT nextval('agent.message_queue_id_seq'::regclass);


--
-- Name: run_events seq; Type: DEFAULT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.run_events ALTER COLUMN seq SET DEFAULT nextval('agent.run_events_seq_seq'::regclass);


--
-- Name: terminal_command_chunks chunk_id; Type: DEFAULT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.terminal_command_chunks ALTER COLUMN chunk_id SET DEFAULT nextval('container.terminal_command_chunks_chunk_id_seq'::regclass);


--
-- Name: provider_events event_id; Type: DEFAULT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.provider_events ALTER COLUMN event_id SET DEFAULT nextval('observability.provider_events_event_id_seq'::regclass);


--
-- Name: agent_configs agent_configs_agent_user_id_key; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_configs
    ADD CONSTRAINT agent_configs_agent_user_id_key UNIQUE (agent_user_id);


--
-- Name: agent_configs agent_configs_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_configs
    ADD CONSTRAINT agent_configs_pkey PRIMARY KEY (id);


--
-- Name: agent_rules agent_rules_config_filename_uq; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_rules
    ADD CONSTRAINT agent_rules_config_filename_uq UNIQUE (agent_config_id, filename);


--
-- Name: agent_rules agent_rules_config_name_uq; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_rules
    ADD CONSTRAINT agent_rules_config_name_uq UNIQUE (agent_config_id, name);


--
-- Name: agent_rules agent_rules_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_rules
    ADD CONSTRAINT agent_rules_pkey PRIMARY KEY (id);


--
-- Name: agent_sub_agents agent_sub_agents_config_name_uq; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_sub_agents
    ADD CONSTRAINT agent_sub_agents_config_name_uq UNIQUE (agent_config_id, name);


--
-- Name: agent_sub_agents agent_sub_agents_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_sub_agents
    ADD CONSTRAINT agent_sub_agents_pkey PRIMARY KEY (id);


--
-- Name: checkpoint_blobs checkpoint_blobs_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.checkpoint_blobs
    ADD CONSTRAINT checkpoint_blobs_pkey PRIMARY KEY (thread_id, checkpoint_ns, channel, version);


--
-- Name: checkpoint_migrations checkpoint_migrations_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.checkpoint_migrations
    ADD CONSTRAINT checkpoint_migrations_pkey PRIMARY KEY (v);


--
-- Name: checkpoint_writes checkpoint_writes_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.checkpoint_writes
    ADD CONSTRAINT checkpoint_writes_pkey PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx);


--
-- Name: checkpoints checkpoints_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.checkpoints
    ADD CONSTRAINT checkpoints_pkey PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id);


--
-- Name: file_operations file_operations_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.file_operations
    ADD CONSTRAINT file_operations_pkey PRIMARY KEY (id);


--
-- Name: message_queue message_queue_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.message_queue
    ADD CONSTRAINT message_queue_pkey PRIMARY KEY (id);


--
-- Name: run_events run_events_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.run_events
    ADD CONSTRAINT run_events_pkey PRIMARY KEY (seq);


--
-- Name: schedule_runs schedule_runs_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.schedule_runs
    ADD CONSTRAINT schedule_runs_pkey PRIMARY KEY (id);


--
-- Name: schedules schedules_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.schedules
    ADD CONSTRAINT schedules_pkey PRIMARY KEY (id);


--
-- Name: skill_bindings skill_bindings_agent_config_id_skill_id_key; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.skill_bindings
    ADD CONSTRAINT skill_bindings_agent_config_id_skill_id_key UNIQUE (agent_config_id, skill_id);


--
-- Name: skill_bindings skill_bindings_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.skill_bindings
    ADD CONSTRAINT skill_bindings_pkey PRIMARY KEY (id);


--
-- Name: summaries summaries_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.summaries
    ADD CONSTRAINT summaries_pkey PRIMARY KEY (summary_id);


--
-- Name: thread_tasks thread_tasks_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.thread_tasks
    ADD CONSTRAINT thread_tasks_pkey PRIMARY KEY (thread_id, task_id);


--
-- Name: threads threads_agent_branch_uq; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.threads
    ADD CONSTRAINT threads_agent_branch_uq UNIQUE (agent_user_id, branch_index);


--
-- Name: threads threads_pkey; Type: CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.threads
    ADD CONSTRAINT threads_pkey PRIMARY KEY (id);


--
-- Name: chat_members chat_members_pkey; Type: CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.chat_members
    ADD CONSTRAINT chat_members_pkey PRIMARY KEY (chat_id, user_id);


--
-- Name: chats chats_pkey; Type: CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.chats
    ADD CONSTRAINT chats_pkey PRIMARY KEY (id);


--
-- Name: contacts contacts_pkey; Type: CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.contacts
    ADD CONSTRAINT contacts_pkey PRIMARY KEY (source_user_id, target_user_id);


--
-- Name: join_requests join_requests_chat_id_requester_user_id_key; Type: CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.join_requests
    ADD CONSTRAINT join_requests_chat_id_requester_user_id_key UNIQUE (chat_id, requester_user_id);


--
-- Name: join_requests join_requests_pkey; Type: CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.join_requests
    ADD CONSTRAINT join_requests_pkey PRIMARY KEY (id);


--
-- Name: messages messages_chat_id_seq_key; Type: CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.messages
    ADD CONSTRAINT messages_chat_id_seq_key UNIQUE (chat_id, seq);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: relationships relationships_pkey; Type: CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.relationships
    ADD CONSTRAINT relationships_pkey PRIMARY KEY (user_low, user_high, kind);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (chat_id, task_id);


--
-- Name: workflow_events workflow_events_pkey; Type: CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.workflow_events
    ADD CONSTRAINT workflow_events_pkey PRIMARY KEY (chat_id, event_id);


--
-- Name: workflow_state workflow_state_pkey; Type: CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.workflow_state
    ADD CONSTRAINT workflow_state_pkey PRIMARY KEY (chat_id);


--
-- Name: abstract_terminals abstract_terminals_pkey; Type: CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.abstract_terminals
    ADD CONSTRAINT abstract_terminals_pkey PRIMARY KEY (terminal_id);


--
-- Name: chat_sessions chat_sessions_pkey; Type: CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.chat_sessions
    ADD CONSTRAINT chat_sessions_pkey PRIMARY KEY (chat_session_id);


--
-- Name: resource_snapshots resource_snapshots_pkey; Type: CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.resource_snapshots
    ADD CONSTRAINT resource_snapshots_pkey PRIMARY KEY (sandbox_id);


--
-- Name: sandbox_recipes sandbox_recipes_pkey; Type: CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.sandbox_recipes
    ADD CONSTRAINT sandbox_recipes_pkey PRIMARY KEY (owner_user_id, recipe_id);


--
-- Name: sandboxes sandboxes_pkey; Type: CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.sandboxes
    ADD CONSTRAINT sandboxes_pkey PRIMARY KEY (id);


--
-- Name: terminal_command_chunks terminal_command_chunks_pkey; Type: CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.terminal_command_chunks
    ADD CONSTRAINT terminal_command_chunks_pkey PRIMARY KEY (chunk_id);


--
-- Name: terminal_commands terminal_commands_pkey; Type: CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.terminal_commands
    ADD CONSTRAINT terminal_commands_pkey PRIMARY KEY (command_id);


--
-- Name: thread_terminal_pointers thread_terminal_pointers_pkey; Type: CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.thread_terminal_pointers
    ADD CONSTRAINT thread_terminal_pointers_pkey PRIMARY KEY (thread_id);


--
-- Name: workspaces workspaces_pkey; Type: CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.workspaces
    ADD CONSTRAINT workspaces_pkey PRIMARY KEY (id);


--
-- Name: invite_codes invite_codes_pkey; Type: CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.invite_codes
    ADD CONSTRAINT invite_codes_pkey PRIMARY KEY (code);


--
-- Name: user_settings user_settings_pkey; Type: CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.user_settings
    ADD CONSTRAINT user_settings_pkey PRIMARY KEY (user_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_mycel_id_key; Type: CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.users
    ADD CONSTRAINT users_mycel_id_key UNIQUE (mycel_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: skill_packages skill_packages_owner_user_id_skill_id_hash_key; Type: CONSTRAINT; Schema: library; Owner: -
--

ALTER TABLE ONLY library.skill_packages
    ADD CONSTRAINT skill_packages_owner_user_id_skill_id_hash_key UNIQUE (owner_user_id, skill_id, hash);


--
-- Name: skill_packages skill_packages_owner_user_id_skill_id_id_key; Type: CONSTRAINT; Schema: library; Owner: -
--

ALTER TABLE ONLY library.skill_packages
    ADD CONSTRAINT skill_packages_owner_user_id_skill_id_id_key UNIQUE (owner_user_id, skill_id, id);


--
-- Name: skill_packages skill_packages_pkey; Type: CONSTRAINT; Schema: library; Owner: -
--

ALTER TABLE ONLY library.skill_packages
    ADD CONSTRAINT skill_packages_pkey PRIMARY KEY (id);


--
-- Name: skill_packages skill_packages_skill_id_id_key; Type: CONSTRAINT; Schema: library; Owner: -
--

ALTER TABLE ONLY library.skill_packages
    ADD CONSTRAINT skill_packages_skill_id_id_key UNIQUE (skill_id, id);


--
-- Name: skills skills_owner_user_id_name_key; Type: CONSTRAINT; Schema: library; Owner: -
--

ALTER TABLE ONLY library.skills
    ADD CONSTRAINT skills_owner_user_id_name_key UNIQUE (owner_user_id, name);


--
-- Name: skills skills_pkey; Type: CONSTRAINT; Schema: library; Owner: -
--

ALTER TABLE ONLY library.skills
    ADD CONSTRAINT skills_pkey PRIMARY KEY (owner_user_id, id);


--
-- Name: eval_llm_calls eval_llm_calls_pkey; Type: CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.eval_llm_calls
    ADD CONSTRAINT eval_llm_calls_pkey PRIMARY KEY (id);


--
-- Name: eval_metrics eval_metrics_pkey; Type: CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.eval_metrics
    ADD CONSTRAINT eval_metrics_pkey PRIMARY KEY (id);


--
-- Name: eval_runs eval_runs_pkey; Type: CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.eval_runs
    ADD CONSTRAINT eval_runs_pkey PRIMARY KEY (id);


--
-- Name: eval_tool_calls eval_tool_calls_pkey; Type: CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.eval_tool_calls
    ADD CONSTRAINT eval_tool_calls_pkey PRIMARY KEY (id);


--
-- Name: evaluation_batch_runs evaluation_batch_runs_pkey; Type: CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.evaluation_batch_runs
    ADD CONSTRAINT evaluation_batch_runs_pkey PRIMARY KEY (batch_run_id);


--
-- Name: evaluation_batches evaluation_batches_pkey; Type: CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.evaluation_batches
    ADD CONSTRAINT evaluation_batches_pkey PRIMARY KEY (batch_id);


--
-- Name: monitor_operations monitor_operations_pkey; Type: CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.monitor_operations
    ADD CONSTRAINT monitor_operations_pkey PRIMARY KEY (operation_id);


--
-- Name: provider_events provider_events_pkey; Type: CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.provider_events
    ADD CONSTRAINT provider_events_pkey PRIMARY KEY (event_id);


--
-- Name: idx_agent_configs_active; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_agent_configs_active ON agent.agent_configs USING btree (owner_user_id, updated_at DESC) WHERE (status = 'active'::text);


--
-- Name: idx_agent_configs_owner; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_agent_configs_owner ON agent.agent_configs USING btree (owner_user_id);


--
-- Name: idx_agent_file_operations_thread; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_agent_file_operations_thread ON agent.file_operations USING btree (thread_id, "timestamp" DESC);


--
-- Name: idx_agent_rules_config; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_agent_rules_config ON agent.agent_rules USING btree (agent_config_id);


--
-- Name: idx_agent_sub_agents_config; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_agent_sub_agents_config ON agent.agent_sub_agents USING btree (agent_config_id);


--
-- Name: idx_agent_summaries_thread_id; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_agent_summaries_thread_id ON agent.summaries USING btree (thread_id, is_active, created_at DESC);


--
-- Name: idx_checkpoint_writes_checkpoint; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_checkpoint_writes_checkpoint ON agent.checkpoint_writes USING btree (thread_id, checkpoint_ns, checkpoint_id);


--
-- Name: idx_checkpoints_thread; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_checkpoints_thread ON agent.checkpoints USING btree (thread_id, checkpoint_ns);


--
-- Name: idx_schedule_runs_owner_created; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_schedule_runs_owner_created ON agent.schedule_runs USING btree (owner_user_id, created_at DESC);


--
-- Name: idx_schedule_runs_schedule_created; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_schedule_runs_schedule_created ON agent.schedule_runs USING btree (schedule_id, created_at DESC);


--
-- Name: idx_schedule_runs_status_scheduled; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_schedule_runs_status_scheduled ON agent.schedule_runs USING btree (status, scheduled_for);


--
-- Name: idx_schedules_agent; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_schedules_agent ON agent.schedules USING btree (agent_user_id);


--
-- Name: idx_schedules_owner_enabled_next_run; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_schedules_owner_enabled_next_run ON agent.schedules USING btree (owner_user_id, next_run_at) WHERE (enabled = true);


--
-- Name: idx_schedules_target_thread; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_schedules_target_thread ON agent.schedules USING btree (target_thread_id) WHERE (target_thread_id IS NOT NULL);


--
-- Name: idx_thread_tasks_thread; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_thread_tasks_thread ON agent.thread_tasks USING btree (thread_id);


--
-- Name: idx_threads_agent_active; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_threads_agent_active ON agent.threads USING btree (agent_user_id) WHERE (status = 'active'::text);


--
-- Name: idx_threads_owner_active; Type: INDEX; Schema: agent; Owner: -
--

CREATE INDEX idx_threads_owner_active ON agent.threads USING btree (owner_user_id, last_active_at DESC) WHERE (status = 'active'::text);


--
-- Name: idx_chat_tasks_owner_user_id; Type: INDEX; Schema: chat; Owner: -
--

CREATE INDEX idx_chat_tasks_owner_user_id ON chat.tasks USING btree (owner_user_id) WHERE (owner_user_id IS NOT NULL);


--
-- Name: idx_chat_workflow_events_kind_state; Type: INDEX; Schema: chat; Owner: -
--

CREATE INDEX idx_chat_workflow_events_kind_state ON chat.workflow_events USING btree (kind, state);


--
-- Name: idx_chat_workflow_events_requested_by_user_id; Type: INDEX; Schema: chat; Owner: -
--

CREATE INDEX idx_chat_workflow_events_requested_by_user_id ON chat.workflow_events USING btree (requested_by_user_id) WHERE (requested_by_user_id IS NOT NULL);


--
-- Name: idx_container_abstract_terminals_runtime_created; Type: INDEX; Schema: container; Owner: -
--

CREATE INDEX idx_container_abstract_terminals_runtime_created ON container.abstract_terminals USING btree (sandbox_runtime_id, created_at DESC);


--
-- Name: idx_container_abstract_terminals_thread_created; Type: INDEX; Schema: container; Owner: -
--

CREATE INDEX idx_container_abstract_terminals_thread_created ON container.abstract_terminals USING btree (thread_id, created_at DESC);


--
-- Name: idx_container_chat_sessions_thread_status; Type: INDEX; Schema: container; Owner: -
--

CREATE INDEX idx_container_chat_sessions_thread_status ON container.chat_sessions USING btree (thread_id, status, started_at DESC);


--
-- Name: idx_container_sandboxes_owner; Type: INDEX; Schema: container; Owner: -
--

CREATE INDEX idx_container_sandboxes_owner ON container.sandboxes USING btree (owner_user_id);


--
-- Name: idx_container_sandboxes_provider_env; Type: INDEX; Schema: container; Owner: -
--

CREATE INDEX idx_container_sandboxes_provider_env ON container.sandboxes USING btree (provider_name, provider_env_id) WHERE (provider_env_id IS NOT NULL);


--
-- Name: idx_container_terminal_command_chunks_command_order; Type: INDEX; Schema: container; Owner: -
--

CREATE INDEX idx_container_terminal_command_chunks_command_order ON container.terminal_command_chunks USING btree (command_id, chunk_id);


--
-- Name: idx_container_terminal_commands_terminal_created; Type: INDEX; Schema: container; Owner: -
--

CREATE INDEX idx_container_terminal_commands_terminal_created ON container.terminal_commands USING btree (terminal_id, created_at DESC);


--
-- Name: idx_container_workspaces_sandbox_path; Type: INDEX; Schema: container; Owner: -
--

CREATE UNIQUE INDEX idx_container_workspaces_sandbox_path ON container.workspaces USING btree (sandbox_id, workspace_path);


--
-- Name: idx_resource_snapshots_collected_at; Type: INDEX; Schema: container; Owner: -
--

CREATE INDEX idx_resource_snapshots_collected_at ON container.resource_snapshots USING btree (collected_at DESC);


--
-- Name: idx_resource_snapshots_owner; Type: INDEX; Schema: container; Owner: -
--

CREATE INDEX idx_resource_snapshots_owner ON container.resource_snapshots USING btree (owner_user_id, collected_at DESC);


--
-- Name: uq_container_chat_sessions_active_terminal; Type: INDEX; Schema: container; Owner: -
--

CREATE UNIQUE INDEX uq_container_chat_sessions_active_terminal ON container.chat_sessions USING btree (terminal_id) WHERE (status = ANY (ARRAY['active'::text, 'idle'::text, 'paused'::text]));


--
-- Name: idx_identity_invite_codes_used_by; Type: INDEX; Schema: identity; Owner: -
--

CREATE INDEX idx_identity_invite_codes_used_by ON identity.invite_codes USING btree (used_by) WHERE (used_by IS NOT NULL);


--
-- Name: idx_identity_users_created_by_user_id; Type: INDEX; Schema: identity; Owner: -
--

CREATE INDEX idx_identity_users_created_by_user_id ON identity.users USING btree (created_by_user_id) WHERE (created_by_user_id IS NOT NULL);


--
-- Name: monitor_operations_target_requested_idx; Type: INDEX; Schema: observability; Owner: -
--

CREATE INDEX monitor_operations_target_requested_idx ON observability.monitor_operations USING btree (target_type, target_id, requested_at DESC);


--
-- Name: agent_rules agent_rules_agent_config_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_rules
    ADD CONSTRAINT agent_rules_agent_config_id_fkey FOREIGN KEY (agent_config_id) REFERENCES agent.agent_configs(id) ON DELETE CASCADE;


--
-- Name: agent_sub_agents agent_sub_agents_agent_config_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.agent_sub_agents
    ADD CONSTRAINT agent_sub_agents_agent_config_id_fkey FOREIGN KEY (agent_config_id) REFERENCES agent.agent_configs(id) ON DELETE CASCADE;


--
-- Name: skill_bindings skill_bindings_agent_config_id_fkey; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.skill_bindings
    ADD CONSTRAINT skill_bindings_agent_config_id_fkey FOREIGN KEY (agent_config_id) REFERENCES agent.agent_configs(id) ON DELETE CASCADE;


--
-- Name: skill_bindings skill_bindings_package_skill_fk; Type: FK CONSTRAINT; Schema: agent; Owner: -
--

ALTER TABLE ONLY agent.skill_bindings
    ADD CONSTRAINT skill_bindings_package_skill_fk FOREIGN KEY (skill_id, package_id) REFERENCES library.skill_packages(skill_id, id);


--
-- Name: join_requests join_requests_chat_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.join_requests
    ADD CONSTRAINT join_requests_chat_id_fkey FOREIGN KEY (chat_id) REFERENCES chat.chats(id);


--
-- Name: join_requests join_requests_decided_by_user_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.join_requests
    ADD CONSTRAINT join_requests_decided_by_user_id_fkey FOREIGN KEY (decided_by_user_id) REFERENCES identity.users(id);


--
-- Name: join_requests join_requests_requester_user_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.join_requests
    ADD CONSTRAINT join_requests_requester_user_id_fkey FOREIGN KEY (requester_user_id) REFERENCES identity.users(id);


--
-- Name: tasks tasks_chat_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.tasks
    ADD CONSTRAINT tasks_chat_id_fkey FOREIGN KEY (chat_id) REFERENCES chat.chats(id) ON DELETE CASCADE;


--
-- Name: tasks tasks_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.tasks
    ADD CONSTRAINT tasks_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES identity.users(id) ON DELETE SET NULL;


--
-- Name: workflow_events workflow_events_chat_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.workflow_events
    ADD CONSTRAINT workflow_events_chat_id_fkey FOREIGN KEY (chat_id) REFERENCES chat.chats(id) ON DELETE CASCADE;


--
-- Name: workflow_events workflow_events_requested_by_user_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.workflow_events
    ADD CONSTRAINT workflow_events_requested_by_user_id_fkey FOREIGN KEY (requested_by_user_id) REFERENCES identity.users(id) ON DELETE SET NULL;


--
-- Name: workflow_state workflow_state_chat_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.workflow_state
    ADD CONSTRAINT workflow_state_chat_id_fkey FOREIGN KEY (chat_id) REFERENCES chat.chats(id) ON DELETE CASCADE;


--
-- Name: workflow_state workflow_state_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: chat; Owner: -
--

ALTER TABLE ONLY chat.workflow_state
    ADD CONSTRAINT workflow_state_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES identity.users(id) ON DELETE SET NULL;


--
-- Name: chat_sessions chat_sessions_terminal_id_fkey; Type: FK CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.chat_sessions
    ADD CONSTRAINT chat_sessions_terminal_id_fkey FOREIGN KEY (terminal_id) REFERENCES container.abstract_terminals(terminal_id) ON DELETE CASCADE;


--
-- Name: terminal_command_chunks terminal_command_chunks_command_id_fkey; Type: FK CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.terminal_command_chunks
    ADD CONSTRAINT terminal_command_chunks_command_id_fkey FOREIGN KEY (command_id) REFERENCES container.terminal_commands(command_id) ON DELETE CASCADE;


--
-- Name: terminal_commands terminal_commands_chat_session_id_fkey; Type: FK CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.terminal_commands
    ADD CONSTRAINT terminal_commands_chat_session_id_fkey FOREIGN KEY (chat_session_id) REFERENCES container.chat_sessions(chat_session_id) ON DELETE SET NULL;


--
-- Name: terminal_commands terminal_commands_terminal_id_fkey; Type: FK CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.terminal_commands
    ADD CONSTRAINT terminal_commands_terminal_id_fkey FOREIGN KEY (terminal_id) REFERENCES container.abstract_terminals(terminal_id) ON DELETE CASCADE;


--
-- Name: thread_terminal_pointers thread_terminal_pointers_active_terminal_id_fkey; Type: FK CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.thread_terminal_pointers
    ADD CONSTRAINT thread_terminal_pointers_active_terminal_id_fkey FOREIGN KEY (active_terminal_id) REFERENCES container.abstract_terminals(terminal_id) ON DELETE CASCADE;


--
-- Name: thread_terminal_pointers thread_terminal_pointers_default_terminal_id_fkey; Type: FK CONSTRAINT; Schema: container; Owner: -
--

ALTER TABLE ONLY container.thread_terminal_pointers
    ADD CONSTRAINT thread_terminal_pointers_default_terminal_id_fkey FOREIGN KEY (default_terminal_id) REFERENCES container.abstract_terminals(terminal_id) ON DELETE CASCADE;


--
-- Name: users users_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.users
    ADD CONSTRAINT users_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES identity.users(id) ON DELETE SET NULL;


--
-- Name: users users_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.users
    ADD CONSTRAINT users_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES identity.users(id);


--
-- Name: skill_packages skill_packages_owner_user_id_skill_id_fkey; Type: FK CONSTRAINT; Schema: library; Owner: -
--

ALTER TABLE ONLY library.skill_packages
    ADD CONSTRAINT skill_packages_owner_user_id_skill_id_fkey FOREIGN KEY (owner_user_id, skill_id) REFERENCES library.skills(owner_user_id, id) ON DELETE CASCADE;


--
-- Name: skills skills_package_fk; Type: FK CONSTRAINT; Schema: library; Owner: -
--

ALTER TABLE ONLY library.skills
    ADD CONSTRAINT skills_package_fk FOREIGN KEY (owner_user_id, id, package_id) REFERENCES library.skill_packages(owner_user_id, skill_id, id);


--
-- Name: eval_llm_calls eval_llm_calls_run_id_fkey; Type: FK CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.eval_llm_calls
    ADD CONSTRAINT eval_llm_calls_run_id_fkey FOREIGN KEY (run_id) REFERENCES observability.eval_runs(id) ON DELETE CASCADE;


--
-- Name: eval_metrics eval_metrics_run_id_fkey; Type: FK CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.eval_metrics
    ADD CONSTRAINT eval_metrics_run_id_fkey FOREIGN KEY (run_id) REFERENCES observability.eval_runs(id) ON DELETE CASCADE;


--
-- Name: eval_tool_calls eval_tool_calls_run_id_fkey; Type: FK CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.eval_tool_calls
    ADD CONSTRAINT eval_tool_calls_run_id_fkey FOREIGN KEY (run_id) REFERENCES observability.eval_runs(id) ON DELETE CASCADE;


--
-- Name: evaluation_batch_runs evaluation_batch_runs_batch_id_fkey; Type: FK CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.evaluation_batch_runs
    ADD CONSTRAINT evaluation_batch_runs_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES observability.evaluation_batches(batch_id) ON DELETE CASCADE;


--
-- Name: evaluation_batch_runs evaluation_batch_runs_eval_run_id_fkey; Type: FK CONSTRAINT; Schema: observability; Owner: -
--

ALTER TABLE ONLY observability.evaluation_batch_runs
    ADD CONSTRAINT evaluation_batch_runs_eval_run_id_fkey FOREIGN KEY (eval_run_id) REFERENCES observability.eval_runs(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--
