"""Synthetic regressions: centroid misses, truncation, orphan vertices, identity."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blnav.nmg9 import NavMesh, Face
from blnav import rnm1
from server import navmesh_diagnostics as diagnostics


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        mesh = NavMesh()
        mesh.vertices = [(0., 0., 1.), (10., 0., 1.), (0., 10., 1.),
                         (.25, .25, 20.)]
        mesh.faces = [Face([0, 1, 2], [], 2, 0, 11, 0, -204, 0)]
        mesh.rebuild_edges()
        self.sess = SimpleNamespace(mesh=mesh, scene_dir=self.temp.name,
                                    navmesh_path=str(Path(self.temp.name) / "navmesh.bin"),
                                    dirty=False, heights=None)
        rnm1.write(self.sess.navmesh_path, mesh.serialize())

    def test_intersection_not_centroid_and_counts_not_truncated(self):
        result = diagnostics.inspect_region(self.sess, .1, .1, .5, .5, limit=0)
        self.assertEqual(result["matching_face_count"], 1)
        self.assertEqual(result["face_counts_by_g3"], {11: 1})
        self.assertAlmostEqual(result["summed_face_area_by_g3"][11], .16)
        self.assertEqual(result["faces"], [])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["vertices_in_bounds"], {"total": 1, "referenced": 0, "unreferenced": 1})
        self.assertTrue(result["identity"]["working_matches_disk"])

    def test_point_preserves_attributes_and_boundary(self):
        result = diagnostics.probe_point(self.sess, 5, 5)
        self.assertEqual(result["faces"][0]["g3"], 11)
        self.assertEqual(result["faces"][0]["g5"], -204)
        self.assertEqual(diagnostics.probe_point(self.sess, 8, 8)["faces"], [])

    def test_stale_working_copy_detected_without_dirty_flag(self):
        self.sess.mesh.faces[0].g3 = 1
        self.assertFalse(diagnostics.mesh_identity(self.sess)["working_matches_disk"])
        self.assertFalse(self.sess.dirty)

    def test_bad_bounds(self):
        with self.assertRaises(ValueError):
            diagnostics.inspect_region(self.sess, 1, 0, 0, 1)


if __name__ == "__main__":
    unittest.main()
