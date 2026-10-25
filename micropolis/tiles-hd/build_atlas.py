#!/usr/bin/env python3
"""Build the HD atlas in the original layout (16 tiles per row, 960 tiles).

usage: build_atlas.py [--only a,b,c] [--jobs N]
Writes atlas_hd32.png, atlas_hd64.png, atlas_hd128.png and redrawn.json next to this file.
Tiles not redrawn are the original upscaled (nearest).
"""
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SRC = os.path.join(HERE, '..', 'content', 'images', 'tiles.png')
NT = 960

from hdlib import RS, Canvas, to_u8  # noqa: E402
import terrain as T  # noqa: E402
import transport as R  # noqa: E402


def single(fn):
    """Wrap a function producing one tile (RS x RS x 3)."""
    return ('one', fn)


REG = {}       # tile -> ('one', fn)
GROUPS = []    # (fn producing {tile: img})


def reg_terrain():
    REG[0] = single(lambda: T.dirt_layer())
    for t in (2, 3, 4) + tuple(79 + 16 * k for k in range(9)):
        REG[t] = single(lambda: T.water_layer())
    for t, s in T.COAST_TILES.items():
        REG[t] = single(lambda s=s: T.coast_tile(s, 0))
        REG[t + 1] = single(lambda s=s: T.coast_tile(s, 1))
    for t, s in T.TREE_TILES.items():
        REG[t] = single(lambda s=s: T.tree_tile(s))
        if t != 37:
            REG[t - 8] = single(lambda s=s: T.tree_tile(s, 1))
    for k in range(4):
        REG[40 + k] = single(lambda k=k: T.park_tile(k))
    for k in range(4):
        REG[44 + k] = single(lambda k=k: T.rubble_tile(k))
        REG[48 + k] = single(lambda k=k: T.flood_tile(k))
    REG[52] = single(lambda: T.radiation_tile())
    for f in range(8):
        REG[56 + f] = single(lambda f=f: T.fire_tile(f))


ROAD_ARMS = ['EW', 'NS', 'NE', 'ES', 'SW', 'NW', 'NEW', 'NES', 'ESW', 'NSW', 'NESW']
RAIL_ARMS = ROAD_ARMS


def road_tile(i, frame=None, heavy=False):
    """i = position 0..14 in a road row (64+i)."""
    if i in (0, 1):
        cv = Canvas(1, 1, RS, T.water_layer())
        arms = 'EW' if i == 0 else 'NS'
        R.draw_road(cv, arms, on_water=True)
    elif i == 13 or i == 14:
        cv = Canvas(1, 1, RS, T.dirt_layer())
        arms = 'EW' if i == 13 else 'NS'
        R.draw_road(cv, arms)
    else:
        cv = Canvas(1, 1, RS, T.dirt_layer())
        arms = ROAD_ARMS[i - 2]
        R.draw_road(cv, arms)
    if frame is not None:
        R.draw_traffic(cv, arms, frame, heavy, seed=17 + i * 3 + (100 if heavy else 0))
    if i == 13:
        R.draw_power(cv, 'NS', pole=False)
    if i == 14:
        R.draw_power(cv, 'EW', pole=False)
    return cv.img


def reg_transport():
    for i in range(15):
        REG[64 + i] = single(lambda i=i: road_tile(i))
        for f in range(4):
            REG[80 + 16 * f + i] = single(lambda i=i, f=f: road_tile(i, f, False))
            t = 144 + 16 * f + i
            if t <= 206:
                REG[t] = single(lambda i=i, f=f: road_tile(i, f, True))
    # power
    def power(arms, water=False):
        cv = Canvas(1, 1, RS, T.water_layer() if water else T.dirt_layer())
        R.draw_power(cv, arms, on_water=water)
        return cv.img
    REG[208] = single(lambda: power('EW', True))
    REG[209] = single(lambda: power('NS', True))
    for k, a in enumerate(ROAD_ARMS):
        REG[210 + k] = single(lambda a=a: power(a))
    # rail
    def rail(arms, water=False):
        cv = Canvas(1, 1, RS, T.water_layer() if water else T.dirt_layer())
        R.draw_rail(cv, arms, on_water=water)
        return cv.img
    REG[224] = single(lambda: rail('EW', True))
    REG[225] = single(lambda: rail('NS', True))
    for k, a in enumerate(RAIL_ARMS):
        REG[226 + k] = single(lambda a=a: rail(a))
    # rail + power
    def railpower(rarms, parms):
        cv = Canvas(1, 1, RS, T.dirt_layer())
        R.draw_rail(cv, rarms)
        R.draw_power(cv, parms, pole=False)
        return cv.img
    REG[221] = single(lambda: railpower('EW', 'NS'))
    REG[222] = single(lambda: railpower('NS', 'EW'))
    # level crossings: 237 = horizontal rail over vertical road, 238 = vertical rail over horizontal road
    REG[237] = single(lambda: level_crossing('EW', 'NS'))
    REG[238] = single(lambda: level_crossing('NS', 'EW'))


def level_crossing(rarms, road):
    import hdlib as H
    cv = Canvas(1, 1, RS, T.dirt_layer())
    R.draw_rail(cv, rarms)
    sd = R.draw_road(cv, road)
    X, Y = cv.X, cv.Y
    on = cv.cov(sd)
    across = Y if rarms == 'EW' else X     # coordinate across the track
    along = X if rarms == 'EW' else Y
    # rubber panel between and around the rails
    panel = (np.abs(across - 0.5) < R.GA + 0.04).astype(float) * on
    cv.paint(H.PAL['concrete'][2], panel)
    seams = (np.abs(((along * 8) % 1) - 0.5) > 0.47) * panel
    cv.shade(seams, 0.5)
    for sg in (-1, 1):
        r = np.abs(across - 0.5 - sg * R.GA)
        cv.paint(H.PAL['steel'][1], cv.cov(r - 0.012) * on)
        cv.paint(H.PAL['steel'][6], cv.cov(np.abs(across - 0.5 - sg * R.GA + 0.003) - 0.005) * on)
    # yellow warning bars across the road on each side of the track
    for sg in (-1, 1):
        bar = (np.abs(across - 0.5 - sg * 0.19) < 0.012) & (np.abs(((along * 10) % 1) - 0.5) < 0.3)
        cv.paint(H.hx('#f2c418'), bar * on)
    return cv.img


def reg_zones_empty():
    import hdlib as H
    from scipy import ndimage
    import buildings as B

    def empty_zone(kind):
        cv = Canvas(3, 3, RS, T.dirt_layer(3, 3))
        B.zone_frame(cv, kind)
        letter = {'res': 'R', 'com': 'C', 'ind': 'I'}[kind]
        m = cv.text_mask(letter, 1.5, 1.52, 0.80, H.FONT_SERIF)
        sh = np.roll(np.roll(m, int(0.03 * RS), 0), int(0.045 * RS), 1)
        cv.shade(ndimage.gaussian_filter(sh, 4), 0.6)
        outline = np.clip(ndimage.maximum_filter(m, 7) - m, 0, 1)
        ramp = H.PAL[kind]
        cv.paint(ramp[0] * 0.5, outline)
        cv.paint(ramp(0.45 + 0.40 * np.clip(1.95 - cv.Y, 0, 1)), m)
        e = np.clip(m - np.roll(np.roll(m, 4, 0), 4, 1), 0, 1)
        cv.light(e, 0.6)
        e2 = np.clip(m - np.roll(np.roll(m, -4, 0), -4, 1), 0, 1)
        cv.shade(e2, 0.45)
        return cv
    for kind, base in (('res', 240), ('com', 423), ('ind', 612)):
        GROUPS.append((base, 3, 3, lambda kind=kind: empty_zone(kind)))


# Building / animation modules, in order; a later module's tiles override an earlier one's.
MODULES = ['buildings', 'blocks_res', 'blocks_com', 'blocks_ind', 'blocks_special', 'anims']


def build_buildings():
    import importlib
    for name in MODULES:
        if not os.path.exists(os.path.join(HERE, name + '.py')):
            continue
        mod = importlib.import_module(name)
        for g in mod.GROUPS:
            GROUPS.append(g)


# ------------------------------------------------------------------ driver
def render_one(t):
    kind, fn = REG[t]
    img = fn()
    return t, img


def render_group(g):
    base, w, h, fn = g
    cv = fn()
    if isinstance(cv, dict):
        return cv
    out = {}
    cells = cv.cells(RS)
    for j in range(h):
        for i in range(w):
            out[base + j * w + i] = cells[j * w + i]
    return out


def downs(img, px):
    f = img.shape[0] // px
    return img.reshape(px, f, px, f, 3).mean(axis=(1, 3))


def main():
    reg_terrain()
    reg_transport()
    reg_zones_empty()
    build_buildings()
    jobs = 8
    only = None
    if '--only' in sys.argv:
        only = set(int(x) for x in sys.argv[sys.argv.index('--only') + 1].split(','))
    t0 = time.time()
    results = {}
    singles = [t for t in REG if only is None or t in only]
    with Pool(jobs) as p:
        for t, img in p.imap_unordered(render_one, singles, chunksize=4):
            results[t] = img
        for out in p.imap_unordered(render_group_idx, range(len(GROUPS))):
            for t, img in out.items():
                if only is None or t in only:
                    results[t] = img
    print('rendered', len(results), 'tiles in %.1fs' % (time.time() - t0))
    guard_edges(results)
    src = Image.open(SRC).convert('RGB')
    for px in (32, 64, 128):
        atlas = src.resize((16 * px, 60 * px), Image.NEAREST)
        a = np.asarray(atlas).copy()
        for t, img in results.items():
            x, y = (t % 16) * px, (t // 16) * px
            a[y:y + px, x:x + px] = to_u8(downs(img, px))
        Image.fromarray(a).save(os.path.join(HERE, 'atlas_hd%d.png' % px))
    if only is None and '--no-ext' not in sys.argv:
        build_ext(jobs)
    write_rgba()
    redrawn = sorted(results)
    if only is None:
        import anims
        unused = sorted(set(anims.UNUSED_DIRT) | set(anims.UNUSED_WATER))
        drawn = [t for t in redrawn if t not in unused]
        kept = [t for t in range(NT) if t not in results]
        json.dump({'tile_px': 64, 'tiles': NT,
                   'redrawn': drawn, 'count': len(drawn),
                   'unused_plain_ground': unused,
                   'original_kept': kept,
                   'note': 'redrawn = generated by our code; unused_plain_ground = slots the engine never draws, filled with plain dirt/water; original_kept = still the original art (nearest-upscaled)'},
                  open(os.path.join(HERE, 'redrawn.json'), 'w'), indent=0)
    print('redrawn', len(redrawn))


def block_map():
    """{tile: (i, j, w, h)} for every cell of every multi-tile building, animation frames included
    (a frame takes the position of the cell it replaces)."""
    import re
    C = json.load(open(os.path.join(HERE, 'classes.json')))
    pos = {}
    for c in C:
        m = re.search(r'cell \((\d),(\d)\) of (\d)x(\d)', c['part_of'] or '')
        if m and not c['class'].startswith('anim'):
            pos[c['tile']] = tuple(map(int, m.groups()))
    import importlib
    for name in MODULES:
        if os.path.exists(os.path.join(HERE, name + '.py')):
            for f, b in getattr(importlib.import_module(name), 'ANIM', {}).items():
                if b in pos:
                    pos[f] = pos[b]
    return pos


# blocks whose outer edge deliberately is not plain ground (none so far)
EDGE_EXEMPT = set()


def guard_edges(results, band=(0.012, 0.024)):
    """Edge contract safety net: within ~1.5 px (at 64) of a building's OUTER border the
    picture fades to the shared plain ground, so nothing (a shadow, a crown, smoke) can
    break the seam with whatever stands next to the block."""
    pos = block_map()
    ground = T.dirt_layer()
    n = RS
    u = (np.arange(n) + 0.5) / n
    for t, img in results.items():
        if t not in pos or t in EDGE_EXEMPT:
            continue
        i, j, w, h = pos[t]
        d = np.full((n, n), 9.0)
        if i == 0:
            d = np.minimum(d, u[None, :])
        if i == w - 1:
            d = np.minimum(d, 1 - u[None, :])
        if j == 0:
            d = np.minimum(d, u[:, None])
        if j == h - 1:
            d = np.minimum(d, 1 - u[:, None])
        wgt = np.clip((band[1] - d) / (band[1] - band[0]), 0, 1)[..., None]
        if wgt.max() > 0:
            results[t] = img * (1 - wgt) + ground * wgt


def render_ext_job(j):
    import variants as V
    return V.render_job(j)


def build_ext(jobs):
    """Extension atlas 960..1023 (variants.py); unused slots are plain ground."""
    import variants as V
    t0 = time.time()
    ext = {}
    with Pool(jobs) as p:
        for t, img in p.imap_unordered(render_ext_job, range(len(V.EXT_JOBS))):
            ext[t] = img
    V.write_json()
    ground = T.dirt_layer()
    for px in (32, 64, 128):
        a = np.zeros((4 * px, 16 * px, 3), np.uint8)
        for k in range(64):
            img = ext.get(960 + k, ground)
            x, y = (k % 16) * px, (k // 16) * px
            a[y:y + px, x:x + px] = to_u8(downs(img, px))
        Image.fromarray(a).save(os.path.join(HERE, 'atlas_hd%d_ext.png' % px))
    print('ext', len(ext), 'tiles in %.1fs' % (time.time() - t0))


def write_rgba():
    """RGBA, premultiplied, for the game: the art has no transparent pixels, so alpha is 255
    everywhere and premultiplied RGB equals RGB."""
    for px in (32, 64, 128):
        for suf in ('', '_ext'):
            src = os.path.join(HERE, 'atlas_hd%d%s.png' % (px, suf))
            if not os.path.exists(src):
                continue
            rgb = np.asarray(Image.open(src).convert('RGB'))
            alpha = np.full(rgb.shape[:2] + (1,), 255, np.uint8)
            pm = (rgb.astype(np.uint16) * alpha // 255).astype(np.uint8)
            Image.fromarray(np.concatenate([pm, alpha], 2), 'RGBA').save(os.path.join(HERE, 'atlas_hd%d%s_rgba.png' % (px, suf)))


def render_group_idx(k):
    return render_group(GROUPS[k])


# populate registries at import so pool workers (fork) see them
reg_terrain()
reg_transport()
reg_zones_empty()
build_buildings()

if __name__ == '__main__':
    REG_COPY = dict(REG)
    GROUPS_COPY = list(GROUPS)
    REG.clear(); GROUPS.clear()
    main()
