import os
import json
import logging
from sqlalchemy import create_engine, text

from core.memory_schema import ensure_memory_shape

logger = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST", "34.175.165.97")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "8lk4vM}BpAPtXY/<")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")

_POOL = None

def init_connection_pool():
    """Initialize the DB connection pool."""
    connection_url = f"postgresql+pg8000://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    pool = create_engine(
        connection_url,
        pool_size=5,
        max_overflow=2,
        pool_timeout=30,
        pool_recycle=1800,
    )
    return pool

def get_pool():
    global _POOL
    if _POOL is None:
        _POOL = init_connection_pool()
    return _POOL


class SessionManager:
    def __init__(self):
        self.pool = get_pool()

    def _normalize_memory(self, raw_memory) -> dict:
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

    def _get_composite_id(self, user_id: str, company_id: str) -> str:
        """Construct the composite session ID."""
        return f"{company_id}_{user_id}"

    def get_session(self, user_id: str, company_id: str) -> dict:
        session_id = self._get_composite_id(user_id, company_id)
        
        default_session = {
            "session_id": session_id,
            "domain": None,
            "target_agent": "receptionist_agent",
            "agent_memory": ensure_memory_shape({}),
            "history": []
        }

        query = text("SELECT domain, target_agent, agent_memory FROM sessions WHERE session_id = :sid")
        try:
            with self.pool.connect() as conn:
                result = conn.execute(query, {"sid": session_id}).fetchone()
                if result:
                    normalized_memory = self._normalize_memory(result[2])
                    return {
                        "session_id": session_id,
                        "domain": result[0],
                        "target_agent": result[1],
                        "agent_memory": ensure_memory_shape(normalized_memory),
                        "history": []
                    }
        except Exception as e:
            logger.error(f"DB Read Error: {e}")
        
        return default_session

    def save_session(self, session_id: str, data: dict):
        domain = data.get("domain")
        target_agent = data.get("target_agent")
        memory_data = ensure_memory_shape(self._normalize_memory(data.get("agent_memory", {})))
        memory = json.dumps(memory_data)

        query = text("""
            INSERT INTO sessions (session_id, domain, target_agent, agent_memory, updated_at)
            VALUES (:sid, :dom, :agt, :mem, NOW())
            ON CONFLICT (session_id) DO UPDATE SET
                domain = EXCLUDED.domain,
                target_agent = EXCLUDED.target_agent,
                agent_memory = EXCLUDED.agent_memory,
                updated_at = NOW();
        """)
        
        try:
            with self.pool.connect() as conn:
                conn.execute(query, {
                    "sid": session_id,
                    "dom": domain,
                    "agt": target_agent,
                    "mem": memory
                })
                conn.commit()
        except Exception as e:
            logger.error(f"DB Write Error: {e}")

    def update_agent_memory(self, user_id: str, new_memory: dict, company_id: str):
        session = self.get_session(user_id, company_id)
        session_id = session["session_id"]
        
        current_mem = ensure_memory_shape(self._normalize_memory(session.get("agent_memory", {})))
        if not isinstance(new_memory, dict):
            new_memory = {}
        new_memory = ensure_memory_shape(new_memory)
        current_mem.update(new_memory)
        session["agent_memory"] = current_mem
        self.save_session(session_id, session)

    def set_target_agent(self, user_id: str, agent_name: str, domain: str = None, company_id: str = "default"):
        session = self.get_session(user_id, company_id)
        session_id = session["session_id"]
        
        session["target_agent"] = agent_name
        session["domain"] = domain
        self.save_session(session_id, session)

    def delete_session(self, user_id: str, company_id: str) -> bool:
        """Delete a session from the database."""
        session_id = self._get_composite_id(user_id, company_id)
        
        query = text("DELETE FROM sessions WHERE session_id = :sid")
        try:
            with self.pool.connect() as conn:
                result = conn.execute(query, {"sid": session_id})
                conn.commit()
                deleted = result.rowcount > 0
                logger.info(f"Session deletion: session_id={session_id}, deleted={deleted}, rowcount={result.rowcount}")
                return deleted
        except Exception as e:
            logger.error(f"DB Delete Error: {e}")
            return False
