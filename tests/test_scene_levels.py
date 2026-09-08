"""Regression: island IDs must never silently become scene visibility masks."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from pydantic import ValidationError

from blnav.nmg9 import Face, NavMesh
from blnav.scene_levels import default_scene_level_mask
from server import state, web


class SceneLevelTests(unittest.TestCase):
    def session(self, name='Main_map'):
        return state.SceneSession(name, params=SimpleNamespace(world_size_x=8, world_size_y=8,
            min_height=0, max_height=1), heights=np.zeros((3, 3), dtype=np.float32))

    def test_scene_defaults_and_generic_faces(self):
        for path in ['C:/Modules/SandBox/SceneObj/Main_map/', 'C:\\Scenes\\MAIN_MAP']:
            self.assertEqual(default_scene_level_mask(path), -109)
        self.assertEqual(default_scene_level_mask('scn_castle'), -1)
        self.assertEqual(Face([0, 1, 2], []).g5, -1)

    def test_campaign_generation_defaults_and_explicit_override(self):
        for name, override, expected in [('Main_map', None, -109), ('castle', None, -1), ('Main_map', -103, -103)]:
            with self.subTest(name=name, override=override):
                sess = self.session(name)
                with patch.object(state, '_current', sess):
                    web.api_generate(web.GenReq(scene_level_mask=override))
                self.assertTrue(sess.mesh.faces)
                self.assertEqual({f.g5 for f in sess.mesh.faces}, {expected})
                self.assertEqual({f.g5 for f in NavMesh.parse(sess.mesh.serialize()).faces}, {expected})

    def test_terrain_edit_preserves_mask_and_explicit_mask_edit_works(self):
        sess = self.session()
        sess.mesh.faces = [Face([0, 1, 2], [], g3=1, g5=-103)]
        with patch.object(state, '_current', sess):
            web.api_set_attrs(web.FacesReq(indices=[0], face_id=7))
            self.assertEqual((sess.mesh.faces[0].g3, sess.mesh.faces[0].g5), (7, -103))
            web.api_set_attrs(web.FacesReq(indices=[0], scene_level_mask=-109))
            self.assertEqual((sess.mesh.faces[0].g3, sess.mesh.faces[0].g5), (7, -109))
            self.assertEqual(web.api_mesh()['scene_level_mask'], [-109])

    def test_obsolete_group_requests_fail_instead_of_silently_mutating(self):
        for cls, args in [(web.GenReq, {'group': -204}), (web.FacesReq, {'indices': [0], 'group': -204})]:
            with self.assertRaises(ValidationError):
                cls(**args)


if __name__ == '__main__':
    unittest.main()
