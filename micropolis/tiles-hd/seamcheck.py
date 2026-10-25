#!/usr/bin/env python3
"""Seam check: for every pair of redrawn tiles that the engine can put side by side and whose
edge contracts agree, compare the two touching pixel columns/rows (64 px atlas).
Reports mean |diff| (0..255) per family pair and the worst pairs."""
import itertools
import os
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
A = np.asarray(Image.open(os.path.join(HERE, 'atlas_hd64.png')).convert('RGB')).astype(float)
P = 64


def tile(n):
    return A[(n // 16) * P:(n // 16 + 1) * P, (n % 16) * P:(n % 16 + 1) * P]


ARMS = ['EW', 'NS', 'NE', 'ES', 'SW', 'NW', 'NEW', 'NES', 'ESW', 'NSW', 'NESW']
fam = {}
fam[0] = ('land', '')
for k, a in enumerate(ARMS):
    fam[66 + k] = ('road', a)
    fam[226 + k] = ('rail', a)
    fam[210 + k] = ('power', a)
COAST = {5: 'N', 13: 'S', 17: 'W', 9: 'E', 15: 'SW', 19: 'NW', 11: 'SE', 7: 'NE'}
for t, s in COAST.items():
    fam[t] = ('coast', s)
    fam[t + 1] = ('coast', s)
fam[2] = ('coast', '')
TREES = {34: 'SW', 36: 'NW', 35: 'W', 32: 'SE', 33: 'S', 30: 'NE', 31: 'E', 29: 'N', 37: ''}
for t, s in TREES.items():
    fam[t] = ('tree', s)
    if t != 37:
        fam[t - 8] = ('tree', s)

OPP = {'E': 'W', 'W': 'E', 'N': 'S', 'S': 'N'}


def edge(n, side):
    t = tile(n)
    return {'E': t[:, -1], 'W': t[:, 0], 'N': t[0, :], 'S': t[-1, :]}[side]


def compatible(a, b, side):
    """a is left/top of b across `side` of a."""
    fa, sa = fam[a]
    fb, sb = fam[b]
    o = OPP[side]
    if fa in ('road', 'rail', 'power') and fa == fb:
        return (side in sa) == (o in sb)
    if fa in ('road', 'rail', 'power') and fb == 'land':
        return side not in sa
    if fb in ('road', 'rail', 'power') and fa == 'land':
        return o not in sb
    if fa == fb == 'coast' or fa == fb == 'tree':
        # both water/forest across this edge, and the land side(s) along it agree
        if side in sa or o in sb:
            return False
        perp = 'NS' if side in 'EW' else 'EW'
        return all((p in sa) == (p in sb) for p in perp)
    return False


res = {}
worst = []
for a, b in itertools.product(fam, fam):
    for side in 'ES':
        if compatible(a, b, side):
            d = np.abs(edge(a, side) - edge(b, OPP[side])).mean()
            key = (fam[a][0], fam[b][0])
            res.setdefault(key, []).append(d)
            worst.append((d, a, b, side))
for k, v in sorted(res.items()):
    print('%-16s pairs %4d  mean %5.2f  max %5.2f' % ('%s|%s' % k, len(v), np.mean(v), np.max(v)))
worst.sort(reverse=True)
print('worst:', [(round(d, 1), a, b, s) for d, a, b, s in worst[:8]])
# reference: two unrelated dirt-texture columns from the same tile
t0 = tile(0)
print('reference (adjacent columns inside dirt tile): %.2f' % np.abs(t0[:, 31] - t0[:, 32]).mean())


# ====================================================================== buildings, animations, variants
import json, re, sys, importlib
sys.path.insert(0, HERE)


def ref_inside(n):
    """Mean |diff| between neighbouring pixel columns/rows inside tile n (its own texture)."""
    t = tile(n)
    return (np.abs(np.diff(t, axis=1)).mean() + np.abs(np.diff(t, axis=0)).mean()) / 2


C = json.load(open(os.path.join(HERE, 'classes.json')))
BLOCKS = {}
for c in C:
    m = re.search(r'cell \((\d),(\d)\) of (\d)x(\d)', c['part_of'] or '')
    if m and not c['class'].startswith('anim'):
        i, j, w, h = map(int, m.groups())
        BLOCKS[c['tile'] - j * w - i] = (w, h)

# 1. outer edge of every multi-tile building against the plain ground it stands on
print('\n-- building outer edges vs plain ground (0 = identical to dirt tile 0) --')
bad = []
allw = []
for base, (w, h) in sorted(BLOCKS.items()):
    ds = []
    for j in range(h):
        for i in range(w):
            n = base + j * w + i
            for side, cond in (('W', i == 0), ('E', i == w - 1), ('N', j == 0), ('S', j == h - 1)):
                if cond:
                    ds.append(np.abs(edge(n, side) - edge(0, side)).mean())
    worst = max(ds)
    allw.append(worst)
    if worst > 6:
        bad.append((base, round(worst, 1)))
print('blocks %d, worst outer edge %.2f; blocks whose outer edge departs from plain ground by > 6: %s' % (len(BLOCKS), max(allw), bad or 'none'))

# 2. internal seams of blocks: |diff| across every internal cell edge vs inside-tile texture
worst_int = []
for base, (w, h) in sorted(BLOCKS.items()):
    for j in range(h):
        for i in range(w):
            n = base + j * w + i
            # ratio of the step across the cell boundary to the largest step one pixel either side
            if i < w - 1:
                a_, b_ = tile(n), tile(n + 1)
                cross = np.abs(a_[:, -1] - b_[:, 0]).mean()
                near = max(np.abs(a_[:, -1] - a_[:, -2]).mean(), np.abs(b_[:, 1] - b_[:, 0]).mean(), 1)
                worst_int.append((cross / near, base, n, 'E'))
            if j < h - 1:
                a_, b_ = tile(n), tile(n + w)
                cross = np.abs(a_[-1] - b_[0]).mean()
                near = max(np.abs(a_[-1] - a_[-2]).mean(), np.abs(b_[1] - b_[0]).mean(), 1)
                worst_int.append((cross / near, base, n, 'S'))
worst_int.sort(reverse=True)
print('internal block seams: %d edges; step across the cell edge / largest step beside it: worst %.2f (%s), mean %.2f' % (
    len(worst_int), worst_int[0][0], worst_int[0][1:], np.mean([x[0] for x in worst_int])))

# 3. animation frames: every frame's four edges vs its static cell's edges
ANIM = {}
for name in ('buildings', 'blocks_res', 'blocks_com', 'blocks_ind', 'blocks_special', 'anims'):
    if os.path.exists(os.path.join(HERE, name + '.py')):
        ANIM.update(getattr(importlib.import_module(name), 'ANIM', {}))
WOF = {}
for base, (w, h) in BLOCKS.items():
    for t in range(base, base + w * h):
        WOF[t] = w
animated_bases = set(ANIM.values())
af = []
for f, b in sorted(ANIM.items()):
    w = WOF.get(b, 1)
    # a side shared with another animated cell of the same building is skipped: both cells are
    # switched together and run in step, so they meet frame for frame (checked below)
    sides = [s for s, o in (('N', -w), ('S', w), ('W', -1), ('E', 1)) if (b + o) not in animated_bases]
    d = max(np.abs(edge(f, s) - edge(b, s)).mean() for s in sides)
    af.append((d, f, b))
# in-step pairs: frame k of one cell against frame k of its partner
pairs = []
inv = {}
for f, b in ANIM.items():
    inv.setdefault(b, []).append(f)
for b, fs in inv.items():
    fs.sort()
    w = WOF.get(b, 1)
    for s, o in (('S', w), ('E', 1)):
        if b + o in inv:
            for k, f in enumerate(fs):
                g = inv[b + o][k % len(inv[b + o])]
                pairs.append(np.abs(edge(f, s) - edge(g, OPP[s])).mean() / max(ref_inside(f), 1))
af.sort(reverse=True)
print('\n-- animation frames vs their static cell (edge |diff|, 0 = identical) --')
print('frames %d, worst %s' % (len(af), [(round(d, 2), f, b) for d, f, b in af[:6]]))
print('in-step animated pairs: %d frame edges, worst ratio to in-tile texture %.2f' % (len(pairs), max(pairs) if pairs else 0))

# 4. variants: woods variants against every compatible tree tile; blob coast on random maps
import variants as V
EXT = np.asarray(Image.open(os.path.join(HERE, 'atlas_hd64_ext.png')).convert('RGB')).astype(float)


def tile2(n):
    if n >= 960:
        k = n - 960
        return EXT[(k // 16) * P:(k // 16 + 1) * P, (k % 16) * P:(k % 16 + 1) * P]
    return tile(n)


def edge2(n, side):
    t = tile2(n)
    return {'E': t[:, -1], 'W': t[:, 0], 'N': t[0, :], 'S': t[-1, :]}[side]


wd = []
for v in V.WOODS_VARIANTS:
    for t, s in TREES.items():
        for side in 'NESW':
            if OPP[side] not in s:   # tile t has trees on the side facing the variant
                d = np.abs(edge2(v, side) - edge2(t, OPP[side])).mean()
                d0 = np.abs(edge2(37, side) - edge2(t, OPP[side])).mean()
                wd.append(d - d0)
print('\n-- woods variants: edge |diff| minus that of base 37 in the same place (0 = as seamless as 37) --')
print('pairs %d, max excess %.3f' % (len(wd), max(wd)))

rng = np.random.default_rng(7)
sd_all, sd_land = [], []
for trial in range(30):
    lw = rng.random((26, 26)) < 0.5
    from scipy import ndimage as ndi
    lw = ndi.binary_opening(ndi.binary_closing(lw)) if trial % 2 else lw
    tiles = np.where(lw, 0, 2)
    tv = V.apply_variants(tiles)
    for y in range(25):
        for x in range(25):
            a = tv[y, x]
            for (dx, dy, side) in ((1, 0, 'E'), (0, 1, 'S')):
                b = tv[y + dy, x + dx]
                d = np.abs(edge2(a, side) - edge2(b, OPP[side])).mean()
                if a != 0 and b != 0:
                    sd_all.append(d)
                elif a != b:
                    sd_land.append(d)
print('\n-- blob coast on 30 random 26x26 maps --')
print('water|water edges %d mean %.2f max %.2f;  water|land edges %d mean %.2f max %.2f' % (
    len(sd_all), np.mean(sd_all), np.max(sd_all), len(sd_land), np.mean(sd_land), np.max(sd_land)))
print('reference: inside water tile 2 %.2f, inside dirt %.2f, inside woods 37 %.2f' % (ref_inside(2), ref_inside(0), ref_inside(37)))
