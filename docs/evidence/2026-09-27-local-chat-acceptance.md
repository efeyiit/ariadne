# Local chat acceptance — 27 September 2026

## Change

Local chat now uses pinned Qwen3-4B-Instruct-2507 weights in NF4 on CUDA.
Answer generation and JSON formatting are separate steps: the model first answers
from retrieved source, then converts that draft into claims. Empty drafts are
rejected; explicitly unsupported questions stop without formatting. Invalid JSON
has one repair attempt. Source quotes and line coordinates remain server-derived
and independently checked by the backend. Distinct claims may share a passage.

The previous 1.5B model and a combined answering/formatting prompt produced wrong
conditional return values and unsupported claims. A larger model alone did not
remove every observed error. Separating the two steps passed the regression set.
No training adapter, cloud inference, or execution of repository code is involved.

## Verification

- `training/.venv/Scripts/python.exe -m unittest discover -s training -p test_local_runtime.py`: 12 passed.
- `backend/.venv/Scripts/python.exe -m unittest discover -s training -p test_chat_model.py`: 1 passed; missing and altered model shards rejected.
- From `backend`, `.venv/Scripts/python.exe -m pytest -q`: 331 passed, 37 skipped (PostgreSQL integration prerequisites); one existing Starlette deprecation warning.
- `training/.venv/Scripts/python.exe training/evaluate_local_chat.py --output training/reports/chat-acceptance-20260927.json`: **18/18** real offline model cases passed. All final claims were also manually reviewed.
- Cases cover English/Turkish source answers, conditional values below/at/above a threshold, constants, booleans, JavaScript, absent features, empty sources, and two source-instruction attacks.
- Actual worker HTTP plus local FastAPI, E5 retrieval and Qdrant: four questions passed. Main function location/output had exact source citations; delivery fees were 0 for total 80 and 8 for total 20; absent PostgreSQL returned `no_evidence`. Temporary synthetic storage was used.
- Edge browser at 2560×1440: opened the saved public `sampleproject`, submitted “main fonksiyonu nerede ve ne yazdırıyor?”, and received the correct Turkish location and printed string with source links. The rendered chat was visually inspected; clicking a citation opened the correct source file and line. No page or console errors were observed.

Model revision: `cdbee75f17c01a7cc42f958dc650907174af0554`.
Prompt version: `two-stage-passage-selection-v6`.
The three pinned weight hashes are in `training/chat_model.py` and checked at startup.
Model data and local runtime reports are not published in Git.

## Limits

These are bounded regression results, not a guarantee that arbitrary model answers
are correct. Citation checking proves source mapping, not semantic entailment.
Retrieval may miss relevant context. CUDA and separately downloaded model data are
required. Positive answers usually require two generations; malformed formatting
can require a third. Existing training experiments retain their original model.

