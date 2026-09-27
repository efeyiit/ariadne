"""Real offline inference on synthetic sources; never executes fixture code.

Checks are intentionally narrow regression signals. Review the returned claims
as well: matching a string is not a general semantic correctness evaluator.
"""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from chat_model import MODEL_ID, REVISION
from local_runtime_server import PROMPT_VERSION, Runtime


def check(case, result):
    claims = result.get("claims", [])
    if case.get("abstain"):
        return not claims and "error" not in result
    if not claims:
        return False
    text = "\n".join(claim["text"] for claim in claims)
    folded = text.casefold()
    if not all(term.casefold() in folded for term in case.get("contains", [])):
        return False
    if case.get("any") and not any(term.casefold() in folded for term in case["any"]):
        return False
    if any(term.casefold() in folded for term in case.get("forbid", [])):
        return False
    values = {"branch-high": 0, "branch-low": 8, "branch-tr": 0, "threshold-equality": 0}
    if case["id"] in values:
        value = values[case["id"]]
        clean = text.replace("`", "").replace("**", "")
        patterns = [rf"\breturns?\s+(?:the value\s+)?{value}\b",
                    rf"\b{value}\s+(?:değerini\s+)?döndür",
                    rf"\breturn\s+{value}\b",
                    rf"\b{value}\s+(?:is returned|olarak döner)"]
        if not any(re.search(pattern, clean, re.IGNORECASE) for pattern in patterns):
            return False
    return True


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = json.loads((root / "fixtures/local_chat_acceptance.json").read_text(encoding="utf-8"))
    runtime = Runtime()
    results = []
    for case in cases:
        evidence = [] if not case["source"] else [{
            "id": "E1", "path": case["path"], "text": case["source"],
            "start_line": 1, "end_line": len(case["source"].splitlines()),
            "commit_sha": "local:" + "a" * 64,
        }]
        started = time.monotonic()
        try:
            result = runtime.answer({"instructions": "Answer only from source.",
                                     "question": case["question"], "evidence": evidence})
        except Exception as exc:
            result = {"error": type(exc).__name__ + ": " + str(exc)}
        entry = {"id": case["id"], "passed": check(case, result), "result": result,
                 "seconds": round(time.monotonic() - started, 2)}
        results.append(entry)
        print(f"{case['id']}: {'PASS' if entry['passed'] else 'FAIL'}", flush=True)
    passed = sum(entry["passed"] for entry in results)
    output = args.output or root / "reports" / ("chat-acceptance-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"model_id": MODEL_ID, "revision": REVISION,
                                  "prompt_version": PROMPT_VERSION, "passed": passed,
                                  "total": len(results), "cases": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{passed}/{len(results)} passed; review claims in {output}")
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
