import json
import threading
from pathlib import Path

import faiss
import numpy as np

import config


class VectorStoreError(RuntimeError):
    """Raised when the persisted FAISS store cannot be read or updated."""


class FaissVectorStore:
    def __init__(self, directory=None, model=None):
        self.directory = Path(directory or config.VECTOR_INDEX_DIR)
        self.model = model or config.EMBEDDING_MODEL
        self.index_path = self.directory / "vectors.faiss"
        self.metadata_path = self.directory / "metadata.json"
        self._lock = threading.RLock()
        self.index = None
        self.records = []
        self.next_id = 1
        if self.index_path.exists() != self.metadata_path.exists():
            raise VectorStoreError(
                "The local vector index is incomplete. Remove its index directory "
                "and restart Pramana to rebuild it."
            )
        if self.index_path.exists():
            self._load()

    def _load(self):
        try:
            self.index = faiss.read_index(str(self.index_path))
            stored = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            if not isinstance(stored, dict) or not isinstance(
                stored.get("records"), list
            ):
                raise VectorStoreError("The FAISS metadata file has an invalid shape.")
            if stored.get("model") != self.model:
                raise VectorStoreError(
                    "The stored FAISS index uses a different embedding model. "
                    "Remove the configured vector index directory to rebuild it."
                )
            self.records = stored["records"]
            if len(self.records) != self.index.ntotal:
                raise VectorStoreError("FAISS vectors and metadata are out of sync.")
            self.next_id = max(
                (record["id"] for record in self.records), default=0
            ) + 1
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            if isinstance(error, VectorStoreError):
                raise
            raise VectorStoreError(
                f"Could not load the local FAISS index: {error}"
            ) from error

    def _persist(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            faiss.write_index(self.index, str(self.index_path))
            self.metadata_path.write_text(
                json.dumps(
                    {"model": self.model, "records": self.records},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except (OSError, TypeError, ValueError) as error:
            raise VectorStoreError(
                f"Could not persist the local FAISS index: {error}"
            ) from error

    def add(self, vectors, records):
        if len(vectors) != len(records) or not vectors:
            raise VectorStoreError("A matching vector and metadata are required.")
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or not np.isfinite(matrix).all():
            raise VectorStoreError("Embeddings must be a finite two-dimensional array.")
        faiss.normalize_L2(matrix)
        with self._lock:
            if self.index is None:
                self.index = faiss.IndexIDMap2(faiss.IndexFlatIP(matrix.shape[1]))
            if matrix.shape[1] != self.index.d:
                raise VectorStoreError(
                    "Embedding dimensions changed; remove the vector index and rebuild it."
                )
            ids = np.arange(
                self.next_id, self.next_id + len(records), dtype=np.int64
            )
            self.index.add_with_ids(matrix, ids)
            self.records.extend(
                {"id": int(record_id), **record}
                for record_id, record in zip(ids, records)
            )
            self.next_id += len(records)
            self._persist()

    def search(self, vector, limit=8):
        query = np.asarray([vector], dtype=np.float32)
        if query.ndim != 2 or not np.isfinite(query).all():
            raise VectorStoreError("The query embedding is invalid.")
        faiss.normalize_L2(query)
        with self._lock:
            if self.index is None or not self.index.ntotal:
                return []
            if query.shape[1] != self.index.d:
                raise VectorStoreError(
                    "The query embedding dimensions do not match the stored FAISS index. "
                    "Remove the configured vector index directory to rebuild it."
                )
            scores, ids = self.index.search(query, min(limit, self.index.ntotal))
            by_id = {record["id"]: record for record in self.records}
            return [
                (float(score), by_id[int(record_id)])
                for score, record_id in zip(scores[0], ids[0])
                if record_id >= 0 and int(record_id) in by_id
            ]

    def remove_document(self, document_id):
        with self._lock:
            remove_ids = np.asarray(
                [
                    record["id"]
                    for record in self.records
                    if record.get("document_id") == document_id
                ],
                dtype=np.int64,
            )
            if not len(remove_ids):
                return False
            self.index.remove_ids(remove_ids)
            self.records = [
                record
                for record in self.records
                if record.get("document_id") != document_id
            ]
            self._persist()
            return True

    def remove_entries(self, entry_ids):
        requested = set(entry_ids)
        with self._lock:
            remove_ids = np.asarray(
                [
                    record["id"]
                    for record in self.records
                    if record.get("entry_id") in requested
                ],
                dtype=np.int64,
            )
            if not len(remove_ids):
                return False
            self.index.remove_ids(remove_ids)
            self.records = [
                record
                for record in self.records
                if record.get("entry_id") not in requested
            ]
            self._persist()
            return True


store = FaissVectorStore()
