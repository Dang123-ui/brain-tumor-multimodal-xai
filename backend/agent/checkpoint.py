import os
from contextlib import AbstractContextManager
from typing import Any


_CHECKPOINTER_CONTEXT: AbstractContextManager | None = None
_CHECKPOINTER = None
_STORE_CONTEXT: AbstractContextManager | None = None
_STORE = None


def _postgres_url() -> str | None:
    return os.getenv("AGENT_POSTGRES_URL") or os.getenv("DATABASE_URL")


def get_postgres_checkpointer():
    """Return a process-global LangGraph PostgresSaver.

    The tunnel deployment uses one backend process per container, so keeping the
    context-manager connection open globally is acceptable. If setup fails, the
    caller can fall back to compiling the graph without a checkpointer.
    """
    global _CHECKPOINTER_CONTEXT, _CHECKPOINTER
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER

    url = _postgres_url()
    if not url or os.getenv("AGENT_DISABLE_POSTGRES_SAVER", "").lower() in {"1", "true", "yes"}:
        return None

    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        _CHECKPOINTER_CONTEXT = PostgresSaver.from_conn_string(url)
        _CHECKPOINTER = _CHECKPOINTER_CONTEXT.__enter__()
        _CHECKPOINTER.setup()
        return _CHECKPOINTER
    except Exception as exc:
        print(f"[AGENT] PostgresSaver disabled: {exc}")
        _CHECKPOINTER = None
        _CHECKPOINTER_CONTEXT = None
        return None


def get_postgres_store():
    """Return a process-global LangGraph PostgresStore for long memory."""
    global _STORE_CONTEXT, _STORE
    if _STORE is not None:
        return _STORE

    url = _postgres_url()
    if not url or os.getenv("AGENT_DISABLE_POSTGRES_STORE", "").lower() in {"1", "true", "yes"}:
        return None

    try:
        from langgraph.store.postgres import PostgresStore

        _STORE_CONTEXT = PostgresStore.from_conn_string(url)
        _STORE = _STORE_CONTEXT.__enter__()
        _STORE.setup()
        return _STORE
    except Exception as exc:
        print(f"[AGENT] PostgresStore disabled: {exc}")
        _STORE = None
        _STORE_CONTEXT = None
        return None


def save_long_memory(namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> bool:
    store = get_postgres_store()
    if not store:
        return False
    try:
        store.put(namespace, key, value)
        return True
    except Exception as exc:
        print(f"[AGENT] Long memory write skipped: {exc}")
        return False


def retrieve_long_memory(namespace_prefix: tuple[str, ...], query: str | None = None, limit: int = 10):
    store = get_postgres_store()
    if not store:
        return []
    try:
        return store.search(namespace_prefix, query=query, limit=limit)
    except Exception as exc:
        print(f"[AGENT] Long memory search skipped: {exc}")
        return []


def delete_long_memory(namespace: tuple[str, ...], key: str) -> bool:
    store = get_postgres_store()
    if not store:
        return False
    try:
        store.delete(namespace, key)
        return True
    except Exception as exc:
        print(f"[AGENT] Long memory delete skipped: {exc}")
        return False
