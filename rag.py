import hashlib
import math

from documents import DocumentError, chunk_text, extract_units
from vector_store import store

EMBEDDING_BATCH_SIZE = 64


class RagError(RuntimeError):
    """Raised when embedding or indexing knowledge-base content fails."""


def embed_texts(texts, embedding_request):
    vectors = []
    for offset in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[offset : offset + EMBEDDING_BATCH_SIZE]
        response = embedding_request(
            "/api/embed",
            {"model": store.model, "input": batch},
        )
        embedded = response.get("embeddings")
        if not isinstance(embedded, list) or len(embedded) != len(batch):
            raise RagError("The local embedding model returned an invalid result.")
        for vector in embedded:
            if (
                not isinstance(vector, list)
                or not vector
                or not all(
                    isinstance(value, (int, float))
                    and math.isfinite(value)
                    for value in vector
                )
            ):
                raise RagError("The local embedding model returned an invalid vector.")
            vectors.append(vector)
    return vectors


def ensure_faq_index(records, embedding_request):
    current_entries = {}
    new_entries = []
    for record in records:
        for pattern in record["patterns"]:
            entry_id = hashlib.sha256(
                (pattern + "\0" + "\0".join(record["responses"])).encode("utf-8")
            ).hexdigest()
            current_entries[entry_id] = {
                "entry_id": entry_id,
                "kind": "faq",
                "pattern": pattern,
                "record": record,
            }
    existing = {
        item.get("entry_id")
        for item in store.records
        if item.get("kind") == "faq"
    }
    store.remove_entries(existing - current_entries.keys())
    new_entries = [
        entry
        for entry_id, entry in current_entries.items()
        if entry_id not in existing
    ]
    if not new_entries:
        return
    vectors = embed_texts(
        [entry["pattern"] for entry in new_entries], embedding_request
    )
    store.add(vectors, new_entries)


def retrieve(query, embedding_request, limit=8):
    query_vector = embed_texts([query], embedding_request)[0]
    return store.search(query_vector, limit=limit)


def ingest_files(files, embedding_request):
    imported = []
    errors = []
    for filename, payload, document_id in files:
        try:
            units = extract_units(filename, payload)
            chunks = [
                (location, text)
                for location, unit in units
                for text in chunk_text(unit)
            ]
            if not chunks:
                raise DocumentError(
                    f"No searchable text was found in '{filename}'."
                )
            vectors = embed_texts(
                [text for _, text in chunks], embedding_request
            )
            store.add(
                vectors,
                [
                    {
                        "kind": "document",
                        "document_id": document_id,
                        "filename": filename,
                        "location": location,
                        "content": text,
                    }
                    for location, text in chunks
                ],
            )
            imported.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "chunks": len(chunks),
                }
            )
        except (DocumentError, RagError, OSError, ValueError) as error:
            errors.append({"filename": filename, "error": str(error)})
    return {"imported": imported, "errors": errors}


def list_documents():
    documents = {}
    for record in store.records:
        if record.get("kind") != "document":
            continue
        document_id = record["document_id"]
        document = documents.setdefault(
            document_id,
            {
                "document_id": document_id,
                "filename": record["filename"],
                "chunks": 0,
            },
        )
        document["chunks"] += 1
    return sorted(documents.values(), key=lambda item: item["filename"].casefold())
