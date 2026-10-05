import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from ollama import ResponseError

from app.graph import support_graph
from app.config import get_settings
from app.sessions import sessions
from app.schemas import AskRequest, AskResponse, Source

logger = logging.getLogger(__name__)
app = FastAPI(
    title="SupportRAG Agent · Ollama",
    version="2.0.0",
    description="Asistente local de soporte técnico con recuperación de documentos.",
)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    # Comprueba la API; no carga modelos ni certifica que Ollama esté disponible.
    return {"status": "ok", "provider": "ollama"}


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    try:
        with sessions.conversation(str(payload.session_id) if payload.session_id else None) as (session_id, session):
            result = support_graph.invoke({"question": payload.question, "logs": payload.logs,
                                           "history": list(session.history)}, {"recursion_limit": 40})
            response = AskResponse(
                category=result.get("category", "general"), answer=result["answer"],
                sources=[Source(source=d["source"], excerpt=d["excerpt"][:800]) for d in result.get("sources", [])],
                session_id=session_id, trace=result.get("trace", []),
                escalations=result.get("escalations", []), limit_reached=result.get("limit_reached", False))
            sessions.append(session, payload.question, payload.logs, result["answer"])
            return response
    except HTTPException:
        raise
    except (httpx.ConnectError, ConnectionError) as exc:
        raise HTTPException(503, "No se puede conectar con Ollama. Abre Ollama y comprueba OLLAMA_BASE_URL.") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "Ollama ha tardado demasiado. Prueba un modelo más pequeño o vuelve a intentarlo.") from exc
    except ResponseError as exc:
        message = (
            "Falta un modelo local. Ejecuta ollama pull llama3.2:3b y ollama pull nomic-embed-text, o descarga los modelos de tu .env."
            if exc.status_code == 404 else "Ollama no ha podido procesar la consulta. Usa un modelo local compatible con herramientas como llama3.2:3b y revisa su estado."
        )
        raise HTTPException(503, message) from exc
    except Exception as exc:
        logger.exception("Error al procesar la consulta local")
        raise HTTPException(500, "No se ha podido procesar la consulta. Revisa la terminal del servidor.") from exc


@app.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str):
    sessions.delete(session_id)


@app.get("/ready")
def ready():
    """Verifica conexión y presencia de modelos sin generar texto."""
    settings = get_settings()
    try:
        response = httpx.get(settings.ollama_base_url.rstrip("/") + "/api/tags", timeout=5)
        response.raise_for_status()
        names = {m["name"] for m in response.json().get("models", [])}
        expected = [settings.ollama_chat_model, settings.ollama_embedding_model]
        missing = [name for name in expected if name not in names and name + ":latest" not in names]
        return {"ready": not missing, "missing_models": missing,
                "chat_model": settings.ollama_chat_model, "embedding_model": settings.ollama_embedding_model}
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(503, "No se puede consultar Ollama. Comprueba que está abierto y la dirección configurada.")
