"""Disk changes must survive saves from an older in-memory scene session."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blnav import nmg9, rnm1
from server import state


class SceneSaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.scene = Path(self.temp.name)
        self.path = self.scene / "navmesh.bin"
        rnm1.write(str(self.path), nmg9.NavMesh().serialize())
        self.session = state.load_scene(str(self.scene))
        self.session.dirty = True

    def test_external_edit_is_not_overwritten_or_backed_up(self):
        self.path.write_bytes(b"external replacement")
        with self.assertRaisesRegex(state.StaleSceneError, "changed on disk"):
            self.session.save()
        self.assertEqual(self.path.read_bytes(), b"external replacement")
        self.assertTrue(self.session.dirty)
        self.assertFalse(self.path.with_suffix(".bin.bak").exists())
        self.assertEqual(list(self.scene.glob(".navmesh-studio-*")), [])

    def test_normal_consecutive_saves_refresh_fingerprint(self):
        for vertex in ((1., 2., 3.), (4., 5., 6.)):
            self.session.mesh.vertices.append(vertex)
            self.session.dirty = True
            self.session.save()
            self.assertEqual(nmg9.NavMesh.parse(rnm1.read(str(self.path))).vertices, self.session.mesh.vertices)
            self.assertEqual(self.session.source_fingerprint, state._fingerprint(str(self.path)))
            self.assertFalse(self.session.dirty)
        self.assertEqual(list(self.scene.glob(".navmesh-studio-*")), [])

    def test_failed_atomic_replace_preserves_original(self):
        before = self.path.read_bytes()
        with patch.object(state.os, "replace", side_effect=OSError("write failed")):
            with self.assertRaisesRegex(OSError, "write failed"):
                self.session.save(backup=False)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(self.session.dirty)
        self.assertEqual(list(self.scene.glob(".navmesh-studio-*")), [])

    def test_external_edit_during_serialization_is_rechecked(self):
        write = state.rnm1.write
        def external_edit_after_temp_write(path, payload):
            write(path, payload)
            self.path.write_bytes(b"newer disk mesh")
        with patch.object(state.rnm1, "write", side_effect=external_edit_after_temp_write):
            with self.assertRaises(state.StaleSceneError):
                self.session.save()
        self.assertEqual(self.path.read_bytes(), b"newer disk mesh")

    def test_new_scene_can_save_twice(self):
        self.path.unlink()
        session = state.load_scene(str(self.scene))
        session.save()
        session.save()
        self.assertEqual(session.source_fingerprint, state._fingerprint(str(self.path)))

    def test_web_save_reports_a_conflict_with_reload_instruction(self):
        from server import web
        self.path.write_bytes(b"external replacement")
        with patch.object(state, "_current", self.session):
            with self.assertRaises(web.HTTPException) as raised:
                web.api_save(web.SaveReq())
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("Reload the scene", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
