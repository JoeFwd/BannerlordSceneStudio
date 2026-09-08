"""RNM1 reads close their input even when container validation fails."""
import builtins
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blnav import rnm1


class ContainerReadResourcesTests(unittest.TestCase):
    def test_read_closes_files_for_valid_and_invalid_containers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "navmesh.bin"
            payload = b"scene payload" * 20
            rnm1.write(str(path), payload)
            opened = []

            def track_open(*args, **kwargs):
                stream = builtins.open(*args, **kwargs)
                opened.append(stream)
                return stream

            try:
                with patch.object(rnm1, "open", track_open, create=True):
                    self.assertEqual(rnm1.read(str(path)), payload)
                    self.assertTrue(opened[-1].closed)
                    path.write_bytes(b"bad container")
                    with self.assertRaisesRegex(ValueError, "bad magic"):
                        rnm1.read(str(path))
                    self.assertTrue(opened[-1].closed)
            finally:
                for stream in opened:
                    stream.close()


if __name__ == "__main__":
    unittest.main()
