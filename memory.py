"""
memory.py — Short-Term & Long-Term Memory Management
======================================================
- **Short-term**: In-memory dict of the last N messages per session.
- **Long-term**: ChromaDB-backed vector store for RAG retrieval.
  Embeds every user/assistant message and retrieves semantically
  relevant context before each LLM call.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

from config import settings
from schemas import Message

logger = logging.getLogger(__name__)

# ============================================================
# Short-Term Memory  (last N messages per session)
# ============================================================

class ShortTermMemory:
    """
    Ring-buffer style chat history keyed by session_id.
    Thread-safe enough for async single-process use (GIL).
    """

    def __init__(self, limit: int = settings.short_term_memory_limit) -> None:
        self._limit = limit
        self._store: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def add(self, session_id: str, message: Message) -> None:
        """Append a message and trim to the limit."""
        self._store[session_id].append(message.model_dump())
        if len(self._store[session_id]) > self._limit:
            self._store[session_id] = self._store[session_id][-self._limit :]
        logger.debug("STM add session=%s len=%d", session_id, len(self._store[session_id]))

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Return the full short-term history for a session."""
        return list(self._store[session_id])

    def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)


# ============================================================
# Long-Term Memory  (ChromaDB vector store + RAG)
# ============================================================

class LongTermMemory:
    """
    Stores every message in a per-session ChromaDB collection.
    At query time, retrieves the top-k most relevant past exchanges
    to inject as context into the LLM prompt.
    """

    def __init__(
        self,
        persist_dir: str = settings.chroma_persist_dir,
        embedding_model: str = settings.embedding_model,
    ) -> None:
        self._persist_dir = persist_dir
        self._embedding_model_name = embedding_model
        self._client: Any = None
        self._embedding_fn: Any = None

    # ---- Lazy initialisation (heavy imports deferred) ----

    def _ensure_client(self) -> None:
        """Create the ChromaDB client on first use."""
        if self._client is not None:
            return
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self._client = chromadb.Client(
                ChromaSettings(
                    anonymized_telemetry=False,
                    is_persistent=True,
                    persist_directory=self._persist_dir,
                )
            )
            logger.info("ChromaDB client initialised (persist_dir=%s)", self._persist_dir)
        except Exception as exc:
            logger.error("Failed to initialise ChromaDB: %s", exc)
            raise

    def _ensure_embedding_fn(self) -> None:
        """Load the sentence-transformer model on first use."""
        if self._embedding_fn is not None:
            return
        try:
            from chromadb.utils import embedding_functions

            self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self._embedding_model_name,
            )
            logger.info("Embedding model loaded: %s", self._embedding_model_name)
        except Exception as exc:
            logger.error("Failed to load embedding model: %s", exc)
            raise

    def _get_collection(self, session_id: str) -> Any:
        """Return (or create) the ChromaDB collection for a session."""
        self._ensure_client()
        self._ensure_embedding_fn()
        # Collection names must be 3-63 chars, alphanumeric + underscores
        safe_name = f"session_{session_id.replace('-', '_')[:50]}"
        return self._client.get_or_create_collection(
            name=safe_name,
            embedding_function=self._embedding_fn,
        )

    # ---- Public API ----

    def add(self, session_id: str, message: Message) -> None:
        """
        Embed and store a message in the vector collection.
        """
        try:
            collection = self._get_collection(session_id)
            doc_id = str(uuid.uuid4())
            collection.add(
                ids=[doc_id],
                documents=[message.content],
                metadatas=[{"role": message.role}],
            )
            logger.debug(
                "LTM add session=%s role=%s len=%d", session_id, message.role, len(message.content)
            )
        except Exception as exc:
            logger.error("LTM add failed session=%s: %s", session_id, exc)

    def search_relevant(
        self, session_id: str, query: str, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the top-k most semantically relevant past messages
        for a given query string.
        """
        try:
            collection = self._get_collection(session_id)
            if collection.count() == 0:
                return []
            results = collection.query(query_texts=[query], n_results=min(top_k, collection.count()))
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            return [
                {"role": m.get("role", "user"), "content": d}
                for d, m in zip(docs, metas)
            ]
        except Exception as exc:
            logger.error("LTM search failed session=%s: %s", session_id, exc)
            return []


# ============================================================
# Unified Memory Manager
# ============================================================

class MemoryManager:
    """
    Combines short-term and long-term memory.
    Call ``add_message()`` after every exchange and
    ``build_context()`` before calling the LLM.
    """

    def __init__(self) -> None:
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory()

    def add_message(self, session_id: str, message: Message) -> None:
        """Store a message in both memory tiers."""
        self.short_term.add(session_id, message)
        self.long_term.add(session_id, message)

    def build_context(
        self,
        session_id: str,
        current_messages: List[Message],
        rag_query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build the full message list for the LLM:
        1. Retrieve relevant long-term context via RAG.
        2. Prepend it as a system message.
        3. Append the short-term history.
        4. Append the current user messages.
        """
        context: List[Dict[str, Any]] = []

        # --- RAG context ---
        if rag_query:
            relevant = self.long_term.search_relevant(session_id, rag_query)
            if relevant:
                rag_text = "\n".join(
                    f"[{r['role']}]: {r['content']}" for r in relevant
                )
                context.append({
                    "role": "system",
                    "content": (
                        "The following is relevant context from previous conversations:\n"
                        f"{rag_text}\n\nUse this context to inform your response."
                    ),
                })

        # --- Short-term history ---
        history = self.short_term.get_history(session_id)
        context.extend(history)

        # --- Current turn ---
        for msg in current_messages:
            context.append(msg.model_dump())

        return context

    def clear_session(self, session_id: str) -> None:
        """Wipe all memory for a session."""
        self.short_term.clear(session_id)
        logger.info("Memory cleared for session=%s", session_id)
