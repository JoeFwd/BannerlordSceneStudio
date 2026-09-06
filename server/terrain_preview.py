"""Downsample the full terrain extent without stretching a truncated stride."""
import numpy as np


def resample_heights(heights, max_dim):
    if max_dim < 2 or max_dim > 4097:
        raise ValueError("max_dim must be from 2 to 4097")
    rows, cols = heights.shape
    xs = np.linspace(0, cols - 1, min(cols, max_dim))
    ys = np.linspace(0, rows - 1, min(rows, max_dim))
    x0, y0 = xs.astype(int), ys.astype(int)
    x1, y1 = np.minimum(x0 + 1, cols - 1), np.minimum(y0 + 1, rows - 1)
    fx, fy = xs - x0, (ys - y0)[:, None]
    low = heights[np.ix_(y0, x0)] * (1 - fx) + heights[np.ix_(y0, x1)] * fx
    high = heights[np.ix_(y1, x0)] * (1 - fx) + heights[np.ix_(y1, x1)] * fx
    return low * (1 - fy) + high * fy
