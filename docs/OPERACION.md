# Operación e integración

## Componentes y dependencias de ejecución

La aplicación expone una API FastAPI y sirve una interfaz web desde el mismo origen. Ollama ejecuta los modelos; Chroma almacena el índice de los procedimientos. LangGraph coordina la recuperación inicial y el bucle de selección de herramientas.

El servidor necesita conectividad con la dirección `OLLAMA_BASE_URL` y acceso de lectura a `knowledge_base/`. El directorio del índice requiere permisos de escritura. La integración no necesita credenciales de OpenAI.

Las descargas de modelos y paquetes requieren acceso a sus proveedores. Después de la instalación, el procesamiento puede mantenerse local configurando un servidor Ollama local y modelos descargados, sin variantes cloud.

## Configuración

Los valores se leen de variables de entorno y del `.env` situado en la raíz del proyecto. Las variables de entorno prevalecen sobre el archivo. El servidor debe reiniciarse después de cambiar la configuración.

| Variable | Valor predeterminado | Función |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Servidor Ollama |
| `OLLAMA_CHAT_MODEL` | `llama3.2:3b` | Modelo con llamadas a herramientas |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Modelo de embeddings |
| `TOP_K` | `4` | Fragmentos recuperados por búsqueda |
| `MAX_AGENT_ROUNDS` | `4` | Máximo de rondas de decisión por consulta |
| `MAX_TOOL_CALLS` | `10` | Máximo de llamadas elegidas por el agente |
| `SESSION_TTL_SECONDS` | `1800` | Caducidad por inactividad |
| `MAX_SESSIONS` | `50` | Capacidad de conversaciones en memoria |
| `CHROMA_DIR` | `.chroma` en la raíz del proyecto | Directorio persistente del índice |

Para `CHROMA_DIR`, utiliza preferentemente una ruta absoluta o un volumen dedicado. Cambiar la dirección de Ollama también cambia la identidad de la colección para evitar reutilizar embeddings de otro servidor inadvertidamente.

## Arranque

Para desarrollo y revisión funcional:

```powershell
python -m uvicorn app.main:app --reload
```

Para ejecución local sin recarga automática:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Utiliza un único proceso. La memoria de conversaciones y los bloqueos de creación del índice no se comparten entre procesos. La opción `--reload` reinicia el proceso al modificar código y borra las conversaciones activas.

## Comprobaciones del servicio

1. `GET /health`: confirma que la API responde.
2. `GET /ready`: consulta los modelos instalados en Ollama. Un resultado `ready: true` no certifica el funcionamiento de las llamadas a herramientas ni la calidad del modelo.
3. Una consulta sobre un procedimiento conocido verifica la ruta de generación y recuperación.
4. `python scripts/evaluate.py` permite registrar cuatro casos con respuestas, herramientas, fuentes y tiempos para revisión.

No se publican resultados de evaluación con modelos reales como si fueran pruebas unitarias. El script genera sus resultados al ejecutarse en el entorno de destino.

## Contrato de conversación

`POST /ask` acepta `question`, `logs` opcional y `session_id` opcional. La primera consulta crea un identificador UUID. Para mantener el contexto, el cliente debe enviarlo en los turnos siguientes.

Ejemplo para un cliente PowerShell:

```powershell
$requestBody = @{
    question = "Docker Desktop no inicia en Windows. ¿Qué debo comprobar?"
} | ConvertTo-Json

$result = Invoke-RestMethod -Uri "http://localhost:8000/ask" -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($requestBody))
$result.answer

$followUpBody = @{
    question = "Ya he revisado WSL y el fallo continúa. Analiza este mensaje."
    logs = "Cannot connect to the Docker daemon"
    session_id = $result.session_id
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/ask" -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($followUpBody))
```

La respuesta conserva compatibilidad con los campos principales `category`, `answer` y `sources`, y añade `session_id`, `trace`, `escalations` y `limit_reached`.

El identificador no es un mecanismo de autenticación. No debe usarse como sustituto de controles de acceso en una aplicación compartida.

## Tratamiento de datos

| Información | Ubicación y ciclo de vida |
| --- | --- |
| Procedimientos | Archivos Markdown de `knowledge_base/` |
| Índice vectorial | Directorio Chroma; persiste hasta su eliminación |
| Conversaciones | Memoria del proceso; caducidad y recorte por longitud |
| Registro de herramientas | Devuelto al cliente como parte de cada consulta |
| Informe exportado | Archivo JSON descargado por la persona usuaria |
| Informe de evaluación | Archivo local generado por `scripts/evaluate.py` |

Los índices contienen información derivada de los procedimientos y deben protegerse como la documentación de origen. Las colecciones antiguas se conservan cuando cambia la base de conocimiento. Eliminar únicamente un documento de la carpeta no elimina automáticamente sus colecciones anteriores: detén el servidor y elimina o reconstruye el índice cuando sea necesario aplicar una retirada de información.

El filtrado de secretos reconoce algunos patrones habituales, pero no garantiza detectar credenciales ni datos personales en todos los formatos. Los fragmentos de logs deben revisarse antes de enviarlos. Los resultados del LLM y los borradores no se almacenan en una base de tickets ni se envían a terceros por las herramientas actuales.

## Recuperación y mantenimiento

- Conserva una copia de la documentación Markdown antes de realizar cambios amplios.
- El índice puede reconstruirse desde esos documentos; detén el servidor antes de eliminar `.chroma/`.
- Si cambias el modelo de embeddings manteniendo su nombre, reconstruye el índice para evitar mezclar representaciones incompatibles.
- Comprueba las dependencias con `python -m pip check` y ejecuta las pruebas antes de publicar cambios.
- Prueba los prompts y herramientas con el modelo configurado; un cambio de modelo puede alterar sus decisiones aunque las pruebas simuladas sigan pasando.
- La API registra excepciones inesperadas en la terminal; no incorpora un sistema centralizado de observabilidad ni métricas de producción.

## Requisitos para una integración corporativa compartida

El código separa herramientas, grafo, recuperación, sesiones y API para facilitar su evolución. Un despliegue compartido debe incorporar, según el entorno:

- Autenticación, autorización y aislamiento de conversaciones y documentos.
- TLS, límites de solicitudes y protección de la API y del servidor Ollama.
- Persistencia compartida de sesiones y coordinación del índice si hay varios procesos.
- Política de retención y eliminación de documentación, vectores, logs e informes.
- Gestión reproducible de dependencias y modelos, y validación de latencia y consumo de memoria.
- Evaluación funcional de respuestas, fuentes, uso de herramientas y resistencia a instrucciones insertadas en documentos o logs.
- Integración explícita con la herramienta corporativa de tickets, si se requiere. El borrador actual no equivale a un ticket creado.

Estos controles se documentan como requisitos de integración; no se presentan como funcionalidades ya implementadas.
