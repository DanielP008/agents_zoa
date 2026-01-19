import os
import json

# Simula Postgres con un dict en memoria por ahora (o usa SQLAlchemy si prefieres real)
# En prod, cambiar esto por psycopg2 / sqlalchemy
_DB = {}

class SessionManager:
    def __init__(self):
        self.db = _DB

    def get_session(self, session_id: str) -> dict:
        return self.db.get(session_id, {
            "session_id": session_id,
            "domain": None,
            "target_agent": "receptionist_agent",
            "agent_memory": {},
            "history": []
        })

    def save_session(self, session_id: str, data: dict):
        self.db[session_id] = data

    def update_agent_memory(self, session_id: str, new_memory: dict):
        session = self.get_session(session_id)
        session["agent_memory"].update(new_memory)
        self.save_session(session_id, session)

    def set_target_agent(self, session_id: str, agent_name: str, domain: str = None):
        session = self.get_session(session_id)
        session["target_agent"] = agent_name
        if domain:
            session["domain"] = domain
        self.save_session(session_id, session)
