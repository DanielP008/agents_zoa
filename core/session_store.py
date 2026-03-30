"""Session persistence layer backed by PostgreSQL."""

import json
import logging
import os
import time
from typing import Any, Optional

from sqlalchemy import create_engine, text

from core.memory import ensure_memory_shape
from infra.timing import Timer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection config
# ---------------------------------------------------------------------------
_MAX_RETRIES = 3
_RETRY_DELAY = 0.5  # seconds

DB_HOST = os.getenv("DB_HOST", "")
DB_USER = os.getenv("DB_USER", "")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")

_POOL = None
_SESSION_MANAGER = None


def get_session_manager():
    """Return a shared SessionManager singleton."""
    global _SESSION_MANAGER
    if _SESSION_MANAGER is None:
        _SESSION_MANAGER = SessionManager()
    return _SESSION_MANAGER


def _init_connection_pool():
    """Initialize the DB connection pool."""
    url = f"postgresql+pg8000://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(
        url,
        pool_size=5,
        max_overflow=2,
        pool_timeout=30,
        pool_recycle=1800,
    )


def _get_pool():
    global _POOL
    if _POOL is None:
        _POOL = _init_connection_pool()
    return _POOL


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _execute_with_retry(pool, timer_label: str, query, params: dict,
                        *, commit: bool = False, fetch: bool = False,
                        error_prefix: str = "DB") -> Optional[Any]:
    """Execute a DB query with retry logic.

    Returns:
        - The fetched row if fetch=True and a row exists, else None.
        - The CursorResult if commit=True (for rowcount checks).
        - None on final failure.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            with Timer("postgres", timer_label):
                with pool.connect() as conn:
                    result = conn.execute(query, params)
                    if commit:
                        conn.commit()
                    if fetch:
                        return result.fetchone()
                    return result
        except Exception as e:
            if attempt < _MAX_RETRIES - 1:
                logger.warning(f"{error_prefix} Error (attempt {attempt + 1}/{_MAX_RETRIES}): {e}")
                time.sleep(_RETRY_DELAY * (attempt + 1))
            else:
                logger.error(f"{error_prefix} Error (final attempt): {e}")
    return None


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------

class SessionManager:
    """Manages agent session state in PostgreSQL."""

    def __init__(self):
        self.pool = _get_pool()

    @staticmethod
    def _normalize_memory(raw_memory) -> dict:
        """Ensure raw_memory is a dict, parsing JSON strings if needed."""
        if not raw_memory:
            return {}
        if isinstance(raw_memory, dict):
            return raw_memory
        if isinstance(raw_memory, str):
            try:
                parsed = json.loads(raw_memory)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _get_composite_id(user_id: str, company_id: str) -> str:
        """Construct the composite session ID."""
        return f"{company_id}_{user_id}"

    # -- Read ---------------------------------------------------------------

    def get_session(self, user_id: str, company_id: str) -> dict:
        """Load a session from DB, returning defaults if not found."""
        session_id = self._get_composite_id(user_id, company_id)

        default_session = {
            "session_id": session_id,
            "domain": None,
            "target_agent": "receptionist_agent",
            "agent_memory": ensure_memory_shape({}),
            "history": [],
        }

        query = text("SELECT domain, target_agent, agent_memory FROM sessions WHERE session_id = :sid")
        row = _execute_with_retry(
            self.pool, "get_session", query, {"sid": session_id},
            fetch=True, error_prefix="DB Read",
        )

        if row is None:
            return default_session

        return {
            "session_id": session_id,
            "domain": row[0],
            "target_agent": row[1],
            "agent_memory": ensure_memory_shape(self._normalize_memory(row[2])),
            "history": [],
        }

    # -- Write --------------------------------------------------------------

    def save_session(self, session_id: str, data: dict) -> None:
        """Upsert session state to DB."""
        memory_data = ensure_memory_shape(self._normalize_memory(data.get("agent_memory", {})))

        query = text("""
            INSERT INTO sessions (session_id, domain, target_agent, agent_memory, updated_at)
            VALUES (:sid, :dom, :agt, :mem, NOW())
            ON CONFLICT (session_id) DO UPDATE SET
                domain = EXCLUDED.domain,
                target_agent = EXCLUDED.target_agent,
                agent_memory = EXCLUDED.agent_memory,
                updated_at = NOW();
        """)
        _execute_with_retry(
            self.pool, "save_session", query,
            {
                "sid": session_id,
                "dom": data.get("domain"),
                "agt": data.get("target_agent"),
                "mem": json.dumps(memory_data),
            },
            commit=True, error_prefix="DB Write",
        )

    def update_agent_memory(self, user_id: str, new_memory: dict, company_id: str) -> None:
        """Merge new_memory into the existing session memory."""
        session = self.get_session(user_id, company_id)
        current_mem = ensure_memory_shape(self._normalize_memory(session.get("agent_memory", {})))
        if not isinstance(new_memory, dict):
            new_memory = {}
        current_mem.update(ensure_memory_shape(new_memory))
        session["agent_memory"] = current_mem
        self.save_session(session["session_id"], session)

    def set_target_agent(self, user_id: str, agent_name: str,
                         domain: str = None, company_id: str = "default") -> None:
        """Update the target agent (and optionally domain) for a session."""
        session = self.get_session(user_id, company_id)
        session["target_agent"] = agent_name
        session["domain"] = domain
        self.save_session(session["session_id"], session)

    # -- Delete -------------------------------------------------------------

    def delete_session(self, user_id: str, company_id: str) -> bool:
        """Delete a session from the database."""
        session_id = self._get_composite_id(user_id, company_id)
        query = text("DELETE FROM sessions WHERE session_id = :sid")

        result = _execute_with_retry(
            self.pool, "delete_session", query, {"sid": session_id},
            commit=True, error_prefix="DB Delete",
        )
        if result is None:
            return False

        deleted = result.rowcount > 0
        logger.info(f"Session deletion: session_id={session_id}, deleted={deleted}")
        return deleted

    # -- Status -------------------------------------------------------------

    def get_session_status(self, user_id: str, company_id: str) -> str | None:
        """Get the AI processing status for a session. Returns 'on', 'off', or None if no session exists."""
        session_id = self._get_composite_id(user_id, company_id)
        query = text("SELECT status FROM sessions WHERE session_id = :sid")
        row = _execute_with_retry(
            self.pool, "get_status", query, {"sid": session_id},
            fetch=True, error_prefix="DB Status",
        )
        if row is None:
            return None
        return row[0] if row[0] else "off"

    def set_session_status(self, user_id: str, company_id: str, status: str) -> None:
        """Set the AI processing status ('on' or 'off') for a session."""
        session_id = self._get_composite_id(user_id, company_id)
        query = text("""
            INSERT INTO sessions (session_id, status, target_agent, updated_at)
            VALUES (:sid, :status, 'receptionist_agent', NOW())
            ON CONFLICT (session_id) DO UPDATE SET
                status = EXCLUDED.status,
                updated_at = NOW();
        """)
        _execute_with_retry(
            self.pool, "set_status", query,
            {"sid": session_id, "status": status},
            commit=True, error_prefix="DB Status Write",
        )
        logger.info(f"[DB] Session {session_id} status set to '{status}'")

    # -- Locking ------------------------------------------------------------

    def try_lock_session(self, user_id: str, company_id: str) -> bool:
        """Atomically lock a session for processing. Returns True if lock acquired."""
        session_id = self._get_composite_id(user_id, company_id)

        query = text("""
            INSERT INTO sessions (session_id, processing, status, target_agent, updated_at)
            VALUES (:sid, TRUE, 'on', 'receptionist_agent', NOW())
            ON CONFLICT (session_id) DO UPDATE
            SET processing = TRUE, updated_at = NOW()
            WHERE sessions.processing = FALSE
               OR sessions.processing IS NULL
               OR sessions.updated_at < NOW() - INTERVAL '60 seconds'
        """)
        result = _execute_with_retry(
            self.pool, "try_lock_session", query, {"sid": session_id},
            commit=True, error_prefix="DB Lock",
        )
        if result is None:
            return False
        return result.rowcount > 0

    def unlock_session(self, user_id: str, company_id: str) -> None:
        """Release the processing lock on a session."""
        session_id = self._get_composite_id(user_id, company_id)
        query = text("UPDATE sessions SET processing = FALSE, updated_at = NOW() WHERE session_id = :sid")

        _execute_with_retry(
            self.pool, "unlock_session", query, {"sid": session_id},
            commit=True, error_prefix="DB Unlock",
        )
