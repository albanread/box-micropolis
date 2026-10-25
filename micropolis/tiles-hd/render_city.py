#!/usr/bin/env python3
"""Compose a Micropolis city map from a tile atlas.

usage: render_city.py CITYFILE ATLAS.png TILE_PX OUT.png [x0 y0 w h]

CITYFILE: classic .cty (27120 bytes, or 51120 with an extra layer at the end).
  3120 bytes of histories/misc, then 120x100 big-endian uint16, column-major
  (index x*100 + y). Tile = value & 0x3FF; values >= 960 (churches 1..7)
  draw tile 414 + (n-956) % 9.
ATLAS: tiles of TILE_PX square, 16 per row, tile n at ((n%16)*P, (n//16)*P).
Optional crop in tiles: x0 y0 w h (default the whole 120x100 map).
"""
import sys
import numpy as np
from PIL import Image

W, H = 120, 100
HDR = 3120


def load_map(path):
    data = open(path, 'rb').read()
    if len(data) not in (27120, 51120):
        raise SystemExit(f'{path}: unexpected size {len(data)}')
    raw = np.frombuffer(data, dtype='>u2', count=W * H, offset=HDR)
    tiles = (raw & 0x3FF).astype(np.int32).reshape(W, H).T  # -> [y][x]
    hi = tiles >= 960
    tiles[hi] = 414 + (tiles[hi] - 956) % 9
    return tiles


def render(tiles, atlas, p, x0=0, y0=0, w=W, h=H):
    a = np.asarray(atlas.convert('RGBA'))
    per_row = a.shape[1] // p
    ntiles = per_row * (a.shape[0] // p)
    out = np.zeros((h * p, w * p, 4), np.uint8)
    for ty in range(h):
        for tx in range(w):
            n = int(tiles[y0 + ty, x0 + tx])
            if n >= ntiles:
                n = 0
            sx, sy = (n % per_row) * p, (n // per_row) * p
            out[ty * p:(ty + 1) * p, tx * p:(tx + 1) * p] = a[sy:sy + p, sx:sx + p]
    return Image.fromarray(out, 'RGBA')


def main(argv):
    if len(argv) not in (5, 9):
        print(__doc__)
        return 2
    city, atlas, p, out = argv[1], argv[2], int(argv[3]), argv[4]
    tiles = load_map(city)
    crop = [int(v) for v in argv[5:9]] if len(argv) == 9 else [0, 0, W, H]
    x0, y0, w, h = crop
    if x0 < 0 or y0 < 0 or x0 + w > W or y0 + h > H:
        raise SystemExit('crop outside the 120x100 map')
    img = render(tiles, Image.open(atlas), p, x0, y0, w, h)
    if Image.open(atlas).mode == 'RGB':
        img = img.convert('RGB')
    img.save(out)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
