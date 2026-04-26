from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def build_observation(app: Any, thread_id: str, config: dict[str, Any]) -> Callable[[], None]:
    obs_handler = None
    obs_active = None
    obs_provider = None

    try:
        thread_data = app.state.thread_repo.get_by_id(thread_id) if hasattr(app.state, "thread_repo") else None
        obs_provider = thread_data.get("observation_provider") if thread_data else None

        if obs_provider:
            from config.observation_loader import ObservationLoader

            obs_config = ObservationLoader().load()

            if obs_provider == "langfuse":
                from langfuse import Langfuse  # pyright: ignore[reportMissingImports, reportAttributeAccessIssue]
                from langfuse.langchain import (
                    CallbackHandler as LangfuseHandler,  # pyright: ignore[reportMissingImports, reportAttributeAccessIssue]
                )

                cfg = obs_config.langfuse
                if cfg.secret_key and cfg.public_key:
                    obs_active = "langfuse"
                    Langfuse(
                        public_key=cfg.public_key,
                        secret_key=cfg.secret_key,
                        host=cfg.host or "https://cloud.langfuse.com",
                    )
                    obs_handler = LangfuseHandler(public_key=cfg.public_key)
                    callbacks = config.setdefault("callbacks", [])
                    if not isinstance(callbacks, list):
                        raise RuntimeError("streaming observation callbacks must be a list")
                    callbacks.append(obs_handler)
                    metadata = config.setdefault("metadata", {})
                    if not isinstance(metadata, dict):
                        raise RuntimeError("streaming observation metadata must be an object")
                    metadata["langfuse_session_id"] = thread_id
            elif obs_provider == "langsmith":
                from langchain_core.tracers.langchain import LangChainTracer  # pyright: ignore[reportMissingImports]
                from langsmith import Client as LangSmithClient  # pyright: ignore[reportMissingImports, reportAttributeAccessIssue]

                cfg = obs_config.langsmith
                if cfg.api_key:
                    obs_active = "langsmith"
                    ls_client = LangSmithClient(
                        api_key=cfg.api_key,
                        api_url=cfg.endpoint or "https://api.smith.langchain.com",
                    )
                    obs_handler = LangChainTracer(
                        client=ls_client,
                        project_name=cfg.project or "default",
                    )
                    callbacks = config.setdefault("callbacks", [])
                    if not isinstance(callbacks, list):
                        raise RuntimeError("streaming observation callbacks must be a list")
                    callbacks.append(obs_handler)
                    metadata = config.setdefault("metadata", {})
                    if not isinstance(metadata, dict):
                        raise RuntimeError("streaming observation metadata must be an object")
                    metadata["session_id"] = thread_id
    except ImportError as imp_err:
        logger.warning(
            "Observation provider '%s' missing package: %s. Install: uv pip install 'mycel[%s]'",
            obs_provider,
            imp_err,
            obs_provider,
        )
    except Exception as obs_err:
        logger.warning("Observation handler error: %s", obs_err, exc_info=True)

    def flush() -> None:
        if obs_handler is None:
            return
        try:
            if obs_active == "langfuse":
                from langfuse import get_client  # pyright: ignore[reportMissingImports, reportAttributeAccessIssue]

                get_client().flush()
            elif obs_active == "langsmith":
                obs_handler.wait_for_futures()
        except Exception as flush_err:
            logger.warning("Observation flush error: %s", flush_err)

    return flush
