import hashlib
import json
from pathlib import Path
from threading import Lock

from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings

KB_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"
INDEX_LOCK = Lock()
CHUNK_SIZE = 700
CHUNK_OVERLAP = 120


def load_documents() -> list[Document]:
    documents = [
        Document(page_content=p.read_text(encoding="utf-8"), metadata={"source": p.name})
        for p in sorted(KB_DIR.glob("*.md"))
        if p.is_file() and not p.is_symlink() and p.read_text(encoding="utf-8").strip()
    ]
    if not documents:
        raise RuntimeError("La carpeta knowledge_base no contiene documentos Markdown.")
    return documents


def build_retriever():
    settings = get_settings()
    documents = load_documents()
    fingerprint = hashlib.sha256(json.dumps({
        "documents": [(d.metadata["source"], d.page_content) for d in documents],
        "embedding_model": settings.ollama_embedding_model,
        "embedding_endpoint": settings.ollama_base_url,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    chunks = splitter.split_documents(documents)
    ids = [f"{fingerprint}-{i}" for i in range(len(chunks))]
    # Serializa la creación en el servidor local y permite reanudar un índice parcial.
    with INDEX_LOCK:
        store = Chroma(
            collection_name=f"support_{fingerprint[:24]}",
            embedding_function=OllamaEmbeddings(
                model=settings.ollama_embedding_model,
                base_url=settings.ollama_base_url,
                client_kwargs={"timeout": 180.0},
            ),
            persist_directory=str(settings.chroma_dir),
            client_settings=ChromaSettings(anonymized_telemetry=False),
        )
        existing = set(store.get()["ids"])
        missing = [(i, chunk) for i, chunk in enumerate(chunks) if ids[i] not in existing]
        if missing:
            store.add_documents(
                [chunk for _, chunk in missing], ids=[ids[i] for i, _ in missing]
            )
    return store.as_retriever(search_kwargs={"k": settings.top_k})
