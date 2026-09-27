"""Passage selection never lets model output invent source coordinates or quotes."""

import json
import unittest
from unittest.mock import patch

from local_runtime_server import Rejected, Runtime


EVIDENCE = [{"id": "E1", "path": "src/example.py", "start_line": 1,
             "end_line": 2, "commit_sha": "a" * 40,
             "text": "def answer():\n    return 42\n"}]
REQUEST = {"instructions": "Cite exact source lines.",
           "question": "What does answer return?", "evidence": EVIDENCE}
VALID = '{"claims":[{"text":"answer returns 42","passage_id":"P01"}]}'


class PassageSelectionTests(unittest.TestCase):
    def setUp(self):
        # These tests exercise formatting and citations independently of drafting.
        draft = patch.object(Runtime, '_draft_answer', return_value='answer returns 42', create=True)
        draft.start()
        self.addCleanup(draft.stop)

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

    def test_cross_file_claim_has_multiple_server_derived_citations(self):
        passages = Runtime._passages(EVIDENCE + [dict(EVIDENCE[0], id='E2', path='other.py')])
        raw = json.dumps({'claims':[{'text':'Both files define answer.', 'passage_ids':['P01','P02']}]})
        output = Runtime._check_selection(raw, passages)
        self.assertEqual([c['evidence_id'] for c in output['claims'][0]['citations']], ['E1','E2'])
        for invalid in ([], ['P01','P99'], ['P01','P01'], ['P01'] * 4, 'P01'):
            with self.subTest(ids=invalid), self.assertRaises(Rejected):
                Runtime._check_selection(json.dumps({'claims':[{'text':'x','passage_ids':invalid}]}), passages)

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

    def test_repair_receives_failed_selection_and_validation_error(self):
        runtime = Runtime.__new__(Runtime)
        evidence = EVIDENCE + [dict(EVIDENCE[0], id='E2', path='other.py')]
        bad = json.dumps({'claims': [{'text': 'src/example.py and other.py define answer.', 'passage_ids': ['P99']}]})
        good = bad.replace('["P99"]', '["P01", "P02"]')
        calls = []
        replies = iter((bad, good))
        def generate(messages):
            calls.append(messages)
            return next(replies)
        runtime._generate = generate
        runtime.answer(dict(REQUEST, evidence=evidence))
        self.assertEqual(calls[1][-2], {'role': 'assistant', 'content': bad})
        self.assertIn('unknown passage ID', calls[1][-1]['content'])

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


class DraftPipelineTests(unittest.TestCase):
    def test_only_multiple_source_files_enable_flow_instructions(self):
        for multi in (False, True):
            runtime = Runtime.__new__(Runtime)
            calls = []
            replies = iter(('The function returns 42.', VALID))
            def generate(messages):
                calls.append(messages)
                return next(replies)
            runtime._generate = generate
            evidence = EVIDENCE + ([dict(EVIDENCE[0], id='E2', path='other.py')] if multi else [])
            runtime.answer(dict(REQUEST, evidence=evidence))
            self.assertEqual('For cross-file questions' in calls[0][0]['content'], multi)
            self.assertEqual('passage_ids' in calls[1][0]['content'], multi)

    def test_empty_draft_is_not_filled_in_by_formatter(self):
        runtime = Runtime.__new__(Runtime)
        calls = []
        def generate(messages):
            calls.append(messages)
            return '   '
        runtime._generate = generate
        with self.assertRaises(Rejected):
            runtime.answer(REQUEST)
        self.assertEqual(len(calls), 1)

    def test_draft_reaches_formatter_but_only_claims_reach_api(self):
        runtime = Runtime.__new__(Runtime)
        replies = iter(('The function returns 42.', VALID))
        calls = []
        def generate(messages):
            calls.append(messages)
            return next(replies)
        runtime._generate = generate
        result = runtime.answer(REQUEST)
        self.assertEqual(len(calls), 2)
        self.assertIn('Source-based answer to format', calls[1][1]['content'])
        self.assertIn('The function returns 42.', calls[1][1]['content'])
        self.assertEqual(set(result), {'claims'})
        self.assertEqual(result['claims'][0]['text'], 'answer returns 42')

    def test_unsupported_draft_stops_before_formatting(self):
        runtime = Runtime.__new__(Runtime)
        calls = []
        def generate(messages):
            calls.append(messages)
            return 'NOT_SUPPORTED'
        runtime._generate = generate
        self.assertEqual(runtime.answer(REQUEST), {'claims': []})
        self.assertEqual(len(calls), 1)

    def test_bad_format_has_one_bounded_repair_after_drafting(self):
        runtime = Runtime.__new__(Runtime)
        replies = iter(('The function returns 42.', 'bad JSON', 'still bad JSON'))
        calls = []
        def generate(messages):
            calls.append(messages)
            return next(replies)
        runtime._generate = generate
        with self.assertRaises(Rejected):
            runtime.answer(REQUEST)
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
