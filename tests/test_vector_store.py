import tempfile
import unittest

from vector_store import FaissVectorStore, VectorStoreError


class FaissVectorStoreTests(unittest.TestCase):
    def test_vectors_and_source_metadata_survive_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FaissVectorStore(directory, "test-embedder")
            store.add(
                [[1.0, 0.0], [0.0, 1.0]],
                [
                    {
                        "kind": "document",
                        "document_id": "doc-a",
                        "filename": "first.txt",
                        "content": "first document",
                    },
                    {
                        "kind": "document",
                        "document_id": "doc-b",
                        "filename": "second.txt",
                        "content": "second document",
                    },
                ],
            )

            restored = FaissVectorStore(directory, "test-embedder")
            results = restored.search([0.0, 1.0], limit=1)

            self.assertEqual(results[0][1]["filename"], "second.txt")
            self.assertEqual(results[0][1]["document_id"], "doc-b")
            self.assertTrue(restored.remove_document("doc-a"))
            self.assertEqual(len(restored.records), 1)

    def test_embedding_model_change_requires_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FaissVectorStore(directory, "first-model")
            store.add([[1.0, 0.0]], [{"kind": "faq", "entry_id": "entry"}])

            with self.assertRaisesRegex(VectorStoreError, "different embedding model"):
                FaissVectorStore(directory, "other-model")

    def test_search_rejects_embedding_dimension_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FaissVectorStore(directory, "test-embedder")
            store.add([[1.0, 0.0]], [{"kind": "faq", "entry_id": "entry"}])

            with self.assertRaisesRegex(VectorStoreError, "dimensions"):
                store.search([1.0, 0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
