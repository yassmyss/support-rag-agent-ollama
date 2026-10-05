"""Herramientas de consulta: no ejecutan comandos ni envían tickets."""
import re
from typing import Literal
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from app import rag


def redact(text: str) -> str:
    text = re.sub(r'(?i)(bearer\s+)\S+', r'\1[REDACTADO]', text)
    text = re.sub(r'sk-[A-Za-z0-9_-]{10,}', '[REDACTADO]', text)
    return re.sub(r'''(?i)((?:password|passwd|pwd|api[_-]?key|token|secret)\s*[=:]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)''', r'\1[REDACTADO]', text)


class SearchInput(BaseModel):
    query: str = Field(min_length=3, max_length=2000)


@tool(args_schema=SearchInput)
def search_knowledge(query: str) -> dict:
    """Busca procedimientos por significado en la base local. Úsala para fundamentar recomendaciones o ampliar una búsqueda."""
    docs = rag.build_retriever().invoke(query)
    return {'documents': [{'source': d.metadata.get('source', 'unknown'), 'excerpt': d.page_content} for d in docs]}


class ReadInput(BaseModel):
    source: str = Field(min_length=1, max_length=100)


@tool(args_schema=ReadInput)
def read_procedure(source: str) -> dict:
    """Lee un procedimiento completo citado en fuentes, por ejemplo docker.md. No admite rutas externas."""
    allowed = {p.name: p for p in rag.KB_DIR.glob('*.md') if p.is_file() and not p.is_symlink()}
    if source not in allowed:
        return {'error': 'Documento no permitido o inexistente.', 'available': sorted(allowed)}
    return {'documents': [{'source': source, 'excerpt': allowed[source].read_text(encoding='utf-8')[:12000]}]}


class LogInput(BaseModel):
    log_text: str = Field(min_length=1, max_length=12000)


@tool(args_schema=LogInput)
def analyze_logs(log_text: str) -> dict:
    """Identifica patrones conocidos en logs aportados. Devuelve indicios, no causas confirmadas. No lee el equipo."""
    text = redact(log_text)
    rules = [
        (r'(?i)no space left|disk full|espacio.*insuficiente', 'storage', 'Espacio en disco insuficiente', 'storage.md'),
        (r'(?i)could not resolve|name.*not.*resolved|nxdomain|dns.*fail', 'network', 'Posible fallo DNS', 'network.md'),
        (r'(?i)connection refused|conexión rechazada', 'network', 'Conexión rechazada; comprobar servicio y puerto', 'network.md'),
        (r'(?i)timeout|timed out', 'network', 'Tiempo agotado; no identifica por sí solo la causa', 'network.md'),
        (r'(?i)password authentication failed|pg_hba', 'database', 'Indicio de autenticación o configuración PostgreSQL', 'postgresql.md'),
        (r'(?i)oomkilled|out of memory|exit(?:ed)?(?: code)?[ :]+137', 'containers', 'Indicio de falta de memoria; código 137 también puede ser terminación externa', 'docker.md'),
        (r'(?i)cannot connect to.*docker|docker daemon.*not', 'containers', 'No se puede conectar con el servicio Docker', 'docker.md'),
        (r'(?i)permission denied|access denied', 'permissions', 'Acceso denegado; comprobar permisos sin modificarlos automáticamente', 'escalation.md'),
    ]
    findings = []
    for pattern, category, meaning, source in rules:
        evidence = next((line[:240] for line in text.splitlines() if re.search(pattern, line)), None)
        if evidence:
            findings.append({'category': category, 'indication': meaning, 'evidence': evidence, 'procedure': source})
    return {'findings': findings, 'matched': bool(findings), 'note': 'Son indicios del texto aportado; solicita contexto si no hay coincidencias.'}


class EscalationInput(BaseModel):
    summary: str = Field(min_length=3, max_length=1000)
    reason: str = Field(min_length=3, max_length=1000)
    impact: Literal['unknown', 'one_user', 'multiple_users', 'critical_service'] = 'unknown'
    checks: list[str] = Field(default_factory=list, max_length=12)
    missing_information: list[str] = Field(default_factory=list, max_length=12)


@tool(args_schema=EscalationInput)
def prepare_escalation(summary: str, reason: str, impact: str = 'unknown', checks: list[str] | None = None, missing_information: list[str] | None = None) -> dict:
    """Prepara un borrador N2 si falta contexto o se requieren permisos. No envía tickets. No inventes comprobaciones realizadas."""
    return {'escalation': {'summary': redact(summary), 'reason': redact(reason), 'impact': impact,
                          'priority': 'high' if impact in {'multiple_users', 'critical_service'} else 'normal',
                          'checks': [redact(x[:1000]) for x in (checks or [])],
                          'missing_information': [redact(x[:1000]) for x in (missing_information or [])], 'status': 'draft'}}


TOOLS = [search_knowledge, read_procedure, analyze_logs, prepare_escalation]
TOOL_MAP = {t.name: t for t in TOOLS}
