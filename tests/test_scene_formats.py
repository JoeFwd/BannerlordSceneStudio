"""Synthetic scene-format regression tests; no game files or running server needed."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import lz4.block

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blnav import nmg8, nmg9, rnm1
from server import state


VERTICES = [(0.0, -0.0, 1.25), (2.0, 0.0, 1.25), (2.0, 2.0, 1.25),
            (0.0, 2.0, 1.25), (1.0, 3.0, -2.5)]
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (3, 4), (4, 2)]
FOOTER = b"\x20\x00\x00\x00" + bytes(256)


def scene_payload(version, face_id=101):
    """Build expected bytes from the disk layouts, independently of NavMesh."""
    out = bytearray(b"NMG8" if version == 8 else b"NMG9")
    out += struct.pack("<I", 5)
    for v in VERTICES:
        out += struct.pack("<fff", *v)
    out += struct.pack("<I", 6)
    for a, b in EDGES:
        if version == 8:
            out += struct.pack("<iIIii", -1, a, b, -1, -1)
        else:
            out += struct.pack("<iIIiiI", -1, a, b, -1, -1, 0)
    out += struct.pack("<I", 2)
    out += struct.pack("<I4I4I5iB", 4, 0, 1, 2, 3, 0, 1, 2, 3,
                       -7, 19, face_id, 1082130432, -18, 253)
    out += struct.pack("<I3I3I5iB", 3, 2, 3, 4, 2, 4, 5,
                       2, -3, 17, 1065353216, 30, 1)
    return bytes(out) + FOOTER


def container_bytes(payload):
    compressed = lz4.block.compress(payload, store_size=False)
    size_minus_8 = 40 + len(compressed)
    # Runtime pointer bytes intentionally differ from rnm1.write's output.
    return (struct.pack("<4sIIIQQ", b"RNM1", size_minus_8, 3, 0,
                        len(payload), size_minus_8)
            + bytes(range(16)) + compressed)


class SceneFormatTests(unittest.TestCase):
    def test_independent_scene_roundtrips(self):
        for version in (8, 9):
            with self.subTest(version=version):
                payload = scene_payload(version)
                mesh = nmg9.NavMesh.parse(payload)
                self.assertEqual(mesh.version, version)
                self.assertEqual(mesh.vertices, VERTICES)
                self.assertEqual([(e.va, e.vb) for e in mesh.edges], EDGES)
                self.assertEqual(mesh.faces, [
                    nmg9.Face([0, 1, 2, 3], [0, 1, 2, 3],
                              -7, 19, 101, 1082130432, -18, 253),
                    nmg9.Face([2, 3, 4], [2, 4, 5],
                              2, -3, 17, 1065353216, 30, 1),
                ])
                self.assertEqual(mesh.serialize(), payload)
                mesh.rebuild_edges()
                self.assertEqual(mesh.serialize(), payload)

    def test_every_truncated_prefix_is_rejected(self):
        for version in (8, 9):
            payload = scene_payload(version)
            for end in range(len(payload)):
                with self.subTest(version=version, end=end):
                    with self.assertRaises(ValueError):
                        nmg9.NavMesh.parse(payload[:end])

    def test_unsupported_scene_magic_and_version(self):
        for magic in (b"NMG7", b"NMG0", b"RNM1"):
            with self.subTest(magic=magic):
                with self.assertRaisesRegex(ValueError, "bad scene magic"):
                    nmg9.NavMesh.parse(magic + scene_payload(9)[4:])
        with self.assertRaisesRegex(ValueError, "unsupported scene navmesh version"):
            nmg9.NavMesh(version=7).serialize()

    def test_unsupported_edge_fields_rejected(self):
        edge_start = 4 + 4 + 5 * 12 + 4
        for version in (8, 9):
            offsets = (0, 12, 16, 20) if version == 9 else (0, 12, 16)
            for offset in offsets:
                with self.subTest(version=version, offset=offset):
                    payload = bytearray(scene_payload(version))
                    struct.pack_into("<I", payload, edge_start + offset, 1)
                    with self.assertRaisesRegex(ValueError, "unexpected edge record fields"):
                        nmg9.NavMesh.parse(payload)

    def test_malformed_counts_and_footer_rejected(self):
        for version in (8, 9):
            edge_count = 8 + 5 * 12
            face_count = edge_count + 4 + 6 * (20 if version == 8 else 24)
            mutations = [(4, 0xFFFFFFFF), (edge_count, 0xFFFFFFFF),
                         (face_count, 0xFFFFFFFF), (face_count + 4, 2),
                         (face_count + 4, 65)]
            for offset, value in mutations:
                with self.subTest(version=version, offset=offset, value=value):
                    payload = bytearray(scene_payload(version))
                    struct.pack_into("<I", payload, offset, value)
                    with self.assertRaises(ValueError):
                        nmg9.NavMesh.parse(payload)
            for payload in (scene_payload(version) + b"\x00",
                            scene_payload(version)[:-1] + b"\x01"):
                with self.subTest(version=version, footer=True):
                    with self.assertRaisesRegex(ValueError, "unexpected footer"):
                        nmg9.NavMesh.parse(payload)

    def test_load_edit_save_preserves_version_and_raw_attributes(self):
        previous = state._current
        self.addCleanup(setattr, state, "_current", previous)
        for version in (8, 9):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "navmesh.bin"
                original = container_bytes(scene_payload(version))
                path.write_bytes(original)
                session = state.load_scene(tmp)
                self.assertEqual(session.mesh.version, version)
                self.assertEqual(state.current(), session)
                session.save()
                self.assertEqual(rnm1.read(str(path)), scene_payload(version))
                self.assertEqual(Path(str(path) + ".bak").read_bytes(), original)
                session.mesh.faces[0].g3 = 99
                session.dirty = True
                session.save()
                self.assertFalse(session.dirty)
                self.assertEqual(rnm1.read(str(path)), scene_payload(version, face_id=99))
                self.assertEqual(Path(str(path) + ".bak").read_bytes(), original)
                self.assertEqual(state.load_scene(tmp).mesh.version, version)

    def test_new_meshes_default_to_nmg9(self):
        expected = b"NMG9" + bytes(12) + FOOTER
        self.assertEqual(nmg9.NavMesh().serialize(), expected)
        self.assertEqual(state.SceneSession("unused").mesh.serialize(), expected)

    def test_prefab_api_is_separate_and_unchanged(self):
        body = (b"NMG8" + struct.pack("<I", 3)
                + b"".join(struct.pack("<fff", *v) for v in VERTICES[:3])
                + struct.pack("<I3I", 1, 0, 1, 2))
        expected = struct.pack("<I", len(body)) + body
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prefab.bin"
            nmg8.write(str(path), VERTICES[:3], [(0, 1, 2)])
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(nmg8.read(str(path)), (VERTICES[:3], [(0, 1, 2)]))
            with self.assertRaisesRegex(ValueError, "bad scene magic"):
                nmg9.NavMesh.parse(expected)
            path.write_bytes(scene_payload(8))
            with self.assertRaisesRegex(ValueError, "bad magic"):
                nmg8.read(str(path))

    def test_face_edge_count_mismatch_still_rejected(self):
        mesh = nmg9.NavMesh.parse(scene_payload(8))
        mesh.faces[0].edge_ids.pop()
        with self.assertRaisesRegex(ValueError, "vertex/edge id count mismatch"):
            mesh.serialize()


if __name__ == "__main__":
    unittest.main()
