# Local inference worker

The application launcher starts one worker on loopback and its API
separately. The default worker port is 8766; a launcher can use 8767 through
child env `ARIADNE_LOCAL_RUNTIME_PORT=8767` and point backend clients to it
with `ARIADNE_LOCAL_RUNTIME_URL=http://127.0.0.1:8767`. Only those two ports
are accepted. The worker uses pinned Qwen3-4B-Instruct-2507
weights in 4-bit CUDA and does not attach any training adapter.
It loads the pinned intfloat/multilingual-e5-small embedding model on CPU. No paid
API, cloud inference, or external repository code execution is involved.

Install its model data explicitly with `training/.venv/Scripts/python.exe
training/download_chat_model.py` (about 8 GB). The pinned revision and all three
weight hashes are in `training/chat_model.py`; inference verifies them and loads
offline. The separate 1.5B training experiments retain their original model.

The launcher must create a fresh `secrets.token_urlsafe(32)` value and pass it
only in the child environment variable `ARIADNE_LOCAL_RUNTIME_TOKEN` to the
worker and API. The worker refuses to start without it. Never log the
value or place it in command arguments, the frontend, metadata, or Git files.

Start the worker as `training/.venv/Scripts/python.exe
training/local_runtime_server.py` with that child environment. The worker
loads both models before binding its port. `GET /health` is tokenless and
returns `status: ready`, model IDs, embedding dimension 384, and `local`
execution location. `POST /answer` and `POST /embed` require the token.
The server is single threaded, so one request runs at a time. Answer context
is bounded to 4,096 tokens with up to 384 generated tokens. The input body is
bounded to 64 KB. The `two-stage-passage-selection-v6` workflow first produces a
source-based draft, then formats it into claims with supplied passage IDs. An
unsupported draft stops immediately. Only validated final claims reach the API;
the server derives source coordinates and exact quotes from the selected passages.
Distinct claims may cite the same passage. One formatting repair is allowed
(at most three generations including the draft). Invalid output then
becomes `rejected`, with no invented answer fallback. Transport failures are
`unavailable`. T21 independently rechecks live authorization and citations.

`LocalAnswerProvider` and `LocalEmbeddingProvider` in
`backend/app/local_inference` are the backend adapters. Both read the loopback
endpoint and token from their child environment.
The multilingual E5 provider emits 384-dimensional normalized mean-pooled
embeddings. Query and source passages use the publisher's `query: ` and
`passage: ` prefixes. Its pinned model ID creates a separate Qdrant collection
from the earlier BGE index. Existing repositories need reindexing with E5.
The small public-repository diagnostic showed README rank 1 for a Turkish
purpose question with E5 versus rank 5 with English-focused BGE. This does
not by itself establish end-to-end answer quality.

The 27 September 2026 production-code run passed 18 synthetic real-model cases covering
English/Turkish answers, conditional returns, absent features, and two source
instruction attacks. This is a bounded regression set, not a guarantee of factual
correctness on arbitrary repositories. Citation validation verifies source mapping,
not semantic entailment. Focused retrieval may omit context elsewhere in a project.
Reproduce it with `training/.venv/Scripts/python.exe training/evaluate_local_chat.py`.
The report includes final claims for manual review; no fixture source is executed.

Sources: [Qwen model](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507),
[multilingual E5 model and usage](https://huggingface.co/intfloat/multilingual-e5-small).
