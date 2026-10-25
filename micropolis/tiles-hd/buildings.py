"""Signature buildings, composed as one picture per zone and cut into cells.

Each entry in GROUPS is (first_tile, w, h, fn); fn returns a Canvas (cut row-major into
w*h consecutive tiles) or a dict {tile: image} for animated pieces.
"""
import math
import numpy as np
from hdlib import *
from terrain import dirt_layer, grass_layer, draw_crown
from scene3d import Box, Gable, Cylinder, Tree, Custom, render, P
import transport as TR

GROUPS = []


# ------------------------------------------------------------------ zone kit
def zone_frame(cv, kind, inset=0.03, width=0.05):
    X, Y = cv.X, cv.Y
    d = -sd_box(X, Y, 0, 0, cv.wt, cv.ht)          # distance inward from the zone edge
    ramp = PAL[kind] if isinstance(kind, str) else kind
    cv.shade(cv.cov(np.abs(d - inset - width - 0.01) - 0.012, 3), 0.30)
    cv.paint(ramp[0] * 0.55, cv.cov(np.abs(d - inset + 0.006) - 0.008))
    cv.paint(ramp[4], cv.cov(np.abs(d - inset - width / 2) - width / 2))
    cv.paint(ramp[6], cv.cov(np.abs(d - inset - 0.012) - 0.006) * 0.7)


def paving(cv, mask, tone=0.55, joints=8):
    n = pnoise(cv.n, 32, 801, cv.wt, cv.ht)
    col = PAL['concrete'](tone + 0.06 * (n - 0.5) * 2)
    cv.paint(col, mask)
    j = ((np.abs(((cv.X * joints) % 1) - 0.5) > 0.47) | (np.abs(((cv.Y * joints) % 1) - 0.5) > 0.47)).astype(float)
    cv.shade(j * mask, 0.18)


def lawn(cv, mask):
    g = grass_layer(cv.wt, cv.ht, cv.n)
    m = np.clip(mask, 0, 1)[..., None]
    cv.img = cv.img * (1 - m) + g * m
    # soft darker border where the lawn meets other ground
    edge = np.clip(mask - cv.blur(mask, 0.01), 0, 1)
    cv.shade(edge * 3, 0.25)


def rect(cv, x0, y0, x1, y1, r=0.0):
    return cv.cov(sd_box(cv.X, cv.Y, x0, y0, x1, y1, r))


def letter_col(kind):
    return {'res': PAL['res'][4], 'com': PAL['com'][5], 'ind': PAL['ind'][5], 'fd': hx('#ffd21a'), 'pd': hx('#ffd21a')}[kind]


def vehicle(cv, x, y, L, W, col, horizontal=True, roofcol=None, stripe=None):
    tx, ty = (1, 0) if horizontal else (0, -1)
    TR.draw_car(cv, x, y, tx, ty, col, L=L, W=W)
    if stripe is not None:
        nx, ny = -ty, tx
        pts = [(x + tx * L * 0.45 + nx * W * 0.08, y + ty * L * 0.45 + ny * W * 0.08),
               (x - tx * L * 0.45 + nx * W * 0.08, y - ty * L * 0.45 + ny * W * 0.08),
               (x - tx * L * 0.45 - nx * W * 0.08, y - ty * L * 0.45 - ny * W * 0.08),
               (x + tx * L * 0.45 - nx * W * 0.08, y + ty * L * 0.45 - ny * W * 0.08)]
        cv.paint(hx(stripe), cv.poly(pts) * 0.9)


def roof_units(units, col=None):
    """Roof detail: small AC boxes / vents at roof-relative fractions."""
    def fn(cv, rx0, ry0, rx1, ry1):
        for (fx, fy, w, h) in units:
            x, y = rx0 + fx * (rx1 - rx0), ry0 + fy * (ry1 - ry0)
            cv.shade(rect(cv, x + 0.01, y + 0.008, x + w + 0.016, y + h + 0.012, 0.004), 0.45)
            c = np.asarray(col if col is not None else PAL['concrete'][5])
            cv.paint(c, rect(cv, x, y, x + w, y + h, 0.003))
            cv.light(rect(cv, x, y, x + w, y + 0.006), 0.35)
            cv.shade(rect(cv, x, y + h - 0.006, x + w, y + h), 0.3)
    return fn


def roof_skylights(n=4, col=None):
    def fn(cv, rx0, ry0, rx1, ry1):
        w = (rx1 - rx0)
        hgt = ry1 - ry0
        npanes = max(1, int(hgt / 0.22))
        for k in range(n):
            x = rx0 + w * (0.12 + 0.76 * k / max(n - 1, 1))
            for j in range(npanes):
                y0 = ry0 + 0.08 + j * (hgt - 0.16) / npanes
                y1 = y0 + (hgt - 0.16) / npanes - 0.05
                cv.shade(rect(cv, x - 0.03, y0 + 0.012, x + 0.05, y1 + 0.012, 0.004), 0.35)
                cv.paint(PAL['glass'](0.45 + 0.25 * np.clip((cv.Y - y0) / max(y1 - y0, 1e-3), 0, 1)), rect(cv, x - 0.035, y0, x + 0.035, y1, 0.004))
                cv.paint(PAL['concrete'][6], cv.cov(np.abs(sd_box(cv.X, cv.Y, x - 0.035, y0, x + 0.035, y1, 0.004)) - 0.004, 1.0) * 0.8)
    return fn


def smoke_puffs(cv, sources, frame, n_puff=5, rise=0.55, col=(0.86, 0.86, 0.84), dark=0.55, clip=None, spread=0.10, drift=(0.0, -1.0)):
    """Plumes rising from (x, y) points; loops over 4 frames."""
    a_tot = np.zeros_like(cv.X)
    col_acc = np.zeros(cv.img.shape)
    for si, (sx, sy) in enumerate(sources):
        for k in range(n_puff):
            t = (k + frame / 4.0 + (si * 0.37) % 1) / n_puff
            t = t % 1.0
            px = sx + drift[0] * rise * t + 0.03 * math.sin(6.0 * t + si)
            py = sy + drift[1] * rise * t
            r = 0.075 + spread * t
            alpha = (1 - t * t) * 0.92
            d = np.hypot(cv.X - px, cv.Y - py)
            m = np.clip(1.25 - 1.25 * d / r, 0, 1) ** 0.7 * alpha
            # lit from the upper left
            lam = np.clip(0.5 + ((px - cv.X) * 0.7 + (py - cv.Y) * 0.7) / r, 0, 1)
            c = np.asarray(col)[None, None, :] * (dark + (1 - dark) * lam)[..., None]
            col_acc = col_acc * (1 - m[..., None]) + c * m[..., None]
            a_tot = a_tot * (1 - m) + m
    col = col_acc / np.maximum(a_tot, 1e-6)[..., None]
    a = np.clip(a_tot if clip is None else a_tot * clip, 0, 1)
    cv.img = cv.img * (1 - a[..., None]) + np.clip(col, 0, 1) * a[..., None]


def cell_clip(cv, cells, margin=0.05):
    """Mask that is 1 inside the union of given cells, fading to 0 at their outer border."""
    m = np.zeros_like(cv.X)
    for (i, j) in cells:
        m = np.maximum(m, ((cv.X >= i) & (cv.X < i + 1) & (cv.Y >= j) & (cv.Y < j + 1)).astype(float))
    d = ndimage.distance_transform_edt(m) / cv.n
    return np.clip(d / margin, 0, 1)


# ------------------------------------------------------------------ residential, low density
def res_low():
    cv = Canvas(3, 3, RS, dirt_layer(3, 3))
    X, Y = cv.X, cv.Y
    lawn(cv, rect(cv, 0.12, 0.12, 2.88, 2.88, 0.08) * (1 - rect(cv, 1.30, 0.70, 1.70, 3.2)))
    paving(cv, rect(cv, 1.32, 0.75, 1.68, 3.05), 0.55)               # drive / footpath
    paving(cv, rect(cv, 0.95, 1.7, 1.68, 2.2), 0.58)                  # parking
    # flower beds
    rng = np.random.default_rng(3)
    for _ in range(70):
        x, y = rng.uniform(0.25, 1.2), rng.uniform(1.95, 2.15)
        cv.paint([hx('#f5d33f'), hx('#ef6f7a'), hx('#f4f1e6')][rng.integers(3)], cv.cov(sd_circle(X, Y, x, y, 0.009), 1.5))
    zone_frame(cv, 'res')
    blue = hx('#7486d8')
    green = hx('#59b85a')
    items = [
        Box(0.25, 0.42, 1.15, 1.62, 0.42, blue, PAL['roof_slate'][3], win={'kind': 'grid', 'floor': 0.14, 'col': 0.12, 'wfrac': 0.5, 'hfrac': 0.5},
            label='R', label_col=letter_col('res'), label_size=0.55, rim=PAL['roof_slate'][5]),
        Gable(1.95, 0.25, 2.65, 1.80, 0.34, 0.22, green, 'roof_red', ridge='y', win={'kind': 'grid', 'floor': 0.15, 'col': 0.13, 'wfrac': 0.45, 'hfrac': 0.45}),
        Gable(0.40, 2.35, 0.95, 2.80, 0.22, 0.14, hx('#e8dcc0'), 'roof_red', ridge='x', win={'kind': 'grid', 'floor': 0.12, 'col': 0.11, 'wfrac': 0.45, 'hfrac': 0.45}),
        Tree(0.32, 2.05, 0.14, 11), Tree(1.12, 2.62, 0.16, 12), Tree(2.45, 2.42, 0.18, 13), Tree(2.05, 2.75, 0.12, 14),
        Tree(2.82, 1.95, 0.11, 15, 0.04), Tree(1.05, 0.32, 0.10, 16),
        Custom(lambda c: vehicle(c, 1.18, 1.95, 0.15, 0.08, '#c0392b'), key=(1.95 - 1.18, 0)),
        Custom(lambda c: vehicle(c, 1.50, 2.6, 0.15, 0.08, '#2c4f9e', horizontal=False), key=(2.6 - 1.5, 0)),
    ]
    render(cv, items)
    return cv


# ------------------------------------------------------------------ residential, high density
def res_high():
    cv = Canvas(3, 3, RS, dirt_layer(3, 3))
    paving(cv, rect(cv, 0.08, 0.08, 2.92, 2.92), 0.62, 6)
    lawn(cv, rect(cv, 0.15, 0.15, 1.35, 0.85, 0.05))
    lawn(cv, rect(cv, 2.2, 2.0, 2.85, 2.85, 0.05))
    zone_frame(cv, 'res')
    conc = hx('#d4d0c8')
    conc2 = hx('#b9c0cc')
    win = {'kind': 'grid', 'floor': 0.115, 'col': 0.10, 'wfrac': 0.55, 'hfrac': 0.5, 'warm': True}
    def helipad(c, rx0, ry0, rx1, ry1):
        cx, cy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
        c.paint(PAL['concrete'][2], c.cov(sd_circle(c.X, c.Y, cx, cy, 0.20)))
        c.paint(PAL['concrete'][8], c.cov(np.abs(np.hypot(c.X - cx, c.Y - cy) - 0.17) - 0.01))
        m = c.text_mask('H', cx, cy, 0.24, FONT_SANS)
        c.paint(PAL['concrete'][8], m)
    items = [
        Box(0.22, 0.95, 1.25, 2.80, 1.05, conc, PAL['roof_tar'][4], win=win, roof_detail=roof_units([(0.15, 0.1, 0.12, 0.07), (0.6, 0.75, 0.15, 0.08), (0.2, 0.55, 0.08, 0.08)])),
        Box(1.45, 1.55, 2.75, 2.80, 0.55, conc2, PAL['roof_tar'][5], win=win, label='R', label_col=letter_col('res'), label_size=0.5),
        Box(1.55, 0.40, 2.55, 1.25, 0.35, conc, PAL['roof_tar'][4], win=win, roof_detail=helipad),
        Tree(0.35, 0.45, 0.11, 21), Tree(0.75, 0.30, 0.12, 22), Tree(2.65, 2.15, 0.1, 23),
    ]
    render(cv, items)
    return cv


# ------------------------------------------------------------------ commercial office tower
def com_tower():
    cv = Canvas(3, 3, RS, dirt_layer(3, 3))
    paving(cv, rect(cv, 0.08, 0.08, 2.92, 2.92), 0.58, 8)
    # granite plaza band and planters
    paving(cv, rect(cv, 0.15, 2.35, 2.85, 2.85), 0.42, 4)
    zone_frame(cv, 'com')
    glass = Ramp(['#0d1838', '#142454', '#1d3472', '#284896', '#3a62b4', '#5582cc', '#77a2de', '#a6c6ee', '#dbe9fa'])
    def roofc(c, rx0, ry0, rx1, ry1):
        units = roof_units([(0.08, 0.1, 0.18, 0.12), (0.72, 0.72, 0.18, 0.14), (0.12, 0.74, 0.1, 0.1)], PAL['concrete'][6])
        units(c, rx0, ry0, rx1, ry1)
    items = [
        Box(0.20, 1.30, 0.85, 2.30, 0.22, hx('#9aa0b8'), PAL['roof_tar'][5], win={'kind': 'bands', 'floor': 0.09, 'col': 0.05}),
        Box(0.95, 0.55, 2.45, 2.15, 0.92, hx('#3a4a8a'), PAL['roof_slate'][2], win={'kind': 'curtain', 'col': 0.075, 'floor': 0.075, 'frame': (0.70, 0.74, 0.86)},
            glass=glass, label='C', label_col=letter_col('com'), label_size=0.62, roof_detail=roofc, rim=PAL['concrete'][6]),
        Tree(0.35, 2.55, 0.10, 31), Tree(0.85, 2.62, 0.10, 32), Tree(1.35, 2.55, 0.10, 33), Tree(1.85, 2.62, 0.10, 34), Tree(2.35, 2.55, 0.10, 35), Tree(2.7, 1.2, 0.12, 36),
    ]
    def fountain(c):
        c.paint(PAL['concrete'][6], c.cov(sd_circle(c.X, c.Y, 2.7, 0.55, 0.16)))
        c.paint(PAL['water'][6], c.cov(sd_circle(c.X, c.Y, 2.7, 0.55, 0.13)))
        c.paint(PAL['water'][9], c.cov(sd_circle(c.X, c.Y, 2.7, 0.55, 0.035), 2) * 0.9)
    items.append(Custom(fountain, key=(-5, 0)))
    render(cv, items)
    return cv


# ------------------------------------------------------------------ industrial with stacks (+ smoke frames)
IND3_BASE = 648      # block k=3; its top-middle cell (649) animates as 896..899
IND3_SMOKE = 896


def ind_stacks(frame=None):
    cv = Canvas(3, 3, RS, dirt_layer(3, 3))
    paving(cv, rect(cv, 0.08, 0.08, 2.92, 2.92), 0.48, 4)
    cv.paint(PAL['dirt'][4], rect(cv, 2.2, 0.15, 2.85, 1.65, 0.05) * 0.85)   # gravel yard
    # oil stains
    n = pnoise(cv.n, 6, 812, 3, 3)
    cv.shade(smoothstep(0.62, 0.8, n) * rect(cv, 0.1, 1.5, 2.9, 2.9), 0.35)
    paving(cv, rect(cv, 2.25, 1.95, 3.0, 2.45), 0.30, 4)                         # access road stub
    zone_frame(cv, 'ind')
    metal = hx('#9ea3a8')
    corr = {'kind': 'curtain', 'col': 0.022, 'floor': 10.0, 'frame': (0.45, 0.47, 0.50)}
    stack_col = hx('#5c5650')
    items = [
        Box(0.18, 0.32, 2.05, 1.45, 0.34, metal, hx('#8d9196'), win={'kind': 'ribs', 'col': 0.035}, roof_detail=roof_skylights(5)),
        Box(0.20, 1.85, 2.15, 2.78, 0.28, hx('#b0a48c'), hx('#6f6a62'), win={'kind': 'doors', 'n': 4, 'h': 0.20, 'glass': Ramp(['#3a3d42', '#55595f', '#6d7279', '#8a8f96'])},
            win_w={'kind': 'ribs', 'col': 0.035}, roof_detail=roof_units([(0.1, 0.2, 0.1, 0.12), (0.5, 0.3, 0.12, 0.1), (0.75, 0.6, 0.12, 0.12)])),
        Cylinder(2.50, 0.95, 0.22, 0.30, hx('#c8c2b4'), top=hx('#d8d2c4')),
        Cylinder(2.50, 1.45, 0.14, 0.22, hx('#c8c2b4'), top=hx('#d8d2c4')),
    ]
    for k, bx in enumerate((0.78, 1.12, 1.46)):
        items.append(Cylinder(bx, 1.02, 0.055, 0.50, stack_col, top=hx('#3a3530'), z0=0.34, hollow=True,
                              bands=[(0.40, 0.04, hx('#c23a2a'))]))
        items[-1].key = (lambda k=k: (10 + k, 0))
    # trucks
    items.append(Custom(lambda c: vehicle(c, 2.55, 2.20, 0.30, 0.11, '#d9822b'), key=(2.2 - 2.55, 0)))
    items.append(Custom(lambda c: vehicle(c, 2.55, 2.70, 0.30, 0.11, '#e8e4dc'), key=(2.7 - 2.55, 0)))
    render(cv, items)
    if frame is not None:
        tops = [P(bx, 1.02, 0.84) for bx in (0.78, 1.12, 1.46)]
        smoke_puffs(cv, tops, frame, n_puff=5, rise=0.50, spread=0.10, clip=cell_clip(cv, [(1, 0)], 0.08), col=(0.80, 0.80, 0.80), dark=0.45)
    return cv


def ind_group():
    out = {}
    cv = ind_stacks(None)
    cells = cv.cells(RS)
    for i in range(9):
        out[IND3_BASE + i] = cells[i]
    for f in range(4):
        c = ind_stacks(f)
        out[IND3_SMOKE + f] = c.cells(RS)[1]
    return out


# ------------------------------------------------------------------ coal power plant 4x4 (+ smoke 916..931)
def coal_plant(frame=None):
    cv = Canvas(4, 4, RS, dirt_layer(4, 4))
    paving(cv, rect(cv, 0.08, 0.08, 3.92, 3.92), 0.50, 4)
    cv.paint(PAL['dirt'][2], rect(cv, 2.45, 1.95, 3.85, 3.05, 0.06) * 0.9)      # coal yard floor
    paving(cv, rect(cv, 2.45, 3.15, 3.85, 3.85), 0.40, 6)                         # switchyard slab
    zone_frame(cv, 'ind')
    hall = hx('#c4c6c8')
    boiler = hx('#8e9196')
    items = [
        Box(0.20, 0.85, 1.45, 3.78, 0.88, hall, hx('#9a9ea4'), win={'kind': 'ribs', 'col': 0.04},
            win_w={'kind': 'grid', 'floor': 0.16, 'col': 0.14, 'wfrac': 0.3, 'hfrac': 0.35, 'margin': 0.08},
            roof_detail=roof_skylights(4)),
        Box(1.45, 1.70, 2.30, 3.05, 1.12, boiler, PAL['roof_tar'][3], win={'kind': 'grid', 'floor': 0.2, 'col': 0.2, 'wfrac': 0.3, 'hfrac': 0.25},
            roof_detail=roof_units([(0.15, 0.1, 0.2, 0.15), (0.55, 0.55, 0.25, 0.2)])),
        # conveyor from the coal yard to the boiler
        Box(2.30, 2.32, 2.70, 2.44, 0.06, hx('#6d6a66'), hx('#7a7672'), parapet=False, z0=0.45),
    ]
    # the yellow lightning on the hall roof, as in the original
    def bolt(c, rx0, ry0, rx1, ry1):
        cx, cy = (rx0 + rx1) / 2, ry0 + 0.72 * (ry1 - ry0)
        pts = [(cx + 0.10, cy - 0.20), (cx - 0.06, cy + 0.02), (cx + 0.02, cy + 0.02), (cx - 0.10, cy + 0.22), (cx + 0.08, cy - 0.04), (cx, cy - 0.04)]
        c.shade(c.poly([(x + 0.02, y + 0.015) for x, y in pts]), 0.5)
        c.paint(hx('#ffd21a'), c.poly(pts))
    items[0].roof_detail = (lambda f1, f2: (lambda c, a, b, d, e: (f1(c, a, b, d, e), f2(c, a, b, d, e))))(roof_skylights(4), bolt)
    for k in range(4):
        bx = 1.62 + 0.30 * k
        cyl = Cylinder(bx, 1.52, 0.09, 1.85, hx('#c9c3ba'), top=hx('#2a2622'), hollow=True,
                       bands=[(1.55, 0.09, hx('#c8352a')), (1.72, 0.08, hx('#c8352a'))])
        cyl.key = (lambda k=k: (1.52 - 1.62 - 0.30 * k, 0))
        items.append(cyl)
    def coal_pile(c):
        X, Y = c.X, c.Y
        lump = pnoise(c.n, 24, 821, c.wt, c.ht) * 0.6 + pnoise(c.n, 60, 822, c.wt, c.ht) * 0.4
        hf = np.zeros_like(X)
        for (cx, cy, rx, ry) in ((2.95, 2.42, 0.44, 0.36), (3.45, 2.66, 0.32, 0.27), (3.15, 2.80, 0.28, 0.18)):
            d2 = ((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2
            hf = np.maximum(hf, np.clip(1 - d2, 0, 1) ** 0.8 * min(rx, ry))
        hf = hf * (1 + 0.25 * (lump - 0.5)) 
        m = np.clip(hf * 300, 0, 1)
        gy, gx = np.gradient(hf, 1.0 / c.n)
        nz = 1.0 / np.sqrt(1 + gx * gx + gy * gy)
        lam = np.clip((0.55 * gx + 0.45 * gy + 0.7) * nz, 0, 1)
        sh = c.blur(np.roll(np.roll(m, int(0.05 * c.n), 1), int(0.03 * c.n), 0), 0.02)
        c.shade(sh * (1 - m), 0.45)
        grain = pnoise(c.n, 140, 820, c.wt, c.ht)
        col = hx('#242120')[None, None, :] * (0.55 + 1.5 * lam + 0.8 * (grain - 0.5))[..., None]
        c.paint(np.clip(col, 0, 1), m)
    items.append(Custom(coal_pile, key=(-9, 0)))
    def switchyard(c):
        X, Y = c.X, c.Y
        for i in range(4):
            for j in range(2):
                x, y = 2.65 + 0.3 * i, 3.32 + 0.3 * j
                c.shade(rect(c, x + 0.02, y + 0.015, x + 0.15, y + 0.13, 0.01), 0.5)
                c.paint(hx('#7c8a7a'), rect(c, x, y, x + 0.12, y + 0.11, 0.01))
                c.paint(hx('#a8b6a4'), rect(c, x, y, x + 0.12, y + 0.03, 0.005))
                c.paint(hx('#e0e4e8'), c.cov(sd_circle(X, Y, x + 0.03, y + 0.05, 0.012)))
                c.paint(hx('#e0e4e8'), c.cov(sd_circle(X, Y, x + 0.09, y + 0.05, 0.012)))
        for j in range(3):
            y = 3.27 + 0.3 * j
            c.paint(hx('#30343a'), c.cov(np.abs(Y - y) - 0.005) * ((X > 2.55) & (X < 3.8)))
    items.append(Custom(switchyard, key=(-8, 0)))
    render(cv, items)
    if frame is not None:
        tops = [P(1.62 + 0.30 * k, 1.52, 1.85) for k in range(4)]
        smoke_puffs(cv, tops, frame, n_puff=6, rise=0.70, spread=0.20, col=(0.90, 0.89, 0.87), dark=0.55,
                    clip=cell_clip(cv, [(2, 0), (3, 0), (2, 1), (3, 1)], 0.06), drift=(0.12, -1.0))
    return cv


def coal_group():
    out = {}
    cells = coal_plant(None).cells(RS)
    for i in range(16):
        out[745 + i] = cells[i]
    smoke_cells = {(2, 0): 916, (3, 0): 920, (2, 1): 924, (3, 1): 928}
    for f in range(4):
        cl = coal_plant(f).cells(RS)
        for (i, j), base in smoke_cells.items():
            out[base + f] = cl[j * 4 + i]
    return out


# ------------------------------------------------------------------ fire station
def fire_station():
    cv = Canvas(3, 3, RS, dirt_layer(3, 3))
    lawn(cv, rect(cv, 0.1, 0.1, 2.9, 2.9, 0.06))
    paving(cv, rect(cv, 0.28, 2.0, 2.25, 2.92), 0.56, 6)          # apron
    paving(cv, rect(cv, 0.28, 0.25, 2.30, 2.0), 0.5, 6)
    zone_frame(cv, Ramp(['#3a0806', '#6a0e0a', '#9a1610', '#c42218', '#e03424', '#f05a46', '#f78a7a', '#fbbdb2']))
    brick = PAL['brick'][4]
    win = {'kind': 'grid', 'floor': 0.16, 'col': 0.12, 'wfrac': 0.5, 'hfrac': 0.45}
    doors = {'kind': 'doors', 'n': 3, 'h': 0.24}
    def bay_doors(c, *a):
        pass
    station = Box(0.30, 0.55, 2.20, 2.00, 0.46, brick, PAL['roof_slate'][3], win=doors, win_w=win,
                  label='FD', label_col=letter_col('fd'), label_size=0.62, label_font=FONT_SANS, rim=PAL['roof_slate'][5])
    station.glass = Ramp(['#5e1a12', '#7e2a1e', '#e8e2d8', '#f2eee6', '#ffffff'])
    tower = Box(2.25, 0.45, 2.62, 0.85, 0.95, brick, PAL['roof_slate'][2], win={'kind': 'grid', 'floor': 0.22, 'col': 0.18, 'wfrac': 0.35, 'hfrac': 0.3})
    items = [station, tower,
             Tree(2.6, 1.55, 0.15, 41), Tree(2.55, 2.35, 0.17, 42), Tree(2.75, 1.95, 0.11, 43),
             Custom(lambda c: vehicle(c, 0.68, 2.45, 0.42, 0.15, '#d42a1c', horizontal=False, stripe='#f2f0e8'), key=(9, 0)),
             Custom(lambda c: vehicle(c, 1.26, 2.50, 0.42, 0.15, '#d42a1c', horizontal=False, stripe='#f2f0e8'), key=(9, 0)),
             ]
    render(cv, items)
    return cv


# ------------------------------------------------------------------ police station
def police_station():
    cv = Canvas(3, 3, RS, dirt_layer(3, 3))
    lawn(cv, rect(cv, 0.1, 0.1, 2.9, 2.9, 0.06))
    paving(cv, rect(cv, 0.3, 2.05, 2.75, 2.85), 0.36, 6)        # car park (asphalt-ish)
    # parking bay lines
    for k in range(6):
        x = 0.45 + 0.38 * k
        cv.paint(PAL['concrete'][8], rect(cv, x - 0.008, 2.12, x + 0.008, 2.42) * 0.9)
    paving(cv, rect(cv, 1.25, 1.85, 1.65, 2.05), 0.6)
    zone_frame(cv, 'com')
    wall = hx('#5c70c4')
    win = {'kind': 'grid', 'floor': 0.15, 'col': 0.11, 'wfrac': 0.55, 'hfrac': 0.45}
    items = [
        Box(0.35, 0.50, 2.55, 1.85, 0.44, wall, PAL['roof_slate'][3], win=win, label='PD', label_col=letter_col('pd'), label_size=0.6,
            label_font=FONT_SANS, rim=PAL['roof_slate'][5], roof_detail=roof_units([(0.04, 0.08, 0.1, 0.1), (0.86, 0.75, 0.1, 0.12)])),
        Tree(0.35, 0.3, 0.1, 51), Tree(2.7, 0.55, 0.13, 52), Tree(2.72, 1.3, 0.12, 53),
    ]
    for k, (x, col) in enumerate(((0.64, '#f4f4f0'), (1.02, '#1e2c5c'), (1.78, '#f4f4f0'), (2.16, '#f4f4f0'))):
        items.append(Custom((lambda x=x, col=col: (lambda c: vehicle(c, x, 2.27, 0.24, 0.12, col, horizontal=False, stripe='#2a48b8' if col != '#1e2c5c' else '#f4f4f0')))(), key=(9, 0)))
    def flag(c):
        bx, by = 1.75, 1.97
        tx, ty = P(bx, by, 0.6)
        c.shade(c.cov(sd_segment(c.X, c.Y, bx, by, bx + SHADOW_DIR[0] * 0.6, by + SHADOW_DIR[1] * 0.6) - 0.006, 2), 0.4)
        c.paint(PAL['steel'][5], c.cov(sd_segment(c.X, c.Y, bx, by, tx, ty) - 0.007))
        c.paint(hx('#2a48b8'), c.poly([(tx, ty), (tx + 0.16, ty + 0.01), (tx + 0.15, ty + 0.1), (tx, ty + 0.09)]))
    items.append(Custom(flag, key=(9.5, 0)))
    render(cv, items)
    return cv


GROUPS.append((333, 3, 3, res_low))
GROUPS.append((360, 3, 3, res_high))
GROUPS.append((504, 3, 3, com_tower))
GROUPS.append((IND3_BASE, 3, 3, ind_group))
GROUPS.append((745, 4, 4, coal_group))
GROUPS.append((761, 3, 3, fire_station))
GROUPS.append((770, 3, 3, police_station))


# ------------------------------------------------------------------ single-tile houses 249..260
def hedge(cv, inset=0.06):
    d = -sd_box(cv.X, cv.Y, 0, 0, 1, 1)
    band = cv.cov(np.abs(d - inset) - 0.025)
    leaf = pnoise(cv.n, 40, 830)
    cv.shade(cv.cov(np.abs(d - inset - 0.03) - 0.02, 3) * (1 - band), 0.35)
    cv.paint(PAL['leaf'](0.35 + 0.35 * leaf), band)


def pool(cv, x0, y0, x1, y1):
    cv.paint(PAL['concrete'][7], rect(cv, x0 - 0.025, y0 - 0.025, x1 + 0.025, y1 + 0.025, 0.02))
    cv.paint(hx('#3ab0d8'), rect(cv, x0, y0, x1, y1, 0.015))
    cv.paint(hx('#1f7fae'), rect(cv, x0, y0, x1, y0 + 0.03) * 0.6)
    rip = pnoise2(cv.n, 10, 30, 831)
    cv.light(smoothstep(0.65, 0.8, rip) * rect(cv, x0, y0, x1, y1), 0.35)


HOUSES = [
    # (ground, hedge, items-spec, extras)
    ('dirt', False, [('g', 0.18, 0.22, 0.52, 0.50, 0.14, 0.10, '#b9b2a2', 'roof_slate', 'x'), ('b', 0.60, 0.62, 0.84, 0.82, 0.12, '#a59a86', '#5a5550')], []),
    ('dirt', False, [('g', 0.22, 0.20, 0.66, 0.56, 0.16, 0.12, '#7486d8', 'roof_slate', 'x'), ('b', 0.68, 0.18, 0.86, 0.34, 0.10, '#59b85a', '#4a4a48')], ['path']),
    ('dirt', False, [('g', 0.12, 0.14, 0.40, 0.36, 0.11, 0.08, '#d84a3a', 'roof_slate', 'x'), ('g', 0.58, 0.14, 0.86, 0.36, 0.11, 0.08, '#59b85a', 'roof_slate', 'x'),
                     ('g', 0.12, 0.58, 0.40, 0.80, 0.11, 0.08, '#4a5cd0', 'roof_slate', 'x'), ('g', 0.58, 0.58, 0.86, 0.80, 0.11, 0.08, '#c8c4bc', 'roof_slate', 'x')], []),
    ('patchy', True, [('g', 0.30, 0.18, 0.62, 0.72, 0.18, 0.12, '#6c7ed0', 'roof_slate', 'y')], ['tree']),
    ('patchy', True, [('g', 0.20, 0.25, 0.70, 0.55, 0.17, 0.12, '#d0503c', 'roof_slate', 'x')], ['path', 'tree']),
    ('patchy', True, [('g', 0.28, 0.24, 0.76, 0.58, 0.17, 0.13, '#e4d8c0', 'roof_red', 'x')], ['path']),
    ('lawn', True, [('g', 0.18, 0.18, 0.78, 0.46, 0.18, 0.12, '#e8963a', 'roof_slate', 'x'), ('g', 0.18, 0.46, 0.44, 0.80, 0.18, 0.12, '#e8963a', 'roof_slate', 'y')], ['pool']),
    ('lawn', True, [('g', 0.16, 0.16, 0.84, 0.40, 0.18, 0.12, '#f0d040', 'roof_slate', 'x'), ('g', 0.60, 0.40, 0.84, 0.80, 0.18, 0.12, '#f0d040', 'roof_slate', 'y')], ['tree2']),
    ('lawn', True, [('g', 0.18, 0.20, 0.80, 0.48, 0.18, 0.13, '#5466d4', 'roof_slate', 'x'), ('g', 0.18, 0.48, 0.46, 0.80, 0.18, 0.13, '#5466d4', 'roof_slate', 'y')], ['path']),
    ('lawn', True, [('g', 0.16, 0.18, 0.84, 0.58, 0.20, 0.14, '#ecebe6', 'roof_slate', 'x')], ['path', 'tree']),
    ('lawn', True, [('g', 0.16, 0.14, 0.84, 0.46, 0.21, 0.13, '#ecebe6', 'roof_tar', 'x')], ['pool']),
    ('lawn', True, [('g', 0.14, 0.14, 0.86, 0.40, 0.22, 0.13, '#ecebe6', 'roof_slate', 'x'), ('g', 0.14, 0.40, 0.42, 0.84, 0.22, 0.13, '#ecebe6', 'roof_slate', 'y')], ['pool2', 'tree']),
]


def house_tile(k):
    ground, hed, specs, extras = HOUSES[k]
    cv = Canvas(1, 1, RS, dirt_layer())
    if ground == 'lawn':
        lawn(cv, rect(cv, 0.0, 0.0, 1.0, 1.0))
    elif ground == 'patchy':
        lawn(cv, smoothstep(0.42, 0.55, pnoise(cv.n, 5, 840 + k)) * rect(cv, 0.03, 0.03, 0.97, 0.97, 0.05))
    if 'path' in extras:
        paving(cv, rect(cv, 0.44, 0.55, 0.56, 1.0), 0.6)
    if 'pool' in extras:
        pool(cv, 0.54, 0.56, 0.84, 0.80)
    if 'pool2' in extras:
        pool(cv, 0.52, 0.52, 0.82, 0.74)
    if hed:
        hedge(cv)
    items = []
    win = {'kind': 'grid', 'floor': 0.11, 'col': 0.09, 'wfrac': 0.45, 'hfrac': 0.45, 'base': 0.03}
    # keep every roof inside the tile: shift the group left / down as needed
    maxx = max(s[3] + OX * (s[5] + (s[6] if s[0] == 'g' else 0)) for s in specs)
    miny = min(s[2] - OY * (s[5] + (s[6] if s[0] == 'g' else 0)) for s in specs)
    dx = min(0.0, 0.95 - maxx)
    dy = max(0.0, 0.06 - miny)
    specs = [(s[0], s[1] + dx, s[2] + dy, s[3] + dx, s[4] + dy) + tuple(s[5:]) for s in specs]
    for s in specs:
        if s[0] == 'g':
            _, x0, y0, x1, y1, h, rh, wall, roof, ridge = s
            items.append(Gable(x0, y0, x1, y1, h, rh, hx(wall), roof, ridge=ridge, win=win))
        else:
            _, x0, y0, x1, y1, h, wall, roof = s
            items.append(Box(x0, y0, x1, y1, h, hx(wall), hx(roof), parapet=False))
    if 'tree' in extras:
        items.append(Tree(0.80, 0.80, 0.11, 860 + k))
    if 'tree2' in extras:
        items.append(Tree(0.28, 0.66, 0.12, 870 + k))
    render(cv, items)
    return cv


for _k in range(12):
    GROUPS.append((249 + _k, 1, 1, (lambda k=_k: house_tile(k))))
