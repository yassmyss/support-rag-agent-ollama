# Contribuir

Usa Python 3.12 y un entorno virtual independiente. Instala `requirements.txt`.
Antes de proponer cambios, ejecuta `python -m pip check` y `python -m pytest -q`.
Las pruebas automatizadas no necesitan Ollama: utilizan modelos y embeddings de prueba.

Al cambiar prompts o herramientas, prueba también `python scripts/evaluate.py` con la API y Ollama arrancados.
Revisa manualmente la respuesta, sus fuentes, las preguntas de aclaración y los borradores N2.
No publiques `.env`, logs reales con datos personales, contraseñas, índices o historiales.
Mantén los procedimientos documentados, las herramientas acotadas y el README coherente con el comportamiento.
