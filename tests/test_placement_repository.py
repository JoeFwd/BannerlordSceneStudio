"""Settlement saves must move one icon and gate without moving its region."""
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np

from server.placement import repository


SCENE = '''<scene><entities>
  <game_entity name="region"><transform position="100, 200, 10" rotation_euler="0, 0, 1.5707963267948966" scale="2, 3, 1" />
    <children>
      <game_entity name="dadg_sco_test"><tags><tag name="town" /></tags>
        <transform position="4, 5, 2" rotation_euler="0, 0, 0" />
        <children><game_entity name="town_gate"><transform position="-2, 0, 0" /></game_entity></children>
      </game_entity>
      <game_entity name="dadg_sco_sibling"><transform position="8, 9, 0" /></game_entity>
    </children>
  </game_entity>
</entities></scene>'''
SETTLEMENTS = '''<Settlements>
<Settlement id="dadg_sco_test" posX="85" posY="208" gate_posX="85" gate_posY="204"><Components><Town is_castle="false" /></Components></Settlement>
</Settlements>'''


def positions(data):
    root = ET.fromstring(data)
    parents = {child: parent for parent in root.iter() for child in parent}
    result = {}
    for entity in root.iter("game_entity"):
        chain, cursor = [], entity
        while cursor is not None:
            if cursor.tag == "game_entity":
                chain.append(cursor)
            cursor = parents.get(cursor)
        world = np.eye(4)
        for item in reversed(chain):
            world = world @ repository._entity_transform(item)
        result[entity.get("name")] = world[:3, 3]
    return result


class PlacementRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name)
        self.scene = self.module / "SceneObj/Main_map"
        self.scene.mkdir(parents=True)
        (self.module / "ModuleData").mkdir()
        self.xml = self.module / "ModuleData/settlements.xml"
        self.xml.write_text(SETTLEMENTS)
        (self.scene / "scene.xscene").write_text(SCENE)

    def test_shared_rotated_scaled_parent_and_gate_move_together(self):
        before = positions(SCENE)
        result = repository.save_moves(str(self.scene), {"dadg_sco_test": (91, 212)})
        after_data = (self.scene / "scene.xscene").read_text()
        after = positions(after_data)
        np.testing.assert_allclose(before["dadg_sco_test"], (85, 208, 12))
        np.testing.assert_allclose(after["dadg_sco_test"], (91, 212, 12))
        np.testing.assert_allclose(after["town_gate"], (91, 208, 12))
        np.testing.assert_array_equal(after["region"], before["region"])
        np.testing.assert_array_equal(after["dadg_sco_sibling"], before["dadg_sco_sibling"])
        self.assertEqual(after_data.replace('position="6.000000, 3.000000, 2.000000"', 'position="4, 5, 2"'), SCENE)
        settlement = ET.parse(self.xml).getroot()[0]
        self.assertEqual(tuple(float(settlement.get(k)) for k in ("gate_posX", "gate_posY")), (91, 208))
        self.assertEqual(result["settlements_updated"], 1)
        self.assertEqual(result["capsules_updated"], 1)

    def test_missing_scene_target_does_not_write_xml_or_backups(self):
        (self.scene / "scene.xscene").write_text(SCENE.replace('name="dadg_sco_test"', 'name="another"'))
        before = self.xml.read_bytes()
        with self.assertRaisesRegex(ValueError, "scene entities not found"):
            repository.save_moves(str(self.scene), {"dadg_sco_test": (91, 212)})
        self.assertEqual(self.xml.read_bytes(), before)
        self.assertFalse(list(self.module.rglob("*.bak_placement_*")))

    def test_full_euler_parent_preserves_world_z(self):
        tilted = SCENE.replace('rotation_euler="0, 0, 1.5707963267948966"', 'rotation_euler="0.3, -0.2, 0.6"')
        path = self.scene / "scene.xscene"
        path.write_text(tilted)
        data, count = repository.apply_moves_scene(str(path), {"dadg_sco_test": (6, 4)})
        before, after = positions(tilted), positions(data)
        np.testing.assert_allclose(after["dadg_sco_test"] - before["dadg_sco_test"], (6, 4, 0), atol=2e-6)
        np.testing.assert_allclose(after["town_gate"] - before["town_gate"], (6, 4, 0), atol=2e-6)
        self.assertEqual(count, 1)

    def test_duplicate_scene_target_is_rejected(self):
        path = self.scene / "scene.xscene"
        path.write_text(SCENE.replace('name="dadg_sco_sibling"', 'name="dadg_sco_test"'))
        with self.assertRaisesRegex(ValueError, "duplicate scene entity"):
            repository.apply_moves_scene(str(path), {"dadg_sco_test": (1, 1)})


if __name__ == "__main__":
    unittest.main()
