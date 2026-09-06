import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.terrain_preview import resample_heights


class TerrainPreviewTests(unittest.TestCase):
    def test_full_extent_nondivisible_source(self):
        # The previous stride-9 preview stopped at 2043, then stretched to 2048.
        heights = np.tile(np.arange(2049), (3, 1))
        result = resample_heights(heights, 256)
        self.assertEqual(result.shape, (3, 256))
        np.testing.assert_allclose(result[1], np.linspace(0, 2048, 256))

    def test_bilinear_plane_and_corners(self):
        ys, xs = np.mgrid[:17, :29]
        result = resample_heights(xs + 2 * ys, 9)
        expected = np.linspace(0, 28, 9) + 2 * np.linspace(0, 16, 9)[:, None]
        np.testing.assert_allclose(result, expected)

    def test_full_resolution_unchanged(self):
        grid = np.arange(35).reshape(5, 7)
        np.testing.assert_array_equal(resample_heights(grid, 32), grid)


if __name__ == "__main__":
    unittest.main()
