"""Evaluación observable del agente en ejecución; no puntúa la corrección factual."""
import argparse
import json
from pathlib import Path
from time import perf_counter
import httpx

CASES = [
    {"name": "docker", "question": "Docker Desktop no inicia en Windows, ¿qué compruebo?", "source": "docker.md"},
    {"name": "logs", "question": "Analiza estos logs de mi contenedor y busca el procedimiento aplicable.",
     "logs": "container stopped: OOMKilled=true, exited code 137", "tool": "analyze_logs", "source": "docker.md"},
    {"name": "escalation", "question": "El servicio falla para varias personas, no tengo permisos. Usa la herramienta para preparar un borrador N2 sin inventar comprobaciones.", "tool": "prepare_escalation"},
    {"name": "missing_context", "question": "No existe procedimiento para mi problema de la impresora; explícame qué información falta y prepara un borrador N2.", "tool": "prepare_escalation"},
]


def evaluate(base_url: str):
    results = []
    with httpx.Client(base_url=base_url, timeout=1200) as client:
        for case in CASES:
            started = perf_counter()
            session_id = None
            result = {"case": case["name"]}
            try:
                response = client.post("/ask", json={k: case[k] for k in ("question", "logs") if k in case})
                response.raise_for_status()
                data = response.json()
                session_id = data["session_id"]
                checks = {"nonempty_answer": bool(data["answer"].strip()), "bounded": not data["limit_reached"]}
                if "tool" in case:
                    checks["expected_tool"] = any(t["tool"] == case["tool"] and t["status"] == "ok" for t in data["trace"])
                if "source" in case:
                    checks["expected_source"] = any(s["source"] == case["source"] for s in data["sources"])
                result.update(passed=all(checks.values()), checks=checks, response=data)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                result.update(passed=False, error=str(exc))
            finally:
                if session_id:
                    try:
                        client.delete("/sessions/" + session_id)
                    except httpx.HTTPError:
                        pass
            result["seconds"] = round(perf_counter() - started, 2)
            results.append(result)
    return {"passed": sum(r["passed"] for r in results), "total": len(results),
            "note": "Estas comprobaciones observan herramientas y fuentes; la calidad y fundamentación deben revisarse manualmente.",
            "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--output", default="eval-report.json")
    args = parser.parse_args()
    report = evaluate(args.url)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Comprobaciones superadas: {report['passed']}/{report['total']}. Informe: {args.output}")
    raise SystemExit(0 if report["passed"] == report["total"] else 1)
