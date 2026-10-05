"""Memoria en RAM con caducidad, capacidad y exclusión por conversación."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from uuid import uuid4
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from app.config import get_settings
from app.tools import redact


@dataclass
class Session:
    history: list = field(default_factory=list)
    updated: float = field(default_factory=monotonic)
    busy: bool = False


class SessionStore:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self.lock = Lock()

    @contextmanager
    def conversation(self, session_id: str | None):
        settings = get_settings()
        with self.lock:
            now = monotonic()
            self.sessions = {key: value for key, value in self.sessions.items()
                             if value.busy or now - value.updated < settings.session_ttl_seconds}
            if session_id and session_id not in self.sessions:
                raise HTTPException(404, "La conversación no existe o ha caducado. Inicia una nueva.")
            if not session_id:
                if len(self.sessions) >= settings.max_sessions:
                    raise HTTPException(503, "Se ha alcanzado el límite de conversaciones. Cierra una o espera a que caduque.")
                session_id = str(uuid4())
                self.sessions[session_id] = Session()
            session = self.sessions[session_id]
            if session.busy:
                raise HTTPException(409, "Esta conversación ya está procesando una consulta.")
            session.busy = True
        try:
            yield session_id, session
        finally:
            with self.lock:
                session.busy = False
                session.updated = monotonic()
                if not session.history:
                    self.sessions.pop(session_id, None)

    def append(self, session, question: str, logs: str, answer: str):
        content = redact(question + ("\nLogs: " + logs if logs else ""))[:6000]
        session.history.extend([HumanMessage(content=content), AIMessage(content=answer[:6000])])
        session.history = session.history[-12:]
        while len(session.history) > 2 and sum(len(m.content) for m in session.history) > 8000:
            session.history = session.history[2:]

    def delete(self, session_id: str):
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                raise HTTPException(404, "Conversación inexistente.")
            if session.busy:
                raise HTTPException(409, "Espera a que termine la consulta antes de cerrar la conversación.")
            del self.sessions[session_id]


sessions = SessionStore()
