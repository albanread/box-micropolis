"""Stand-alone animations and odd tiles: drawbridges, explosion, fountain, network dish,
the no-power sign, rubble, the road/power duplicate 239, tile 1 and the unused slots.

GROUPS / ANIM follow the convention in BRIEF.md.
"""
import math
import numpy as np
from hdlib import *
from terrain import dirt_layer, water_layer, grass_layer, cached
from scene3d import face_uv, Cylinder, render, P
import transport as TR
from buildings import rect, smoke_puffs

GROUPS = []
ANIM = {}


def _cells(cv):
    return cv.cells(RS)


# ------------------------------------------------------------------ drawbridges
def leaf(cv, x_or_y, span0, span1, L, axis, surface):
    """A raised bascule leaf: a vertical plane standing on the line x = const (axis 'x', the
    plane spans y in [span0, span1]) or y = const (axis 'y', spans x), lifted to height L.
    surface: 'road' (asphalt with dashes) or 'under' (concrete underside with girders)."""
    if axis == 'x':
        xp = x_or_y
        pts = [P(xp, span0, 0), P(xp, span1, 0), P(xp, span1, L), P(xp, span0, L)]
        O = P(xp, span1, 0)
        U, V = (0.0, -1.0), (OX, -OY)
        light = 1.0
    else:
        yp = x_or_y
        pts = [P(span0, yp, 0), P(span1, yp, 0), P(span1, yp, L), P(span0, yp, L)]
        O = P(span0, yp, 0)
        U, V = (1.0, 0.0), (OX, -OY)
        light = 0.72
    m = cv.poly(pts, ss=2)
    u, v = face_uv(cv, O, U, V)
    w = span1 - span0
    if surface == 'road':
        tex = np.tile(TR.asphalt_tex(cv.n), (cv.ht, cv.wt, 1))
        col = tex * light * (0.9 + 0.12 * np.clip(v / L, 0, 1))[..., None]
        cv.paint(col, m)
        # kerbs along both long edges
        kerb = ((u < 0.035) | (u > w - 0.035)).astype(float)
        cv.paint(PAL['concrete'][5] * light, kerb * m)
        dash = (np.abs(u - w / 2) < 0.012) & (np.abs(((v + 0.25) % 0.5) - 0.25) < 0.11)
        cv.paint(hx('#ecebe4') * light, dash * m * 0.9)
    else:
        col = PAL['concrete'](0.62 + 0.08 * np.clip(v / L, 0, 1)) * light
        cv.paint(col, m)
        gird = (np.abs(((u / w) * 4 % 1) - 0.5) > 0.42).astype(float)
        cv.shade(gird * m, 0.35)
        rib = (np.abs((v / 0.25) % 1 - 0.5) > 0.44).astype(float)
        cv.shade(rib * m, 0.2)
    # top edge highlight and outline
    a, b = pts[2], pts[3]
    cv.light(cv.cov(sd_segment(cv.X, cv.Y, a[0], a[1], b[0], b[1]) - 0.006, 1.0), 0.5)
    for (p0, p1) in ((pts[0], pts[3]), (pts[1], pts[2])):
        cv.paint(PAL['asphalt'][0], cv.cov(sd_segment(cv.X, cv.Y, p0[0], p0[1], p1[0], p1[1]) - 0.005, 1.0) * 0.8)
    return m


def leaf_shadow(cv, poly_pts, fade_box):
    """Soft shadow on the water, faded out before the given box's edges (x0,y0,x1,y1)."""
    sh = cv.blur(cv.poly(poly_pts), 0.02)
    x0, y0, x1, y1 = fade_box
    d = -sd_box(cv.X, cv.Y, x0, y0, x1, y1)
    cv.shade(sh * smoothstep(0.0, 0.12, d), 0.55)


def pier(cv, x0, y0, x1, y1):
    """Bridge abutment block under the leaf pivot."""
    cv.shade(cv.blur(rect(cv, x0 + 0.03, y0 + 0.02, x1 + 0.05, y1 + 0.03), 0.01), 0.5)
    cv.paint(PAL['concrete'][4], rect(cv, x0, y0, x1, y1, 0.01))
    cv.light(rect(cv, x0, y0, x1, y0 + 0.012), 0.3)


HL = 1.40   # horizontal leaves' lifted length
VL = 1.00   # vertical leaves'


def hbridge_west():
    """828 HBRDG0 (row 0) and 829 HBRDG1 (above it): canvas 1x2, 829 on top."""
    cv = Canvas(1, 2, RS, water_layer(1, 2))
    y0, y1 = 1.5 - TR.HW - TR.KW, 1.5 + TR.HW + TR.KW
    xp = 0.06
    # stub of deck from the west edge to the pivot (joins the road bridge 64)
    road = Canvas(1, 1, RS, water_layer())
    TR.draw_road(road, 'EW', on_water=True)
    m = (cv.X < xp + 0.004).astype(float) * (cv.Y >= 1.0)
    cv.img[RS:] = cv.img[RS:] * (1 - m[RS:, :, None]) + road.img * m[RS:, :, None]
    foot = [(xp, y0), (xp, y1)]
    shp = [(xp, y0), (xp, y1), (xp + SHADOW_DIR[0] * HL, y1 + SHADOW_DIR[1] * HL), (xp + SHADOW_DIR[0] * HL, y0 + SHADOW_DIR[1] * HL)]
    leaf_shadow(cv, shp, (0, 1, 1, 2))
    pier(cv, 0.0, y0 - 0.02, xp + 0.05, y1 + 0.03)
    leaf(cv, xp + 0.02, y0, y1, HL, 'x', 'road')
    c = cv.cells(RS)
    return {829: c[0], 828: c[1]}


def hbridge_east():
    """830 HBRDG2 (row 0) and 831 HBRDG3 (above)."""
    cv = Canvas(1, 2, RS, water_layer(1, 2))
    y0, y1 = 1.5 - TR.HW - TR.KW, 1.5 + TR.HW + TR.KW
    xp = 0.12
    road = Canvas(1, 1, RS, water_layer())
    TR.draw_road(road, 'EW', on_water=True)
    m = (cv.X > xp).astype(float)
    m[:RS] = 0
    cv.img[RS:] = cv.img[RS:] * (1 - m[RS:, :, None]) + road.img * m[RS:, :, None]
    shp = [(xp, y0), (xp, y1), (xp + SHADOW_DIR[0] * HL, y1 + SHADOW_DIR[1] * HL), (xp + SHADOW_DIR[0] * HL, y0 + SHADOW_DIR[1] * HL)]
    leaf_shadow(cv, shp, (0, 1, 1, 2))
    pier(cv, xp - 0.04, y0 - 0.02, xp + 0.06, y1 + 0.03)
    leaf(cv, xp, y0, y1, HL, 'x', 'under')
    c = cv.cells(RS)
    return {831: c[0], 830: c[1]}


def vbridge_north():
    """948 VBRDG0 (on the road line) and 949 VBRDG1 (east of it): canvas 2x1."""
    cv = Canvas(2, 1, RS, water_layer(2, 1))
    x0, x1 = 0.5 - TR.HW - TR.KW, 0.5 + TR.HW + TR.KW
    yp = 0.86
    road = Canvas(1, 1, RS, water_layer())
    TR.draw_road(road, 'NS', on_water=True)
    m = (cv.Y < yp).astype(float)
    m[:, RS:] = 0
    cv.img[:, :RS] = cv.img[:, :RS] * (1 - m[:, :RS, None]) + road.img * m[:, :RS, None]
    shp = [(x0, yp), (x1, yp), (x1 + SHADOW_DIR[0] * VL, yp + SHADOW_DIR[1] * VL), (x0 + SHADOW_DIR[0] * VL, yp + SHADOW_DIR[1] * VL)]
    leaf_shadow(cv, shp, (0, 0, 2, 1))
    pier(cv, x0 - 0.03, yp - 0.05, x1 + 0.02, yp + 0.04)
    leaf(cv, yp, x0, x1, VL, 'y', 'under')
    c = cv.cells(RS)
    return {948: c[0], 949: c[1]}


def vbridge_south():
    """950 VBRDG2 (on the road line) and 951 VBRDG3 (east of it)."""
    cv = Canvas(2, 1, RS, water_layer(2, 1))
    x0, x1 = 0.5 - TR.HW - TR.KW, 0.5 + TR.HW + TR.KW
    yp = 0.58
    road = Canvas(1, 1, RS, water_layer())
    TR.draw_road(road, 'NS', on_water=True)
    m = (cv.Y > yp).astype(float)
    m[:, RS:] = 0
    cv.img[:, :RS] = cv.img[:, :RS] * (1 - m[:, :RS, None]) + road.img * m[:, :RS, None]
    shp = [(x0, yp), (x1, yp), (x1 + SHADOW_DIR[0] * VL, yp + SHADOW_DIR[1] * VL), (x0 + SHADOW_DIR[0] * VL, yp + SHADOW_DIR[1] * VL)]
    leaf_shadow(cv, shp, (0, 0, 2, 1))
    pier(cv, x0 - 0.03, yp - 0.03, x1 + 0.02, yp + 0.05)
    leaf(cv, yp, x0, x1, VL, 'y', 'road')
    c = cv.cells(RS)
    return {950: c[0], 951: c[1]}


def bridge_gaps():
    """79 BRWH / 95 BRWV: the open span is water, with fender piles marking the channel."""
    out = {}
    for t, horiz in ((79, True), (95, False)):
        cv = Canvas(1, 1, RS, water_layer())
        for s in (-1, 1):
            for k in (0.18, 0.5, 0.82):
                # dolphins (pile clusters) beside the channel, kept off the edges
                if horiz:
                    x, y = k, 0.5 + s * 0.40
                else:
                    x, y = 0.5 + s * 0.40, k
                if not (0.08 < x < 0.92 and 0.08 < y < 0.92):
                    continue
                cv.shade(cv.cov(sd_circle(cv.X, cv.Y, x + 0.03, y + 0.018, 0.045), 4), 0.5)
                cv.paint(PAL['timber'][2], cv.cov(sd_circle(cv.X, cv.Y, x, y, 0.042)))
                cv.paint(PAL['timber'][4], cv.cov(sd_circle(cv.X, cv.Y, x - 0.01, y - 0.01, 0.02), 2))
                cv.paint(PAL['water'][9], cv.cov(np.abs(sd_circle(cv.X, cv.Y, x, y, 0.05)) - 0.004, 2) * 0.4)
        out[t] = cv.img
    return out


GROUPS.append((828, 1, 1, hbridge_west))
GROUPS.append((830, 1, 1, hbridge_east))
GROUPS.append((948, 1, 1, vbridge_north))
GROUPS.append((950, 1, 1, vbridge_south))
GROUPS.append((79, 1, 1, bridge_gaps))


# ------------------------------------------------------------------ rubble: broken material
def debris_points(seed, n, rmin, rmax, lo=0.0, hi=1.0):
    rng = np.random.default_rng(seed)
    return [(rng.uniform(lo, hi), rng.uniform(lo, hi), rng.uniform(rmin, rmax), int(rng.integers(1 << 30))) for _ in range(n)]


def shard(cv, x, y, r, s, hf, colf):
    """One broken slab: irregular convex polygon with a tilt; returns nothing, writes into hf/colf."""
    rng = np.random.default_rng(s)
    m = int(rng.integers(4, 7))
    a0 = rng.uniform(0, 6.28)
    pts = [(x + r * math.cos(a0 + 6.283 * i / m + rng.uniform(-0.3, 0.3)) * rng.uniform(0.6, 1.15),
            y + r * math.sin(a0 + 6.283 * i / m + rng.uniform(-0.3, 0.3)) * rng.uniform(0.6, 1.15)) for i in range(m)]
    mask = cv.poly(pts, ss=1)
    if mask.max() == 0:
        return
    tx, ty = rng.uniform(-1.6, 1.6, 2)
    h = rng.uniform(0.02, 0.05) + (cv.X - x) * tx * 0.15 + (cv.Y - y) * ty * 0.15 + r * 0.5
    upd = (mask > 0.5) & (h > hf)
    hf[upd] = h[upd]
    k = rng.random()
    if k < 0.55:
        c = PAL['concrete'](rng.uniform(0.35, 0.75))
    elif k < 0.85:
        c = PAL['brick'](rng.uniform(0.35, 0.65))
    else:
        c = PAL['roof_tar'](rng.uniform(0.2, 0.5))
    colf[upd] = c


def rubble_img(k):
    cv = Canvas(1, 1, RS, dirt_layer())
    X, Y = cv.X, cv.Y
    # dust: pale concrete powder over the ground, periodic, plus darker scorch patches
    dust = pnoise(cv.n, 8, 1300) * 0.6 + pnoise(cv.n, 24, 1301) * 0.4
    cv.paint(hx('#a39486'), smoothstep(0.35, 0.75, dust) * 0.55)
    cv.shade(smoothstep(0.62, 0.85, pnoise(cv.n, 6, 1302 + k)) * smoothstep(0.03, 0.2, -sd_box(X, Y, 0, 0, 1, 1)), 0.30)
    hf = np.zeros_like(X)
    colf = np.zeros(cv.img.shape)
    # small fragments: one periodic set shared by all four tiles (so rubble joins rubble)
    for (x, y, r, s) in wrap_points(debris_points(1310, 150, 0.012, 0.030)):
        if -0.05 < x < 1.05 and -0.05 < y < 1.05:
            shard(cv, x, y, r, s, hf, colf)
    # big slabs and brick heaps: per variant, kept inside the tile
    for (x, y, r, s) in debris_points(1320 + k, 22, 0.045, 0.10, 0.15, 0.85):
        shard(cv, x, y, r, s, hf, colf)
    m = (hf > 0).astype(float)
    m = cv.blur(m, 0.0015)
    gy, gx = np.gradient(cv.blur(hf, 0.002), 1.0 / cv.n)
    nz = 1 / np.sqrt(1 + gx * gx + gy * gy)
    lam = np.clip((-0.55 * gx - 0.45 * gy) * nz * 0.8 + 0.75 * nz, 0.3, 1.25)
    # cast shadows of the heap (right/down)
    sh = np.roll(np.roll(hf, int(0.02 * cv.n), 1), int(0.012 * cv.n), 0)
    cv.shade(cv.blur(np.clip((sh - hf) * 40, 0, 1), 0.004), 0.55)
    grain = pnoise(cv.n, 120, 1330)
    col = colf * (lam * (0.9 + 0.2 * grain))[..., None]
    cv.paint(np.clip(col, 0, 1), m)
    # cracks / edges on slabs
    e = np.clip(np.abs(cv.blur(hf, 0.001) - hf) * 300, 0, 1)
    cv.shade(e * m, 0.35)
    # a few bent rebars on the big slabs
    rng = np.random.default_rng(1340 + k)
    for _ in range(4):
        x, y = rng.uniform(0.2, 0.8, 2)
        a = rng.uniform(0, 6.28)
        L = rng.uniform(0.06, 0.1)
        pts = [(x, y), (x + L * math.cos(a), y + L * math.sin(a)), (x + L * math.cos(a) + 0.03 * math.cos(a + 1.2), y + L * math.sin(a) + 0.03 * math.sin(a + 1.2))]
        d = sd_polyline(X, Y, pts)
        cv.shade(cv.cov(sd_polyline(X - 0.01, Y - 0.006, pts) - 0.004, 2), 0.4)
        cv.paint(hx('#6a4a32'), cv.cov(d - 0.0035, 1.0))
    return cv.img


for _k in range(4):
    GROUPS.append((44 + _k, 1, 1, (lambda k=_k: {44 + k: rubble_img(k)})))


# ------------------------------------------------------------------ explosion 860..867
def explosion(f):
    """8 frames: flash, fireball growing, breaking up, smoke and debris; 867 is the final rubble."""
    if f == 7:
        img = rubble_img(1)
        cv = Canvas(1, 1, RS, img)
        # scorch around the heap
        cv.shade(smoothstep(0.42, 0.1, np.hypot(cv.X - 0.5, cv.Y - 0.5)), 0.45)
        return cv.img
    cv = Canvas(1, 1, RS, dirt_layer())
    X, Y = cv.X, cv.Y
    r = np.hypot(X - 0.5, Y - 0.5)
    edge = smoothstep(0.0, 0.08, -sd_box(X, Y, 0, 0, 1, 1))       # keep the border plain ground
    ang = np.arctan2(Y - 0.5, X - 0.5)
    lumps = pnoise(cv.n, 10, 1400 + f) * 0.6 + pnoise(cv.n, 30, 1410 + f) * 0.4
    R = [0.07, 0.15, 0.25, 0.34, 0.38, 0.40, 0.40][f]
    if f >= 2:
        cv.shade(smoothstep(R + 0.08, R * 0.5, r) * edge, 0.6)            # scorch
    if f >= 3:
        # debris under the fire
        deb = Canvas(1, 1, RS, rubble_img(1))
        a = smoothstep(R * 0.9, R * 0.6, r) * min(1.0, (f - 2) / 3) * edge
        cv.img = cv.img * (1 - a[..., None]) + deb.img * a[..., None]
    heat_f = [1.0, 1.0, 0.95, 0.85, 0.6, 0.35, 0.12][f]
    rr = r / max(R, 1e-3) + 0.35 * (lumps - 0.5) + 0.05 * np.sin(7 * ang + f)
    heat = np.clip(1.15 - rr, 0, 1) * heat_f
    if f >= 4:
        heat = heat * smoothstep(0.35, 0.65, lumps + 0.15 * (6 - f) / 2)
    cv.paint(PAL['fire'](0.2 + 0.8 * heat), smoothstep(0.05, 0.25, heat) * edge)
    cv.light(smoothstep(0.75, 1.0, heat) * edge, 0.5, (1, 1, 0.92))
    glow = cv.blur(heat, 0.06)
    cv.light(glow * edge * (1 - smoothstep(0.05, 0.25, heat)), 0.35, PAL['fire'][4])
    if f >= 3:
        # smoke puffs drifting up from the blaze (inside the tile)
        smoke_puffs(cv, [(0.45, 0.62), (0.58, 0.55)], f - 3, n_puff=4, rise=0.35, spread=0.10,
                    col=(0.35, 0.33, 0.32) if f < 6 else (0.55, 0.54, 0.52), dark=0.5,
                    clip=smoothstep(0.0, 0.1, -sd_box(X, Y, 0, 0, 1, 1)))
    # sparks / flying bits
    rng = np.random.default_rng(1420 + f)
    if 1 <= f <= 5:
        for _ in range(14):
            a = rng.uniform(0, 6.28)
            d = rng.uniform(R * 0.8, min(0.42, R * 1.4 + 0.05))
            x, y = 0.5 + d * math.cos(a), 0.5 + d * math.sin(a)
            col = PAL['fire'][7] if f < 4 else PAL['concrete'][2]
            cv.paint(col, cv.cov(sd_circle(X, Y, x, y, 0.008), 1.2) * edge)
    return cv.img


GROUPS.append((860, 1, 1, lambda: {860 + f: explosion(f) for f in range(8)}))


# ------------------------------------------------------------------ fountain 840..843
def fountain(f):
    cv = Canvas(1, 1, RS, grass_layer())
    X, Y = cv.X, cv.Y
    # paths crossing the plaza, fading into the lawn before the edges
    fade = smoothstep(0.06, 0.2, -sd_box(X, Y, 0, 0, 1, 1))
    gravel = PAL['sand'](0.62 + 0.15 * (pnoise(cv.n, 64, 1500) - 0.5))
    for d in (np.abs(Y - 0.5) - 0.07, np.abs(X - 0.5) - 0.07):
        cv.paint(gravel, cv.cov(d) * fade)
    cv.paint(PAL['concrete'](0.62 + 0.06 * (pnoise(cv.n, 40, 1501) - 0.5)), cv.cov(sd_circle(X, Y, 0.5, 0.5, 0.30)))
    cv.shade(cv.cov(np.abs(sd_circle(X, Y, 0.5, 0.5, 0.30)) - 0.006, 1.5), 0.35)
    # paving rings
    cv.shade(cv.cov(np.abs(np.hypot(X - 0.5, Y - 0.5) - 0.25) - 0.003, 1.0), 0.15)
    # basin: rim (lit upper-left), water inside
    cv.shade(cv.cov(sd_circle(X, Y, 0.52, 0.51, 0.22), 4), 0.4)
    cv.paint(PAL['concrete'][7], cv.cov(sd_circle(X, Y, 0.5, 0.5, 0.21)))
    wn = pnoise2(cv.n, 10, 26, 1502 + f)
    water = PAL['shallow'](0.45 + 0.35 * (wn - 0.5) + 0.25 * np.clip((0.5 - Y) * 2, -1, 1))
    cv.paint(water, cv.cov(sd_circle(X, Y, 0.5, 0.5, 0.185)))
    cv.shade(cv.cov(np.abs(sd_circle(X, Y, 0.5, 0.5, 0.185)) - 0.008, 2) * (Y > 0.45) * 0 + cv.cov(sd_circle(X, Y, 0.47, 0.47, 0.185) * -1 - 0.0) * 0, 0)
    # ripples spreading outward, phase per frame (loops over 4 frames)
    r = np.hypot(X - 0.5, Y - 0.5)
    ring = np.cos((r / 0.06 - f / 4.0) * 2 * math.pi)
    cv.light(smoothstep(0.75, 0.95, ring) * cv.cov(sd_circle(X, Y, 0.5, 0.5, 0.175)) * smoothstep(0.04, 0.08, r), 0.35, (0.95, 0.98, 1.0))
    # centre pedestal
    cv.paint(PAL['concrete'][6], cv.cov(sd_circle(X, Y, 0.5, 0.5, 0.045)))
    cv.light(cv.cov(sd_circle(X, Y, 0.49, 0.49, 0.025), 2), 0.3)
    # jets: arcs of droplets rising up-right (oblique height), animated along the arc
    for k in range(6):
        a = k * math.pi / 3 + 0.3
        for j in range(7):
            t = ((j / 7.0) + f / 28.0) % 1.0
            reach = 0.15 * t
            z = 0.34 * t * (1 - t) * 4 * 0.5
            gx, gy = 0.5 + reach * math.cos(a), 0.5 + reach * 0.75 * math.sin(a)
            sx, sy = gx + OX * z, gy - OY * z
            cv.paint(hx('#eef6ff'), cv.cov(sd_circle(X, Y, sx, sy, 0.010 - 0.004 * t), 1.2) * 0.9)
    # central plume
    for j in range(6):
        t = ((j / 6.0) + f / 24.0) % 1.0
        z = 0.30 * math.sin(math.pi * t)
        cv.paint(hx('#f4f9ff'), cv.cov(sd_circle(X, Y, 0.5 + OX * z, 0.5 - OY * z, 0.016 - 0.006 * t), 1.2) * 0.85)
    cv.paint(hx('#ffffff'), cv.cov(sd_circle(X, Y, 0.5 + OX * 0.31, 0.5 - OY * 0.31, 0.03 + 0.006 * math.sin(f * math.pi / 2)), 3) * 0.5)
    # benches at the plaza edge
    for (x, y, horiz) in ((0.24, 0.24, True), (0.76, 0.76, True)):
        cv.shade(rect(cv, x - 0.05 + 0.012, y - 0.015 + 0.01, x + 0.05 + 0.012, y + 0.015 + 0.01), 0.45)
        cv.paint(PAL['timber'][4], rect(cv, x - 0.05, y - 0.015, x + 0.05, y + 0.015, 0.004))
    return cv.img


GROUPS.append((840, 1, 1, lambda: {840 + f: fountain(f) for f in range(4)}))


# ------------------------------------------------------------------ network dish 844..851
def dish(cv, cx, cy, mast_h, ang, r=0.22):
    """A parabolic dish on a lattice mast; ang = azimuth of the dish axis (radians, 0 = east).
    Shared by the network tile; the airport radar is drawn by blocks_special."""
    X, Y = cv.X, cv.Y
    # mast shadow
    tx, ty = P(cx, cy, mast_h)
    cv.shade(cv.blur(cv.cov(sd_segment(X, Y, cx, cy, cx + SHADOW_DIR[0] * mast_h, cy + SHADOW_DIR[1] * mast_h) - 0.015, 2), 0.004), 0.5)
    # dish shadow (ellipse at the shadow of the mast top)
    sx, sy = cx + SHADOW_DIR[0] * mast_h, cy + SHADOW_DIR[1] * mast_h
    ca, sa = math.cos(ang), math.sin(ang)
    du = (X - sx) * ca + (Y - sy) * sa
    dv = -(X - sx) * sa + (Y - sy) * ca
    cv.shade(cv.blur(((du / (r * 0.45)) ** 2 + (dv / r) ** 2 < 1).astype(float), 0.006), 0.45)
    # base pad
    cv.shade(rect(cv, cx - 0.09 + 0.02, cy - 0.06 + 0.015, cx + 0.09 + 0.02, cy + 0.06 + 0.015, 0.01), 0.4)
    cv.paint(PAL['concrete'][5], rect(cv, cx - 0.09, cy - 0.06, cx + 0.09, cy + 0.06, 0.01))
    # lattice mast (two legs and cross braces)
    for dx in (-0.03, 0.03):
        a, b = (cx + dx, cy), (tx + dx * 0.3, ty)
        cv.paint(PAL['steel'][2], cv.cov(sd_segment(X, Y, a[0], a[1], b[0], b[1]) - 0.006))
    for k in range(4):
        t0, t1 = k / 4, (k + 1) / 4
        a = (cx - 0.03 + (tx - cx) * t0 + 0.021 * t0, cy + (ty - cy) * t0)
        b = (cx + 0.03 + (tx - cx) * t1 - 0.021 * t1, cy + (ty - cy) * t1)
        cv.paint(PAL['steel'][3], cv.cov(sd_segment(X, Y, a[0], a[1], b[0], b[1]) - 0.003))
    # the dish: an ellipse whose minor axis is along its pointing direction; concave side lit
    # when it faces the light (west/north), shaded otherwise
    du = (X - tx) * ca + (Y - ty) * sa
    dv = -(X - tx) * sa + (Y - ty) * ca
    e = (du / (r * 0.42)) ** 2 + (dv / r) ** 2
    m = cv.cov((np.sqrt(e) - 1) * r * 0.42, 1.2)
    facing = -(ca * -0.75 + sa * -0.6)   # >0 when the concave side looks away from the light
    inner = np.clip(1 - e, 0, 1)
    base = PAL['concrete'](0.80 - 0.25 * max(0, facing)) * np.ones_like(X)[..., None]
    shade = (0.72 + 0.35 * (du / (r * 0.42)) * (-1 if facing > 0 else 1) * 0.5)
    cv.paint(np.clip(base * np.clip(shade, 0.5, 1.15)[..., None], 0, 1), m)
    cv.paint(PAL['concrete'][3], cv.cov(np.abs(np.sqrt(e) - 1) * r * 0.42 - 0.004, 1.0) * 0.8)
    # feed horn on struts, toward the pointing direction
    fx, fy = tx + ca * r * 0.65, ty + sa * r * 0.65
    for s in (-1, 1):
        cv.paint(PAL['steel'][2], cv.cov(sd_segment(X, Y, tx - sa * r * 0.8 * s, ty + ca * r * 0.8 * s, fx, fy) - 0.0035))
    cv.paint(PAL['steel'][1], cv.cov(sd_circle(X, Y, fx, fy, 0.014)))
    cv.paint(hx('#e23a2a'), cv.cov(sd_circle(X, Y, tx - 0.005, ty - 0.035, 0.008), 1.0))


def network(f):
    cv = Canvas(1, 1, RS, dirt_layer())
    cv.paint(PAL['dirt'][4], smoothstep(0.32, 0.18, np.hypot(cv.X - 0.42, cv.Y - 0.62)) * 0.5)
    dish(cv, 0.38, 0.68, 0.46, -math.pi / 2 + f * math.pi / 4 + math.pi)
    # equipment hut
    cv.shade(rect(cv, 0.66 + 0.03, 0.64 + 0.02, 0.86 + 0.03, 0.82 + 0.02, 0.01), 0.5)
    cv.paint(PAL['concrete'][3], rect(cv, 0.66, 0.70, 0.86, 0.82))
    cv.paint(PAL['concrete'][6], rect(cv, 0.68, 0.62, 0.88, 0.74))
    cv.paint(PAL['concrete'][3] * 0.9, rect(cv, 0.66, 0.70, 0.68, 0.82))
    return cv.img


GROUPS.append((844, 1, 1, lambda: {844 + f: network(f) for f in range(8)}))


# ------------------------------------------------------------------ no-power sign 827
def no_power():
    cv = Canvas(1, 1, RS, dirt_layer())
    X, Y = cv.X, cv.Y
    red = hx('#d42a1c')
    cv.shade(cv.blur(rect(cv, 0.08 + 0.03, 0.08 + 0.02, 0.92 + 0.03, 0.92 + 0.02, 0.06), 0.01), 0.55)
    cv.paint(red * 0.7, rect(cv, 0.08, 0.08, 0.92, 0.92, 0.06))
    cv.paint(red, rect(cv, 0.09, 0.09, 0.90, 0.90, 0.05))
    cv.light(cv.cov(np.abs(sd_box(X, Y, 0.09, 0.09, 0.90, 0.90, 0.05)) - 0.006, 1.0) * (X + Y < 1.0), 0.45)
    panel = rect(cv, 0.17, 0.17, 0.83, 0.83, 0.03)
    cv.paint(PAL['concrete'](0.35 + 0.15 * (1 - Y)), panel)
    # red cross
    for (a, b) in (((0.2, 0.2), (0.8, 0.8)), ((0.8, 0.2), (0.2, 0.8))):
        cv.paint(red, cv.cov(sd_segment(X, Y, a[0], a[1], b[0], b[1]) - 0.028) * panel)
    pts = [(0.58, 0.18), (0.34, 0.53), (0.49, 0.53), (0.40, 0.84), (0.68, 0.44), (0.53, 0.44), (0.64, 0.18)]
    cv.shade(cv.blur(cv.poly([(x + 0.025, y + 0.02) for x, y in pts]), 0.006), 0.6)
    cv.paint(hx('#ffd21a'), cv.poly(pts, ss=2))
    cv.paint(hx('#fff3a0'), cv.poly([(0.58, 0.18), (0.36, 0.52), (0.40, 0.52), (0.61, 0.20)], ss=2))
    cv.paint(hx('#a07a00'), cv.cov(np.abs(cv.poly(pts) - 0.5) - 0.45, 1) * 0)
    return cv.img


GROUPS.append((827, 1, 1, lambda: {827: no_power()}))


# ------------------------------------------------------------------ 239: road N-S with power E-W (as 78)
def road_power_239():
    cv = Canvas(1, 1, RS, dirt_layer())
    TR.draw_road(cv, 'NS')
    TR.draw_power(cv, 'EW', pole=False)
    return cv.img


GROUPS.append((239, 1, 1, lambda: {239: road_power_239()}))


# ------------------------------------------------------------------ tile 1 and unused slots
def speckled_dirt():
    cv = Canvas(1, 1, RS, dirt_layer())
    rng = np.random.default_rng(1600)
    for _ in range(9):
        x, y = rng.uniform(0.12, 0.88, 2)
        r = rng.uniform(0.012, 0.022)
        cv.shade(cv.cov(sd_circle(cv.X, cv.Y, x + r * 0.5, y + r * 0.4, r), 2), 0.4)
        cv.paint(PAL['dirt'][1], cv.cov(sd_circle(cv.X, cv.Y, x, y, r)))
        cv.paint(PAL['dirt'][4], cv.cov(sd_circle(cv.X, cv.Y, x - r * 0.3, y - r * 0.3, r * 0.4), 2))
    return cv.img


UNUSED_WATER = [111, 127, 143, 159, 175, 191, 207]
UNUSED_DIRT = [38, 39, 53, 54, 55, 223] + list(range(868, 884)) + [956, 957, 958, 959]


def unused():
    d = {t: dirt_layer() for t in UNUSED_DIRT}
    d.update({t: water_layer() for t in UNUSED_WATER})
    d[1] = speckled_dirt()
    return d


GROUPS.append((1, 1, 1, unused))


# coal plant smoke (drawn in buildings.coal_group): frames -> the cell each replaces
ANIM.update({916 + f: 747 for f in range(4)})
ANIM.update({920 + f: 748 for f in range(4)})
ANIM.update({924 + f: 751 for f in range(4)})
ANIM.update({928 + f: 752 for f in range(4)})
