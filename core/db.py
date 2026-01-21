import os
import json
import logging
from typing import Optional

# Conditional import to allow local dev without installing cloud-sql-connector
try:
    from google.cloud.sql.connector import Connector, IPTypes
    import sqlalchemy
    from sqlalchemy import text
except ImportError:
    Connector = None
    sqlalchemy = None

logger = logging.getLogger(__name__)

# Global pool
_POOL = None

def init_connection_pool():
    """Initializes the connection pool based on environment."""
    if os.environ.get("USE_CLOUD_SQL", "false").lower() != "true":
        return MockDB()

    instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")
    db_user = os.environ.get("DB_USER")
    db_pass = os.environ.get("DB_PASS")
    db_name = os.environ.get("DB_NAME")
    ip_type = IPTypes.PRIVATE if os.environ.get("DB_PRIVATE_IP", "true").lower() == "true" else IPTypes.PUBLIC

    connector = Connector()

    def getconn():
        conn = connector.connect(
            instance_connection_name,
            "pg8000",
            user=db_user,
            password=db_pass,
            db=db_name,
            ip_type=ip_type,
        )
        return conn

    pool = sqlalchemy.create_engine(
        "postgresql+pg8000://",
        creator=getconn,
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


class MockDB:
    """In-memory mock for local development."""
    def __init__(self):
        self._data = {}
        logger.warning("Using In-Memory Mock DB. Data will be lost on restart.")

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, query, params=None):
        # Very simple mock that only handles specific keys if needed, 
        # or we just bypass SQL and use the methods below.
        pass
    
    # Custom methods to mimic the SessionManager logic directly on the mock
    def get_session_data(self, session_id):
        return self._data.get(session_id)

    def upsert_session(self, session_id, domain, target_agent, memory):
        self._data[session_id] = {
            "session_id": session_id,
            "domain": domain,
            "target_agent": target_agent,
            "agent_memory": memory
        }


class SessionManager:
    def __init__(self):
        self.pool = get_pool()

    def get_session(self, session_id: str) -> dict:
        default_session = {
            "session_id": session_id,
            "domain": None,
            "target_agent": "receptionist_agent",
            "agent_memory": {},
            "history": []
        }

        if isinstance(self.pool, MockDB):
            return self.pool.get_session_data(session_id) or default_session

        query = text("SELECT domain, target_agent, agent_memory FROM sessions WHERE session_id = :sid")
        try:
            with self.pool.connect() as conn:
                result = conn.execute(query, {"sid": session_id}).fetchone()
                if result:
                    return {
                        "session_id": session_id,
                        "domain": result[0],
                        "target_agent": result[1],
                        "agent_memory": result[2] if result[2] else {},
                        "history": [] 
                    }
        except Exception as e:
            logger.error(f"DB Read Error: {e}")
        
        return default_session

    def save_session(self, session_id: str, data: dict):
        domain = data.get("domain")
        target_agent = data.get("target_agent")
        memory = json.dumps(data.get("agent_memory", {}))

        if isinstance(self.pool, MockDB):
            self.pool.upsert_session(session_id, domain, target_agent, data.get("agent_memory", {}))
            return

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

    def update_agent_memory(self, session_id: str, new_memory: dict):
        session = self.get_session(session_id)
        current_mem = session.get("agent_memory", {})
        current_mem.update(new_memory)
        session["agent_memory"] = current_mem
        self.save_session(session_id, session)

    def set_target_agent(self, session_id: str, agent_name: str, domain: str = None):
        session = self.get_session(session_id)
        session["target_agent"] = agent_name
        if domain:
            session["domain"] = domain
        self.save_session(session_id, session)
