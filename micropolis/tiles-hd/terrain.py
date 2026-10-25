"""Terrain families: dirt, water, coast, trees, parks, rubble, fire, flood, radiation."""
import math
import numpy as np
from hdlib import *

_cache = {}


def cached(key, fn):
    if key not in _cache:
        _cache[key] = fn()
    return _cache[key]


# ------------------------------------------------------------------ ground
def dirt_layer(wt=1, ht=1, n=RS):
    """The ground every land tile starts from: periodic per tile, so all land joins."""
    def make():
        lo = fbm(n, 11, (2, 4), 0.6, wt, ht)
        mid = fbm(n, 12, (8, 16), 0.6, wt, ht)
        hi = fbm(n, 13, (48, 96), 0.7, wt, ht)
        t = 0.62 + 0.10 * (lo - 0.5) * 2 + 0.07 * (mid - 0.5) * 2 + 0.07 * (hi - 0.5) * 2
        img = PAL['dirt'](t)
        cv = Canvas(wt, ht, n, img)
        # pebbles: periodic scatter, light top-left, shade bottom-right
        rng = np.random.default_rng(7)
        pts = [(rng.random(), rng.random(), rng.uniform(0.008, 0.016)) for _ in range(26)]
        for (x, y, r) in wrap_points(pts, wt, ht):
            if not (-0.05 < x < wt + 0.05 and -0.05 < y < ht + 0.05):
                continue
            sh = sd_circle(cv.X, cv.Y, x + r * 0.5, y + r * 0.4, r)
            cv.shade(cv.cov(sh, 2.0), 0.35)
            d = sd_circle(cv.X, cv.Y, x, y, r)
            cv.paint(PAL['dirt'][3], cv.cov(d))
            hl = sd_circle(cv.X, cv.Y, x - r * 0.3, y - r * 0.3, r * 0.45)
            cv.paint(PAL['dirt'][7], cv.cov(hl, 2.0) * 0.8)
        # fine light grains
        g = pnoise(n, 128, 14, wt, ht)
        cv.light(smoothstep(0.80, 0.95, g), 0.25, PAL['dirt'][8])
        return cv.img
    return cached(('dirt', wt, ht, n), make).copy()


def grass_layer(wt=1, ht=1, n=RS):
    def make():
        lo = fbm(n, 21, (2, 4, 8), 0.6, wt, ht)
        hi = fbm(n, 22, (32, 64, 128), 0.7, wt, ht)
        t = 0.50 + 0.12 * (lo - 0.5) * 2 + 0.16 * (hi - 0.5) * 2
        img = PAL['grass'](t)
        cv = Canvas(wt, ht, n, img)
        blades = pnoise2(n, 160, 40, 23, wt, ht)
        cv.light(smoothstep(0.75, 0.95, blades), 0.25, PAL['grass'][7])
        cv.shade(smoothstep(0.25, 0.05, blades), 0.25)
        return cv.img
    return cached(('grass', wt, ht, n), make).copy()


# ------------------------------------------------------------------ water
def water_layer(wt=1, ht=1, n=RS):
    """Open water: deep lavender-blue (the original's #6666e6 family) with ripple dashes."""
    def make():
        lo = fbm(n, 31, (4, 8), 0.6, wt, ht)
        t = 0.515 + 0.035 * (lo - 0.5) * 2
        img = PAL['water'](t)
        cv = Canvas(wt, ht, n, img)
        # ripples: horizontally stretched noise -> short dashes, dark troughs + light crests
        r1 = pnoise2(n, 16, 52, 32, wt, ht)
        r2 = pnoise2(n, 22, 64, 33, wt, ht)
        rip = 0.55 * r1 + 0.45 * r2
        cv.paint(PAL['water'][2], smoothstep(0.66, 0.76, rip) * 0.55)
        cv.paint(PAL['water'][3], smoothstep(0.58, 0.66, rip) * smoothstep(0.76, 0.68, rip) * 0.30)
        crest = pnoise2(n, 18, 60, 34, wt, ht) * 0.6 + pnoise2(n, 26, 80, 35, wt, ht) * 0.4
        cv.paint(PAL['water'][7], smoothstep(0.66, 0.76, crest) * 0.45)
        cv.paint(PAL['water'][8], smoothstep(0.76, 0.84, crest) * 0.5)
        return cv.img
    return cached(('water', wt, ht, n), make).copy()


def coast_noise(n=RS):
    return cached(('coastn', n), lambda: (fbm(n, 41, (3, 6, 12), 0.5) - 0.5) * 0.10)


# depth of the land strip a coast tile keeps along a land-facing edge
COAST_D = 0.24


def coast_sdf(X, Y, land_sides, d=COAST_D, k=0.32):
    """Positive = water. land_sides: subset of 'NESW'."""
    terms = []
    for s in land_sides:
        dist = {'N': Y, 'S': 1 - Y, 'W': X, 'E': 1 - X}[s]
        terms.append(dist - d)
    if not terms:
        return np.full_like(X, 1.0)
    sd = terms[0]
    for t in terms[1:]:
        sd = smin(sd, t, k)
    return sd


def coast_tile(land_sides, variant=0, n=RS):
    cv = Canvas(1, 1, n)
    sd = coast_sdf(cv.X, cv.Y, land_sides) + coast_noise(n)
    land = dirt_layer(1, 1, n)
    water = water_layer(1, 1, n)
    # shallow tint near the shore
    depth = smoothstep(0.0, 0.34, sd)
    sh = PAL['shallow'](0.55 - 0.45 * smoothstep(0.0, 0.2, sd) + 0.1 * coast_noise(n) * 10)
    wimg = water * depth[..., None] + sh * (1 - depth[..., None])
    # ripples fade in with depth: already in water layer; lighten shallows sand showing through
    cv.img = land
    # beach: dirt -> dry sand -> wet sand
    beach = smoothstep(-0.13, -0.03, sd)
    sandn = pnoise(n, 64, 42)
    cv.paint(PAL['sand'](0.62 + 0.25 * (sandn - 0.5)), beach)
    cv.paint(PAL['sand'](0.30 + 0.15 * (sandn - 0.5)), smoothstep(-0.045, -0.005, sd) * 0.85)
    # water
    wa = cv.cov(-sd, 1.5)
    cv.img = cv.img * (1 - wa[..., None]) + wimg * wa[..., None]
    # foam line + soft swash
    swash = smoothstep(0.0, 0.012, sd) * smoothstep(0.05, 0.012, sd)
    foamn = pnoise2(n, 6, 24, 43)
    cv.paint(PAL['water'][9], swash * (0.45 + 0.5 * smoothstep(0.35, 0.7, foamn)))
    second = smoothstep(0.045, 0.06, sd) * smoothstep(0.085, 0.06, sd)
    cv.paint(PAL['water'][8], second * 0.35 * smoothstep(0.45, 0.75, foamn))
    if variant:
        # a few shore rocks, kept well inside the tile
        rng = np.random.default_rng(100 + hash(land_sides) % 1000)
        for _ in range(3):
            for _try in range(40):
                x, y = rng.uniform(0.2, 0.8, 2)
                s = coast_sdf(np.array([[x]]), np.array([[y]]), land_sides)[0, 0]
                if -0.06 < s < 0.04:
                    break
            r = rng.uniform(0.018, 0.03)
            cv.shade(cv.cov(sd_circle(cv.X, cv.Y, x + r * 0.6, y + r * 0.35, r), 2), 0.5)
            cv.paint(PAL['concrete'][3], cv.cov(sd_circle(cv.X, cv.Y, x, y, r)))
            cv.paint(PAL['concrete'][6], cv.cov(sd_circle(cv.X, cv.Y, x - r * .35, y - r * .35, r * .45), 2) * .8)
    return cv.img


# REdTab semantics: tile -> sides that face land (edge tiles 5..20, pairs n, n+1)
COAST_TILES = {
    5: 'N', 13: 'S', 17: 'W', 9: 'E',
    15: 'SW', 19: 'NW', 11: 'SE', 7: 'NE',
}


# ------------------------------------------------------------------ trees
LIGHT = np.array([-0.55, -0.45, 0.70])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def crown_list(seed=51, grid=6, rmin=0.095, rmax=0.125):
    rng = np.random.default_rng(seed)
    pts = []
    for j in range(grid):
        for i in range(grid):
            x = (i + 0.5 + rng.uniform(-0.38, 0.38)) / grid
            y = (j + 0.5 + rng.uniform(-0.38, 0.38)) / grid
            pts.append((x % 1, y % 1, rng.uniform(rmin, rmax), rng.integers(1 << 30)))
    return pts


def draw_crown(cv, x, y, r, seed, ramp=None, hue=0.0):
    ramp = ramp or PAL['leaf']
    ang = np.arctan2(cv.Y - y, cv.X - x)
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 6.28, 3)
    rr = r * (1 + 0.07 * np.sin(5 * ang + ph[0]) + 0.05 * np.sin(8 * ang + ph[1]) + 0.04 * np.sin(13 * ang + ph[2]))
    d = np.hypot(cv.X - x, cv.Y - y)
    m = cv.cov(d - rr, 1.3)
    if m.max() <= 0:
        return
    nx = (cv.X - x) / r
    ny = (cv.Y - y) / r
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
    lam = np.clip(nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2], 0, 1)
    leaves = cached(('leafn', cv.wt, cv.ht, cv.n), lambda: pnoise(cv.n, 40, 52, cv.wt, cv.ht) * 0.6 + pnoise(cv.n, 80, 53, cv.wt, cv.ht) * 0.4)
    t = 0.12 + 0.78 * lam + 0.30 * (leaves - 0.5) + hue
    cv.paint(ramp(t), m)


def forest(cv, include, seed=51, ground_shade=True, hue_seed=0):
    """Periodic canopy. include(x, y) -> bool decides each crown (by its centre)."""
    pts = [p for p in wrap_points(crown_list(seed), cv.wt, cv.ht) if include(p[0], p[1])]
    pts = [p for p in pts if -0.2 < p[0] < cv.wt + 0.2 and -0.2 < p[1] < cv.ht + 0.2]
    # shadows first (cast right/down), as one soft layer
    sh = np.zeros_like(cv.X)
    for (x, y, r, s) in pts:
        sx, sy = x + SHADOW_DIR[0] * 0.10, y + SHADOW_DIR[1] * 0.10
        sh = np.maximum(sh, cv.cov(sd_circle(cv.X, cv.Y, sx, sy, r * 1.02), 6))
    cv.shade(sh, 0.55)
    # crowns, north to south so southern crowns overlap
    rng = np.random.default_rng(hue_seed)
    for (x, y, r, s) in sorted(pts, key=lambda p: (p[1], p[0])):
        hue = ((s % 7) - 3) * 0.015
        draw_crown(cv, x, y, r, s, hue=hue)


def tree_field(X, Y, open_sides, d=0.30, k=0.2):
    return coast_sdf(X, Y, open_sides, d, k)


def tree_tile(open_sides, variant=0, n=RS):
    cv = Canvas(1, 1, n, dirt_layer(1, 1, n))
    tn = cached(('treen',), lambda: None)
    def inside(x, y):
        X, Y = np.array([[x]]), np.array([[y]])
        # evaluate the field with the tile's own formula (also beyond its edge)
        return tree_field(X, Y, open_sides)[0, 0] + 0.05 * math.sin(2 * math.pi * x + 1.3) * math.cos(4 * math.pi * y + 0.4) > 0
    # litter under the canopy region
    f = tree_field(cv.X, cv.Y, open_sides)
    cv.paint(PAL['dirt'][2], smoothstep(-0.14, 0.0, f) * 0.5)
    cv.paint(PAL['leaf'][1], smoothstep(-0.02, 0.10, f) * 0.85)
    forest(cv, inside)
    return cv.img


# treeTable: tile -> sides WITHOUT tree neighbours (open sides)
TREE_TILES = {
    34: 'SW', 36: 'NW', 35: 'W', 32: 'SE', 33: 'S', 30: 'NE', 31: 'E', 29: 'N', 37: '',
}


def woods_tile(n=RS):
    return tree_tile('', n=n)


def park_tile(k, n=RS):
    cv = Canvas(1, 1, n, grass_layer(1, 1, n))
    rng = np.random.default_rng(600 + k)
    # flowers / clover specks
    for _ in range(40):
        x, y = rng.uniform(0.05, 0.95, 2)
        col = [hx('#f4f0d8'), hx('#f2d64b'), hx('#e86a8a'), hx('#c9b6f0')][rng.integers(4)]
        cv.paint(col, cv.cov(sd_circle(cv.X, cv.Y, x, y, 0.007), 1.5) * 0.9)
    layouts = [
        [(0.32, 0.36, 0.13), (0.68, 0.64, 0.11)],
        [(0.5, 0.40, 0.16)],
        [(0.28, 0.30, 0.10), (0.70, 0.32, 0.10), (0.48, 0.70, 0.12)],
        [(0.62, 0.40, 0.14), (0.30, 0.70, 0.09)],
    ][k]
    if k == 1:
        # a small gravel patch with a bench beside the tree
        d = sd_box(cv.X, cv.Y, 0.30, 0.66, 0.70, 0.80, 0.05)
        cv.paint(PAL['sand'](0.7 + 0.2 * (pnoise(n, 48, 610) - 0.5)), cv.cov(d) * 0.9)
        cv.shade(cv.cov(sd_box(cv.X, cv.Y, 0.40, 0.70, 0.62, 0.745, 0.008) , 2), 0.5)
        cv.paint(PAL['timber'][3], cv.cov(sd_box(cv.X, cv.Y, 0.38, 0.69, 0.60, 0.725, 0.006)))
        cv.paint(PAL['timber'][5], cv.cov(sd_box(cv.X, cv.Y, 0.38, 0.69, 0.60, 0.70, 0.004)))
    sh = np.zeros_like(cv.X)
    for (x, y, r) in layouts:
        sh = np.maximum(sh, cv.cov(sd_circle(cv.X, cv.Y, x + SHADOW_DIR[0] * .1, y + SHADOW_DIR[1] * .1, r), 5))
    cv.shade(sh, 0.55)
    for i, (x, y, r) in enumerate(layouts):
        draw_crown(cv, x, y, r, 700 + 10 * k + i, hue=0.05)
    return cv.img


# ------------------------------------------------------------------ rubble, fire, flood, radiation
def rubble_tile(k, n=RS):
    cv = Canvas(1, 1, n, dirt_layer(1, 1, n))
    cv.paint(PAL['dirt'][3], smoothstep(0.45, 0.7, pnoise(n, 6, 900 + k)) * 0.6)
    rng = np.random.default_rng(910 + k)
    for _ in range(26):
        x, y = rng.uniform(0.08, 0.92, 2)
        r = rng.uniform(0.02, 0.06)
        m = rng.integers(3, 6)
        a0 = rng.uniform(0, 6.28)
        pts = [(x + r * math.cos(a0 + 6.28 * i / m) * rng.uniform(0.6, 1.2), y + r * math.sin(a0 + 6.28 * i / m) * rng.uniform(0.6, 1.2)) for i in range(m)]
        shp = [(px + 0.015, py + 0.01) for px, py in pts]
        cv.shade(cv.poly(shp), 0.5)
        col = PAL['concrete'](rng.uniform(0.25, 0.7)) if rng.random() < 0.7 else PAL['brick'](rng.uniform(0.3, 0.6))
        cv.paint(col, cv.poly(pts))
        cv.light(cv.poly([(px - 0.004, py - 0.004) for px, py in pts[:2]] + [(x, y)]), 0.25)
    return cv.img


def _scroll_noise(cv, px, py, seed, ph):
    rng = np.random.default_rng(seed)
    L = rng.random((py, px))
    u = cv.X * px
    v = (cv.Y + ph) * py
    i0 = np.floor(u).astype(int); j0 = np.floor(v).astype(int)
    fu = u - i0; fv = v - j0
    fu = fu * fu * (3 - 2 * fu); fv = fv * fv * (3 - 2 * fv)
    a = L[j0 % py, i0 % px]; b = L[j0 % py, (i0 + 1) % px]
    c = L[(j0 + 1) % py, i0 % px]; d = L[(j0 + 1) % py, (i0 + 1) % px]
    return (a * (1 - fu) + b * fu) * (1 - fv) + (c * (1 - fu) + d * fu) * fv


def fire_tile(frame, n=RS):
    """8-frame loop: flame tongues scroll up one tile per cycle (periodic in time and space)."""
    cv = Canvas(1, 1, n, dirt_layer(1, 1, n))
    char = pnoise(n, 24, 975)
    cv.paint(hx('#2b1d18') * (0.8 + 0.4 * char[..., None]), 0.85 * np.ones_like(cv.X))
    ph = frame / 8.0
    f = (0.50 * _scroll_noise(cv, 6, 2, 970, ph) + 0.30 * _scroll_noise(cv, 12, 4, 971, ph * 2 % 1)
         + 0.20 * _scroll_noise(cv, 24, 8, 972, ph * 4 % 1))
    base = pnoise2(n, 5, 1, 973)                       # where the fire burns hardest (static)
    heat = (f - 0.50) * 3.0 + 0.9 * (cv.Y - 0.35) + 0.5 * (base - 0.5)
    heat = np.clip(heat, 0, 1)
    glow = cv.blur(heat, 0.05)
    cv.paint(hx('#8a3010'), np.clip(glow * 1.6, 0, 1) * 0.6)
    cv.paint(PAL['fire'](0.15 + 0.85 * heat), smoothstep(0.05, 0.22, heat))
    cv.light(smoothstep(0.85, 1.0, heat), 0.3, (1, 1, 0.9))
    rng = np.random.default_rng(980 + frame)
    for _ in range(12):
        x, y = rng.uniform(0.05, 0.95), rng.uniform(0.05, 0.5)
        cv.paint(PAL['fire'][6], cv.cov(sd_circle(cv.X, cv.Y, x, y, 0.007), 1.5))
    return cv.img


def flood_tile(k, n=RS):
    cv = Canvas(1, 1, n, water_layer(1, 1, n))
    cv.paint(hx('#6e6a8a'), 0.25 * np.ones_like(cv.X))  # muddy
    rng = np.random.default_rng(1200 + k)
    for _ in range(9):
        x, y = rng.uniform(0.1, 0.9, 2)
        w, h = rng.uniform(0.03, 0.09), rng.uniform(0.015, 0.03)
        d = sd_box(cv.X, cv.Y, x - w, y - h, x + w, y + h, 0.006)
        cv.paint(PAL['water'][9], cv.cov(d) * 0.85)
        cv.paint(PAL['water'][7], cv.cov(np.abs(d + 0.0) - 0.01, 2) * 0.3)
    return cv.img


def radiation_tile(n=RS):
    cv = Canvas(1, 1, n, dirt_layer(1, 1, n))
    cv.paint(hx('#8a8a30'), smoothstep(0.5, 0.0, np.hypot(cv.X - .5, cv.Y - .5)) * 0.35)
    r = np.hypot(cv.X - 0.5, cv.Y - 0.5)
    a = np.arctan2(cv.Y - 0.5, cv.X - 0.5)
    blade = (np.cos(3 * (a + math.pi / 2)) > 0.5) & (r > 0.09) & (r < 0.33)
    m = blade.astype(float)
    m = ndimage.uniform_filter(m, 3)
    cv.shade(np.roll(np.roll(m, 6, 0), 8, 1), 0.5)
    cv.paint(hx('#e8c818'), m)
    cv.paint(hx('#e8c818'), cv.cov(r - 0.065))
    cv.paint(hx('#1a1a1a'), cv.cov(np.abs(r - 0.36) - 0.012))
    return cv.img
