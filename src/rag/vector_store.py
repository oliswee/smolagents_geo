"""ChromaDB vector store operations for suburb report chunks."""
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional
import numpy as np


class VectorStore:
    """Manages ChromaDB collection for suburb analysis report chunks."""

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        collection_name: str = "suburb_reports",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model

        self._client = None
        self._collection = None
        self._model = None

    @property
    def client(self) -> chromadb.PersistentClient:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(anonymized_telemetry=False),
            )
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.embedding_model_name)
        return self._model

    def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for a list of texts."""
        return self.model.encode(texts, show_progress_bar=False)

    def embed_query(self, query: str) -> np.ndarray:
        """Generate embedding for a single query string."""
        return self.model.encode([query], show_progress_bar=False)[0]

    def add_chunks(self, chunks: List[Dict], batch_size: int = 32):
        """Add report chunks to the ChromaDB collection.

        Args:
            chunks: List of dicts with 'text' and 'metadata' keys.
            batch_size: Embedding batch size.
        """
        texts = [c["text"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]
        ids = [
            f"{m['suburb_name']}_{m['dimension']}"
            for m in metadatas
        ]

        # Embed in batches
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            all_embeddings.append(self.embed(batch))

        embeddings = np.concatenate(all_embeddings, axis=0)

        # Add to collection (clear existing first)
        self.collection.delete(ids=ids)
        self.collection.add(
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )
        return len(texts)

    def search(
        self,
        query: str,
        k: int = 5,
        filter_dimension: Optional[str] = None,
    ) -> List[Dict]:
        """Search for the most relevant chunks.

        Args:
            query: Natural language query.
            k: Number of top results to return.
            filter_dimension: Optionally filter by dimension label.

        Returns:
            List of dicts with keys: text, metadata, similarity.
        """
        query_embedding = self.embed_query(query)

        where_filter = None
        if filter_dimension:
            where_filter = {"dimension": filter_dimension}

        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        for i in range(len(results["ids"][0])):
            chunks.append({
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "similarity": 1.0 - results["distances"][0][i],  # cosine → similarity
            })

        return chunks

    def count(self) -> int:
        """Return number of chunks in the collection."""
        return self.collection.count()
