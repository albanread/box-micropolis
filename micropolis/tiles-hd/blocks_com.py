"""Commercial 3x3 zone blocks, every density and land value.

base = (value*5 + density)*9 + 432 (density 0..4, value 0..3). Each block is one picture
cut into nine cells. Buildings are given by their ROOF rectangle as read from the original
(see work/orig_BASE.png) plus a height; the footprint follows from the oblique projection
(roof = footprint + (h/2, -h/2)), so the picture keeps the original's silhouette.
"""
import math
import numpy as np
from hdlib import *
from terrain import dirt_layer, grass_layer, draw_crown
from scene3d import Box, Cylinder, Tree, Custom, P, face_uv, windows, LIGHT_S, LIGHT_W
from buildings import zone_frame, paving, lawn, rect, letter_col, vehicle, roof_units, roof_skylights
import transport as TR

GROUPS = []
ANIM = {}

# ------------------------------------------------------------------ colours
LAV = PAL['com'][4]                 # original #6666e6 west walls
LAV_S = hx('#3a3ad8')               # original #0000e6 south walls (x0.64 when drawn)
DARK_ROOF = PAL['roof_tar'][2]      # original #3f3f3f roofs
GREY_ROOF = PAL['concrete'][3]      # original #7f7f7f roofs
LIGHT_ROOF = PAL['concrete'][5]     # original #bfbfbf roofs
GREEN_W = hx('#46c04c')             # original #00e600 walls
GREEN_S = hx('#2a9a30')             # original #007f00 walls
RED_W = hx('#d8402e')
RED_S = hx('#c8301f')
DARK_W = hx('#55565e')
WHITE_W = hx('#ecebe6')
C_COL = letter_col('com')

DARK_GLASS = Ramp(['#0a0f22', '#111a36', '#18244a', '#22325e', '#2e4274', '#3e568c'])
BRIGHT_GLASS = Ramp(['#8fa6c8', '#b4c8e2', '#d8e4f2', '#f2f6fb'])
GREEN_GLASS = Ramp(['#0b2a14', '#11391c', '#184a26', '#235e33', '#317442'])

W_DOTS = {'kind': 'grid', 'floor': 0.12, 'col': 0.10, 'wfrac': 0.45, 'hfrac': 0.45, 'glass': DARK_GLASS}
W_SHOP = {'kind': 'grid', 'floor': 0.11, 'col': 0.09, 'wfrac': 0.6, 'hfrac': 0.5}
W_OFFICE = {'kind': 'grid', 'floor': 0.10, 'col': 0.08, 'wfrac': 0.55, 'hfrac': 0.55, 'warm': True}


# ------------------------------------------------------------------ primitives
def edge_fade(cv, a=0.022, b=0.05):
    d = -sd_box(cv.X, cv.Y, 0, 0, cv.wt, cv.ht)
    return smoothstep(a, b, d)


def draw_C(cv, cx, cy, size=0.55, mask=None):
    m = cv.text_mask('C', cx, cy, size, FONT_SERIF)
    if mask is not None:
        m = m * mask
    sh = np.roll(np.roll(m, int(0.012 * cv.n), 0), int(0.016 * cv.n), 1)
    cv.shade(sh, 0.55)
    cv.paint(C_COL, m)
    e = np.clip(m - np.roll(np.roll(m, 2, 0), 2, 1), 0, 1)
    cv.light(e, 0.45)


class Box2(Box):
    """Box with its own south-wall colour, a C anywhere on the roof and extra roof detail."""

    def __init__(self, *a, wall_s=None, cpos=None, csize=0.55, extra=None, **k):
        super().__init__(*a, **k)
        self.wall_s, self.cpos, self.csize, self.extra = wall_s, cpos, csize, extra
        rd = self.roof_detail
        if cpos is not None or extra is not None:
            def det(cv, rx0, ry0, rx1, ry1, rd=rd):
                if rd:
                    rd(cv, rx0, ry0, rx1, ry1)
                if extra:
                    extra(cv, rx0, ry0, rx1, ry1)
                if cpos is not None:
                    rm = cv.cov(sd_box(cv.X, cv.Y, rx0, ry0, rx1, ry1))
                    draw_C(cv, rx0 + cpos[0] * (rx1 - rx0), ry0 + cpos[1] * (ry1 - ry0), csize, rm)
            self.roof_detail = det

    def draw(self, cv):
        Box.draw(self, cv)
        if self.wall_s is None:
            return
        x0, y0, x1, y1, h, z0 = self.x0, self.y0, self.x1, self.y1, self.h, self.z0
        zt = z0 + h
        O = P(x0, y1, z0)
        U = (1.0, 0.0)
        V = (OX, -OY)
        m = cv.poly([P(x0, y1, z0), P(x1, y1, z0), P(x1, y1, zt), P(x0, y1, zt)])
        u, v = face_uv(cv, O, U, V)
        lv = h
        col = np.asarray(self.wall_s, float) * LIGHT_S * (0.92 + 0.12 * np.clip(v / max(lv, 1e-3), 0, 1))[..., None]
        if self.ao:
            col = col * (1 - 0.25 * np.exp(-(v + z0) / 0.05))[..., None]
        cv.paint(col, m)
        glass = PAL['glass'] if self.glass is None else self.glass
        self._windows(cv, m, u, v, x1 - x0, lv, self.win, lit=False, glass=glass)
        a, b = P(x0, y1, z0), P(x0, y1, zt)
        cv.light(cv.cov(sd_segment(cv.X, cv.Y, a[0], a[1], b[0], b[1]) - 0.004, 1.0) * m.max(), 0.25)


def RB(rx0, ry0, rx1, ry1, h, wall, roof, z0=0.0, **k):
    """A box given by its projected roof rectangle (as read off the original)."""
    s = (z0 + h) / 2
    assert rx1 < 2.94 and ry0 > 0.06, ('roof outside block', rx1, ry0)
    x0, y0, x1, y1 = rx0 - s, ry0 + s, rx1 - s, ry1 + s
    assert x0 > 0.08 and y1 < 2.92, ('footprint outside frame', x0, y1)
    return Box2(x0, y0, x1, y1, h, wall, roof, z0=z0, **k)


class Hip:
    """Hipped / pyramid roof on low walls."""

    def __init__(self, x0, y0, x1, y1, h, rh, wall, ramp, wall_s=None, courses=0.06, win=None):
        self.__dict__.update(locals())
        del self.__dict__['self']

    def key(self):
        return ((self.y0 + self.y1) / 2 - (self.x0 + self.x1) / 2, 0)

    def shadow_poly(self):
        x0, y0, x1, y1 = self.x0, self.y0, self.x1, self.y1
        h = self.h + self.rh * 0.6
        foot = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        sx, sy = SHADOW_DIR * h
        from scene3d import hull
        return hull(foot + [(x + sx, y + sy) for x, y in foot])

    def draw(self, cv):
        x0, y0, x1, y1, h, rh = self.x0, self.y0, self.x1, self.y1, self.h, self.rh
        Box2(x0, y0, x1, y1, h, self.wall, self.wall, parapet=False, wall_s=self.wall_s, win=self.win).draw(cv)
        e = 0.015
        a0, b0, a1, b1 = x0 - e, y0 - e, x1 + e, y1 + e
        if (a1 - a0) <= (b1 - b0):
            d = (a1 - a0) / 2
            R1, R2 = P((a0 + a1) / 2, b0 + d, h + rh), P((a0 + a1) / 2, b1 - d, h + rh)
        else:
            d = (b1 - b0) / 2
            R1, R2 = P(a0 + d, (b0 + b1) / 2, h + rh), P(a1 - d, (b0 + b1) / 2, h + rh)
        A, B, C, D = P(a0, b0, h), P(a1, b0, h), P(a1, b1, h), P(a0, b1, h)
        if (a1 - a0) <= (b1 - b0):
            faces = [([A, B, R1], 0.66), ([B, C, R2, R1], 0.38), ([A, R1, R2, D], 0.80), ([D, R2, C], 0.48)]
        else:
            faces = [([A, B, R2, R1], 0.66), ([B, C, R2], 0.38), ([A, R1, D], 0.80), ([D, R1, R2, C], 0.48)]
        tex = pnoise(cv.n, 48, 905, cv.wt, cv.ht)
        # concentric courses: distance to the eaves outline in plan, as the original's rings
        cx, cy = (A[0] + C[0]) / 2, (A[1] + C[1]) / 2
        ring = np.maximum(np.abs(cv.X - cx) / max(C[0] - A[0], 1e-3), np.abs(cv.Y - cy) / max(C[1] - A[1], 1e-3))
        crs = (np.abs(((ring / self.courses) % 1) - 0.5) > 0.30).astype(float)
        for pts, t in faces:
            m = cv.poly(pts, 2)
            cv.paint(self.ramp(t + 0.08 * (tex - 0.5)), m)
            cv.shade(crs * m, 0.18)
        for a, b in ((A, R1), (D, R2) if (a1 - a0) <= (b1 - b0) else (D, R1), (R1, R2), (B, R1 if (a1 - a0) <= (b1 - b0) else R2), (C, R2)):
            cv.light(cv.cov(sd_segment(cv.X, cv.Y, a[0], a[1], b[0], b[1]) - 0.003, 1.0), 0.25)


def render2(cv, items, shadow_strength=0.62):
    """scene3d.render, with every shadow faded out before the block's outer edge."""
    sh = np.zeros_like(cv.X)
    for it in items:
        if isinstance(it, Tree):
            sh = np.maximum(sh, it.shadow(cv))
            continue
        p = it.shadow_poly()
        if p:
            sh = np.maximum(sh, cv.poly(p))
    sh = cv.blur(sh, 0.008) * edge_fade(cv)
    cv.shade(sh, shadow_strength)
    for it in sorted(items, key=lambda i: i.key()):
        it.draw(cv)


def ground(kind='dirt'):
    cv = Canvas(3, 3, RS, dirt_layer(3, 3))
    if kind == 'lawn':
        lawn(cv, rect(cv, 0.08, 0.08, 2.92, 2.92))
    elif kind == 'paving':
        paving(cv, rect(cv, 0.08, 0.08, 2.92, 2.92), 0.58, 6)
    elif kind == 'light':
        paving(cv, rect(cv, 0.08, 0.08, 2.92, 2.92), 0.70, 6)
    return cv


def asphalt(cv, mask, tone=0.45):
    n = pnoise(cv.n, 40, 911, cv.wt, cv.ht)
    g = pnoise(cv.n, 150, 912, cv.wt, cv.ht)
    cv.paint(PAL['asphalt'](tone + 0.10 * (n - 0.5) + 0.08 * (g - 0.5)), mask)


def kerb(cv, mask, w=0.012):
    """Thin light kerb around a paved mask."""
    e = np.clip(mask - cv.blur(mask, w), 0, 1) * 2.2
    cv.paint(PAL['concrete'][6], np.clip(e, 0, 1) * 0.8)


def stall_lines(cv, x0, x1, y0, y1, step=0.17, horizontal=False):
    """Parking bay lines."""
    if not horizontal:
        k = np.abs(((cv.X - x0) / step) % 1 - 0.5) > 0.5 - 0.012 / step
        m = k & (cv.X > x0 - 0.01) & (cv.X < x1 + 0.01) & (cv.Y > y0) & (cv.Y < y1)
    else:
        k = np.abs(((cv.Y - y0) / step) % 1 - 0.5) > 0.5 - 0.012 / step
        m = k & (cv.Y > y0 - 0.01) & (cv.Y < y1 + 0.01) & (cv.X > x0) & (cv.X < x1)
    cv.paint(PAL['concrete'][8], m.astype(float) * 0.75)


def shrubs(cv, pts, r=0.035, seed=0):
    rng = np.random.default_rng(seed)
    for (x, y) in pts:
        rr = r * rng.uniform(0.8, 1.2)
        cv.shade(cv.cov(sd_circle(cv.X, cv.Y, x + 0.02, y + 0.012, rr), 3), 0.5)
        draw_crown(cv, x, y, rr, int(rng.integers(1000)))


def bollard(cv, x, y, col='#2a2a2e', h=0.10, r=0.014):
    tx, ty = P(x, y, h)
    cv.shade(cv.cov(sd_segment(cv.X, cv.Y, x, y, x + SHADOW_DIR[0] * h, y + SHADOW_DIR[1] * h) - r * 0.8, 2), 0.4)
    cv.paint(hx(col), cv.cov(sd_segment(cv.X, cv.Y, x, y, tx, ty) - r))
    cv.light(cv.cov(sd_circle(cv.X, cv.Y, tx - 0.004, ty - 0.004, r * 0.6), 1.5), 0.4)


def lamp(cv, x, y, col='#fff3c0', h=0.16):
    bollard(cv, x, y, '#303036', h, 0.009)
    tx, ty = P(x, y, h)
    cv.light(cv.cov(sd_circle(cv.X, cv.Y, tx, ty, 0.03), 6), 0.35, hx(col))
    cv.paint(hx(col), cv.cov(sd_circle(cv.X, cv.Y, tx, ty, 0.012), 1.2))


def car(cv, x, y, col, vertical=False, L=0.15, W=0.08):
    vehicle(cv, x, y, L, W, col, horizontal=not vertical)


def cust(fn, key):
    return Custom(fn, key=key)


def units(*u, col=None):
    return roof_units(list(u), col)


def rooflights(rows, cols, col=None, size=0.035, mx=0.12, my=0.12):
    def fn(cv, rx0, ry0, rx1, ry1):
        c = PAL['glass'](0.7) if col is None else col
        for i in range(cols):
            for j in range(rows):
                x = rx0 + (rx1 - rx0) * (mx + (1 - 2 * mx) * (i + 0.5) / cols)
                y = ry0 + (ry1 - ry0) * (my + (1 - 2 * my) * (j + 0.5) / rows)
                cv.shade(rect(cv, x - size / 2 + 0.008, y - size / 2 + 0.008, x + size / 2 + 0.008, y + size / 2 + 0.008), 0.4)
                cv.paint(c, rect(cv, x - size / 2, y - size / 2, x + size / 2, y + size / 2, 0.003))
    return fn


def finish(cv, items):
    zone_frame(cv, 'com')
    render2(cv, items)
    return cv


# ================================================================== value 0
def c432():
    """Density 0: a small shop on a lawn, U-shaped drive in front, C on the drive."""
    cv = ground('lawn')
    pv = np.maximum(rect(cv, 0.48, 0.30, 2.52, 2.30, 0.12), rect(cv, 0.08, 2.30, 2.92, 2.62))
    pv = np.maximum(pv, rect(cv, 0.95, 2.4, 1.85, 2.82, 0.06))
    asphalt(cv, pv, 0.62)
    kerb(cv, pv)
    paving(cv, rect(cv, 0.62, 0.42, 2.38, 2.20, 0.06), 0.62, 8)
    shrubs(cv, [(0.55, 0.22), (2.55, 0.32), (0.32, 2.15), (2.62, 2.15), (2.75, 0.75), (0.2, 0.6), (1.3, 2.78), (2.2, 2.78)], 0.04, 1)
    draw_C(cv, 1.42, 2.52, 0.48)
    def front(cv, rx0, ry0, rx1, ry1):
        # the green-framed light panel of the original
        cv.paint(GREEN_S * 0.8, rect(cv, 1.30, ry0 + 0.06, 1.78, ry1 - 0.02, 0.01))
        cv.paint(PAL['concrete'][6], rect(cv, 1.34, ry0 + 0.10, 1.74, ry1 - 0.06, 0.008))
    items = [
        RB(1.10, 0.55, 2.05, 1.25, 0.42, DARK_W, DARK_ROOF, win=W_SHOP, glass=BRIGHT_GLASS, rim=PAL['roof_tar'][4],
           roof_detail=units((0.05, 0.12, 0.10, 0.10), (0.84, 0.12, 0.10, 0.10), (0.4, 0.6, 0.14, 0.10))),
        Box2(0.82, 1.40, 2.12, 1.98, 0.20, DARK_W, PAL['roof_tar'][3], win={'kind': 'grid', 'floor': 0.09, 'col': 0.10, 'wfrac': 0.7, 'hfrac': 0.6, 'base': 0.04},
             glass=BRIGHT_GLASS, extra=front),
        # green canopy along the shop front
        Box2(0.68, 2.00, 2.30, 2.16, 0.025, GREEN_S, GREEN_S, z0=0.16, parapet=False, shadow=True),
        # white roadside sign on two legs
        Box2(0.18, 1.02, 0.25, 1.78, 0.30, WHITE_W, WHITE_W, z0=0.14, parapet=False, wall_s=WHITE_W),
        Cylinder(0.215, 1.12, 0.018, 0.16, PAL['timber'][3]),
        Cylinder(0.215, 1.68, 0.018, 0.16, PAL['timber'][3]),
        cust(lambda c: car(c, 2.25, 1.85, '#c0392b', vertical=True), (0.0, 0)),
    ]
    return finish(cv, items)


def c441():
    """Density 1: the round restaurant on stilts, a kiosk, a gravel lot, C on the ground."""
    cv = ground()
    X, Y = cv.X, cv.Y
    lot = rect(cv, 0.10, 0.10, 2.90, 2.90)
    # gravel: dark and brown chips on the dirt
    g = pnoise(cv.n, 64, 913, 3, 3)
    g2 = pnoise(cv.n, 64, 914, 3, 3)
    cv.paint(PAL['asphalt'][4], smoothstep(0.80, 0.86, g) * lot)
    cv.paint(PAL['sand'][2], smoothstep(0.80, 0.86, g2) * lot)
    paving(cv, np.maximum(rect(cv, 0.18, 0.40, 0.32, 1.66), rect(cv, 0.08, 1.52, 0.32, 1.68)), 0.50, 8)
    draw_C(cv, 0.45, 2.36, 0.50)
    tank = hx('#a9a9ae')
    cx, cy, z0 = 1.08, 1.92, 0.95
    items = []
    for k, (lx, ly) in enumerate(((0.80, 1.58), (0.94, 1.86), (1.10, 2.14), (1.26, 2.42))):
        leg = Cylinder(lx, ly, 0.022, z0 + 0.05 + 0.1 * k, hx('#26262a'), top=hx('#26262a'))
        items.append(leg)
    t = Cylinder(cx, cy, 0.52, 1.10, tank, top=hx('#c4c4c8'), z0=z0,
                 bands=[(0.30, 0.09, hx('#1d2b48')), (0.62, 0.09, hx('#1d2b48'))])
    t.key = lambda: (5, 0)
    items.append(t)
    def beacon(c):
        tx, ty = P(cx, cy, z0 + 1.15)
        c.paint(PAL['concrete'][4], c.cov(sd_circle(c.X, c.Y, tx, ty, 0.30), 2) * 0.35)
        bx, by = tx + 0.25, ty - 0.20
        c.paint(hx('#e02a1a'), c.cov(sd_circle(c.X, c.Y, bx, by, 0.025)))
        c.light(c.cov(sd_circle(c.X, c.Y, bx, by, 0.06), 6), 0.25, hx('#ff6040'))
    items.append(cust(beacon, (6, 0)))
    items.append(RB(0.25, 0.30, 0.60, 0.78, 0.18, DARK_W, PAL['roof_tar'][1], win=W_SHOP, glass=BRIGHT_GLASS,
                    extra=lambda c, a, b, d, e: c.paint(hx('#ff8a1a'), c.cov(sd_circle(c.X, c.Y, a + 0.07, e - 0.07, 0.022)))))
    return finish(cv, items)


def c450():
    """Density 2: green slab west, low green bar north, red shop south-west, lavender block with C."""
    cv = ground()
    win_g = dict(W_DOTS, glass=GREEN_GLASS)
    items = [
        RB(0.50, 0.16, 1.05, 2.00, 0.60, GREEN_S, GREY_ROOF, wall_s=GREEN_S, win=win_g, rim=PAL['concrete'][5],
           roof_detail=units((0.2, 0.2, 0.12, 0.06), (0.25, 0.75, 0.12, 0.06))),
        RB(1.15, 0.16, 2.72, 0.85, 0.36, GREEN_S, GREY_ROOF, wall_s=GREEN_S, win=win_g, rim=PAL['concrete'][5],
           roof_detail=units((0.45, 0.35, 0.05, 0.12), (0.52, 0.35, 0.05, 0.12))),
        RB(1.95, 0.95, 2.82, 2.25, 1.00, LAV, GREY_ROOF, wall_s=LAV_S, win=W_DOTS, rim=PAL['roof_tar'][1], cpos=(0.42, 0.42),
           roof_detail=units((0.75, 0.2, 0.08, 0.08), (0.75, 0.6, 0.08, 0.08), (0.55, 0.85, 0.08, 0.06))),
        RB(0.55, 2.04, 1.72, 2.45, 0.55, RED_W, DARK_ROOF, wall_s=RED_S, win=W_DOTS, rim=PAL['roof_tar'][5],
           roof_detail=units((0.2, 0.4, 0.08, 0.1), (0.5, 0.4, 0.08, 0.1), (0.8, 0.4, 0.08, 0.1), col=PAL['roof_tar'][1])),
    ]
    return finish(cv, items)


def c459():
    """Density 3: tall lavender block with C and a mast, two-part east wing, paved ring."""
    cv = ground('paving')
    lawn(cv, np.maximum.reduce([rect(cv, 0.10, 0.10, 0.18, 2.90), rect(cv, 0.10, 0.10, 2.90, 0.17), rect(cv, 2.82, 0.10, 2.90, 2.90),
                                rect(cv, 0.26, 0.24, 0.95, 0.75, 0.04), rect(cv, 0.22, 2.86, 2.90, 2.90)]))
    asphalt(cv, rect(cv, 0.30, 2.74, 2.78, 2.85), 0.4)
    paving(cv, np.maximum(rect(cv, 0.20, 0.17, 0.27, 2.86), rect(cv, 0.20, 0.17, 2.80, 0.24)), 0.75, 8)
    def mast(c, rx0, ry0, rx1, ry1):
        bx, by = 1.40, 1.62
        tx, ty = bx + 0.32, by - 0.32
        c.shade(c.cov(sd_segment(c.X, c.Y, bx, by, bx + 0.30, by + 0.04) - 0.006, 2), 0.4)
        c.paint(PAL['steel'][1], c.cov(sd_segment(c.X, c.Y, bx, by, tx, ty) - 0.008))
        c.paint(hx('#e02a1a'), c.cov(sd_circle(c.X, c.Y, tx, ty, 0.012)))
        c.paint(PAL['concrete'][2], c.cov(sd_circle(c.X, c.Y, bx, by, 0.025)))
    items = [
        RB(0.95, 0.24, 1.95, 2.20, 1.20, LAV, GREY_ROOF, wall_s=LAV_S, win=W_DOTS, rim=PAL['com'][2], cpos=(0.27, 0.48),
           roof_detail=units((0.6, 0.06, 0.14, 0.08), (0.12, 0.85, 0.12, 0.08)), extra=mast),
        RB(1.98, 0.30, 2.72, 0.76, 1.00, LAV, GREY_ROOF, wall_s=LAV_S, win=W_DOTS, rim=PAL['com'][2]),
        RB(1.98, 0.80, 2.72, 1.04, 0.55, DARK_W, DARK_ROOF, wall_s=DARK_W, win=W_DOTS),
        RB(1.98, 1.06, 2.72, 2.30, 1.00, LAV, GREY_ROOF, wall_s=LAV_S, win=W_DOTS, rim=PAL['com'][2],
           roof_detail=units((0.2, 0.15, 0.1, 0.08), (0.6, 0.7, 0.12, 0.1))),
    ]
    return finish(cv, items)


def c468():
    """Density 4: red-and-blue tower with C, small blue block north, red block NE, lavender SE."""
    cv = ground()
    brick_glass = {'kind': 'grid', 'floor': 0.09, 'col': 0.08, 'wfrac': 0.6, 'hfrac': 0.6, 'glass': Ramp(['#16206a', '#2232a0', '#3446c8', '#5060e0'])}
    items = [
        RB(0.68, 0.10, 1.32, 0.62, 1.00, PAL['brick'][4], GREY_ROOF, wall_s=LAV_S, win=W_DOTS, win_w=brick_glass, rim=PAL['com'][3]),
        RB(0.62, 0.62, 1.32, 1.05, 0.70, DARK_W, DARK_ROOF, wall_s=DARK_W, win=W_DOTS),
        RB(0.80, 1.05, 1.56, 2.02, 1.30, PAL['brick'][4], GREY_ROOF, wall_s=LAV_S, win=W_DOTS, win_w=brick_glass, rim=PAL['com'][5],
           cpos=(0.45, 0.48), roof_detail=units((0.75, 0.08, 0.12, 0.08))),
        RB(2.05, 0.20, 2.82, 1.25, 0.80, RED_W, GREY_ROOF, wall_s=RED_S, win=W_DOTS, rim=PAL['roof_tar'][1],
           roof_detail=units((0.2, 0.2, 0.15, 0.1), (0.6, 0.7, 0.15, 0.12))),
        RB(2.10, 1.45, 2.85, 2.20, 0.90, LAV, GREY_ROOF, wall_s=LAV_S, win=W_DOTS, rim=PAL['com'][5],
           roof_detail=units((0.45, 0.55, 0.06, 0.06), (0.58, 0.55, 0.06, 0.06), (0.45, 0.70, 0.06, 0.06), (0.58, 0.70, 0.06, 0.06), col=PAL['roof_tar'][1])),
    ]
    return finish(cv, items)


# ================================================================== value 1
def c477():
    """Density 0: hip-roofed shop, car park with C, a road through, red shop south."""
    cv = ground('lawn')
    lot = rect(cv, 1.18, 0.20, 2.86, 1.52, 0.04)
    paving(cv, lot, 0.50, 8)
    kerb(cv, lot)
    stall_lines(cv, 1.20, 1.50, 0.30, 1.30, 0.17, horizontal=True)
    road = rect(cv, 0.08, 1.50, 2.92, 1.80)
    asphalt(cv, road, 0.5)
    for k in range(9):
        x = 0.25 + k * 0.32
        cv.paint(PAL['concrete'][8], rect(cv, x, 1.64, x + 0.10, 1.665) * 0.9)
    drv = rect(cv, 0.55, 1.80, 2.45, 2.18, 0.05)
    asphalt(cv, drv, 0.62)
    lawn(cv, rect(cv, 0.80, 1.84, 2.18, 1.89, 0.02))
    draw_C(cv, 1.62, 1.30, 0.46)
    clay = Ramp(['#5a3020', '#7a4430', '#9a5c40', '#b87454', '#cc8a68', '#dca484'])
    items = [
        Hip(0.30, 0.22, 1.20, 1.30, 0.12, 0.38, hx('#b09a70'), clay, wall_s=LAV_S, win=W_SHOP),
        RB(1.10, 2.40, 2.15, 2.68, 0.25, RED_W, DARK_ROOF, wall_s=RED_S, win=W_SHOP, glass=BRIGHT_GLASS, rim=PAL['roof_tar'][0]),
        # orange-and-white sign on a pole over the road
        Cylinder(1.98, 1.58, 0.016, 0.58, PAL['steel'][3]),
        Box2(1.72, 1.40, 2.42, 1.46, 0.14, hx('#ff8a1a'), hx('#ff8a1a'), z0=0.56, parapet=False, wall_s=WHITE_W),
    ]
    for (x, y, col, v) in ((1.33, 0.42, '#c0392b', False), (1.33, 0.76, '#2c4f9e', False), (1.33, 0.93, '#f0f0ee', False),
                           (1.33, 1.20, '#6a6ae0', False), (2.18, 0.66, '#2c4f9e', False), (2.5, 0.35, '#e8e4dc', True)):
        items.append(cust((lambda x=x, y=y, col=col, v=v: lambda c: car(c, x, y, col, v))(), (y - x, 0)))
    items.append(cust(lambda c: shrubs(c, [(0.3, 2.3), (0.55, 2.6), (2.6, 2.3), (2.75, 2.6), (2.75, 0.4), (2.6, 2.0), (0.2, 1.4)], 0.04, 7), (-9, 0)))
    return finish(cv, items)


def c486():
    """Density 1: lavender low block NE, white-and-dark tower with roof garden, plaza with C."""
    cv = ground()
    pl = np.maximum(rect(cv, 1.50, 1.40, 2.50, 2.55, 0.03), rect(cv, 2.40, 1.42, 2.92, 1.88))
    paving(cv, pl, 0.56, 8)
    kerb(cv, pl)
    draw_C(cv, 1.88, 1.78, 0.48)
    rng = np.random.default_rng(86)
    pts = [(x, y) for x, y in rng.uniform(0.15, 2.85, (60, 2)) if not (1.2 < x < 2.8 and 0.2 < y < 1.3) and not (0.2 < x < 1.6 and 0.5 < y < 2.8) and not (1.45 < x < 2.95 and 1.35 < y < 2.6)]
    items = [
        RB(1.55, 0.30, 2.72, 0.95, 0.35, LAV, DARK_ROOF, wall_s=LAV_S, win=W_DOTS, rim=PAL['com'][5],
           roof_detail=units((0.30, 0.35, 0.05, 0.25), (0.36, 0.44, 0.14, 0.06), (0.46, 0.35, 0.05, 0.25), col=PAL['roof_tar'][0])),
        Box2(0.80, 0.60, 1.22, 1.45, 0.16, DARK_W, lambda c, a, b, d, e: grass_layer(3, 3, c.n) * 0.95, wall_s=DARK_W,
             rim=PAL['roof_tar'][1]),
        RB(0.70, 1.36, 1.46, 2.35, 0.80, WHITE_W, DARK_ROOF, wall_s=hx('#3a3a40'), win={'kind': 'grid', 'floor': 0.12, 'col': 0.10, 'wfrac': 0.5, 'hfrac': 0.5},
           glass=BRIGHT_GLASS, roof_detail=rooflights(5, 4, PAL['concrete'][7], 0.05)),
    ]
    items.append(cust(lambda c: shrubs(c, pts, 0.03, 8), (-9, 0)))
    for x in (1.85, 2.10, 2.35):
        items.append(cust((lambda x=x: lambda c: car(c, x, 2.40, '#26262c', True, 0.14, 0.075))(), (2.4 - x, 0)))
    return finish(cv, items)


def c495():
    """Density 2: green-walled offices, the tallest with C, a smaller one south-east."""
    cv = ground()
    win_g = dict(W_DOTS, glass=GREEN_GLASS)
    items = [
        RB(0.50, 0.32, 1.10, 2.45, 0.60, GREEN_W, GREY_ROOF, wall_s=GREEN_S, win=win_g, rim=PAL['concrete'][5],
           roof_detail=units((0.3, 0.1, 0.12, 0.06), (0.4, 0.5, 0.12, 0.06), (0.3, 0.85, 0.12, 0.06))),
        RB(1.55, 0.22, 2.72, 1.35, 1.00, GREEN_W, DARK_ROOF, wall_s=GREEN_S, win=win_g, rim=PAL['roof_tar'][4], cpos=(0.40, 0.48),
           roof_detail=units((0.8, 0.1, 0.1, 0.1), (0.8, 0.75, 0.1, 0.12))),
        RB(2.05, 1.78, 2.58, 2.45, 0.60, GREEN_W, GREY_ROOF, wall_s=GREEN_S, win=win_g, rim=PAL['concrete'][5]),
    ]
    return finish(cv, items)


def c504():
    """Density 3: the big lavender tower with C on a paved plaza (re-done to follow the original)."""
    cv = ground('paving')
    asphalt(cv, rect(cv, 0.95, 2.10, 2.75, 2.76), 0.55)
    walk = np.maximum.reduce([rect(cv, 0.16, 0.16, 0.30, 2.84), rect(cv, 0.16, 2.70, 1.00, 2.84), rect(cv, 2.70, 2.10, 2.84, 2.84)])
    paving(cv, walk, 0.80, 8)
    strips = {'kind': 'grid', 'floor': 0.07, 'col': 0.14, 'wfrac': 0.38, 'hfrac': 0.88, 'glass': BRIGHT_GLASS}
    strips_s = {'kind': 'grid', 'floor': 0.07, 'col': 0.14, 'wfrac': 0.38, 'hfrac': 0.88, 'glass': DARK_GLASS}
    items = [
        RB(1.25, 0.10, 2.90, 1.75, 1.50, LAV, DARK_ROOF, wall_s=LAV_S, win=strips_s, win_w=strips, rim=PAL['com'][4],
           cpos=(0.40, 0.40), csize=0.62,
           roof_detail=units((0.08, 0.75, 0.16, 0.12), (0.72, 0.72, 0.16, 0.14), (0.75, 0.10, 0.12, 0.10))),
    ]
    return finish(cv, items)


def c513():
    """Density 4: the green tower with C, a small dark block behind, cars by the plaza."""
    cv = ground('light')
    lawn(cv, np.maximum(rect(cv, 0.22, 0.18, 0.62, 0.95, 0.04), rect(cv, 0.12, 0.12, 0.18, 2.88)))
    win_w = {'kind': 'grid', 'floor': 0.11, 'col': 0.10, 'wfrac': 0.45, 'hfrac': 0.45, 'glass': BRIGHT_GLASS}
    items = [
        RB(0.55, 0.10, 1.00, 0.45, 0.40, DARK_W, DARK_ROOF, wall_s=DARK_W, win=W_DOTS),
        RB(1.40, 0.10, 2.90, 1.55, 2.00, GREEN_W, DARK_ROOF, wall_s=GREEN_S, win=dict(win_w, glass=GREEN_GLASS), win_w=win_w,
           rim=PAL['roof_tar'][4], cpos=(0.57, 0.50), csize=0.62,
           roof_detail=units((0.08, 0.08, 0.14, 0.1), (0.8, 0.8, 0.12, 0.12), (0.1, 0.8, 0.1, 0.1))),
        Tree(2.42, 2.28, 0.08, 513),
    ]
    for (x, y) in ((2.25, 2.55), (2.45, 2.55), (2.65, 2.55)):
        items.append(cust((lambda x=x, y=y: lambda c: car(c, x, y, '#202024', True, 0.13, 0.07))(), (y - x, 0)))
    return finish(cv, items)


# ================================================================== value 2
def c522():
    """Density 0: a strip of shops with coloured awnings, a big car park with C, two kiosks east."""
    cv = ground()
    lot = np.maximum.reduce([rect(cv, 0.20, 1.05, 2.05, 2.05), rect(cv, 0.72, 2.0, 1.22, 2.30), rect(cv, 1.34, 2.0, 2.02, 2.56),
                             rect(cv, 0.08, 2.14, 1.22, 2.50), rect(cv, 2.0, 1.72, 2.25, 1.90), rect(cv, 2.0, 2.38, 2.2, 2.50)])
    asphalt(cv, lot, 0.42)
    # chevron bays as in the original
    for row in range(3):
        y = 1.22 + row * 0.30
        for k in range(6):
            x = 0.35 + k * 0.28
            if row == 2 and not (0.75 < x < 1.15 or 1.4 < x < 2.0):
                continue
            pts = [(x - 0.07, y - 0.05), (x, y + 0.03), (x + 0.07, y - 0.05)]
            cv.paint(PAL['concrete'][5], cv.cov(sd_polyline(cv.X, cv.Y, pts) - 0.008) * 0.8)
    draw_C(cv, 1.05, 1.78, 0.48)
    cv.paint(PAL['asphalt'][0], rect(cv, 0.15, 0.98, 2.68, 1.04) * 0.9)
    awn = [('#3a3ad8', 0.30, 0.82), ('#ff8a1a', 0.82, 1.08), ('#3a3ad8', 1.08, 1.42), ('#d8402e', 1.42, 1.62),
           ('#9a9aa0', 1.62, 1.82), ('#2a9a30', 1.82, 2.30), ('#9a9aa0', 2.30, 2.85)]
    items = []
    for i, (col, a, b) in enumerate(awn):
        h = 0.40 if 1.82 <= a < 2.3 else 0.30
        roof = LIGHT_ROOF if i == 5 else (GREY_ROOF if i in (4, 6) else DARK_ROOF)
        it = RB(a, 0.20 if i not in (0,) else 0.24, b, 0.82, h, LAV if i == 0 else DARK_W, roof, wall_s=hx(col),
                win={'kind': 'doors', 'n': max(1, int((b - a) / 0.16)), 'h': 0.14, 'glass': BRIGHT_GLASS}, rim=PAL['roof_tar'][4],
                roof_detail=units((0.4, 0.3, 0.2, 0.15)) if b - a > 0.3 else None)
        items.append(it)
    items += [
        RB(2.35, 1.30, 2.68, 2.00, 0.30, LAV, DARK_ROOF, wall_s=LAV_S, win=W_DOTS, rim=PAL['com'][5]),
        RB(2.30, 2.14, 2.56, 2.55, 0.28, LAV, DARK_ROOF, wall_s=LAV_S, win=W_DOTS, rim=PAL['com'][5]),
    ]
    for (x, y, col) in ((0.25, 2.24, '#f0d040'), (0.62, 2.40, '#f0d040'), (0.95, 2.10, '#e8e4dc')):
        items.append(cust((lambda x=x, y=y, col=col: lambda c: car(c, x, y, col))(), (y - x, 0)))
    for (x, y, col, v) in ((0.62, 1.30, '#c0392b', True), (1.45, 1.30, '#2c4f9e', True), (1.73, 1.58, '#e8e4dc', True)):
        items.append(cust((lambda x=x, y=y, col=col, v=v: lambda c: car(c, x, y, col, v))(), (y - x, 0)))
    items.append(cust(lambda c: shrubs(c, [(0.2, 2.65), (0.5, 2.7), (1.25, 2.75), (2.75, 2.65), (2.5, 2.8), (2.05, 2.75), (0.18, 1.5)], 0.035, 22), (-9, 0)))
    return finish(cv, items)


def c531():
    """Density 1: L-shaped lavender offices with C, a dome, a road, orange kiosk, round pavilion."""
    cv = ground('lawn')
    rd = np.maximum(rect(cv, 0.08, 1.34, 1.95, 1.74), rect(cv, 1.28, 1.34, 1.80, 2.92))
    asphalt(cv, rd, 0.6)
    kerb(cv, rd)
    def dome(c):
        cx, cy, r = 0.62, 0.66, 0.36
        c.shade(c.cov(sd_circle(c.X, c.Y, cx + 0.22, cy + 0.10, r * 0.95), 8), 0.55)
        d = np.hypot(c.X - cx, c.Y - cy) / r
        m = c.cov(sd_circle(c.X, c.Y, cx, cy, r))
        nz = np.sqrt(np.clip(1 - d * d, 0, 1))
        nx, ny = (c.X - cx) / r, (c.Y - cy) / r
        lam = np.clip(-0.55 * nx - 0.55 * ny + 0.65 * nz, 0, 1)
        col = PAL['concrete'](0.15 + 0.85 * lam)
        c.paint(col, m)
        rib = (np.abs(((np.arctan2(ny, nx) / (2 * math.pi) * 16) % 1) - 0.5) > 0.44).astype(float)
        c.shade(rib * m * (d > 0.15), 0.15)
        c.paint(PAL['concrete'][7], c.cov(sd_circle(c.X, c.Y, cx - 0.04, cy - 0.04, 0.05)))
    items = [
        Custom(dome, key=(0.04, 0), shadow=None),
        RB(1.00, 0.28, 2.85, 1.02, 0.40, LAV, DARK_ROOF, wall_s=LAV_S, win=W_DOTS, rim=PAL['roof_tar'][4],
           roof_detail=units((0.17, 0.25, 0.03, 0.4), (0.20, 0.25, 0.03, 0.4), (0.27, 0.25, 0.03, 0.4), (0.68, 0.3, 0.03, 0.3), col=PAL['concrete'][6])),
        RB(2.10, 1.02, 2.85, 2.58, 0.40, LAV, DARK_ROOF, wall_s=LAV_S, win=W_DOTS, rim=PAL['roof_tar'][4], cpos=(0.30, 0.17),
           roof_detail=rooflights(4, 1, PAL['roof_tar'][0], 0.04, 0.5, 0.25)),
        RB(1.48, 1.52, 1.92, 1.88, 0.10, hx('#e07a1a'), hx('#ff8a1a'), wall_s=hx('#e07a1a'), rim=PAL['roof_tar'][0]),
        Cylinder(0.80, 2.28, 0.16, 0.22, LAV, top=PAL['com'][2]),
        Tree(0.38, 2.02, 0.12, 531), Tree(0.62, 1.95, 0.10, 532), Tree(0.55, 2.68, 0.11, 533), Tree(0.98, 2.62, 0.12, 534),
        Tree(0.25, 1.15, 0.08, 535), Tree(2.72, 2.75, 0.07, 536),
    ]
    return finish(cv, items)


def c540():
    """Density 2: twin lavender slabs, C on the west one, on a low lavender plinth."""
    cv = ground('paving')
    paving(cv, rect(cv, 0.11, 0.11, 0.20, 2.86), 0.80, 8)
    asphalt(cv, rect(cv, 0.11, 2.76, 2.89, 2.88), 0.45)
    lawn(cv, rect(cv, 0.24, 0.22, 0.62, 0.62, 0.05))
    win = {'kind': 'grid', 'floor': 0.11, 'col': 0.11, 'wfrac': 0.42, 'hfrac': 0.45, 'glass': DARK_GLASS}
    def planter(c, rx0, ry0, rx1, ry1):
        c.paint(PAL['concrete'][6], rect(c, 1.18, ry0 + 0.04, 1.48, ry1 - 0.03, 0.02))
        c.img = c.img * (1 - rect(c, 1.21, ry0 + 0.06, 1.45, ry1 - 0.05, 0.02)[..., None]) + grass_layer(3, 3, c.n) * rect(c, 1.21, ry0 + 0.06, 1.45, ry1 - 0.05, 0.02)[..., None]
        rng = np.random.default_rng(540)
        for _ in range(25):
            x, y = rng.uniform(1.23, 1.43), rng.uniform(ry0 + 0.07, ry1 - 0.06)
            c.paint(hx('#e8302a'), c.cov(sd_circle(c.X, c.Y, x, y, 0.009), 1.5))
    items = [
        RB(0.95, 0.16, 1.60, 1.80, 1.40, LAV, DARK_ROOF, wall_s=LAV_S, win=win, rim=PAL['com'][2], cpos=(0.42, 0.30),
           roof_detail=units((0.2, 0.75, 0.25, 0.1), (0.6, 0.55, 0.15, 0.08))),
        RB(2.10, 0.16, 2.86, 1.80, 1.00, LAV, DARK_ROOF, wall_s=LAV_S, win=win, rim=PAL['com'][2],
           roof_detail=units((0.2, 0.2, 0.2, 0.1), (0.5, 0.7, 0.25, 0.12))),
        Box2(0.30, 2.40, 2.55, 2.74, 0.10, LAV, PAL['com'][6], wall_s=LAV_S, rim=PAL['concrete'][7], extra=planter),
    ]
    return finish(cv, items)


def c549():
    """Density 3: white tower with C on a podium with three white entrance pyramids."""
    cv = ground('light')
    lawn(cv, np.maximum(rect(cv, 0.10, 0.10, 0.18, 2.90), rect(cv, 0.20, 0.16, 1.30, 0.62, 0.05)))
    lawn(cv, rect(cv, 0.20, 2.82, 2.90, 2.90))
    lawn(cv, rect(cv, 2.82, 1.30, 2.90, 2.80))
    paving(cv, rect(cv, 0.22, 0.24, 1.0, 0.32), 0.8)
    def stripes(c, rx0, ry0, rx1, ry1):
        m = rect(c, rx0 + 0.04, ry0 + 0.04, min(rx1, 0.95), ry1 - 0.04)
        s = (np.abs(((c.X / 0.09) % 1) - 0.5) > 0.3).astype(float)
        c.paint(PAL['concrete'][7], s * m * 0.8)
    pod_win = {'kind': 'grid', 'floor': 0.10, 'col': 0.09, 'wfrac': 0.5, 'hfrac': 0.45, 'glass': DARK_GLASS}
    tw = {'kind': 'grid', 'floor': 0.11, 'col': 0.10, 'wfrac': 0.38, 'hfrac': 0.40, 'glass': Ramp(['#5a5e68', '#7a7e88', '#9a9ea8'])}
    items = [
        Box2(0.30, 0.72, 2.70, 2.76, 0.25, PAL['concrete'][5], LIGHT_ROOF, wall_s=PAL['concrete'][2], win=pod_win, win_w=pod_win,
             rim=PAL['concrete'][7], extra=stripes),
        RB(1.75, 0.10, 2.86, 1.30, 1.35, WHITE_W, DARK_ROOF, z0=0.25, wall_s=PAL['concrete'][5], win=tw, win_w=tw,
           rim=PAL['concrete'][6], cpos=(0.45, 0.42), roof_detail=units((0.1, 0.1, 0.12, 0.1), (0.75, 0.8, 0.12, 0.1))),
    ]
    items[1].key = lambda: (10, 0)
    for k, x in enumerate((1.20, 1.58, 1.96)):
        hp = Hip(x - 0.14, 2.28, x + 0.14, 2.56, 0.0, 0.42, WHITE_W, Ramp(['#55555c', '#8c8c94', '#d0d0d4', '#ffffff']))
        hp.h = 0.0
        hp.z0 = 0.25
        items.append(Custom((lambda hp=hp: lambda c: _hip_at(c, hp, 0.25))(), key=(5 + k, 0)))
    return finish(cv, items)


def _hip_at(cv, hp, z0):
    """Draw a pyramid standing at height z0 (on a podium roof)."""
    s = z0 / 2
    q = Hip(hp.x0 + s, hp.y0 - s, hp.x1 + s, hp.y1 - s, 0.001, hp.rh, hp.wall, hp.ramp, courses=10)
    sh = cv.poly([(q.x0, q.y0), (q.x1 + 0.2, q.y0 + 0.08), (q.x1 + 0.2, q.y1 + 0.08), (q.x0, q.y1)])
    cv.shade(cv.blur(sh, 0.01), 0.3)
    q.draw(cv)


def c558():
    """Density 4: the dark glass tower with a light roof and C, a car park north-west."""
    cv = ground('light')
    lot = np.maximum(rect(cv, 0.12, 0.12, 0.92, 1.05, 0.04), rect(cv, 0.50, 0.08, 0.85, 0.3))
    asphalt(cv, lot, 0.62)
    kerb(cv, lot)
    win = {'kind': 'grid', 'floor': 0.085, 'col': 0.085, 'wfrac': 0.55, 'hfrac': 0.55, 'glass': Ramp(['#1a1c22', '#2a2d36', '#3c404c', '#55596a'])}
    items = [
        RB(1.45, 0.10, 2.90, 1.65, 2.30, PAL['concrete'][2], LIGHT_ROOF, wall_s=PAL['concrete'][2], win=win, win_w=win,
           rim=PAL['roof_tar'][1], cpos=(0.52, 0.42), csize=0.62,
           roof_detail=units((0.08, 0.08, 0.16, 0.10), (0.75, 0.82, 0.16, 0.12), (0.08, 0.82, 0.10, 0.10))),
    ]
    for (x, y, col, v) in ((0.27, 0.42, '#ff8a1a', True), (0.44, 0.42, '#2a9a30', True), (0.78, 0.40, '#1a6a22', True),
                           (0.52, 0.74, '#f0d040', True), (0.22, 0.98, '#2c4f9e', False)):
        items.append(cust((lambda x=x, y=y, col=col, v=v: lambda c: car(c, x, y, col, v))(), (y - x, 0)))
    def lamps(c):
        for (x, y) in ((0.32, 2.85), (0.95, 2.85), (2.65, 2.85), (2.78, 2.85)):
            lamp(c, x, y)
    items.append(cust(lamps, (20, 0)))
    return finish(cv, items)


# ================================================================== value 3
def c567():
    """Density 0: shopping parade north, huge car park with C, small pavilion south."""
    cv = ground()
    lawn(cv, rect(cv, 0.12, 0.52, 0.96, 1.06, 0.03))
    lot = np.maximum.reduce([cv.poly([(0.10, 1.06), (0.96, 1.06), (0.96, 0.76), (2.84, 0.76), (2.84, 1.94), (2.90, 2.02), (2.90, 2.30), (0.10, 2.20)])])
    asphalt(cv, lot, 0.40)
    kerb(cv, lot)
    cv.paint(PAL['dirt'][5], rect(cv, 0.96, 1.80, 2.80, 1.86) * 0.9)
    stall_lines(cv, 1.0, 2.7, 0.80, 1.00, 0.18)
    stall_lines(cv, 0.2, 2.7, 1.60, 1.78, 0.18)
    draw_C(cv, 1.55, 1.27, 0.50)
    items = [
        RB(1.35, 0.22, 2.70, 0.62, 0.22, LAV, GREY_ROOF, wall_s=LAV_S, win={'kind': 'doors', 'n': 7, 'h': 0.14, 'glass': BRIGHT_GLASS},
           win_w=W_DOTS, rim=PAL['com'][5], roof_detail=units((0.1, 0.25, 0.08, 0.3), (0.5, 0.3, 0.1, 0.3), (0.85, 0.25, 0.08, 0.3))),
        Box2(0.22, 0.60, 0.86, 0.98, 0.12, PAL['concrete'][4], GREY_ROOF, wall_s=PAL['concrete'][4], win=W_SHOP, rim=PAL['concrete'][6]),
        RB(1.52, 2.30, 2.30, 2.60, 0.12, PAL['concrete'][5], GREY_ROOF, wall_s=PAL['concrete'][5], win=W_SHOP, rim=PAL['concrete'][8]),
    ]
    for (x, y, col, v) in ((1.18, 0.88, '#c0392b', False), (1.08, 1.50, '#c0392b', True), (0.92, 1.50, '#2c4f9e', True),
                           (2.72, 0.88, '#46c04c', False), (2.65, 1.20, '#1a6a22', False), (2.72, 1.38, '#2c4f9e', False),
                           (2.40, 1.62, '#1a6a22', True), (0.45, 1.95, '#e8e4dc', False)):
        items.append(cust((lambda x=x, y=y, col=col, v=v: lambda c: car(c, x, y, col, v))(), (y - x, 0)))
    def lamps(c):
        for (x, y) in ((0.15, 0.15), (1.02, 0.42), (2.74, 0.24), (0.15, 2.45), (0.26, 2.75), (2.75, 2.82)):
            lamp(c, x, y)
    items.append(cust(lamps, (20, 0)))
    return finish(cv, items)


def c576():
    """Density 1: grand building with a raised centre (C), striped canopy, steps, fountain plaza."""
    cv = ground()
    lawn(cv, rect(cv, 0.42, 0.10, 0.80, 1.80, 0.04))
    lawn(cv, rect(cv, 0.70, 1.20, 2.86, 1.78, 0.04))
    lawn(cv, np.maximum(rect(cv, 0.12, 2.0, 0.78, 2.86, 0.06), rect(cv, 2.38, 2.0, 2.88, 2.86, 0.06)))
    steps = rect(cv, 0.98, 1.72, 2.18, 2.16)
    paving(cv, steps, 0.42, 4)
    for k in range(5):
        y = 1.76 + k * 0.08
        cv.light(rect(cv, 0.98, y, 2.18, y + 0.012) * steps, 0.3)
    plaza = rect(cv, 0.80, 2.10, 2.36, 2.92)
    paving(cv, plaza, 0.72, 6)
    kerb(cv, plaza)
    def fountain(c):
        fx, fy = 1.52, 2.46
        c.paint(PAL['steel'][0], c.cov(sd_circle(c.X, c.Y, fx, fy, 0.20)))
        c.paint(PAL['concrete'][6], c.cov(sd_circle(c.X, c.Y, fx, fy, 0.18)))
        c.paint(PAL['water'](0.45 + 0.25 * np.clip((c.Y - fy + 0.15) / 0.3, 0, 1)), c.cov(sd_circle(c.X, c.Y, fx, fy, 0.15)))
        rip = np.sin(np.hypot(c.X - fx, c.Y - fy) * 90)
        c.light(np.clip(rip, 0, 1) * c.cov(sd_circle(c.X, c.Y, fx, fy, 0.14)), 0.12)
        c.paint(PAL['water'][9], c.cov(sd_circle(c.X, c.Y, fx, fy, 0.05), 2))
        c.paint(PAL['water'][8], c.cov(np.abs(np.hypot(c.X - fx, c.Y - fy) - 0.085) - 0.01, 2) * 0.7)
        for x in (0.92, 2.08):
            bollard(c, x, 2.62, '#1c1c20', 0.12, 0.02)
    def canopy_roof(c, rx0, ry0, rx1, ry1):
        s = (np.abs((((c.X - c.Y) / 0.10) % 1) - 0.5) > 0.25)
        col = np.where(s[..., None], hx('#f0c020'), hx('#202020'))
        return col
    win = {'kind': 'grid', 'floor': 0.12, 'col': 0.10, 'wfrac': 0.5, 'hfrac': 0.5, 'glass': DARK_GLASS}
    items = [
        RB(0.92, 0.10, 2.85, 1.25, 0.50, PAL['concrete'][4], GREY_ROOF, wall_s=PAL['concrete'][3], win=win, rim=PAL['concrete'][6],
           roof_detail=units((0.03, 0.15, 0.1, 0.1), (0.85, 0.15, 0.1, 0.1), (0.85, 0.75, 0.1, 0.1))),
        RB(1.30, 0.18, 2.00, 1.20, 0.30, PAL['concrete'][6], LIGHT_ROOF, z0=0.50, wall_s=PAL['concrete'][5], win=win, rim=PAL['concrete'][7],
           cpos=(0.50, 0.42), csize=0.55),
        RB(1.25, 1.24, 2.06, 1.62, 0.04, WHITE_W, canopy_roof, z0=0.30, wall_s=WHITE_W, parapet=False),
        Cylinder(1.08 - 0.0, 1.70, 0.02, 0.30, WHITE_W), Cylinder(1.86, 1.70, 0.02, 0.30, WHITE_W),
        cust(fountain, (-3, 0)),
    ]
    for k in range(6):
        items.append(Tree(0.60, 0.25 + k * 0.27, 0.10, 576 + k))
    items.append(cust(lambda c: shrubs(c, [(0.3, 2.3), (0.45, 2.55), (0.25, 2.7), (2.6, 2.3), (2.72, 2.55), (2.55, 2.7), (2.75, 1.95), (0.22, 0.4), (0.25, 1.5)], 0.04, 576), (-9, 0)))
    return finish(cv, items)


def c585():
    """Density 2: column-striped office with C, low blocks east around a car court."""
    cv = ground('lawn')
    court = np.maximum(rect(cv, 1.62, 1.12, 2.82, 2.00, 0.03), rect(cv, 2.3, 1.46, 2.92, 1.84))
    paving(cv, court, 0.72, 8)
    kerb(cv, court)
    asphalt(cv, rect(cv, 1.64, 1.14, 1.92, 1.98), 0.6)
    for k in range(5):
        x = 2.02 + k * 0.17
        cv.paint(PAL['concrete'][8], rect(cv, x, 1.38, x + 0.06, 1.41) * 0.9)
    paving(cv, rect(cv, 1.72, 2.6, 1.98, 2.92), 0.5)
    paving(cv, rect(cv, 0.12, 0.2, 0.22, 2.86), 0.8)
    cols = {'kind': 'grid', 'floor': 0.06, 'col': 0.075, 'wfrac': 0.38, 'hfrac': 0.92, 'glass': DARK_GLASS}
    bands = {'kind': 'grid', 'floor': 0.13, 'col': 0.12, 'wfrac': 0.8, 'hfrac': 0.4, 'glass': DARK_GLASS}
    win = {'kind': 'grid', 'floor': 0.12, 'col': 0.10, 'wfrac': 0.55, 'hfrac': 0.45, 'glass': DARK_GLASS}
    items = [
        RB(0.80, 0.28, 1.65, 2.25, 1.20, PAL['concrete'][6], DARK_ROOF, wall_s=PAL['concrete'][4], win=bands, win_w=cols,
           rim=PAL['concrete'][6], cpos=(0.42, 0.53), roof_detail=units((0.6, 0.06, 0.16, 0.08), (0.12, 0.88, 0.16, 0.06))),
        RB(1.78, 0.32, 2.72, 0.78, 0.45, PAL['concrete'][4], DARK_ROOF, wall_s=PAL['concrete'][4], win=win, rim=PAL['roof_tar'][0]),
        RB(1.55, 2.08, 2.55, 2.45, 0.45, PAL['concrete'][4], DARK_ROOF, wall_s=PAL['concrete'][4], win=win, rim=PAL['roof_tar'][0]),
        Tree(2.7, 2.45, 0.1, 585), Tree(2.75, 1.0, 0.08, 586), Tree(2.6, 2.75, 0.08, 587),
    ]
    for (x, y, col, v) in ((2.48, 1.26, '#c0392b', True), (1.78, 1.28, '#2c4f9e', True), (1.80, 1.82, '#c0392b', True), (2.05, 1.84, '#b09068', True),
                           (2.25, 1.26, '#e8e4dc', True), (2.62, 1.66, '#e8e4dc', False)):
        items.append(cust((lambda x=x, y=y, col=col, v=v: lambda c: car(c, x, y, col, v))(), (y - x, 0)))
    return finish(cv, items)


def c594():
    """Density 3: banded tower with C, a podium wing south-west, a slab north-west."""
    cv = ground('lawn')
    fore = rect(cv, 0.20, 1.86, 0.62, 2.80, 0.04)
    paving(cv, fore, 0.78)
    paving(cv, rect(cv, 0.08, 1.28, 0.62, 1.86), 0.55)
    bands = {'kind': 'bands', 'floor': 0.11, 'col': 0.06}
    win = {'kind': 'grid', 'floor': 0.10, 'col': 0.09, 'wfrac': 0.5, 'hfrac': 0.5, 'glass': DARK_GLASS}
    def edge_lights(c, rx0, ry0, rx1, ry1):
        for k in range(6):
            x = rx0 + 0.1 + k * (rx1 - rx0 - 0.2) / 5
            c.paint(PAL['roof_tar'][0], rect(c, x - 0.02, ry0 + 0.05, x + 0.02, ry0 + 0.09))
        for k in range(6):
            y = ry0 + 0.15 + k * (ry1 - ry0 - 0.3) / 5
            c.paint(PAL['roof_tar'][0], rect(c, rx1 - 0.09, y - 0.02, rx1 - 0.05, y + 0.02))
    items = [
        RB(0.38, 0.36, 1.36, 0.66, 0.30, PAL['concrete'][6], DARK_ROOF, wall_s=PAL['concrete'][4], win=win),
        RB(1.75, 0.22, 2.78, 1.55, 2.30, PAL['concrete'][5], DARK_ROOF, wall_s=PAL['concrete'][4], win=bands, glass=Ramp(['#3a3e48', '#5a5e6a', '#7a7e8a', '#a0a4ae']),
           rim=PAL['concrete'][6], cpos=(0.48, 0.40), extra=edge_lights),
        RB(0.56, 1.88, 1.26, 2.24, 0.60, PAL['concrete'][6], DARK_ROOF, wall_s=PAL['concrete'][3], win=win, rim=PAL['concrete'][5],
           roof_detail=rooflights(2, 5, PAL['roof_tar'][0], 0.035)),
    ]
    return finish(cv, items)


def c603():
    """Density 4: the round tower with C, an office block behind, a low wing south-east."""
    cv = ground('lawn')
    paving(cv, rect(cv, 0.16, 0.16, 2.84, 2.84, 0.1), 0.66, 6)
    win = {'kind': 'grid', 'floor': 0.10, 'col': 0.09, 'wfrac': 0.5, 'hfrac': 0.5, 'glass': DARK_GLASS}
    cx, cy, r, h = 0.96, 2.10, 0.66, 2.48
    bands = [(0.10 + 0.12 * k, 0.045, hx('#8a8e9c')) for k in range(20)]
    tower = Cylinder(cx, cy, r, h, hx('#e4e4e6'), top=PAL['roof_tar'][2], bands=bands)
    def crown(c):
        tx, ty = P(cx, cy, h)
        c.paint(hx('#f4f4f4'), c.cov(np.abs(np.hypot(c.X - tx, c.Y - ty) - r + 0.025) - 0.018))
        draw_C(c, tx - 0.04, ty - 0.08, 0.62)
    items = [
        RB(0.50, 0.20, 1.30, 1.15, 0.50, PAL['concrete'][5], DARK_ROOF, wall_s=PAL['concrete'][3], win=win, win_w=win, rim=PAL['concrete'][6]),
        RB(2.05, 1.84, 2.72, 2.46, 0.30, PAL['concrete'][3], GREY_ROOF, wall_s=PAL['roof_tar'][1], win=win, rim=PAL['roof_tar'][0],
           roof_detail=rooflights(3, 4, PAL['roof_tar'][1], 0.04)),
        tower,
        Custom(crown, key=(99, 0)),
    ]
    def lights(c):
        for x in (1.90, 2.06, 2.22):
            c.paint(PAL['com'][4], c.cov(sd_circle(c.X, c.Y, x, 2.66, 0.022)))
            c.light(c.cov(sd_circle(c.X, c.Y, x, 2.66, 0.05), 5), 0.25, PAL['com'][6])
    items.append(cust(lights, (20, 0)))
    return finish(cv, items)


BLOCKS = {432: c432, 441: c441, 450: c450, 459: c459, 468: c468,
          477: c477, 486: c486, 495: c495, 504: c504, 513: c513,
          522: c522, 531: c531, 540: c540, 549: c549, 558: c558,
          567: c567, 576: c576, 585: c585, 594: c594, 603: c603}
for _b, _f in BLOCKS.items():
    GROUPS.append((_b, 3, 3, _f))
