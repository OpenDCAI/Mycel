from core.runtime.langgraph_checkpoint_store import agent_checkpoint_conn_string


def test_agent_checkpoint_conn_string_adds_agent_search_path() -> None:
    conn = agent_checkpoint_conn_string("postgresql://user:pass@db.example/postgres")

    assert conn == "postgresql://user:pass@db.example/postgres?options=-csearch_path%3Dagent"


def test_agent_checkpoint_conn_string_preserves_existing_query_params() -> None:
    conn = agent_checkpoint_conn_string("postgresql://user:pass@db.example/postgres?sslmode=require")

    assert conn == "postgresql://user:pass@db.example/postgres?sslmode=require&options=-csearch_path%3Dagent"


def test_agent_checkpoint_conn_string_merges_existing_libpq_options() -> None:
    conn = agent_checkpoint_conn_string("postgresql://user:pass@db.example/postgres?options=-cstatement_timeout%3D5000")

    assert conn == "postgresql://user:pass@db.example/postgres?options=-cstatement_timeout%3D5000%20-csearch_path%3Dagent"
