import os
from pathlib import Path
import json
from unittest.mock import patch
import unittest

import app
import config


class ChatbotRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_homepage_loads(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"id=\"chat-form\"", response.data)
        self.assertIn(b"id=\"user-input-text\"", response.data)
        self.assertIn(b"data-prompt", response.data)
        self.assertIn(b"aria-live=\"polite\"", response.data)
        self.assertIn(b"pramana-current-conversation", response.data)
        self.assertIn(config.BOT_NAME.encode(), response.data)
        self.assertIn(config.BOT_TAGLINE.encode(), response.data)
        self.assertIn(
            f"{config.BOT_NAME} — {config.BOT_TAGLINE}".encode(),
            response.data,
        )

    def test_configured_paths_support_project_relative_and_absolute_values(self):
        relative = config.configured_path(
            "PRAMANA_TEST_PATH", "database/test.json"
        )
        absolute_path = Path(self.id()).resolve()
        with patch.dict(os.environ, {"PRAMANA_TEST_PATH": str(absolute_path)}):
            absolute = config.configured_path(
                "PRAMANA_TEST_PATH", "database/test.json"
            )

        self.assertEqual(relative, config.PROJECT_DIR / "database" / "test.json")
        self.assertEqual(absolute, absolute_path)

    def test_exact_faq_returns_a_dataset_answer(self):
        question = "What is cloud computing?"
        response = self.client.post(
            "/get_response",
            data={"user_input": question},
        )

        self.assertEqual(response.status_code, 200)
        answer = response.get_json()["bot_response"]
        for expected in app.answer_index[app.normalize_text(question)]:
            self.assertIn(expected, answer)

    def test_exact_match_ignores_case_and_punctuation(self):
        response = self.client.post(
            "/get_response",
            data={"user_input": "  WHAT IS CLOUD COMPUTING  "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("cloud computing", response.get_json()["bot_response"].lower())

    def test_ambiguous_exact_question_includes_all_grounded_answers(self):
        question = "What is machine learning?"
        expected_answers = app.answer_index[app.normalize_text(question)]
        response = self.client.post(
            "/get_response",
            data={"user_input": question},
        )
        answer = response.get_json()["bot_response"]

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(expected_answers), 1)
        for expected in expected_answers:
            self.assertIn(expected, answer)

    def test_paraphrased_question_uses_local_ai_with_retrieved_faq(self):
        question = "Could you explain cloud computing in simple words?"
        context_record = {
            "tag": "cloud_computing_intro",
            "patterns": ["What is cloud computing?"],
            "responses": ["Cloud computing provides services over the internet."],
        }
        with (
            patch(
                "app.retrieve_faq_context",
                return_value=[(0.82, context_record)],
            ),
            patch(
                "app.ollama_request",
                return_value={
                    "message": {
                        "content": "Cloud computing provides services over the internet."
                    }
                },
            ) as ollama_request,
        ):
            response = self.client.post(
                "/get_response",
                data={"user_input": question},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("services over the internet", response.get_json()["bot_response"])
        system_prompt = ollama_request.call_args.args[1]["messages"][0]["content"]
        self.assertIn("Cloud computing provides services over the internet.", system_prompt)

    def test_general_question_uses_local_ai_when_no_faq_matches(self):
        with (
            patch("app.retrieve_faq_context", return_value=[]),
            patch(
                "app.ollama_request",
                return_value={
                    "message": {"content": "Photosynthesis converts light into energy."}
                },
            ) as ollama_request,
        ):
            response = self.client.post(
                "/get_response",
                data={"user_input": "Explain photosynthesis simply."},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Photosynthesis", response.get_json()["bot_response"])
        self.assertEqual(ollama_request.call_args.args[0], "/api/chat")

    def test_follow_up_uses_chat_history_for_retrieval_and_generation(self):
        question = "Could you give an example of that?"
        history = [
            {"role": "user", "content": "What is cloud computing?"},
            {
                "role": "assistant",
                "content": "Cloud computing provides services over the internet.",
            },
        ]
        context_record = {
            "tag": "cloud_computing_intro",
            "patterns": ["What is cloud computing?"],
            "responses": ["Cloud computing provides services over the internet."],
        }
        with (
            patch(
                "app.retrieve_faq_context",
                return_value=[(0.82, context_record)],
            ) as retrieve_faq_context,
            patch(
                "app.ollama_request",
                return_value={
                    "message": {"content": "A cloud drive is one example."}
                },
            ) as ollama_request,
        ):
            response = self.client.post(
                "/get_response",
                data={
                    "user_input": question,
                    "conversation_history": json.dumps(history),
                },
            )

        self.assertEqual(response.status_code, 200)
        retrieval_query = retrieve_faq_context.call_args.args[0]
        self.assertIn("What is cloud computing?", retrieval_query)
        self.assertIn(question, retrieval_query)
        messages = ollama_request.call_args.args[1]["messages"]
        self.assertEqual(messages[1:3], history)
        self.assertEqual(messages[-1], {"role": "user", "content": question})

    def test_local_follow_up_uses_previous_local_question_before_abstaining(self):
        history = [
            {"role": "user", "content": "What is Deogiri College's phone number?"},
            {"role": "assistant", "content": "The number is 02402367333."},
        ]
        with (
            patch("app.retrieve_faq_context", return_value=[]) as retrieve_faq_context,
            patch("app.ollama_request") as ollama_request,
        ):
            response = self.client.post(
                "/get_response",
                data={
                    "user_input": "And where is it?",
                    "conversation_history": json.dumps(history),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["bot_response"], app.NO_ANSWER)
        self.assertIn(
            "Deogiri College",
            retrieve_faq_context.call_args.args[0],
        )
        ollama_request.assert_not_called()

    def test_invalid_conversation_history_is_rejected(self):
        response = self.client.post(
            "/get_response",
            data={
                "user_input": "What is cloud computing?",
                "conversation_history": json.dumps(
                    [
                        {"role": "assistant", "content": "Not preceded by a user turn."},
                        {"role": "user", "content": "This role is out of order."},
                    ]
                ),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid message", response.get_json()["error"])

    def test_unknown_local_question_abstains_without_relevant_faq(self):
        with (
            patch("app.retrieve_faq_context", return_value=[]),
            patch("app.ollama_request") as ollama_request,
        ):
            response = self.client.post(
                "/get_response",
                data={
                    "user_input": (
                        "What are the opening hours of Ziba Dental in Aurangabad?"
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["bot_response"], app.NO_ANSWER)
        ollama_request.assert_not_called()

    def test_local_ai_failure_is_reported_as_service_unavailable(self):
        with (
            patch("app.retrieve_faq_context", return_value=[]),
            patch(
                "app.ollama_request",
                side_effect=app.LocalAIUnavailable("Ollama is not running."),
            ),
        ):
            response = self.client.post(
                "/get_response",
                data={"user_input": "Explain photosynthesis simply."},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Ollama is not running", response.get_json()["error"])

    def test_legacy_general_faq_is_in_retrieval_corpus(self):
        self.assertGreater(len(app.retrieval_records), len(app.data["intents"]))
        self.assertTrue(
            any("python_programming" in record["tag"] for record in app.retrieval_records)
        )

    def test_verified_local_listings_have_required_provenance_and_are_deduplicated(self):
        listings = app.legacy_data["verified_local_listings"]

        self.assertEqual(len(listings), 88)
        names = [app.normalize_text(listing["name"]) for listing in listings]
        self.assertEqual(len(names), len(set(names)))
        department_listings = [
            item for item in listings if item["category"] == "university department"
        ]
        self.assertEqual(len(department_listings), 33)
        for listing in listings:
            with self.subTest(listing=listing["name"]):
                self.assertTrue(listing["address"])
                self.assertTrue(listing["phone"])
                self.assertTrue(
                    any(
                        listing["source_url"].startswith(prefix)
                        for prefix in app.OFFICIAL_SOURCE_PREFIXES
                    )
                )
                self.assertRegex(listing["verified_on"], r"^\d{4}-\d{2}-\d{2}$")

    def test_bamu_department_contact_has_phone_email_and_official_source(self):
        listing = next(
            item
            for item in app.legacy_data["verified_local_listings"]
            if item["name"] == "BAMU Department of Chemistry"
        )
        answer = app.chat(
            "How can I contact the BAMU Department of Chemistry?"
        )

        self.assertIn(listing["phone"], answer)
        self.assertIn(listing["email"], answer)
        self.assertIn(listing["address"], answer)
        self.assertIn(listing["source_url"], answer)

    def test_bamu_department_directory_question_lists_all_33_departments(self):
        departments = [
            item
            for item in app.legacy_data["verified_local_listings"]
            if item["category"] == "university department"
        ]

        answer = app.chat("List all BAMU university departments with contact details.")

        for department in departments:
            with self.subTest(department=department["name"]):
                self.assertIn(department["name"], answer)
                self.assertIn(department["phone"], answer)

    def test_verified_local_listing_answers_exact_contact_question(self):
        listing = next(
            item
            for item in app.legacy_data["verified_local_listings"]
            if item["name"] == "AIMS Hospital"
        )
        question = f"What is the address and phone number for {listing['name']}?"

        answer = app.chat(question)

        self.assertIn(listing["address"], answer)
        self.assertIn(listing["phone"], answer)
        self.assertIn(listing["source_url"], answer)

        record = next(
            item
            for item in app.retrieval_records
            if listing["name"] in " ".join(item["patterns"])
        )
        context = app.format_faq_context([(0.9, record)])
        self.assertIn(listing["source_url"], context)
        self.assertIn(listing["verified_on"], context)

    def test_unverified_legacy_local_intents_remain_excluded(self):
        legacy_only_pattern = app.normalize_text(
            "Tell me about Great Sagar Restaurant in restaurant,hotels."
        )
        retrieved_patterns = {
            app.normalize_text(pattern)
            for record in app.retrieval_records
            for pattern in record["patterns"]
        }
        legacy_local_patterns = {
            app.normalize_text(pattern)
            for intent in app.legacy_data["intents"]
            if app.is_local_intent(intent)
            for pattern in intent.get("patterns", [])
        }

        self.assertIn(legacy_only_pattern, legacy_local_patterns)
        self.assertNotIn(legacy_only_pattern, retrieved_patterns)

    def test_cosine_similarity_handles_matching_and_zero_vectors(self):
        self.assertAlmostEqual(app.cosine_similarity([1, 0], [1, 1]), 0.7071, places=4)
        self.assertEqual(app.cosine_similarity([0, 0], [1, 0]), 0.0)

    def test_semantic_retrieval_returns_similar_faq_records(self):
        app._embedding_index = None

        def fake_embedding_request(endpoint, payload):
            self.assertEqual(endpoint, "/api/embed")
            inputs = payload["input"]
            if isinstance(inputs, str):
                inputs = [inputs]
            return {
                "embeddings": [
                    [1.0, 0.0] if "cloud" in text.casefold() else [0.0, 1.0]
                    for text in inputs
                ]
            }

        try:
            with patch("app.ollama_request", side_effect=fake_embedding_request):
                matches = app.retrieve_faq_context("Explain cloud technology.")
        finally:
            app._embedding_index = None

        self.assertTrue(matches)
        self.assertIn("cloud", " ".join(matches[0][1]["patterns"]).casefold())
        self.assertEqual(matches[0][0], 1.0)

    def test_semantic_retrieval_deduplicates_identical_answers(self):
        question = "Give me a paraphrased cloud explanation."
        first_record = {
            "tag": "cloud_intro",
            "patterns": ["What is cloud computing?"],
            "responses": ["Cloud services are delivered online."],
        }
        duplicate_record = {
            "tag": "technology_faq",
            "patterns": ["How does cloud computing work?"],
            "responses": ["Cloud services are delivered online."],
        }
        vector = [1.0, 0.0]
        with (
            patch(
                "app.ollama_request",
                return_value={"embeddings": [vector]},
            ),
            patch(
                "app.embedding_index",
                return_value=[(vector, first_record), (vector, duplicate_record)],
            ),
        ):
            matches = app.retrieve_faq_context(question)

        self.assertEqual(len(matches), 1)
        self.assertIs(matches[0][1], first_record)

    def test_unmatched_local_faq_question_abstains_instead_of_guessing(self):
        with patch("app.retrieve_faq_context", return_value=[]):
            response = self.client.post(
                "/get_response",
                data={"user_input": "Where can I eat in Aurangabad?"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["bot_response"], app.NO_ANSWER)

    def test_placeholder_question_does_not_return_template_as_fact(self):
        response = self.client.post(
            "/get_response",
            data={"user_input": "Tell me more about [office_name]"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["bot_response"], app.NO_ANSWER)
        self.assertNotIn("[", response.get_json()["bot_response"])

    def test_every_dataset_pattern_returns_only_its_grounded_answers(self):
        for intent in app.data["intents"]:
            for question in intent["patterns"]:
                key = app.normalize_text(question)
                expected_answers = app.answer_index.get(key, [])
                answer = app.chat(question)

                with self.subTest(question=question):
                    if not expected_answers:
                        self.assertEqual(answer, app.NO_ANSWER)
                    else:
                        for expected in expected_answers:
                            self.assertIn(expected, answer)
                        self.assertNotIn("[", answer)

    def test_empty_input_is_rejected(self):
        response = self.client.post(
            "/get_response",
            data={"user_input": "   "},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()
