"""Extension atlas (tiles 960..1023): variants the game may substitute at draw time.

The base atlas stays correct alone; these only improve two inherited flaws.

1. Woods (37): three more canopies. Crowns that can touch the tile edge (or cast a shadow
   over it) are the same periodic crowns as tile 37, so any variant meets any woods tile;
   only the interior crowns change. Choose by a hash of the map position.
2. Coast ("blob" autotile): every water tile (2, 3, 4 and the coast tiles 5..20) is drawn from
   its 8 neighbours. A side whose neighbour is land gets the beach strip of the base coast
   tiles (same depth, same noise); a corner whose diagonal is land while both adjacent sides
   are water gets a quarter-round beach of the same depth. Along any shared edge the two
   water tiles then agree exactly, which removes the staircase banks of the scenario maps
   and the small steps at concave corners. 47 reduced masks; mask 0 is tile 2 itself.

Run directly to write variants.json; build_atlas.py renders the tiles.
"""
import json
import math
import os
import numpy as np
from hdlib import *
from terrain import (dirt_layer, water_layer, coast_noise, COAST_D, crown_list, draw_crown,
                     tree_field, cached)

HERE = os.path.dirname(os.path.abspath(__file__))
EXT0 = 960

# ------------------------------------------------------------------ woods
WOODS_VARIANTS = [960, 961, 962]


def _interior(x, y, r):
    m = 1.15 * r
    return (x - m > 0.015 and x + m + 0.11 < 0.985 and y - m > 0.015 and y + m + 0.07 < 0.985)


def woods_variant(v, n=RS):
    base = crown_list(51)
    rng = np.random.default_rng(2000 + v)
    pts = []
    for (x, y, r, s) in base:
        if _interior(x, y, r):
            if v == 2 and rng.random() < 0.30:
                continue                        # small clearings
            x2 = x + rng.uniform(-0.05, 0.05)
            y2 = y + rng.uniform(-0.05, 0.05)
            r2 = r * rng.uniform(0.85, 1.12)
            if not _interior(x2, y2, r2):
                x2, y2, r2 = x, y, r
            pts.append((x2, y2, r2, int(rng.integers(1 << 30)), True))
        else:
            pts.append((x, y, r, s, False))
    if v == 1:
        # one extra small tree in the largest interior gap
        pts.append((0.46, 0.52, 0.07, 777, True))
    cv = Canvas(1, 1, n, dirt_layer(1, 1, n))
    f = tree_field(cv.X, cv.Y, '')
    cv.paint(PAL['dirt'][2], smoothstep(-0.14, 0.0, f) * 0.5)
    cv.paint(PAL['leaf'][1], smoothstep(-0.02, 0.10, f) * 0.85)
    if v == 2:
        # clearing floor: grass and fallen leaves where crowns were dropped
        g = pnoise(n, 12, 2010)
        cv.paint(PAL['grass'](0.35 + 0.3 * g), smoothstep(0.55, 0.75, g) * smoothstep(0.15, 0.3, -sd_box(cv.X, cv.Y, 0, 0, 1, 1)) * 0.6)
    allp = []
    for p in pts:
        x, y, r, s, inner = p
        if inner:
            allp.append((x, y, r, s))
        else:
            for i in (-1, 0, 1):
                for j in (-1, 0, 1):
                    allp.append((x + i, y + j, r, s))
    allp = [p for p in allp if -0.2 < p[0] < 1.2 and -0.2 < p[1] < 1.2]
    sh = np.zeros_like(cv.X)
    for (x, y, r, s) in allp:
        sx, sy = x + SHADOW_DIR[0] * 0.10, y + SHADOW_DIR[1] * 0.10
        sh = np.maximum(sh, cv.cov(sd_circle(cv.X, cv.Y, sx, sy, r * 1.02), 6))
    cv.shade(sh, 0.55)
    for (x, y, r, s) in sorted(allp, key=lambda p: (p[1], p[0])):
        hue = ((s % 7) - 3) * 0.015
        if v == 1:
            hue -= 0.04
        draw_crown(cv, x, y, r, s, hue=hue)
    return cv.img


# ------------------------------------------------------------------ coast blob
BITS = {'N': 1, 'NE': 2, 'E': 4, 'SE': 8, 'S': 16, 'SW': 32, 'W': 64, 'NW': 128}
DIRS = {'N': (0, -1), 'NE': (1, -1), 'E': (1, 0), 'SE': (1, 1), 'S': (0, 1), 'SW': (-1, 1), 'W': (-1, 0), 'NW': (-1, -1)}
CORNERS = {'NE': ('N', 'E'), 'SE': ('S', 'E'), 'SW': ('S', 'W'), 'NW': ('N', 'W')}

REPLACEABLE = [2, 3, 4] + list(range(5, 21))
# water tiles carrying a structure: count as water for their neighbours but are never replaced
STRUCTURES = ([64, 65, 79, 95, 208, 209, 224, 225, 828, 829, 830, 831, 948, 949, 950, 951]
              + [80 + 16 * f + i for f in range(4) for i in (0, 1)]
              + [144 + 16 * f + i for f in range(4) for i in (0, 1)]
              + [111, 127, 143, 159, 175, 191, 207])
WATER_SET = sorted(set(REPLACEABLE) | set(STRUCTURES))


def reduce_mask(m):
    for c, (a, b) in CORNERS.items():
        if m & (BITS[a] | BITS[b]):
            m &= ~BITS[c]
    return m


REDUCED = sorted(set(reduce_mask(m) for m in range(256)))
assert len(REDUCED) == 47
BLOB_TILE = {}
_k = EXT0 + len(WOODS_VARIANTS)
for m in REDUCED:
    if m == 0:
        BLOB_TILE[m] = 2
    else:
        BLOB_TILE[m] = _k
        _k += 1
EXT_LAST = _k - 1
assert EXT_LAST <= 1023


def blob_sdf(X, Y, m, d=COAST_D, k=0.32):
    terms = []
    for s in 'NESW':
        if m & BITS[s]:
            terms.append({'N': Y, 'S': 1 - Y, 'W': X, 'E': 1 - X}[s] - d)
    for c in CORNERS:
        if m & BITS[c]:
            cx = 1.0 if 'E' in c else 0.0
            cy = 0.0 if c[0] == 'N' else 1.0
            terms.append(np.hypot(X - cx, Y - cy) - d)
    if not terms:
        return np.full_like(X, 1.0)
    sd = terms[0]
    for t in terms[1:]:
        sd = smin(sd, t, k)
    return sd


def blob_tile(m, n=RS):
    """Same painting as terrain.coast_tile, with the blob field."""
    cv = Canvas(1, 1, n)
    sd = blob_sdf(cv.X, cv.Y, m) + coast_noise(n)
    land = dirt_layer(1, 1, n)
    water = water_layer(1, 1, n)
    depth = smoothstep(0.0, 0.34, sd)
    sh = PAL['shallow'](0.55 - 0.45 * smoothstep(0.0, 0.2, sd) + 0.1 * coast_noise(n) * 10)
    wimg = water * depth[..., None] + sh * (1 - depth[..., None])
    cv.img = land
    beach = smoothstep(-0.13, -0.03, sd)
    sandn = pnoise(n, 64, 42)
    cv.paint(PAL['sand'](0.62 + 0.25 * (sandn - 0.5)), beach)
    cv.paint(PAL['sand'](0.30 + 0.15 * (sandn - 0.5)), smoothstep(-0.045, -0.005, sd) * 0.85)
    wa = cv.cov(-sd, 1.5)
    cv.img = cv.img * (1 - wa[..., None]) + wimg * wa[..., None]
    swash = smoothstep(0.0, 0.012, sd) * smoothstep(0.05, 0.012, sd)
    foamn = pnoise2(n, 6, 24, 43)
    cv.paint(PAL['water'][9], swash * (0.45 + 0.5 * smoothstep(0.35, 0.7, foamn)))
    second = smoothstep(0.045, 0.06, sd) * smoothstep(0.085, 0.06, sd)
    cv.paint(PAL['water'][8], second * 0.35 * smoothstep(0.45, 0.75, foamn))
    return cv.img


# ------------------------------------------------------------------ the rules (reference implementation)
def pos_hash(x, y):
    h = (x * 73856093) ^ (y * 19349663)
    h &= 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    h ^= h >> 15
    return h


def apply_variants(tiles):
    """tiles: [y][x] int array of base tile numbers (0..959). Returns the drawn tile numbers."""
    H, W = tiles.shape
    water = np.isin(tiles, WATER_SET)
    struct = np.isin(tiles, STRUCTURES)
    out = tiles.copy()
    for y in range(H):
        for x in range(W):
            t = tiles[y, x]
            if t == 37:
                k = pos_hash(x, y) % 4
                if k:
                    out[y, x] = WOODS_VARIANTS[k - 1]
            elif t in REPLACEABLE:
                m = 0
                for name, (dx, dy) in DIRS.items():
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < W and 0 <= yy < H and not water[yy, xx]:
                        m |= BITS[name]
                for c, (a, b) in CORNERS.items():
                    if m & BITS[c]:
                        dx, dy = DIRS[c]
                        quad = [(x, y), (x + dx, y), (x, y + dy), (x + dx, y + dy)]
                        if any(0 <= qx < W and 0 <= qy < H and struct[qy, qx] for qx, qy in quad):
                            m &= ~BITS[c]
                out[y, x] = BLOB_TILE[reduce_mask(m)]
    return out


EXT_TILES = list(range(EXT0, EXT_LAST + 1))


def render_ext():
    """{tile: RSxRSx3} for every extension tile."""
    res = {}
    for v, t in enumerate(WOODS_VARIANTS):
        res[t] = woods_variant(v)
    for m, t in BLOB_TILE.items():
        if t >= EXT0:
            res[t] = blob_tile(m)
    return res


EXT_JOBS = [('woods', v, t) for v, t in enumerate(WOODS_VARIANTS)] + [('blob', m, t) for m, t in BLOB_TILE.items() if t >= EXT0]


def render_job(j):
    kind, a, t = EXT_JOBS[j]
    return t, (woods_variant(a) if kind == 'woods' else blob_tile(a))


def write_json():
    table = [BLOB_TILE[reduce_mask(m)] for m in range(256)]
    doc = {
        'atlas': 'atlas_hd64_ext.png (also _ext32 / _ext128): 16 tiles per row, tile t at ((t-960)%16, (t-960)//16)',
        'first_tile': EXT0, 'last_tile': EXT_LAST,
        'note': 'The base atlas is complete and correct alone. These variants are optional substitutions chosen at draw time; the map keeps the base tile numbers.',
        'hash': 'h = ((x*73856093) ^ (y*19349663)) & 0xFFFFFFFF; h ^= h>>13; h = (h*0x5BD1E995) & 0xFFFFFFFF; h ^= h>>15  (x, y map tile coordinates)',
        'rules': [
            {'name': 'woods', 'replaces': [37], 'variants': WOODS_VARIANTS,
             'rule': 'k = hash(x,y) % 4; draw 37 if k == 0 else variants[k-1]. Interior crowns differ, edge crowns are identical, so any choice meets any woods tile.'},
            {'name': 'coast-blob', 'replaces': REPLACEABLE,
             'water_set': WATER_SET, 'structures': STRUCTURES,
             'bits': BITS,
             'rule': ('For a tile in replaces: m = OR of bits for each of the 8 neighbours that is on the map and NOT in water_set '
                      '(off-map counts as water). For each corner bit set, clear it if any of the 4 tiles meeting at that corner '
                      '(this tile, the two side neighbours, the diagonal) is in structures. Then reduce: clear a corner bit if either '
                      'adjacent side bit is set. Draw table[m] (index by the unreduced m after the structure step; the table already '
                      'applies the reduction). table value 2 means plain water.'),
             'table': table,
             'reduced': {str(m): BLOB_TILE[m] for m in REDUCED}},
        ],
    }
    json.dump(doc, open(os.path.join(HERE, 'variants.json'), 'w'), indent=1)


if __name__ == '__main__':
    write_json()
    print('ext tiles', EXT0, '..', EXT_LAST)
