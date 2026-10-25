"""Residential zone blocks (all 16 density/value steps), the hospital and the church.

base = (value*4 + density)*9 + 261. Every block follows its original's layout read at
12x (origblock.py): same buildings, footprints, heights, wall colours, R position.
Value 0 frames are the original's dark green, values 1..3 the bright green; the
hospital and church keep the original's thin black outline.
Footprints below are in plan (ground) coordinates; a roof is drawn at (+h/2, -h/2).
"""
import math
import numpy as np
from scipy import ndimage
from hdlib import *
from terrain import dirt_layer, grass_layer, draw_crown
from scene3d import Box, Gable, Cylinder, Tree, Custom, P, cached_noise, cached_grain, LIGHT_W, LIGHT_S, LIGHT_ROOF
from buildings import zone_frame, paving, lawn, rect, letter_col, vehicle, roof_units

GROUPS = []
ANIM = {}

# ------------------------------------------------------------------ colours
LAV = hx('#7486d8')       # original #6666e6 walls
BLUE = hx('#4458d0')      # original pure blue walls (288)
RED = hx('#cf4430')       # original red walls
GREEN = hx('#55bf4f')     # original bright green walls
ORANGE = hx('#e3892f')    # original orange walls
LGREY = hx('#c6c6ca')     # original #bfbfbf walls
DGREY = hx('#5a5a61')     # original #3f3f3f walls
TERRA = PAL['dirt'][5]
R_GREY = PAL['concrete'][3]
R_DARK = PAL['roof_tar'][2]
R_BROWN = PAL['timber'][4]
R_LIGHT = PAL['concrete'][5]
WHITE = PAL['concrete'][8]
RLET = hx('#138a22')

RES_DARK = Ramp(['#03260a', '#063d0e', '#0a5214', '#0e6a1a', '#127f20', '#1f9a2e', '#46b452', '#86d28e'])
CIVIC = Ramp(['#000000', '#08080a', '#101014', '#18181c', '#1e1e24', '#2a2a30', '#4a4a52', '#6a6a72'])


def win(floor=0.13, col=0.11, wf=0.5, hf=0.48, **kw):
    d = {'kind': 'grid', 'floor': floor, 'col': col, 'wfrac': wf, 'hfrac': hf}
    d.update(kw)
    return d


# ------------------------------------------------------------------ kit additions
def inner_fade(cv, m0=0.05, m1=0.10):
    d = -sd_box(cv.X, cv.Y, 0, 0, cv.wt, cv.ht)
    return smoothstep(m0, m1, d)


def rproj(x0, y0, x1, y1, z):
    a = P(x0, y0, z)
    b = P(x1, y1, z)
    return a[0], a[1], b[0], b[1]


class Mass:
    """A union of plan rectangles at one height: walls of every part, then one roof."""

    def __init__(self, rects, h, wall, roof, win=None, win_w=None, z0=0.0, rim=None, label=None,
                 label_at=None, label_size=0.5, roof_detail=None, parapet=True, k=None, glass=None,
                 roof_tex=None, ao=True):
        self.__dict__.update(locals())
        del self.__dict__['self']

    def key(self):
        if self.k is not None:
            return (self.k, 0)
        xs = [(r[0] + r[2]) / 2 for r in self.rects]
        ys = [(r[1] + r[3]) / 2 for r in self.rects]
        return (np.mean(ys) - np.mean(xs), self.z0)

    def shadow_mask(self, cv):
        m = np.zeros_like(cv.X)
        H = self.h + self.z0
        for (x0, y0, x1, y1) in self.rects:
            foot = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            sx, sy = SHADOW_DIR * H
            from scene3d import hull
            m = np.maximum(m, cv.poly(hull(foot + [(x + sx, y + sy) for x, y in foot])))
        return m

    def roof_mask(self, cv):
        zt = self.z0 + self.h
        rm = np.zeros_like(cv.X)
        for (x0, y0, x1, y1) in self.rects:
            a, b, c, d = rproj(x0, y0, x1, y1, zt)
            rm = np.maximum(rm, cv.poly([(a, b), (c, b), (c, d), (a, d)]))
        return rm

    def draw(self, cv):
        parts = sorted(self.rects, key=lambda r: ((r[1] + r[3]) / 2 - (r[0] + r[2]) / 2))
        for (x0, y0, x1, y1) in parts:
            Box(x0, y0, x1, y1, self.h, self.wall, self.wall, win=self.win, win_w=self.win_w, parapet=False,
                z0=self.z0, glass=self.glass, ao=self.ao).draw(cv)
        rm = self.roof_mask(cv)
        roof = np.asarray(self.roof, float)
        rn, rg = cached_noise(cv), cached_grain(cv)
        rc = roof * LIGHT_ROOF * (0.95 + 0.10 * (rn - 0.5) * 2 + 0.07 * (rg - 0.5) * 2)[..., None]
        if self.roof_tex is not None:
            rc = self.roof_tex(cv, rc)
        cv.paint(rc, rm)
        if self.parapet:
            inside = rm > 0.5
            d = ndimage.distance_transform_edt(inside) / cv.n
            t = 0.018
            rim = np.clip((t - d) * cv.n / 1.2 + 0.5, 0, 1) * rm
            rimc = np.asarray(self.rim if self.rim is not None else roof * 1.25, float)
            cv.paint(np.clip(rimc, 0, 1), rim)
            k = int(0.022 * cv.n)
            sh = np.roll(np.roll(rim, k, 0), k, 1) * (1 - rim) * rm
            cv.shade(cv.blur(sh, 0.004), 0.30)
        if self.roof_detail:
            self.roof_detail(cv, self.z0 + self.h)
        if self.label:
            zt = self.z0 + self.h
            lx, ly = P(self.label_at[0], self.label_at[1], zt)
            draw_label(cv, self.label, lx, ly, self.label_size, rm)


def draw_label(cv, ch, lx, ly, size, clipm=None, col=None, font=None):
    m = cv.text_mask(ch, lx, ly, size, font or FONT_SERIF)
    if clipm is not None:
        m = m * clipm
    sh = np.roll(np.roll(m, int(0.012 * cv.n), 0), int(0.016 * cv.n), 1)
    cv.shade(sh, 0.6)
    cv.paint(col if col is not None else RLET, m)
    e = np.clip(m - np.roll(np.roll(m, 2, 0), 2, 1), 0, 1)
    cv.light(e, 0.45)


def framed_panel(x0, y0, x1, y1, fill, frame=WHITE, w=0.03, extra=None):
    """Roof detail: a rimmed panel given in plan coords, projected at roof height."""
    def fn(cv, zt):
        a, b, c, d = rproj(x0, y0, x1, y1, zt)
        cv.shade(rect(cv, a + 0.015, b + 0.012, c + 0.02, d + 0.016), 0.35)
        cv.paint(frame, rect(cv, a, b, c, d))
        cv.paint(np.asarray(fill) * (0.97 + 0.06 * (cached_noise(cv) - 0.5))[..., None], rect(cv, a + w, b + w, c - w, d - w))
        k = rect(cv, a + w, b + w, c - w, b + w + 0.02) + rect(cv, a + w, b + w, a + w + 0.02, d - w)
        cv.shade(np.clip(k, 0, 1) * rect(cv, a + w, b + w, c - w, d - w), 0.3)
        if extra:
            extra(cv, a, b, c, d)
    return fn


def vents(pts, col=None, s=0.04):
    def fn(cv, zt):
        for (x, y) in pts:
            px, py = P(x, y, zt)
            cv.shade(rect(cv, px - s / 2 + 0.01, py - s / 2 + 0.01, px + s / 2 + 0.014, py + s / 2 + 0.012, 0.004), 0.45)
            cv.paint(col if col is not None else PAL['roof_tar'][1], rect(cv, px - s / 2, py - s / 2, px + s / 2, py + s / 2, 0.004))
            cv.light(rect(cv, px - s / 2, py - s / 2, px + s / 2, py - s / 2 + 0.008), 0.3)
    return fn


def chain(*fns):
    def fn(cv, zt):
        for f in fns:
            f(cv, zt)
    return fn


def roof_garden(spots, seed=0):
    def fn(cv, zt):
        for i, (x, y, r) in enumerate(spots):
            px, py = P(x, y, zt)
            cv.paint(PAL['timber'][2], cv.cov(sd_box(cv.X, cv.Y, px - r - 0.015, py - r - 0.015, px + r + 0.015, py + r + 0.015, 0.01)))
            draw_crown(cv, px, py, r, seed + i)
    return fn


def specks(cv, n, seed, cols, box=(0.14, 0.14, 2.86, 2.86), r=(0.008, 0.016), avoid=None):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        x, y = rng.uniform(box[0], box[2]), rng.uniform(box[1], box[3])
        if avoid is not None and avoid(x, y):
            continue
        rr = rng.uniform(*r)
        c = cols[rng.integers(len(cols))]
        cv.shade(cv.cov(sd_circle(cv.X, cv.Y, x + rr * 0.6, y + rr * 0.5, rr), 2), 0.3)
        cv.paint(c, cv.cov(sd_circle(cv.X, cv.Y, x, y, rr)))


def tufts(cv, n, seed, box=(0.14, 0.14, 2.86, 2.86), avoid=None):
    """Small grass tufts on dirt."""
    rng = np.random.default_rng(seed)
    for _ in range(n):
        x, y = rng.uniform(box[0], box[2]), rng.uniform(box[1], box[3])
        if avoid is not None and avoid(x, y):
            continue
        r = rng.uniform(0.018, 0.035)
        cv.paint(PAL['grass'][3], cv.cov(sd_circle(cv.X, cv.Y, x + 0.004, y + 0.004, r)))
        cv.paint(PAL['grass'](0.55 + 0.2 * (cached_grain(cv) - 0.5)), cv.cov(sd_circle(cv.X, cv.Y, x - 0.003, y - 0.003, r * 0.8)))


def civic_frame(cv):
    d = -sd_box(cv.X, cv.Y, 0, 0, cv.wt, cv.ht)
    cv.shade(cv.cov(np.abs(d - 0.085) - 0.012, 3), 0.30)
    cv.paint(hx('#141417'), cv.cov(np.abs(d - 0.047) - 0.028))
    cv.paint(hx('#3a3a42'), cv.cov(np.abs(d - 0.030) - 0.004) * 0.7)


def frame(cv, value):
    zone_frame(cv, RES_DARK if value == 0 else 'res')


def drive(cv, x0, y0, x1, y1, tone=0.5, joints=8):
    paving(cv, rect(cv, x0, y0, x1, y1), tone, joints)


def asphalt(cv, mask, tone=0.45):
    n = pnoise(cv.n, 40, 851, cv.wt, cv.ht)
    cv.paint(PAL['asphalt'](tone + 0.1 * (n - 0.5)), mask)


def pool(cv, x0, y0, x1, y1, rim=0.03, water=None):
    cv.shade(rect(cv, x0 - rim + 0.01, y0 - rim + 0.01, x1 + rim + 0.016, y1 + rim + 0.014, 0.02), 0.3)
    cv.paint(PAL['concrete'][7], rect(cv, x0 - rim, y0 - rim, x1 + rim, y1 + rim, 0.02))
    cv.paint(water if water is not None else hx('#5f72e4'), rect(cv, x0, y0, x1, y1, 0.012))
    cv.paint(PAL['water'][3], rect(cv, x0, y0, x1, y0 + 0.03) * 0.6)
    cv.paint(PAL['water'][3], rect(cv, x0, y0, x0 + 0.025, y1) * 0.5)
    rip = pnoise2(cv.n, 10, 30, 831, cv.wt, cv.ht)
    cv.light(smoothstep(0.65, 0.8, rip) * rect(cv, x0, y0, x1, y1), 0.35)


def finish(cv):
    """Hard guarantee for the seam rule: the outermost band is the shared dirt."""
    base = dirt_layer(cv.wt, cv.ht, cv.n)
    d = -sd_box(cv.X, cv.Y, 0, 0, cv.wt, cv.ht)
    a = 1 - smoothstep(0.010, 0.015, d)
    cv.img = cv.img * (1 - a[..., None]) + base * a[..., None]
    return cv


def render2(cv, items, strength=0.62):
    from scene3d import hull
    sh = np.zeros_like(cv.X)
    for it in items:
        if isinstance(it, Tree):
            sh = np.maximum(sh, it.shadow(cv))
        elif hasattr(it, 'shadow_mask'):
            sh = np.maximum(sh, it.shadow_mask(cv))
        else:
            p = it.shadow_poly()
            if p:
                sh = np.maximum(sh, cv.poly(p))
    sh = cv.blur(sh, 0.008) * inner_fade(cv)
    cv.shade(sh, strength)
    def k(it):
        kk = getattr(it, 'k', None)
        return (kk, 0) if kk is not None else it.key()
    for it in sorted(items, key=k):
        it.draw(cv)


def car(x, y, col, horizontal=True, L=0.15, W=0.08, k=-5):
    return Custom(lambda c: vehicle(c, x, y, L, W, col, horizontal=horizontal), key=(k, 0))


def ground(kind, value):
    cv = Canvas(3, 3, RS, dirt_layer(3, 3))
    if kind == 'lawn':
        lawn(cv, rect(cv, 0.08, 0.08, 2.92, 2.92, 0.04))
    return cv


def parking_marks(cv, x0, x1, ys, col=None):
    for y in ys:
        cv.paint(col if col is not None else PAL['concrete'][8], rect(cv, x0, y - 0.007, x1, y + 0.007) * 0.85)


# ================================================================== value 0 (dirt, dark frame)
def r261():
    """v0 d0: long dark block + the R block, a broken concrete lot to the south-west."""
    cv = ground('dirt', 0)
    n = pnoise(cv.n, 6, 901, 3, 3)
    n2 = pnoise(cv.n, 12, 911, 3, 3)
    core = cv.blur(rect(cv, 0.55, 1.62, 1.45, 2.62, 0.2) + rect(cv, 0.95, 2.3, 1.3, 2.84), 0.08)
    lot = rect(cv, 0.35, 1.42, 1.62, 2.86, 0.06) * smoothstep(0.50, 0.53, 0.25 * n + 0.25 * n2 + 0.55 * core)
    lot = np.clip(lot + rect(cv, 0.95, 2.2, 1.25, 2.82, 0.05), 0, 1) * rect(cv, 0.3, 1.4, 1.65, 2.88)
    paving(cv, lot, 0.42, 5)
    cracks = pnoise(cv.n, 30, 902, 3, 3)
    cv.shade(smoothstep(0.03, 0.0, np.abs(cracks - 0.5)) * lot, 0.4)
    specks(cv, 60, 903, [PAL['grass'][3], PAL['concrete'][3], PAL['timber'][3]])
    frame(cv, 0)
    items = [
        Mass([(0.75, 0.70, 2.40, 1.35)], 0.60, DGREY, R_GREY, win=win(0.12, 0.13, 0.4, 0.4, warm=True),
             win_w=win(0.12, 0.12, 0.3, 0.35), rim=PAL['concrete'][4],
             roof_detail=vents([(1.2, 0.95), (1.55, 0.85), (2.0, 0.9)])),
        Mass([(1.75, 1.45, 2.45, 2.30)], 0.50, DGREY, R_GREY, win=win(0.12, 0.12, 0.4, 0.4, warm=True),
             win_w=win(0.12, 0.13, 0.3, 0.35), rim=PAL['concrete'][4], label='R', label_at=(2.10, 1.86), label_size=0.5),
    ]
    render2(cv, items)
    return finish(cv)


def r270():
    """v0 d1: two long brown-roofed blocks either side of an internal street, side lanes."""
    cv = ground('dirt', 0)
    asphalt(cv, rect(cv, 0.09, 1.38, 2.91, 1.62), 0.42)
    for k in range(9):
        x = 0.25 + 0.32 * k
        cv.paint(PAL['concrete'][7], rect(cv, x - 0.05, 1.494, x + 0.05, 1.506) * 0.85)
    paving(cv, rect(cv, 2.45, 0.42, 2.85, 1.40), 0.45, 6)
    paving(cv, rect(cv, 0.22, 1.60, 0.46, 2.88), 0.45, 6)
    specks(cv, 45, 904, [PAL['grass'][3], PAL['concrete'][3], PAL['timber'][3]],
           avoid=lambda x, y: 1.3 < y < 1.7)
    frame(cv, 0)
    items = [
        Mass([(0.20, 0.65, 1.90, 1.15)], 0.60, DGREY, R_BROWN, win=win(0.12, 0.11, 0.35, 0.4, warm=True),
             win_w=win(0.12, 0.12, 0.3, 0.35), rim=PAL['timber'][5], roof_detail=vents([(0.6, 0.9), (1.5, 0.95)], PAL['timber'][2])),
        Mass([(0.62, 2.10, 2.48, 2.85)], 0.70, hx('#7d7d84'), R_BROWN, win=win(0.12, 0.11, 0.4, 0.42, warm=True),
             win_w=win(0.13, 0.13, 0.3, 0.38), rim=PAL['timber'][5], label='R', label_at=(1.20, 2.50), label_size=0.52,
             roof_detail=roof_garden([(1.68, 2.42, 0.07), (1.82, 2.6, 0.06), (1.62, 2.66, 0.05)], 950)),
        car(2.65, 0.62, '#2a3fc0', False, k=-6), car(2.62, 0.95, '#e8c020', False, k=-6),
        car(0.34, 2.10, '#3fae3a', False, k=-6), car(0.34, 2.50, '#d42a1c', False, k=-6),
    ]
    render2(cv, items)
    return finish(cv)


def r279():
    """v0 d2: dark courtyard block (rimmed roof terrace + R panel), brown east wings."""
    cv = ground('dirt', 0)
    specks(cv, 30, 905, [PAL['grass'][3], PAL['concrete'][3]])
    cv.paint(PAL['dirt'][4], rect(cv, 0.95, 1.30, 1.70, 1.98) * 0.5)
    tufts(cv, 6, 906, box=(1.05, 1.4, 1.6, 1.9))
    frame(cv, 0)
    h = 0.6
    pent = framed_panel(0.25, 0.52, 0.90, 1.25, PAL['roof_tar'][2], PAL['concrete'][6])
    rpanel = framed_panel(0.30, 1.98, 1.80, 2.78, PAL['roof_tar'][2], PAL['concrete'][6],
                          extra=lambda c, a, b, cc, d: [c.paint(PAL['dirt'][5], rect(c, a + 0.12 + 0.09 * i, d - 0.20, a + 0.17 + 0.09 * i, d - 0.15)) for i in range(3)])
    items = [
        Mass([(0.20, 0.50, 1.75, 1.30), (0.20, 0.50, 0.95, 2.85), (0.20, 1.95, 1.80, 2.85), (1.62, 1.25, 1.80, 1.95)], h, DGREY, R_DARK,
             win=win(0.12, 0.10, 0.4, 0.4), win_w=win(0.12, 0.11, 0.35, 0.4, glass=PAL['concrete']),
             rim=PAL['concrete'][3], label='R', label_at=(1.35, 2.38), label_size=0.48,
             roof_detail=chain(pent, rpanel)),
        Mass([(1.85, 0.48, 2.52, 1.80)], h, DGREY, R_BROWN, win=win(0.12, 0.10, 0.4, 0.4), rim=PAL['concrete'][4]),
        Mass([(1.88, 1.90, 2.48, 2.85)], h, DGREY, R_BROWN, win=win(0.12, 0.10, 0.4, 0.4), rim=PAL['roof_tar'][1],
             roof_tex=lambda c, rc: rc * (0.8 + 0.4 * smoothstep(0.4, 0.6, pnoise(c.n, 24, 907, 3, 3)))[..., None]),
    ]
    render2(cv, items)
    return finish(cv)


def r288():
    """v0 d3: tall red tower with the R, blue tower behind, red-sided north-east block."""
    cv = ground('dirt', 0)
    specks(cv, 20, 908, [PAL['grass'][3], PAL['concrete'][3]])
    frame(cv, 0)
    dense = win(0.10, 0.09, 0.45, 0.45, warm=True)
    items = [
        Mass([(1.55, 0.36, 2.55, 0.95)], 0.45, RED, R_GREY, win=win(0.11, 0.1, 0.4, 0.4), k=-2,
             roof_detail=vents([(1.8, 0.55), (2.3, 0.7)])),
        Mass([(2.00, 0.98, 2.55, 2.45)], 0.35, DGREY, R_GREY, win=win(0.11, 0.1, 0.4, 0.4), k=-1),
        Mass([(0.20, 0.52, 0.85, 1.45)], 0.85, BLUE, R_GREY, win=dense, k=0, roof_detail=vents([(0.45, 0.8), (0.45, 1.05)])),
        Mass([(0.20, 1.90, 1.78, 2.85)], 1.50, RED, R_GREY, win=dense, k=1, rim=hx('#e05a40'),
             label='R', label_at=(1.05, 2.40), label_size=0.55,
             roof_detail=vents([(0.55, 2.3), (1.55, 2.15), (1.55, 2.5)], PAL['concrete'][6], 0.035)),
    ]
    render2(cv, items)
    return finish(cv)


# ================================================================== value 1 (dirt + tufts)
def r297():
    """v1 d0: red L with the R, lavender hook block, a paved cross-shaped plaza."""
    cv = ground('dirt', 1)
    plaza = np.clip(rect(cv, 1.10, 2.02, 2.90, 2.80) + rect(cv, 1.64, 1.20, 1.92, 2.92), 0, 1)
    paving(cv, plaza, 0.74, 8)
    m = (np.abs(((cv.X * 8) % 1) - ((cv.Y * 8) % 1)) < 0.12).astype(float)
    cv.shade(m * plaza * rect(cv, 1.2, 2.1, 2.8, 2.72), 0.15)
    tufts(cv, 28, 909, avoid=lambda x, y: (1.0 < x < 2.95 and 1.9 < y < 2.9) or (0.15 < x < 1.2 and 0.4 < y < 2.85) or (1.4 < x < 2.65 and 0.2 < y < 1.95))
    frame(cv, 1)
    items = [
        Mass([(0.20, 0.55, 0.70, 2.80), (0.20, 0.55, 1.15, 1.20)], 0.50, RED, R_GREY, win=win(0.13, 0.12, 0.4, 0.45),
             label='R', label_at=(0.45, 1.98), label_size=0.46, roof_detail=vents([(0.35, 1.0), (0.45, 2.7)])),
        Mass([(1.75, 0.38, 2.45, 1.90), (1.50, 0.38, 1.80, 0.95)], 0.30, LAV, R_GREY, win=win(0.12, 0.12, 0.42, 0.45),
             roof_detail=vents([(2.2, 0.7), (2.2, 1.5)])),
        Tree(1.25, 1.60, 0.09, 960), Tree(2.70, 1.70, 0.10, 961),
    ]
    render2(cv, items)
    return finish(cv)


def r306():
    """v1 d1: lavender courtyard block with paved inner court, east blocks, north path."""
    cv = ground('dirt', 1)
    paving(cv, rect(cv, 0.85, 0.95, 1.70, 2.02), 0.70, 6)
    paving(cv, rect(cv, 1.64, 0.08, 1.84, 0.60), 0.55, 6)
    tufts(cv, 18, 910, avoid=lambda x, y: (0.15 < x < 2.65 and 0.3 < y < 2.88))
    frame(cv, 1)
    w = win(0.12, 0.11, 0.42, 0.42, warm=True)
    items = [
        Mass([(0.20, 0.50, 0.85, 2.85), (0.20, 0.50, 1.62, 0.95), (0.20, 2.00, 1.85, 2.85)], 0.35, LAV, R_GREY, win=w,
             label='R', label_at=(0.50, 1.68), label_size=0.46, roof_detail=vents([(0.45, 0.75), (0.45, 0.95), (1.3, 2.4)])),
        Mass([(1.72, 0.45, 2.55, 1.55)], 0.40, LAV, R_GREY, win=w),
        Mass([(1.80, 1.62, 2.52, 2.85)], 0.35, LAV, R_GREY, win=w, roof_detail=vents([(2.15, 2.25)], PAL['timber'][3], 0.06)),
        Tree(1.25, 1.45, 0.08, 962),
    ]
    render2(cv, items)
    return finish(cv)


def r315():
    """v1 d2: green-walled L and the R block with balcony planters, car park south-east."""
    cv = ground('dirt', 1)
    paving(cv, rect(cv, 2.08, 1.66, 2.82, 2.86, 0.02), 0.40, 6)
    paving(cv, rect(cv, 2.38, 2.80, 2.66, 2.92), 0.40, 6)
    asphalt(cv, rect(cv, 2.08, 1.66, 2.82, 1.80), 0.35)
    parking_marks(cv, 2.32, 2.58, [1.95, 2.17, 2.39, 2.61])
    tufts(cv, 26, 911, avoid=lambda x, y: (0.1 < x < 2.85 and 0.3 < y < 2.85 and not (x > 2.0 and y < 0.6)))
    frame(cv, 1)
    w = win(0.12, 0.11, 0.45, 0.42, warm=True)
    def planters(cv, zt):
        for k in range(12):
            x = 1.02 + 0.115 * k
            for z in (0.18, 0.40):
                a = P(x, 1.55, z)
                cv.paint(PAL['leaf'][6], cv.cov(sd_circle(cv.X, cv.Y, a[0], a[1], 0.022)))
    items = [
        Mass([(0.15, 0.80, 0.60, 2.72), (0.15, 2.15, 1.62, 2.72)], 0.70, GREEN, R_GREY, win=w, roof_detail=vents([(0.35, 1.4), (1.2, 2.45)])),
        Mass([(0.95, 0.60, 2.45, 1.55)], 0.60, GREEN, R_GREY, win=w, label='R', label_at=(2.0, 1.12), label_size=0.5,
             roof_detail=chain(vents([(1.4, 0.95), (1.25, 1.2)]), planters)),
        car(2.16, 1.94, '#d42a1c', False, 0.14, 0.075, -6), car(2.16, 2.62, '#2a3fc0', False, 0.14, 0.075, -6),
        car(2.72, 2.40, '#2a3fc0', False, 0.14, 0.075, -6),
        Tree(0.32, 0.38, 0.09, 963), Tree(1.70, 0.30, 0.08, 964),
    ]
    render2(cv, items)
    return finish(cv)


def r324():
    """v1 d3: lavender slab with tall north-west tower, NE block with red roof edge."""
    cv = ground('dirt', 1)
    tufts(cv, 10, 912, avoid=lambda x, y: x > 0.15)
    frame(cv, 1)
    dense = win(0.10, 0.09, 0.48, 0.45, warm=True)
    items = [
        Mass([(1.50, 0.45, 2.45, 0.98)], 0.45, LAV, R_GREY, win=win(0.11, 0.1, 0.4, 0.4), rim=RED, k=-3),
        Mass([(1.35, 0.95, 2.05, 1.40)], 0.25, LAV, PAL['roof_red'][4], win=win(0.11, 0.1, 0.4, 0.4), k=-2),
        Mass([(0.20, 0.70, 1.20, 1.40)], 0.80, LAV, R_GREY, win=dense, k=-1, parapet=False),
        Mass([(0.20, 1.40, 2.45, 2.85)], 0.80, LAV, R_GREY, win=dense, k=0, label='R', label_at=(1.95, 1.88), label_size=0.5,
             roof_detail=vents([(1.85, 2.4), (1.95, 2.4)], PAL['concrete'][7], 0.04)),
        Mass([(0.20, 0.70, 1.20, 2.05)], 0.40, LAV, R_GREY, z0=0.80, win=dense, k=1, roof_detail=vents([(0.5, 1.2)])),
    ]
    render2(cv, items)
    return finish(cv)


# ================================================================== value 2
def r333():
    """v2 d0: lavender R block, small car park, ivy-green block east, four bushes."""
    cv = ground('dirt', 2)
    paving(cv, rect(cv, 1.05, 0.55, 1.85, 1.46, 0.02), 0.48, 6)
    paving(cv, rect(cv, 1.45, 1.40, 1.75, 2.92), 0.48, 6)
    frame(cv, 2)
    def ivy(cv_, rc):
        return rc
    items = [
        Mass([(0.20, 0.55, 0.80, 1.15)], 0.50, LAV, R_DARK, win=win(0.12, 0.11, 0.42, 0.42), rim=hx('#2a2a30'), k=-1),
        Mass([(0.20, 1.15, 0.75, 1.95)], 0.40, LAV, R_GREY, win=win(0.12, 0.11, 0.42, 0.42), k=0,
             label='R', label_at=(0.48, 1.55), label_size=0.46),
        Mass([(1.90, 0.45, 2.45, 1.75)], 0.40, GREEN, R_DARK, win=win(0.12, 0.12, 0.35, 0.4), rim=hx('#202024'),
             roof_detail=vents([(2.2, 0.9), (2.2, 1.4)], PAL['roof_tar'][4])),
        car(1.30, 0.72, '#2a3fc0', False, 0.14, 0.075, -6), car(1.48, 0.72, '#202024', False, 0.14, 0.075, -6),
        car(1.16, 1.02, '#202024', True, 0.14, 0.075, -6), car(1.18, 1.22, '#d42a1c', True, 0.14, 0.075, -6),
        car(1.66, 1.08, '#2f8f36', True, 0.14, 0.075, -6),
        car(0.78, 2.70, '#f08a20', True, 0.20, 0.10, -6),
        Tree(1.25, 1.95, 0.17, 970), Tree(0.45, 2.50, 0.20, 971), Tree(1.30, 2.62, 0.19, 972), Tree(2.50, 2.55, 0.22, 973),
    ]
    # ivy on the green block's west wall
    def ivyfn(c):
        x0, y0, x1, y1, h = 1.90, 0.45, 2.45, 1.75, 0.40
        m = c.poly([P(x0, y0, 0), P(x0, y1, 0), P(x0, y1, h), P(x0, y0, h)])
        lv = pnoise(c.n, 36, 974, 3, 3)
        c.paint(PAL['leaf'](0.45 + 0.6 * (lv - 0.5)), m * smoothstep(0.35, 0.5, lv))
    items.append(Custom(ivyfn, key=(-0.5, 1)))
    render2(cv, items)
    return finish(cv)


def r342():
    """v2 d1: lawn; brick L with dark roof, lavender J with the R, court paths, car park."""
    cv = ground('lawn', 2)
    paving(cv, rect(cv, 1.38, 1.25, 1.48, 2.02), 0.65, 10)
    paving(cv, rect(cv, 1.0, 1.28, 1.92, 1.36), 0.65, 10)
    paving(cv, rect(cv, 1.95, 1.95, 2.76, 2.76, 0.02), 0.40, 6)
    paving(cv, rect(cv, 2.38, 2.70, 2.60, 2.92), 0.40, 6)
    for i in range(3):
        for j in range(3):
            x, y = 2.12 + 0.22 * i, 2.08 + 0.2 * j
            cv.paint(PAL['asphalt'][1], cv.cov(sd_segment(cv.X, cv.Y, x - 0.05, y - 0.05, x, y) - 0.008) * 0.8)
            cv.paint(PAL['asphalt'][1], cv.cov(sd_segment(cv.X, cv.Y, x + 0.05, y - 0.05, x, y) - 0.008) * 0.8)
    frame(cv, 2)
    brickwin = win(0.08, 0.07, 0.55, 0.55)
    items = [
        Mass([(0.30, 0.65, 0.75, 2.75), (0.30, 2.25, 1.62, 2.75)], 0.50, RED, R_DARK, win=brickwin, rim=hx('#18181c'),
             roof_detail=vents([(0.55, 1.2), (0.55, 1.7)], PAL['roof_tar'][4])),
        Mass([(0.90, 0.45, 2.60, 1.00), (1.95, 0.45, 2.60, 1.75)], 0.30, LAV, R_LIGHT, win=win(0.11, 0.11, 0.42, 0.42, warm=True),
             label='R', label_at=(2.30, 1.05), label_size=0.46, roof_detail=vents([(1.4, 0.6)], PAL['concrete'][2])),
        Tree(0.15 + 0.03, 2.82, 0.0, 0),
    ]
    items = items[:2] + [Tree(1.10, 1.75, 0.08, 975), Tree(1.75, 1.65, 0.08, 976), Tree(2.80, 1.95, 0.08, 977), Tree(0.20, 0.30, 0.08, 978)]
    render2(cv, items)
    return finish(cv)


def r351():
    """v2 d2: orange-brick blocks on a dark podium, lavender blocks east."""
    cv = ground('dirt', 2)
    paving(cv, rect(cv, 1.25, 0.62, 1.80, 0.80), 0.55, 8)
    paving(cv, rect(cv, 2.28, 2.55, 2.66, 2.92), 0.55, 8)
    tufts(cv, 10, 913, avoid=lambda x, y: (0.2 < x < 2.7 and 0.3 < y < 2.88))
    frame(cv, 2)
    brick = win(0.09, 0.08, 0.5, 0.5, glass=PAL['concrete'])
    orange_rim = hx('#f0a050')
    items = [
        Mass([(0.25, 1.05, 2.05, 2.85), (1.85, 0.50, 2.05, 1.10)], 0.25, DGREY, R_DARK, win=None, rim=PAL['roof_tar'][3], k=-3),
        Mass([(0.25, 0.60, 1.00, 1.15)], 0.60, ORANGE, R_GREY, win=brick, rim=orange_rim, k=-2, roof_detail=vents([(0.5, 0.85)])),
        Mass([(1.45, 0.60, 1.80, 1.80), (1.45, 1.55, 2.30, 1.80)], 0.60, ORANGE, R_GREY, win=brick, rim=orange_rim, k=-1),
        Mass([(2.10, 0.45, 2.55, 1.05)], 0.40, LAV, R_LIGHT, win=win(0.11, 0.1, 0.4, 0.4), rim=WHITE, k=-1.5),
        Mass([(0.28, 1.60, 0.75, 2.62), (0.28, 2.20, 1.70, 2.62)], 0.60, ORANGE, R_GREY, win=brick, rim=orange_rim, k=0,
             label='R', label_at=(0.50, 1.95), label_size=0.44),
        Mass([(2.00, 1.80, 2.52, 2.60)], 0.50, LAV, R_DARK, win=win(0.11, 0.1, 0.4, 0.4), rim=hx('#202024'), k=0.5,
             roof_detail=vents([(2.1, 2.0), (2.25, 2.0), (2.4, 2.0)], hx('#101012'), 0.035)),
    ]
    render2(cv, items)
    return finish(cv)


def r360():
    """v2 d3: tall light-grey slab with raised R deck, NW tower (pool), NE tower (courts)."""
    cv = ground('dirt', 2)
    frame(cv, 2)
    dense = win(0.10, 0.09, 0.45, 0.45, warm=True, glass=None)
    def cross_pool(cv_, a, b, c, d):
        cx, cy = (a + c) / 2, (b + d) / 2 - 0.05
        m = np.clip(rect(cv_, cx - 0.12, cy - 0.04, cx + 0.12, cy + 0.04) + rect(cv_, cx - 0.04, cy - 0.12, cx + 0.04, cy + 0.12), 0, 1)
        cv_.paint(PAL['concrete'][7], cv_.blur(m, 0.008) > 0.02)
        cv_.paint(hx('#3a52d8'), m)
        cv_.light(m * smoothstep(0.65, 0.8, pnoise2(cv_.n, 10, 30, 831, 3, 3)), 0.3)
        for dx in (-0.06, 0.04):
            cv_.paint(hx('#e0201a'), rect(cv_, cx + dx, d - 0.1, cx + dx + 0.03, d - 0.07))
    def courts(cv_, a, b, c, d):
        cv_.paint(hx('#3a52d8'), rect(cv_, a + 0.25, b + 0.08, a + 0.33, b + 0.12))
        for x in (a + 0.3, a + 0.72):
            cv_.paint(WHITE, cv_.cov(sd_segment(cv_.X, cv_.Y, x, b + 0.45, x + 0.12, b + 0.32) - 0.012))
    items = [
        Mass([(1.35, 0.58, 2.38, 1.25)], 0.85, LGREY, R_DARK, win=dense, k=-2, rim=WHITE,
             roof_detail=framed_panel(1.35, 0.58, 2.38, 1.25, R_GREY, WHITE, 0.035, courts)),
        Mass([(0.20, 0.60, 0.75, 1.30)], 1.00, LGREY, R_DARK, win=dense, k=-1, rim=WHITE,
             roof_detail=framed_panel(0.20, 0.60, 0.75, 1.30, R_GREY, WHITE, 0.035, cross_pool)),
        Mass([(0.20, 1.30, 2.30, 2.85)], 1.00, LGREY, R_DARK, win=dense, k=0, rim=PAL['concrete'][4],
             roof_detail=vents([(0.35, 1.8), (2.1, 1.5)], WHITE, 0.035)),
        Mass([(0.42, 1.78, 1.72, 2.58)], 0.10, WHITE, R_LIGHT, z0=1.0, win=None, k=1, rim=WHITE, label='R',
             label_at=(1.07, 2.18), label_size=0.5),
    ]
    render2(cv, items)
    return finish(cv)


# ================================================================== value 3 (lawns)
def r369():
    """v3 d0: lawn; red and lavender blocks north, paved court with pool and the R bed."""
    cv = ground('lawn', 3)
    court = np.clip(rect(cv, 0.45, 0.98, 2.60, 2.12, 0.04) + rect(cv, 0.10, 1.30, 2.90, 1.60), 0, 1)
    paving(cv, court, 0.50, 6)
    for (x, ys) in ((0.62, (1.12, 1.30, 1.70, 1.88)), (2.30, (1.12, 1.30, 1.70, 1.88))):
        for y in ys:
            cv.paint(PAL['concrete'][1], cv.cov(sd_segment(cv.X, cv.Y, x - 0.06, y + 0.04, x + 0.06, y - 0.04) - 0.01) * 0.8)
    lawn(cv, rect(cv, 0.86, 1.62, 1.08, 2.10) + rect(cv, 1.75, 1.66, 1.97, 2.10))
    pool(cv, 1.18, 1.14, 1.62, 1.84)
    cv.paint(WHITE, rect(cv, 1.37, 1.04, 1.43, 1.20))
    # the R: a clipped box-hedge parterre in the court
    m = cv.text_mask('R', 1.95, 1.43, 0.42, FONT_SERIF)
    cv.shade(np.roll(np.roll(m, 4, 0), 5, 1), 0.5)
    cv.paint(PAL['leaf'](0.18 + 0.2 * pnoise(cv.n, 40, 52, 3, 3)), m)
    cv.light(np.clip(m - np.roll(np.roll(m, 3, 0), 3, 1), 0, 1), 0.3)
    frame(cv, 3)
    w = win(0.11, 0.11, 0.42, 0.42, warm=True)
    items = [
        Mass([(0.35, 0.50, 0.85, 1.00)], 0.40, RED, R_GREY, win=w),
        Mass([(1.15, 0.35, 2.45, 0.90)], 0.30, LAV, R_GREY, win=w,
             roof_detail=vents([(1.5, 0.45), (1.5, 0.72), (2.15, 0.45), (2.15, 0.72)], hx('#141416'), 0.035)),
        Mass([(0.45, 2.40, 1.85, 2.85)], 0.20, LAV, R_GREY, win=win(0.1, 0.11, 0.42, 0.5)),
        Mass([(2.10, 2.40, 2.65, 2.85)], 0.20, TERRA, R_LIGHT, win=win(0.1, 0.11, 0.42, 0.5), rim=PAL['timber'][4]),
        Tree(0.22, 2.22, 0.09, 980), Tree(2.80, 2.30, 0.09, 981), Tree(2.85, 0.35, 0.09, 982),
    ]
    render2(cv, items)
    return finish(cv)


def r378():
    """v3 d1: lavender courtyard ring with the R, pool court inside, fountain south-east."""
    cv = ground('lawn', 3)
    paving(cv, rect(cv, 0.98, 1.08, 1.62, 1.66, 0.02), 0.5, 6)
    pool(cv, 1.12, 1.20, 1.48, 1.52)
    paving(cv, rect(cv, 0.86, 1.80, 1.62, 1.88), 0.55, 10)
    paving(cv, rect(cv, 0.64, 2.80, 0.84, 2.92), 0.48, 8)
    paving(cv, rect(cv, 1.55, 0.08, 1.75, 0.58), 0.48, 8)
    paving(cv, rect(cv, 2.38, 1.70, 2.56, 2.0), 0.48, 8)
    cx, cy = 2.47, 2.25
    cv.shade(cv.cov(sd_circle(cv.X, cv.Y, cx + 0.02, cy + 0.015, 0.31), 3), 0.3)
    paving(cv, cv.cov(sd_circle(cv.X, cv.Y, cx, cy, 0.30)), 0.55, 8)
    cv.paint(PAL['concrete'][7], cv.cov(sd_circle(cv.X, cv.Y, cx, cy, 0.20)))
    cv.paint(hx('#5f72e4'), cv.cov(sd_circle(cv.X, cv.Y, cx, cy, 0.17)))
    cv.paint(PAL['water'][3], cv.cov(sd_circle(cv.X, cv.Y, cx, cy, 0.17)) * (1 - cv.cov(sd_circle(cv.X, cv.Y, cx + 0.02, cy + 0.02, 0.16), 3)) * 0.7)
    cv.paint(PAL['concrete'][7], cv.cov(sd_circle(cv.X, cv.Y, cx, cy, 0.045)))
    cv.paint(PAL['water'][9], cv.cov(sd_circle(cv.X, cv.Y, cx - 0.01, cy - 0.04, 0.03), 3))
    frame(cv, 3)
    w = win(0.12, 0.11, 0.42, 0.45, warm=True)
    items = [
        Mass([(0.30, 0.55, 0.75, 2.82), (0.30, 0.55, 2.45, 1.00), (1.85, 0.55, 2.45, 1.70), (0.30, 2.25, 1.62, 2.82)], 0.50, LAV, R_GREY,
             win=w, label='R', label_at=(2.12, 1.05), label_size=0.46, rim=PAL['concrete'][5],
             roof_detail=vents([(0.55, 1.6), (0.92, 2.45), (2.22, 1.48)], hx('#141416'), 0.04)),
        Tree(2.82, 1.75, 0.10, 983), Tree(0.18, 0.30, 0.08, 984), Tree(2.8, 2.82, 0.0, 0),
    ]
    items = items[:3]
    render2(cv, items)
    return finish(cv)


class WinCylinder(Cylinder):
    """Round tower with rings of windows."""

    def __init__(self, *a, rows=0.12, ncol=12, glass=None, **kw):
        super().__init__(*a, **kw)
        self.rows, self.ncol, self.glass = rows, ncol, glass or PAL['glass']

    def draw(self, cv):
        super().draw(cv)
        bx, by = P(self.cx, self.cy, self.z0)
        tx, ty = P(self.cx, self.cy, self.z0 + self.h)
        r = self.r
        ax, ay = tx - bx, ty - by
        L = math.hypot(ax, ay)
        ux, uy = ax / L, ay / L
        nx, ny = -uy, ux
        s = ((cv.X - bx) * nx + (cv.Y - by) * ny) / r       # -1..1 across
        t = ((cv.X - bx) * ux + (cv.Y - by) * uy) / L        # 0..1 along the axis
        body = (np.abs(s) < 0.97) & (t > 0) & (t < 1)
        top = cv.cov(sd_circle(cv.X, cv.Y, tx, ty, r)) > 0.01
        bot = sd_circle(cv.X, cv.Y, bx, by, r) < 0
        # a cross point (s,t) in the body: the circle of a level z sits at t ~ z/h; surface point within r
        ang = np.arcsin(np.clip(s, -1, 1))
        z = t * self.h
        # the ring at height z is the circle centred on the axis; along the axis the circle offset is cos(ang)*r
        zz = z + np.cos(ang) * r * 0.0
        row = (np.abs(((zz / self.rows) % 1) - 0.5) < 0.22) & (zz > 0.06) & (zz < self.h - 0.04)
        col = np.abs((((ang / math.pi + 0.5) * self.ncol) % 1) - 0.5) < 0.3
        m = (body & row & col & ~top).astype(float)
        lam = np.clip(0.55 + 0.45 * s, 0, 1)
        cv.paint(self.glass(0.25 + 0.45 * lam), m)
        rng = (np.sin(np.floor(zz / self.rows) * 12.9 + np.floor((ang / math.pi + 0.5) * self.ncol) * 78.2) * 43758.5) % 1
        cv.paint(hx('#f6d27a') * 0.9, m * (rng > 0.85))


def r387():
    """v3 d2: park with two round towers (R on the south-east one), kiosk, court, playground."""
    cv = ground('lawn', 3)
    path = lambda x0, y0, x1, y1: paving(cv, rect(cv, x0, y0, x1, y1, 0.01), 0.58, 10)
    path(0.09, 2.04, 1.02, 2.16)
    path(0.92, 2.04, 1.02, 2.64)
    path(0.92, 2.54, 1.58, 2.64)
    path(1.74, 0.36, 1.84, 1.62)
    path(1.74, 0.36, 2.06, 0.46)
    path(1.42, 1.52, 1.84, 1.62)
    # small tennis court NE
    paving(cv, rect(cv, 2.04, 0.18, 2.48, 0.68), 0.7, 8)
    cv.paint(hx('#2f7a46'), rect(cv, 2.09, 0.23, 2.43, 0.63))
    for d in (0.0,):
        cv.paint(WHITE, cv.cov(np.abs(sd_box(cv.X, cv.Y, 2.12, 0.26, 2.40, 0.60)) - 0.005))
        cv.paint(WHITE, rect(cv, 2.12, 0.425, 2.40, 0.435))
        cv.paint(WHITE, rect(cv, 2.255, 0.30, 2.265, 0.56))
    # playground
    cv.paint(PAL['sand'][5], rect(cv, 1.03, 2.30, 1.30, 2.52, 0.04))
    for (x, y, c) in ((1.08, 2.35, '#f0d020'), (1.18, 2.35, '#e8241a'), (1.13, 2.44, '#3a52d8'), (1.24, 2.44, '#f0d020'), (1.07, 2.46, '#e8241a')):
        cv.shade(rect(cv, x + 0.01, y + 0.008, x + 0.05, y + 0.048), 0.4)
        cv.paint(hx(c), rect(cv, x, y, x + 0.04, y + 0.04, 0.005))
    frame(cv, 3)
    tower = LGREY
    t1 = WinCylinder(0.58, 1.25, 0.40, 1.36, tower, top=R_GREY, rows=0.12, ncol=14)
    t2 = WinCylinder(1.90, 2.38, 0.37, 1.24, tower, top=R_GREY, rows=0.12, ncol=14)
    def roofs(c):
        for (cx, cy, r, h) in ((0.58, 1.25, 0.40, 1.36), (1.90, 2.38, 0.37, 1.24)):
            tx, ty = P(cx, cy, h)
            c.paint(PAL['concrete'][2], c.cov(np.abs(sd_circle(c.X, c.Y, tx, ty, r - 0.02)) - 0.012))
            c.paint(PAL['concrete'][4], c.cov(sd_circle(c.X, c.Y, tx - 0.05, ty - 0.07, 0.07)))
            c.shade(c.cov(sd_circle(c.X, c.Y, tx - 0.03, ty - 0.05, 0.07)) * (1 - c.cov(sd_circle(c.X, c.Y, tx - 0.05, ty - 0.07, 0.07))), 0.4)
        tx, ty = P(1.90, 2.38, 1.24)
        draw_label(c, 'R', tx + 0.03, ty + 0.03, 0.46)
    t1.k, t2.k = 1, 2
    trees = [Tree(1.05, 1.62, 0.13, 990), Tree(1.25, 1.80, 0.12, 991), Tree(0.98, 1.88, 0.11, 992), Tree(1.20, 1.98, 0.10, 993),
             Tree(2.35, 2.62, 0.13, 994), Tree(2.62, 2.48, 0.11, 995), Tree(2.70, 2.75, 0.10, 996), Tree(2.45, 2.82, 0.0, 0),
             Tree(0.25, 0.35, 0.09, 997), Tree(2.75, 0.85, 0.09, 998), Tree(0.30, 2.62, 0.10, 999)]
    trees = [t for t in trees if t.r > 0]
    for t in trees:
        t.k = 0 if t.y < 2.1 and t.x < 1.5 else 3
    kiosk = Mass([(1.80, 0.96, 1.98, 1.22)], 0.16, hx('#3a4ad0'), R_LIGHT, win=None, k=0.5)
    items = [kiosk, t1, t2, Custom(roofs, key=(2.5, 0))] + trees
    render2(cv, items)
    return finish(cv)


def r396():
    """v3 d3: tall light-grey block with balconies, rimmed roof terraces, R deck, roof pool."""
    cv = ground('lawn', 3)
    frame(cv, 3)
    balc = win(0.14, 0.17, 0.78, 0.62, glass=Ramp(['#3a3a40', '#6a6a72', '#f2f2f3', '#ffffff']), sill=False)
    dense = win(0.10, 0.09, 0.45, 0.45, warm=True)
    def terrace(cv_, zt):
        # lower L-shaped rimmed terrace along the south and the court with the pool
        a, b, c, d = rproj(0.25, 2.15, 2.30, 2.80, zt)
        cv_.paint(WHITE, cv_.cov(np.abs(sd_box(cv_.X, cv_.Y, a + 0.02, b, c - 0.02, d - 0.02)) - 0.016))
        a2, b2, c2, d2 = rproj(0.25, 1.30, 1.05, 2.15, zt)
        cv_.paint(PAL['roof_tar'][2], rect(cv_, a2 + 0.03, b2 + 0.03, c2 - 0.02, d2 - 0.02))
        pa, pb, pc, pd = rproj(0.65, 1.55, 0.95, 2.05, zt)
        pool(cv_, pa + 0.02, pb + 0.04, pc - 0.04, pd - 0.02, 0.025)
        for y in (1.42, 1.58, 1.74):
            px, py = P(1.35, y + 0.2, zt)
            cv_.paint(hx('#121214'), rect(cv_, px, py, px + 0.035, py + 0.035))
            cv_.paint(hx('#121214'), rect(cv_, px + 0.08, py, px + 0.115, py + 0.035))
    items = [
        Mass([(1.45, 0.45, 2.35, 1.30)], 0.60, DGREY, R_DARK, win=dense, k=-2, rim=PAL['roof_tar'][3],
             roof_detail=vents([(1.95, 0.8), (2.05, 0.8)], hx('#101012'), 0.035)),
        Mass([(0.20, 0.64, 0.70, 1.30)], 1.10, LGREY, R_LIGHT, win=dense, k=-1, rim=WHITE,
             roof_detail=framed_panel(0.20, 0.64, 0.70, 1.30, R_LIGHT, WHITE, 0.035)),
        Mass([(0.20, 1.30, 2.30, 2.85)], 1.10, LGREY, R_LIGHT, win=balc, win_w=dense, k=0, rim=PAL['concrete'][6],
             roof_detail=terrace),
        Mass([(1.62, 1.42, 2.28, 2.42)], 0.10, WHITE, R_LIGHT, z0=1.10, win=None, k=1, rim=WHITE,
             label='R', label_at=(1.95, 1.88), label_size=0.5),
        Tree(0.13, 0.5, 0.0, 0),
    ]
    items = items[:4]
    render2(cv, items)
    return finish(cv)


# ================================================================== civic
def hospital():
    """Tall cross-shaped hospital, red cross on the roof, car parks west, trees south-east."""
    cv = Canvas(3, 3, RS, dirt_layer(3, 3))
    lawn(cv, rect(cv, 0.06, 0.06, 2.94, 2.94, 0.03))
    paving(cv, rect(cv, 0.25, 0.10, 0.95, 1.00, 0.02), 0.42, 6)
    paving(cv, rect(cv, 0.08, 0.54, 0.30, 0.68), 0.42, 6)
    paving(cv, rect(cv, 0.45, 0.08, 0.60, 0.15), 0.42, 6)
    parking_marks(cv, 0.30, 0.48, [0.30, 0.45, 0.60, 0.75])
    paving(cv, rect(cv, 0.25, 2.10, 0.80, 2.92, 0.02), 0.42, 6)
    paving(cv, rect(cv, 0.08, 2.44, 0.30, 2.56), 0.42, 6)
    parking_marks(cv, 0.55, 0.75, [2.25, 2.40, 2.70])
    civic_frame(cv)
    h = 1.30
    def redcross(c, zt):
        x, y = P(1.32, 1.58, zt)
        c.shade(c.cov(sd_circle(c.X, c.Y, x + 0.02, y + 0.016, 0.24), 3), 0.4)
        c.paint(WHITE, c.cov(sd_circle(c.X, c.Y, x, y, 0.24)))
        m = np.clip(rect(c, x - 0.15, y - 0.05, x + 0.15, y + 0.05) + rect(c, x - 0.05, y - 0.15, x + 0.05, y + 0.15), 0, 1)
        c.paint(hx('#e0201a'), m)
    items = [
        Mass([(0.95, 0.80, 1.75, 1.25), (0.50, 1.20, 2.20, 1.95), (0.95, 1.90, 1.70, 2.30)], h, LGREY, R_DARK,
             win=win(0.10, 0.10, 0.5, 0.42), rim=PAL['concrete'][4],
             roof_detail=chain(redcross, vents([(0.75, 1.4), (1.95, 1.75), (1.2, 2.1)], PAL['concrete'][5], 0.045))),
        car(0.40, 0.38, '#f4f4f0', True, 0.15, 0.08, -6), car(0.40, 0.68, '#2a3fc0', True, 0.15, 0.08, -6),
        car(0.65, 2.32, '#f4f4f0', True, 0.15, 0.08, -6), car(0.65, 2.55, '#d42a1c', True, 0.15, 0.08, -6),
    ]
    rng = np.random.default_rng(1001)
    for k in range(60):
        x, y = rng.uniform(1.05, 2.84), rng.uniform(1.70, 2.84)
        if y < 2.45 - 0.9 * (x - 1.0) + 0.25:  # keep the band south-east of the building
            continue
        items.append(Tree(x, y, rng.uniform(0.10, 0.14), 1010 + k))
    items += [Tree(2.75, 0.30, 0.10, 1040), Tree(2.70, 1.50, 0.10, 1041), Tree(0.20, 1.60, 0.09, 1042)]
    render2(cv, items)
    return finish(cv)


def church():
    """The classic church: light-grey nave with lancet windows, front tower with spire and cross."""
    cv = Canvas(3, 3, RS, dirt_layer(3, 3))
    lawn(cv, rect(cv, 0.06, 0.06, 2.94, 2.94, 0.03))
    paving(cv, rect(cv, 1.28, 2.45, 1.72, 2.92), 0.6, 8)
    civic_frame(cv)
    lancet = {'kind': 'grid', 'floor': 0.42, 'col': 0.16, 'wfrac': 0.28, 'hfrac': 0.72, 'base': 0.08,
              'glass': Ramp(['#141420', '#202038', '#34345a', '#4e5a8a']), 'sill': False}
    h = 0.90
    nave = Mass([(0.35, 0.75, 2.35, 2.48)], h, LGREY, R_DARK, win=lancet, rim=PAL['concrete'][3], k=0,
                roof_detail=vents([(0.62, 1.15), (0.62, 1.40), (0.62, 1.65), (1.45, 1.05), (1.70, 1.05), (1.95, 1.05), (2.15, 0.85)], hx('#0e0e10'), 0.035))
    chapel = Mass([(0.35, 0.75, 0.88, 1.18)], 1.02, LGREY, R_DARK, win=None, rim=PAL['concrete'][4], k=1)
    tx0, ty0, tx1, ty1, th = 1.22, 2.06, 1.68, 2.50, 0.98
    tower = Mass([(tx0, ty0, tx1, ty1)], th, LGREY, R_GREY, win={'kind': 'grid', 'floor': 0.3, 'col': 0.14, 'wfrac': 0.3, 'hfrac': 0.4, 'base': 0.45,
                 'glass': Ramp(['#141420', '#202038', '#34345a'])}, rim=PAL['concrete'][6], k=2, parapet=False)
    def door(c):
        a = P(1.38, ty1, 0.0)
        pts = [P(1.38, ty1, 0), P(1.52, ty1, 0), P(1.52, ty1, 0.22), P(1.45, ty1, 0.27), P(1.38, ty1, 0.22)]
        c.paint(PAL['timber'][2], c.poly(pts))
        c.paint(PAL['timber'][4], c.poly([P(1.39, ty1, 0.01), P(1.445, ty1, 0.01), P(1.445, ty1, 0.24), P(1.39, ty1, 0.21)]) * 0.6)
    def spire(c):
        zb, zt = th, th + 1.30
        cx, cy = (tx0 + tx1) / 2, (ty0 + ty1) / 2
        A = P(cx, cy, zt)
        e = 0.0
        N = [P(tx0, ty0, zb), P(tx1, ty0, zb), A]
        E = [P(tx1, ty0, zb), P(tx1, ty1, zb), A]
        W = [P(tx0, ty0, zb), P(tx0, ty1, zb), A]
        S = [P(tx0, ty1, zb), P(tx1, ty1, zb), A]
        tex = cached_noise(c)
        slate = PAL['concrete']
        c.paint(slate(0.35 + 0.1 * (tex - 0.5)), c.poly(E))
        c.paint(slate(0.75 + 0.1 * (tex - 0.5)), c.poly(N))
        c.paint(slate(0.85 + 0.1 * (tex - 0.5)), c.poly(W))
        c.paint(slate(0.50 + 0.1 * (tex - 0.5)), c.poly(S))
        # the lit arris from the south-west corner to the apex, as the original's white edge
        a = P(tx0, ty1, zb)
        c.paint(PAL['concrete'][8], c.cov(sd_segment(c.X, c.Y, a[0], a[1], A[0], A[1]) - 0.007, 1.0))
        # cross: post up the oblique axis, bar across in x
        p0, p1 = P(cx, cy, zt), P(cx, cy, zt + 0.34)
        b0, b1 = P(cx - 0.10, cy, zt + 0.23), P(cx + 0.10, cy, zt + 0.23)
        for (u, v) in ((p0, p1), (b0, b1)):
            c.shade(c.cov(sd_segment(c.X, c.Y, u[0] + 0.012, u[1] + 0.012, v[0] + 0.012, v[1] + 0.012) - 0.012, 2), 0.5)
        for (u, v) in ((p0, p1), (b0, b1)):
            c.paint(hx('#f4f1e6'), c.cov(sd_segment(c.X, c.Y, u[0], u[1], v[0], v[1]) - 0.014))
            c.paint(hx('#ffd84a'), c.cov(sd_segment(c.X, c.Y, u[0] - 0.004, u[1] - 0.004, v[0] - 0.004, v[1] - 0.004) - 0.005) * 0.6)
    spire_shadow = lambda c: c.poly([(tx0, ty0), (tx1, ty0), (tx1, ty1), (tx0, ty1)])
    items = [nave, chapel, tower, Custom(door, key=(2.5, 0)), Custom(spire, key=(3, 0))]
    for it in items:
        if isinstance(it, Custom):
            it.k = it._key[0]
    def spire_sh(c):
        cx, cy = (tx0 + tx1) / 2, (ty0 + ty1) / 2
        H = th + 1.30
        return c.poly([(tx0 + SHADOW_DIR[0] * th, ty0 + SHADOW_DIR[1] * th), (tx1 + SHADOW_DIR[0] * th, ty1 + SHADOW_DIR[1] * th),
                       (cx + SHADOW_DIR[0] * H, cy + SHADOW_DIR[1] * H)])
    items[-1].shadow_mask = spire_sh
    rng = np.random.default_rng(1101)
    for k in range(24):
        x, y = rng.uniform(0.25, 2.82), rng.uniform(2.55, 2.84)
        if 1.2 < x < 1.8:
            continue
        items.append(Tree(x, y, rng.uniform(0.09, 0.12), 1110 + k))
    for k in range(6):
        items.append(Tree(2.82, 0.6 + 0.35 * k, 0.09, 1140 + k))
    render2(cv, items)
    return finish(cv)


for _b, _f in ((261, r261), (270, r270), (279, r279), (288, r288), (297, r297), (306, r306), (315, r315), (324, r324),
               (333, r333), (342, r342), (351, r351), (360, r360), (369, r369), (378, r378), (387, r387), (396, r396),
               (405, hospital), (414, church)):
    GROUPS.append((_b, 3, 3, _f))
