#!/usr/bin/env python3
"""Preview one building/animation module without touching the atlas.

usage: preview.py MODULE [--only BASE,BASE,...] [--px 64] [--out FILE]

For every group (base, w, h, fn) in MODULE.GROUPS it draws the original block
(tiles.png, nearest) beside the HD render, both at --px per tile, labelled.
If MODULE.ANIM = {frame_tile: base_cell_tile} exists, every animation frame is
also shown substituted into its block (original | HD), which is how the game
shows it - use it to check that frames meet their neighbours.
Writes preview_MODULE.png (or --out).
"""
import importlib
import os
import sys
import multiprocessing

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hdlib import RS, to_u8  # noqa: E402

SRC = Image.open(os.path.join(HERE, '..', 'content', 'images', 'tiles.png')).convert('RGB')
FONT = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 15)
MOD = None
PX = 64
GROUPS_SEL = []   # filled before the pool forks; workers index into it


def downs(img, px):
    f = img.shape[0] // px
    return img.reshape(px, f, px, f, 3).mean(axis=(1, 3))


def render(k):
    base, w, h, fn = GROUPS_SEL[k]
    cv = fn()
    if isinstance(cv, dict):
        return {t: to_u8(downs(im, PX)) for t, im in cv.items()}
    cells = cv.cells(PX)
    return {base + j * w + i: to_u8(cells[j * w + i]) for j in range(h) for i in range(w)}


def orig_tile(t):
    x, y = (t % 16) * 16, (t // 16) * 16
    return np.asarray(SRC.crop((x, y, x + 16, y + 16)).resize((PX, PX), Image.NEAREST))


def block(tiles_fn, base, w, h, sub=None):
    a = np.zeros((h * PX, w * PX, 3), np.uint8)
    for j in range(h):
        for i in range(w):
            t = base + j * w + i
            if sub and t in sub:
                t = sub[t]
            im = tiles_fn(t)
            if im is not None:
                a[j * PX:(j + 1) * PX, i * PX:(i + 1) * PX] = im
    return a


def main():
    global MOD, PX
    name = sys.argv[1]
    only = None
    if '--only' in sys.argv:
        only = set(int(x) for x in sys.argv[sys.argv.index('--only') + 1].split(','))
    if '--px' in sys.argv:
        PX = int(sys.argv[sys.argv.index('--px') + 1])
    out = os.path.join(HERE, 'preview_%s.png' % name)
    if '--out' in sys.argv:
        out = sys.argv[sys.argv.index('--out') + 1]
    MOD = importlib.import_module(name)
    groups = [g for g in MOD.GROUPS if only is None or g[0] in only]
    GROUPS_SEL[:] = groups
    res = {}
    with multiprocessing.get_context("fork").Pool(min(12, max(1, len(groups)))) as p:
        for d in p.imap_unordered(render, range(len(groups))):
            res.update(d)
    hd = lambda t: res.get(t)
    panels = []
    anim = getattr(MOD, 'ANIM', {})
    for (base, w, h, fn) in groups:
        rng = set(range(base, base + w * h))
        panels.append(('%d..%d' % (base, base + w * h - 1), block(orig_tile, base, w, h), block(hd, base, w, h)))
        for f, b in sorted(anim.items()):
            if b in rng and f in res:
                panels.append(('frame %d in %d' % (f, b), block(orig_tile, base, w, h, {b: f}), block(hd, base, w, h, {b: f})))
    # tiles rendered that are not inside any block and not anim frames: show singly
    inblock = set()
    for (base, w, h, fn) in groups:
        inblock |= set(range(base, base + w * h))
    loose = sorted(t for t in res if t not in inblock and t not in anim)
    for t in loose:
        panels.append(('%d' % t, orig_tile(t), res[t]))
    # layout: panels in rows, max width ~ 2600
    pad, lab = 12, 20
    rows, cur, curw = [], [], 0
    for p in panels:
        pw = p[1].shape[1] * 2 + pad * 3
        if curw + pw > 2600 and cur:
            rows.append(cur); cur, curw = [], 0
        cur.append(p); curw += pw
    if cur:
        rows.append(cur)
    W = max(sum(p[1].shape[1] * 2 + pad * 3 for p in r) for r in rows)
    H = sum(max(p[1].shape[0] for p in r) + lab + pad for r in rows) + pad
    img = Image.new('RGB', (W, H), (28, 28, 32))
    d = ImageDraw.Draw(img)
    y = pad
    for r in rows:
        x = 0
        for (label, a, b) in r:
            d.text((x + pad, y), label, font=FONT, fill=(230, 230, 230))
            img.paste(Image.fromarray(a), (x + pad, y + lab))
            img.paste(Image.fromarray(b), (x + pad * 2 + a.shape[1], y + lab))
            x += a.shape[1] * 2 + pad * 3
        y += max(p[1].shape[0] for p in r) + lab + pad
    img.save(out)
    print(out, len(res), 'tiles')


if __name__ == '__main__':
    main()
