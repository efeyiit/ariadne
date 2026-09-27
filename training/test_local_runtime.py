"""Passage selection never lets model output invent source coordinates or quotes."""

import json
import unittest

from local_runtime_server import Rejected, Runtime


EVIDENCE = [{"id": "E1", "path": "src/example.py", "start_line": 1,
             "end_line": 2, "commit_sha": "a" * 40,
             "text": "def answer():\n    return 42\n"}]
REQUEST = {"instructions": "Cite exact source lines.",
           "question": "What does answer return?", "evidence": EVIDENCE}
VALID = '{"claims":[{"text":"answer returns 42","passage_id":"P01"}]}'


class PassageSelectionTests(unittest.TestCase):
    def test_local_content_identity_is_accepted_without_fake_commit(self):
        runtime = Runtime.__new__(Runtime)
        runtime._generate = lambda messages: VALID
        request = dict(REQUEST, evidence=[dict(EVIDENCE[0], commit_sha="local:" + "b" * 64)])
        self.assertTrue(runtime.answer(request)["claims"])
        for invalid in ("x" * 40, "local:" + "b" * 40, "local:" + "z" * 64):
            with self.subTest(identity=invalid), self.assertRaises(Rejected):
                runtime.answer(dict(REQUEST, evidence=[dict(EVIDENCE[0], commit_sha=invalid)]))

    def test_server_derives_exact_quote_and_coordinates(self):
        passages = Runtime._passages(EVIDENCE)
        output = Runtime._check_selection(VALID, passages)
        citation = output["claims"][0]["citations"][0]
        self.assertEqual(citation, {"evidence_id": "E1", "start_line": 1,
                                    "end_line": 2,
                                    "quote": "def answer():\n    return 42"})

    def test_unknown_and_conflicting_ids_reject(self):
        passages = Runtime._passages(EVIDENCE)
        for claims in (
            [{"text": "wrong", "passage_id": "P99"}],
            [{"text": "wrong", "passage_id": "P01", "quote": "fake"}],
        ):
            with self.subTest(claims=claims), self.assertRaises(Rejected):
                Runtime._check_selection(json.dumps({"claims": claims}), passages)
        with self.assertRaises(Rejected):
            Runtime._check_selection(
                '{"claims":[],"claims":[{"text":"a","passage_id":"P01"}]}',
                passages)

    def test_distinct_claims_can_share_exact_source_without_repair(self):
        runtime = Runtime.__new__(Runtime)
        calls = []
        raw = json.dumps({"claims": [
            {"text": "answer is a function", "passage_id": "P01"},
            {"text": "answer returns 42", "passage_id": "P01"},
        ]})
        def generate(messages):
            calls.append(messages)
            return raw
        runtime._generate = generate
        result = runtime.answer(REQUEST)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(result["claims"]), 2)
        for claim in result["claims"]:
            self.assertEqual(claim["citations"][0], {
                "evidence_id": "E1", "start_line": 1, "end_line": 2,
                "quote": "def answer():\n    return 42"})

    def test_shared_passage_does_not_allow_unknown_second_citation(self):
        raw = json.dumps({"claims": [
            {"text": "answer returns 42", "passage_id": "P01"},
            {"text": "another claim", "passage_id": "P99"},
        ]})
        with self.assertRaises(Rejected):
            Runtime._check_selection(raw, Runtime._passages(EVIDENCE))

    def test_valid_abstention_does_not_retry_into_an_invented_answer(self):
        runtime = Runtime.__new__(Runtime)
        calls = []
        def generate(messages):
            calls.append(messages)
            return '{"claims":[]}'
        runtime._generate = generate
        self.assertEqual(runtime.answer(REQUEST), {"claims": []})
        self.assertEqual(len(calls), 1)

    def test_one_repair_accepts_valid_second_generation(self):
        runtime = Runtime.__new__(Runtime)
        replies = iter(("not json", VALID))
        calls = []

        def generate(messages):
            calls.append(messages)
            return next(replies)

        runtime._generate = generate
        result = runtime.answer(REQUEST)
        self.assertEqual(result["claims"][0]["citations"][0]["quote"],
                         "def answer():\n    return 42")
        self.assertEqual(len(calls), 2)

    def test_two_invalid_generations_reject_without_fallback(self):
        runtime = Runtime.__new__(Runtime)
        calls = []

        def generate(messages):
            calls.append(messages)
            return "not json"

        runtime._generate = generate
        with self.assertRaises(Rejected):
            runtime.answer(REQUEST)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
