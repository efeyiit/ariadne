# Shared source citations

The local answer worker used to reject two distinct claims citing the same source
passage. A real answer naming `main` and describing its print output was therefore
discarded during format repair. Both claims may now cite that passage; source
coordinates and quotations still come from the server.

Validation on 27 September 2026:

- The new regression failed against the previous worker with `unknown or reused passage ID`.
- `training/.venv/Scripts/python.exe -m unittest discover -s training -p test_local_runtime.py`: 8 passed.
- Backend pytest for `tests/local/test_retrieval.py`, `tests/local_inference`, and
  `tests/api/test_local_launcher.py`: 12 passed.
- Unknown passage IDs, extra model-supplied citation fields, duplicate JSON keys,
  exact quote matching, and abstention without retry remain covered.

This repairs citation selection, not factual model quality. The existing 1.5B model
still fails Turkish and unsupported-behavior probes, including an invented HTTP
endpoint. Removing 4-bit quantization did not resolve these failures. Chat quality
acceptance remains open; matching quotations alone do not establish that a claim
is supported by them.
