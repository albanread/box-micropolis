"""Industrial zone blocks 621..692 (8 blocks, density 0..3 x land value 0..1) and their animations.

base = (value*4 + density)*9 + 621.  Animated cells (from the engine's animation table):
  852..859  cell (0,0) of 621   (8 frames: the four piston pumps)
  884..887  cell (2,0) of 639,  888..891 cell (2,1) of 639   (smoke)
  892..895  cell (1,0) of 648,  896..899 cell (2,0) of 648
  900..903  cell (1,0) of 675,  904..907 cell (2,0) of 675
  908..911  cell (2,0) of 684,  912..915 cell (2,1) of 684
Each frame is the whole block drawn again with only the moving parts changed; two sequences in
one block run in step, so their smoke is clipped to the union of the block's animated cells.

GROUPS / ANIM follow BRIEF.md.
"""
import math
import numpy as np
from hdlib import *
from terrain import dirt_layer, draw_crown
from scene3d import Box, Cylinder, Tree, Custom, P, hull
from buildings import zone_frame, paving, rect, vehicle, roof_units, smoke_puffs, cell_clip

GROUPS = []
ANIM = {}

# ------------------------------------------------------------------ colours
CON = PAL['concrete']
GREY = CON[3]            # original #7f7f7f
LGREY = CON[5]           # original #bfbfbf
DGREY = PAL['asphalt'][4]  # original #3f3f3f
STACK = hx('#34363c')    # the original's black chimneys
SMOKE = (0.76, 0.68, 0.56)  # the original's smoke is brown-grey
RED = hx('#c8352a')
BLUE = hx('#3a46d8')
WIN_W = {'kind': 'grid', 'floor': 0.11, 'col': 0.10, 'wfrac': 0.40, 'hfrac': 0.42, 'glass': Ramp(['#20242c', '#2c3440', '#3c4a5c', '#56687e'])}
WIN_S = {'kind': 'grid', 'floor': 0.11, 'col': 0.12, 'wfrac': 0.40, 'hfrac': 0.40, 'glass': Ramp(['#121418', '#1c2028', '#2a303a', '#3a4250'])}
RIBS = {'kind': 'ribs', 'col': 0.035}


# ------------------------------------------------------------------ kit (module-local primitives)
def render_in(cv, items, strength=0.62, margin=0.035):
    """scene3d.render, with every drop shadow kept off the block's outermost margin."""
    sh = np.zeros_like(cv.X)
    for it in items:
        if isinstance(it, Tree):
            sh = np.maximum(sh, it.shadow(cv))
            continue
        p = it.shadow_poly()
        if p:
            sh = np.maximum(sh, cv.poly(p))
    sh = cv.blur(sh, 0.008)
    inner = np.clip((-sd_box(cv.X, cv.Y, 0, 0, cv.wt, cv.ht) - margin) / 0.03, 0, 1)
    cv.shade(sh * inner, strength)
    for it in sorted(items, key=lambda i: i.key()):
        it.draw(cv)


def stack_at(top, z0, h, r=0.055, col=STACK, band=RED, order=0.0, bands=None):
    """A chimney standing at z0 whose open top projects to screen point top."""
    cx = top[0] - OX * (z0 + h)
    cy = top[1] + OY * (z0 + h)
    if bands is None:
        bands = [(h * 0.70, 0.07, band), (h * 0.84, 0.04, band)] if band is not None else None
    c = Cylinder(cx, cy, r, h, col, top=col * 0.6, z0=z0, hollow=True, bands=bands)
    c.key = (lambda o=order: (10 + o, 0))
    return c


SMOKE_DARK = np.array([0.30, 0.24, 0.18])   # sooty, at the stack
SMOKE_LIGHT = np.array([0.88, 0.72, 0.52])  # the original's brown-grey (#997f4c / #cc7f66 family), thinned


def ind_smoke(cv, tops, frame, cells, drift=(0.78, -0.62), rise=0.9, spread=0.17, n_puff=11, r0=0.085):
    """Dense brown-grey plumes: dark at the stack, paler and wider as they rise; 4-frame loop.
    Clipped to the union of the animated cells (fading before its outer border) and off the block margin."""
    dl = math.hypot(*drift)
    dx, dy = drift[0] / dl, drift[1] / dl
    nx, ny = -dy, dx
    puffs = []
    for si, (sx, sy) in enumerate(tops):
        for k in range(n_puff):
            t = ((k + frame / 4.0 + (si * 0.37) % 1) / n_puff) % 1.0
            wob = 0.035 * math.sin(2 * math.pi * t * 1.5 + si * 1.7) * t
            puffs.append((t, sx + dx * rise * t + nx * wob, sy + dy * rise * t + ny * wob))
    a_tot = np.zeros_like(cv.X)
    col_acc = np.zeros(cv.img.shape)
    for (t, px, py) in sorted(puffs, key=lambda p: -p[0]):     # oldest first, fresh smoke on top
        r = r0 + spread * t
        alpha = smoothstep(0.0, 0.05, t) * (1 - t) ** 0.7
        d = np.hypot(cv.X - px, cv.Y - py)
        m = np.clip(1.35 - 1.35 * d / r, 0, 1) ** 0.45 * alpha
        if m.max() <= 0:
            continue
        lam = np.clip(0.55 + ((px - cv.X) * 0.7 + (py - cv.Y) * 0.7) / r * 0.6, 0, 1)
        base = SMOKE_DARK + (SMOKE_LIGHT - SMOKE_DARK) * (t ** 0.6)
        c = base[None, None, :] * (0.62 + 0.45 * lam)[..., None]
        col_acc = col_acc * (1 - m[..., None]) + c * m[..., None]
        a_tot = a_tot * (1 - m) + m
    col = col_acc / np.maximum(a_tot, 1e-6)[..., None]
    clip = cell_clip(cv, cells, 0.10) * np.clip((-sd_box(cv.X, cv.Y, 0, 0, cv.wt, cv.ht) - 0.09) / 0.07, 0, 1)
    a = np.clip(a_tot * clip, 0, 1)
    cv.img = cv.img * (1 - a[..., None]) + np.clip(col, 0, 1) * a[..., None]


def ground_pipe(cv, pts, w=0.035, col=None, z=0.03):
    """A pipe lying on low supports: soft shadow, rounded body lit from the upper left."""
    col = np.asarray(col if col is not None else CON[4], float)
    d = sd_polyline(cv.X, cv.Y, pts)
    sd = sd_polyline(cv.X - SHADOW_DIR[0] * z * 2, cv.Y - SHADOW_DIR[1] * z * 2, pts)
    cv.shade(cv.cov(sd - w * 0.6, 4), 0.45)
    m = cv.cov(d - w / 2)
    # light across the pipe: lit toward the north-west
    q = np.clip(1 - d / (w / 2), 0, 1)
    sx = sd_polyline(cv.X + 0.006, cv.Y + 0.006, pts) - d     # >0 on the lit (upper-left) side
    lam = 0.62 + 0.25 * np.sign(sx) * (1 - q) + 0.15 * q
    cv.paint(col[None, None, :] * lam[..., None], m)


def htank(x0, x1, cy, r, col, cap=None, key=None):
    """A horizontal cylindrical tank lying east-west on the ground; its west end is seen."""
    col = np.asarray(col, float)
    th = np.linspace(0, 2 * math.pi, 48, endpoint=False)

    def cap_pts(x):
        return [(x + OX * r * (1 + math.sin(t)), cy + r * math.cos(t) - OY * r * (1 + math.sin(t))) for t in th]

    c0, c1 = cap_pts(x0), cap_pts(x1)
    ys = [p[1] for p in c0]
    ytop, ybot = min(ys), max(ys)

    def draw(cv):
        m = cv.poly(hull(c0 + c1))
        s = np.clip((cv.Y - ytop) / (ybot - ytop), 0, 1)
        lam = 1.08 - 0.62 * s ** 1.3 + 0.12 * np.exp(-((s - 0.22) / 0.08) ** 2)
        cv.paint(col[None, None, :] * lam[..., None], m)
        # weld seams around the shell
        for k in range(1, 4):
            xs = x0 + (x1 - x0) * k / 4
            cv.shade(cv.cov(sd_polyline(cv.X, cv.Y, cap_pts(xs)[12:37]) - 0.004, 1.0) * m, 0.35)
        mc = cv.poly(c0)
        cv.paint(col * 0.95, mc)
        ccx, ccy = x0 + OX * r, cy - OY * r
        if cap is not None:
            cv.paint(cap, cv.poly([(ccx + (px - ccx) * 0.62, ccy + (py - ccy) * 0.62) for px, py in c0]))
        cv.shade(cv.cov(np.abs(sd_polyline(cv.X, cv.Y, c0 + c0[:1])) - 0.004, 1.0), 0.4)

    foot = [(x0, cy - r), (x1, cy - r), (x1, cy + r), (x0, cy + r)]
    sh = hull(foot + [(x + SHADOW_DIR[0] * 2 * r, y + SHADOW_DIR[1] * 2 * r) for x, y in foot])
    return Custom(draw, key=key if key is not None else (cy - (x0 + x1) / 2, 0), shadow=sh)


def shrub(cv, x, y, r, seed):
    cv.shade(cv.cov(sd_circle(cv.X, cv.Y, x + 0.03, y + 0.02, r), 4), 0.45)
    draw_crown(cv, x, y, r, seed)


def lamps(pts, col=hx('#ff9a1a'), r=0.018):
    def fn(cv, *a):
        for (x, y) in pts:
            cv.light(cv.cov(sd_circle(cv.X, cv.Y, x, y, r * 2.2), 6), 0.35, col)
            cv.paint(col, cv.cov(sd_circle(cv.X, cv.Y, x, y, r)))
            cv.light(cv.cov(sd_circle(cv.X, cv.Y, x - r * 0.3, y - r * 0.3, r * 0.4)), 0.6)
    return fn


def chain(*fns):
    def fn(cv, *a):
        for f in fns:
            f(cv, *a)
    return fn


def vents(pts, s=0.05, col=None):
    """Dark square roof vents (the original's black dots on roofs)."""
    def fn(cv, *a):
        c = np.asarray(col if col is not None else PAL['asphalt'][1], float)
        for (x, y) in pts:
            cv.light(rect(cv, x - s / 2 - 0.008, y - s / 2 - 0.008, x + s / 2, y + s / 2), 0.25)
            cv.paint(c, rect(cv, x - s / 2, y - s / 2, x + s / 2, y + s / 2, 0.004))
            cv.paint(c * 1.8, rect(cv, x - s / 2, y - s / 2, x + s / 2, y - s / 2 + 0.008))
    return fn


def louvres(x0, y0, x1, y1, n, col=None):
    def fn(cv, *a):
        c = np.asarray(col if col is not None else CON[6], float)
        w = (x1 - x0) / n
        for k in range(n):
            xa = x0 + k * w
            cv.shade(rect(cv, xa + 0.01, y0 + 0.01, xa + w * 0.55 + 0.012, y1 + 0.012), 0.4)
            cv.paint(c, rect(cv, xa, y0, xa + w * 0.55, y1, 0.003))
    return fn


def anim_group(base, draw, seqs, nframes=4):
    """seqs: list of ((i, j), first_frame_tile). Returns the group fn (dict of tiles)."""
    for (i, j), ft in seqs:
        for f in range(nframes):
            ANIM[ft + f] = base + j * 3 + i

    def fn():
        out = {}
        cells = draw(None).cells(RS)
        for k in range(9):
            out[base + k] = cells[k]
        for f in range(nframes):
            cl = draw(f).cells(RS)
            for (i, j), ft in seqs:
                out[ft + f] = cl[j * 3 + i]
        return out
    return fn


def block(paved=None, tone=0.46):
    cv = Canvas(3, 3, RS, dirt_layer(3, 3))
    if paved is not None:
        paving(cv, paved(cv), tone, 4)
    return cv


# ------------------------------------------------------------------ 621: low value, density 0 (pumps, pipes, silos)
PUMPS = [(0.10, 0.12, 0.0), (0.52, 0.12, 0.5), (0.10, 0.54, 0.625), (0.52, 0.54, 0.125)]
ROD_MIN, ROD_MAX = 0.06, 0.34


def pump_unit(x0, y0, L, items, cv):
    # pad and the rail along its west side (drawn on the ground)
    cv.shade(rect(cv, x0 + 0.02, y0 + 0.02, x0 + 0.37, y0 + 0.36, 0.02), 0.35)
    cv.paint(PAL['timber'](0.42 + 0.05 * (cached_n(cv) - 0.5)), rect(cv, x0, y0, x0 + 0.34, y0 + 0.34, 0.02))
    cv.paint(PAL['timber'][2], cv.cov(np.abs(sd_box(cv.X, cv.Y, x0, y0, x0 + 0.34, y0 + 0.34, 0.02)) - 0.006) * 0.7)
    cv.paint(CON[6], rect(cv, x0 + 0.020, y0 + 0.04, x0 + 0.050, y0 + 0.31, 0.006))
    cv.paint(RED * 0.9, rect(cv, x0 + 0.06, y0 + 0.08, x0 + 0.10, y0 + 0.31, 0.006))
    cv.paint(RED * 0.9, rect(cv, x0 + 0.06, y0 + 0.27, x0 + 0.31, y0 + 0.31, 0.006))
    hb = Box(x0 + 0.08, y0 + 0.13, x0 + 0.27, y0 + 0.29, 0.11, RED, PAL['roof_tar'][2], parapet=False, rim=None)
    items.append(hb)
    xr, yr = x0 + 0.165, y0 + 0.225
    lit = L > (ROD_MIN + ROD_MAX) / 2

    def rod(c, xr=xr, yr=yr, L=L, lit=lit):
        a = P(xr, yr, 0.10)
        b = P(xr, yr, 0.10 + L)
        d = sd_segment(c.X, c.Y, a[0], a[1], b[0], b[1])
        r = 0.036
        m = c.cov(d - r)
        side = ((c.X - a[0]) * (-0.7071) + (c.Y - a[1]) * (-0.7071))   # toward the upper left
        lam = np.clip(0.62 + 0.4 * side / r, 0.35, 1.1)
        c.paint(CON[8][None, None, :] * lam[..., None], m)
        # collar where the rod leaves the housing
        c.paint(CON[2], c.cov(sd_circle(c.X, c.Y, a[0], a[1], 0.038)))
        lc = hx('#ff3020') if lit else hx('#30e040')
        c.light(c.cov(sd_circle(c.X, c.Y, b[0], b[1], 0.05), 8), 0.35, lc)
        c.paint(lc * 0.7, c.cov(sd_circle(c.X, c.Y, b[0], b[1], 0.032)))
        c.paint(lc, c.cov(sd_circle(c.X, c.Y, b[0] - 0.004, b[1] - 0.004, 0.024)))
        c.light(c.cov(sd_circle(c.X, c.Y, b[0] - 0.008, b[1] - 0.008, 0.007)), 0.7)
    items.append(Custom(rod, key=(20 + y0 - x0, 0)))


_nc = {}


def cached_n(cv):
    k = (cv.W, cv.H)
    if k not in _nc:
        _nc[k] = pnoise(cv.n, 24, 911, cv.wt, cv.ht)
    return _nc[k]


def ind_621(frame=None):
    cv = block()
    zone_frame(cv, 'ind')
    # pipework on the ground, as the original's grey runs
    pipes = [[(1.55, 0.14), (1.55, 0.52), (1.36, 0.70), (1.36, 1.66), (0.78, 1.66)],
             [(1.36, 1.66), (1.36, 2.16), (1.56, 2.40), (2.16, 2.40)],
             [(1.36, 0.86), (1.72, 0.86)],
             [(1.36, 1.30), (1.80, 1.30), (1.80, 1.86)],
             [(1.25, 2.45), (1.56, 2.45)]]
    for p in pipes:
        ground_pipe(cv, p, 0.045, CON[3])
    for p in pipes:
        for (x, y) in p[1:-1]:
            cv.paint(CON[2], cv.cov(sd_circle(cv.X, cv.Y, x, y, 0.035)))
    items = []
    for (x0, y0, ph) in PUMPS:
        if frame is None:
            L = ROD_MAX
        else:
            L = ROD_MIN + (ROD_MAX - ROD_MIN) * (0.5 + 0.5 * math.cos(2 * math.pi * (frame / 8.0 + ph)))
        pump_unit(x0, y0, L, items, cv)
    # the horizontal tank and its pump house
    items.append(htank(1.62, 2.38, 0.82, 0.21, LGREY * 0.95, cap=PAL['asphalt'][1], key=(-2, 0)))
    items.append(Box(1.95, 1.06, 2.52, 1.36, 0.16, GREY, PAL['roof_tar'][3], win=WIN_S, roof_detail=roof_units([(0.15, 0.25, 0.12, 0.3)])))
    # three open-topped silos
    for (cx, cy) in ((0.52, 1.52), (1.85, 1.98), (2.15, 2.42)):
        items.append(Cylinder(cx, cy, 0.15, 0.58, CON[6], top=CON[7], hollow=True,
                              bands=[(0.12, 0.025, CON[4]), (0.40, 0.025, CON[4])]))
    items.append(Box(0.92, 2.32, 1.25, 2.68, 0.18, LGREY, PAL['roof_tar'][4], win=WIN_S))
    render_in(cv, items)
    return cv


# ------------------------------------------------------------------ 630: low value, density 1 (brown-roof warehouse, dark shed)
def ind_630(frame=None):
    cv = block()
    paving(cv, rect(cv, 0.16, 1.62, 1.40, 2.50, 0.03), 0.40, 4)        # loading apron
    paving(cv, rect(cv, 0.10, 2.32, 0.80, 2.50), 0.38, 4)
    zone_frame(cv, 'ind')
    brown = PAL['timber'][4]
    items = [
        Box(0.13, 0.55, 1.20, 1.77, 0.50, GREY, brown, win=WIN_S, win_w={'kind': 'grid', 'floor': 0.2, 'col': 0.16, 'wfrac': 0.3, 'hfrac': 0.3, 'glass': Ramp(['#c8ccd2', '#e8eaee'])},
            rim=PAL['timber'][2], roof_detail=chain(roof_units([(0.06, 0.06, 0.12, 0.08)], PAL['timber'][2]))),
        # dark shed, roof in two tones as in the original
        Box(1.55, 0.86, 2.20, 2.80, 0.20, LGREY, PAL['roof_tar'][2], win=None, win_w={'kind': 'grid', 'floor': 0.4, 'col': 0.45, 'wfrac': 0.18, 'hfrac': 0.3, 'margin': 0.2, 'glass': Ramp(['#e8eaee', '#ffffff'])},
            rim=PAL['roof_tar'][3], roof_detail=vents([(2.06 - 1.55 + 1.55 + 0.0, 1.25), (2.06, 1.68), (2.06, 2.10)], 0.04, CON[5])),
        Box(2.20, 0.86, 2.76, 2.80, 0.20, PAL['roof_tar'][2], PAL['roof_tar'][0], win=WIN_S, rim=PAL['roof_tar'][2],
            roof_detail=vents([(2.48, 1.25), (2.48, 1.68), (2.48, 2.10)], 0.04, PAL['roof_tar'][3])),
        Box(1.94, 0.42, 2.22, 0.70, 0.12, GREY, PAL['roof_tar'][2], win=None),
        Box(2.30, 0.30, 2.66, 0.62, 0.14, GREY, PAL['roof_tar'][3], win=WIN_S, roof_detail=roof_units([(0.3, 0.3, 0.3, 0.25)], CON[4])),
        Box(1.05, 2.56, 1.30, 2.76, 0.08, BLUE, BLUE * 1.1, parapet=False),
        Box(0.36, 2.28, 0.54, 2.40, 0.06, PAL['timber'][3], PAL['timber'][4], parapet=False),
    ]
    items[0].key = lambda: (-1, 0)

    def signal(c):
        bx, by = 0.86, 2.02
        t = P(bx, by, 0.40)
        c.shade(c.cov(sd_segment(c.X, c.Y, bx, by, bx + SHADOW_DIR[0] * 0.34, by + SHADOW_DIR[1] * 0.34) - 0.008, 2), 0.4)
        c.paint(PAL['steel'][2], c.cov(sd_segment(c.X, c.Y, bx, by, t[0], t[1]) - 0.013))
        for z, col in ((0.36, '#ff8a1a'), (0.26, '#30d040')):
            q = P(bx, by, z)
            c.paint(hx('#202020'), c.cov(sd_circle(c.X, c.Y, q[0], q[1], 0.042)))
            c.paint(hx(col), c.cov(sd_circle(c.X, c.Y, q[0], q[1], 0.03)))
    items.append(Custom(signal, key=(5, 0)))
    items.append(Custom(lambda c: vehicle(c, 0.46, 2.66, 0.36, 0.13, '#eef0f2', stripe='#4a5ad8'), key=(5, 0)))
    render_in(cv, items)
    return cv


# ------------------------------------------------------------------ 639: low value, density 2 (works with two stacks)
T639 = [(2.22, 0.96), (2.22, 1.56)]


def ind_639(frame=None):
    cv = block(lambda c: rect(c, 0.14, 0.14, 2.90, 2.52, 0.03), 0.44)
    paving(cv, rect(cv, 1.22, 1.40, 1.48, 2.52), 0.66, 6)                 # light walkway
    cv.paint(PAL['timber'][3], rect(cv, 1.00, 1.34, 1.22, 1.50, 0.01) * 0.9)  # pallets
    zone_frame(cv, 'ind')
    hall_roof = chain(roof_units([(0.22, 0.30, 0.18, 0.06), (0.22, 0.42, 0.18, 0.06), (0.62, 0.30, 0.10, 0.18), (0.82, 0.30, 0.06, 0.1), (0.82, 0.55, 0.06, 0.1)], CON[5]))
    east_roof = chain(roof_units([(0.10, 0.10, 0.06, 0.03), (0.22, 0.08, 0.06, 0.03), (0.22, 0.13, 0.06, 0.03), (0.10, 0.15, 0.06, 0.03),
                                  (0.72, 0.84, 0.18, 0.05), (0.72, 0.90, 0.18, 0.04)], CON[5]),
                      vents([(1.62, 1.12), (1.62, 1.88)], 0.04),
                      lamps([(1.58, 0.33), (2.78, 0.33), (1.58, 2.28), (2.78, 2.28)]))
    items = [
        Box(0.22, 0.42, 1.25, 1.42, 0.40, LGREY, GREY, win=WIN_S, win_w=WIN_W, rim=CON[5], roof_detail=hall_roof),
        Box(0.38, 1.40, 1.00, 1.62, 0.12, DGREY, PAL['roof_tar'][1], win=None, parapet=False),
        Cylinder(0.56, 1.62, 0.05, 0.24, RED, top=RED * 1.2),
        Box(0.18, 1.72, 0.92, 2.80, 0.14, GREY, GREY, win=WIN_S, rim=CON[4],
            roof_detail=vents([(0.42, 1.88), (0.68, 1.88), (0.42, 2.18), (0.68, 2.18), (0.42, 2.48), (0.68, 2.48)])),
        Box(1.40, 0.40, 2.70, 2.45, 0.24, LGREY, GREY, win=WIN_S, win_w=WIN_W, rim=CON[4], roof_detail=east_roof),
    ]
    for k, t in enumerate(T639):
        items.append(stack_at(t, 0.24, 0.84, 0.075, order=-k))
    items.append(Custom(lambda c: vehicle(c, 1.86, 2.72, 0.44, 0.15, '#3446c8', stripe='#ff9a2a'), key=(5, 0)))
    render_in(cv, items)
    if frame is not None:
        ind_smoke(cv, T639, frame, [(2, 0), (2, 1)], rise=1.0, drift=(0.48, -0.88))
    return cv


# ------------------------------------------------------------------ 648: low value, density 3 (big works, three stacks)
T648 = [(1.14, 0.80), (1.60, 0.80), (2.07, 0.80)]


def ind_648(frame=None):
    cv = block(lambda c: rect(c, 0.10, 0.10, 2.90, 2.90, 0.03), 0.40)
    zone_frame(cv, 'ind')
    north_roof = chain(roof_units([(0.04, 0.06, 0.03, 0.12), (0.08, 0.06, 0.03, 0.12), (0.12, 0.06, 0.03, 0.12)], CON[6]),
                       vents([(0.48, 0.80), (0.48, 1.06), (0.48, 1.32)], 0.035, CON[5]),
                       roof_units([(0.76, 0.66, 0.16, 0.16)], PAL['asphalt'][2]))
    south_roof = chain(roof_units([(0.06, 0.40, 0.05, 0.18), (0.15, 0.40, 0.05, 0.18), (0.42, 0.25, 0.03, 0.3)], CON[6]),
                       vents([(0.52, 2.52), (0.74, 2.52), (1.18, 2.52), (2.12, 2.52)], 0.035))
    items = [
        Box(0.12, 0.42, 2.52, 1.98, 0.50, LGREY, GREY, win=WIN_S, win_w=WIN_W, rim=CON[5], roof_detail=north_roof),
        Box(0.20, 2.10, 2.40, 2.82, 0.30, LGREY, GREY * 0.97, win=WIN_S, win_w=WIN_W, rim=CON[6], roof_detail=south_roof),
        Box(1.95, 2.18, 2.30, 2.55, 0.12, GREY, PAL['roof_tar'][4], z0=0.30, win=None, rim=CON[6]),
    ]
    items[2].key = lambda: (8, 0)
    for k, t in enumerate(T648):
        items.append(stack_at(t, 0.50, 0.92, 0.075, band=BLUE, order=-k))
    render_in(cv, items)
    if frame is not None:
        ind_smoke(cv, T648, frame, [(1, 0), (2, 0)], rise=0.95, drift=(0.82, -0.57))
    return cv


# ------------------------------------------------------------------ 657: high value, density 0 (silos, car park)
def ind_657(frame=None):
    cv = block()
    paving(cv, rect(cv, 1.96, 0.14, 2.76, 1.40, 0.03), 0.40, 4)
    for k in range(4):
        y = 0.32 + 0.26 * k
        cv.paint(CON[8], rect(cv, 2.04, y - 0.007, 2.30, y + 0.007) * 0.85)
        cv.paint(CON[8], rect(cv, 2.42, y - 0.007, 2.68, y + 0.007) * 0.85)
    cv.paint(PAL['timber'][3], rect(cv, 2.30, 1.18, 2.46, 1.30, 0.01) * 0.8)
    zone_frame(cv, 'ind')
    items = [
        Box(0.48, 0.68, 1.62, 1.04, 0.15, LGREY, GREY, win=WIN_S, rim=CON[5], roof_detail=roof_units([(0.1, 0.2, 0.06, 0.4), (0.5, 0.2, 0.06, 0.4)], CON[5])),
        Box(0.62, 1.96, 0.92, 2.10, 0.08, LGREY, CON[6], parapet=False),
        Box(2.22, 2.08, 2.50, 2.62, 0.26, CON[7], GREY, win=WIN_S, rim=CON[5]),
    ]
    for (cx, cy) in ((1.30, 1.78), (0.60, 2.62), (1.17, 2.62), (1.74, 2.62)):
        items.append(Cylinder(cx, cy, 0.15, 0.40, CON[7], top=CON[6], bands=[(0.30, 0.02, CON[4])]))

    def beacons(c):
        for (cx, cy) in ((1.30, 1.78), (0.60, 2.62), (1.17, 2.62), (1.74, 2.62)):
            t = P(cx + 0.07, cy - 0.04, 0.40)
            c.light(c.cov(sd_circle(c.X, c.Y, t[0], t[1], 0.04), 6), 0.3, hx('#ff3020'))
            c.paint(hx('#e02a1a'), c.cov(sd_circle(c.X, c.Y, t[0], t[1], 0.022)))
    items.append(Custom(beacons, key=(30, 0)))
    items.append(Custom(lambda c: ground_pipe(c, [(0.90, 2.04), (1.32, 2.04)], 0.035, CON[4]), key=(-9, 0)))
    items.append(Custom(lambda c: vehicle(c, 2.50, 0.58, 0.20, 0.10, '#3a48d8', horizontal=False), key=(-9, 0)))
    items.append(Custom(lambda c: vehicle(c, 2.18, 0.86, 0.20, 0.10, '#2aa83a', horizontal=False), key=(-9, 0)))
    render_in(cv, items)
    return cv


# ------------------------------------------------------------------ 666: high value, density 1 (gas holder, water tower)
GH = (1.47, 1.55, 0.88, 0.36)    # gas holder: ground centre, radius, height


def ind_666(frame=None):
    cv = block()
    zone_frame(cv, 'ind')
    cx, cy, r, h = GH
    items = [Cylinder(cx, cy, r, h, CON[6] * 1.02, top=PAL['asphalt'][3])]
    items[0].key = lambda: (0, 0)

    def holder_top(c):
        tx, ty = P(cx, cy, h)
        d = np.hypot(c.X - tx, c.Y - ty)
        m = c.cov(d - r + 0.01)
        dome = np.clip(1 - (d / r) ** 2, 0, 1)
        lam = 0.80 + 0.25 * dome - 0.18 * ((c.X - tx) + (c.Y - ty)) / r
        c.paint(PAL['asphalt'][3][None, None, :] * lam[..., None], m)
        g = 0.125
        gx = np.abs(((c.X - tx) / g) % 1 - 0.5)
        gy = np.abs(((c.Y - ty) / g) % 1 - 0.5)
        dots = ((gx < 0.22) & (gy < 0.22)).astype(float)
        c.paint(PAL['asphalt'][0], dots * c.cov(d - r + 0.05))
        lines = ((gx > 0.44) | (gy > 0.44)).astype(float)
        c.light(lines * c.cov(d - r + 0.05), 0.10)
        c.paint(CON[4], c.cov(np.abs(d - r + 0.012) - 0.010))
        c.paint(CON[4], c.cov(sd_circle(c.X, c.Y, tx, ty, 0.035)))
    items.append(Custom(holder_top, key=(1, 0)))

    # water tower on legs, top left
    tz = 0.30

    def legs(c):
        for (lx, ly) in ((0.12, 0.58), (0.38, 0.58), (0.12, 0.80), (0.38, 0.80)):
            a, b = P(lx, ly, 0), P(lx, ly, tz)
            c.shade(c.cov(sd_segment(c.X, c.Y, lx, ly, lx + SHADOW_DIR[0] * tz, ly + SHADOW_DIR[1] * tz) - 0.008, 2), 0.35)
            c.paint(PAL['steel'][3], c.cov(sd_segment(c.X, c.Y, a[0], a[1], b[0], b[1]) - 0.016))
        c.paint(PAL['steel'][2], c.cov(sd_segment(c.X, c.Y, *P(0.12, 0.80, 0.12), *P(0.38, 0.80, 0.12)) - 0.006))
    items.append(Custom(legs, key=(-5, 0)))
    wt = Box(0.10, 0.55, 0.42, 0.84, 0.24, LGREY, GREY, z0=tz, win=None, rim=CON[5])
    wt.key = lambda: (-4, 0)
    items.append(wt)
    # pipe from the holder to the pump house, and the pump house
    items.append(Custom(lambda c: (ground_pipe(c, [(1.44, 2.36), (1.44, 2.74), (2.48, 2.74)], 0.04, CON[6])), key=(-9, 0)))
    items.append(Box(2.48, 2.60, 2.80, 2.84, 0.16, GREY, PAL['roof_tar'][3], win=WIN_S, rim=CON[4]))

    def mast(c):
        bx, by, hh = 0.34, 2.80, 0.52
        t = P(bx, by, hh)
        c.shade(c.cov(sd_segment(c.X, c.Y, bx, by, bx + SHADOW_DIR[0] * hh, by + SHADOW_DIR[1] * hh) - 0.008, 2), 0.4)
        c.paint(PAL['steel'][4], c.cov(sd_segment(c.X, c.Y, bx, by, t[0], t[1]) - 0.017))
        c.light(c.cov(sd_segment(c.X, c.Y, bx - 0.006, by - 0.006, t[0] - 0.006, t[1] - 0.006) - 0.003), 0.3)
        q = P(bx, by, hh * 0.8)
        c.paint(PAL['steel'][2], c.cov(sd_segment(c.X, c.Y, q[0] - 0.07, q[1] + 0.07, q[0] + 0.07, q[1] - 0.07) - 0.007))
    items.append(Custom(mast, key=(5, 0)))
    rng = np.random.default_rng(66)
    bushes = [(0.14, 0.24), (0.80, 0.42), (2.30, 0.37), (2.70, 0.20), (2.86 - 0.06, 0.50), (2.74, 1.64), (2.48, 2.10), (2.60, 2.24), (0.98, 2.72)]
    for k, (x, y) in enumerate(bushes):
        items.append(Tree(x, y, 0.055 + 0.015 * rng.random(), 660 + k))
    render_in(cv, items)
    return cv


# ------------------------------------------------------------------ 675: high value, density 2 (two stacks, yard)
T675 = [(1.15, 0.60), (1.68, 0.60)]


def ind_675(frame=None):
    cv = block(lambda c: rect(c, 0.14, 0.14, 2.88, 2.62, 0.03) + rect(c, 0.84, 2.5, 1.16, 2.86), 0.44)
    cv.paint(PAL['dirt'][4], rect(cv, 0.40, 2.08, 0.58, 2.24, 0.04) * 0.8)
    zone_frame(cv, 'ind')
    for k, (x, y) in enumerate(((0.18, 2.10), (0.16, 2.78), (0.46, 2.78), (1.42, 2.78), (0.26, 2.66))):
        shrub(cv, x, y, 0.06, 670 + k)
    north_roof = chain(louvres(2.08, 0.96, 2.22, 1.26, 3), vents([(0.70, 0.32), (2.36, 0.32), (2.48, 0.52)], 0.03, CON[7]))
    se_roof = vents([(2.18, 1.92), (2.38, 1.92), (2.58, 1.92), (2.18, 2.18), (2.38, 2.18), (2.58, 2.18)], 0.05)
    items = [
        Box(0.12, 0.38, 2.42, 1.68, 0.45, LGREY, GREY, win=WIN_S, win_w={'kind': 'grid', 'floor': 0.14, 'col': 0.13, 'wfrac': 0.35, 'hfrac': 0.4, 'glass': Ramp(['#d8dadc', '#f6f6f6'])},
            rim=CON[6], roof_detail=north_roof),
        Box(0.30, 1.98, 1.30, 2.56, 0.10, GREY, CON[4], win=None, rim=CON[5]),
        Box(1.74, 1.79, 2.70, 2.72, 0.28, LGREY, GREY, win=WIN_S, win_w=WIN_W, rim=CON[5], roof_detail=se_roof),
    ]
    for k, t in enumerate(T675):
        items.append(stack_at(t, 0.45, 0.90, 0.075, band=BLUE, order=-k))
    items.append(Custom(lambda c: vehicle(c, 1.47, 2.10, 0.30, 0.12, '#2a3ad8'), key=(-9, 0)))
    items.append(Custom(lambda c: vehicle(c, 1.47, 2.42, 0.30, 0.12, '#d42a1c'), key=(-9, 0)))
    items.append(Custom(lambda c: vehicle(c, 0.78, 2.74, 0.18, 0.09, '#f2f2f0'), key=(-9, 0)))
    render_in(cv, items)
    if frame is not None:
        ind_smoke(cv, T675, frame, [(1, 0), (2, 0)], rise=1.05, drift=(0.89, -0.46))
    return cv


# ------------------------------------------------------------------ 684: high value, density 3 (tall works, three stacks)
T684 = [(2.13, 0.34), (2.13, 0.90), (2.12, 1.46)]


def ind_684(frame=None):
    cv = block()
    zone_frame(cv, 'ind')
    h = 0.90

    def roofd(c, rx0, ry0, rx1, ry1):
        xm = rx0 + 0.64 * (rx1 - rx0)
        c.shade(rect(c, xm, ry0 + 0.02, rx1 - 0.02, ry1 - 0.02), 0.22)
        c.paint(CON[6], c.cov(np.abs(sd_box(c.X, c.Y, rx0 + 0.08, ry0 + 0.06, xm, ry1 - 0.08)) - 0.012) * 0.9)
        c.paint(CON[6], rect(c, xm - 0.006, ry0 + 0.06, xm + 0.006, ry1 - 0.08))
        roof_units([(0.10, 0.12, 0.10, 0.04), (0.10, 0.20, 0.10, 0.04), (0.82, 0.86, 0.06, 0.05), (0.90, 0.86, 0.05, 0.05)], CON[5])(c, rx0, ry0, rx1, ry1)
        vents([(rx0 + 0.25, ry1 - 0.20), (rx0 + 0.50, ry1 - 0.20), (rx1 - 0.35, ry1 - 0.12), (rx1 - 0.15, ry1 - 0.12)], 0.04)(c)
    items = [Box(0.12, 0.65, 2.18, 2.84, h, LGREY, GREY, win=WIN_S,
                 win_w={'kind': 'grid', 'floor': 0.13, 'col': 0.12, 'wfrac': 0.30, 'hfrac': 0.55, 'glass': Ramp(['#5a5e66', '#8a8e96', '#c8cad0'])},
                 rim=CON[5], roof_detail=roofd)]
    for k, t in enumerate(T684):
        items.append(stack_at(t, h, 1.15, 0.078, order=-k))
    render_in(cv, items)
    if frame is not None:
        ind_smoke(cv, T684, frame, [(2, 0), (2, 1)], rise=0.95, drift=(0.36, -0.93))
    return cv


GROUPS.append((621, 3, 3, anim_group(621, ind_621, [((0, 0), 852)], nframes=8)))
GROUPS.append((630, 3, 3, ind_630))
GROUPS.append((639, 3, 3, anim_group(639, ind_639, [((2, 0), 884), ((2, 1), 888)])))
GROUPS.append((648, 3, 3, anim_group(648, ind_648, [((1, 0), 892), ((2, 0), 896)])))
GROUPS.append((657, 3, 3, ind_657))
GROUPS.append((666, 3, 3, ind_666))
GROUPS.append((675, 3, 3, anim_group(675, ind_675, [((1, 0), 900), ((2, 0), 904)])))
GROUPS.append((684, 3, 3, anim_group(684, ind_684, [((2, 0), 908), ((2, 1), 912)])))
