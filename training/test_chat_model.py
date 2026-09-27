"""Model integrity checks do not require CUDA or model downloads."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from chat_model import verify_weights


class ModelIntegrityTests(unittest.TestCase):
    def test_all_shards_are_required_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = {'one.safetensors': hashlib.sha256(b'one').hexdigest(),
                        'two.safetensors': hashlib.sha256(b'two').hexdigest()}
            (root / 'one.safetensors').write_bytes(b'one')
            with self.assertRaisesRegex(RuntimeError, 'missing'):
                verify_weights(root, expected)
            (root / 'two.safetensors').write_bytes(b'wrong')
            with self.assertRaisesRegex(RuntimeError, 'mismatch'):
                verify_weights(root, expected)
            (root / 'two.safetensors').write_bytes(b'two')
            verify_weights(root, expected)


if __name__ == '__main__':
    unittest.main()
