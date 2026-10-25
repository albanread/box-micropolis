"""A tiny oblique 'scene' renderer for buildings: boxes, gable roofs, cylinders, trees.

Projection: (x, y, z) -> (x + OX*z, y - OY*z). Visible walls: west (lit) and south (shade).
Items are collected, then drawn: all drop shadows first, then bodies far-to-near
(far = north and east, i.e. ascending y - x of the footprint centre).
"""
import math
import numpy as np
from hdlib import *
from terrain import draw_crown

LIGHT_W = 1.00   # west wall brightness factor
LIGHT_S = 0.64   # south wall
LIGHT_ROOF = 1.06


def P(x, y, z):
    return (x + OX * z, y - OY * z)


def face_uv(cv, O, U, V):
    """Inverse of screen = O + u*U + v*V (2D) for every pixel."""
    det = U[0] * V[1] - U[1] * V[0]
    dx, dy = cv.X - O[0], cv.Y - O[1]
    u = (dx * V[1] - dy * V[0]) / det
    v = (U[0] * dy - U[1] * dx) / det
    return u, v


def hull(pts):
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


# ------------------------------------------------------------------ window styles
def windows(u, v, lu, lv, style, seed=0):
    """Return (mask_glass, mask_frame) for face coords u (along) v (height)."""
    if style is None:
        return None, None
    kind = style.get('kind', 'grid')
    m = (u > 0) & (u < lu) & (v > 0) & (v < lv)
    if kind == 'grid':
        fh = style.get('floor', 0.12)
        cw = style.get('col', 0.09)
        wf = style.get('wfrac', 0.55)
        hf = style.get('hfrac', 0.55)
        base = style.get('base', 0.04)
        top = style.get('top', 0.02)
        uu = (u - style.get('margin', 0.03)) / cw
        vv = (v - base) / fh
        inu = (np.abs((uu % 1) - 0.5) < wf / 2) & (u > style.get('margin', 0.03)) & (u < lu - style.get('margin', 0.03))
        inv = (np.abs((vv % 1) - 0.5) < hf / 2) & (v > base) & (v < lv - top)
        g = (inu & inv & m).astype(float)
        return g, None
    if kind == 'bands':   # office: continuous glass bands with mullions
        fh = style.get('floor', 0.10)
        vv = (v - 0.03) / fh
        inv = (np.abs((vv % 1) - 0.5) < 0.36) & (v > 0.03) & (v < lv - 0.03)
        mull = np.abs(((u / style.get('col', 0.06)) % 1) - 0.5) > 0.42
        g = (inv & m & (u > 0.02) & (u < lu - 0.02)).astype(float)
        return g, (mull & inv & m).astype(float)
    if kind == 'curtain':  # full glass with grid
        g = (m & (u > 0.015) & (u < lu - 0.015) & (v > 0.02) & (v < lv - 0.015)).astype(float)
        fr = ((np.abs(((u / style.get('col', 0.07)) % 1) - 0.5) > 0.44) | (np.abs(((v / style.get('floor', 0.08)) % 1) - 0.5) > 0.42)) & (g > 0)
        return g, fr.astype(float)
    if kind == 'ribs':    # corrugated cladding: no glass, just vertical ribs
        r = (np.abs(((u / style.get('col', 0.03)) % 1) - 0.5) > 0.3) & m
        return None, r.astype(float)
    if kind == 'doors':   # garage / apparatus doors along the bottom
        n = style.get('n', 3)
        w = lu / n
        k = np.floor(u / w)
        within = np.abs((u - (k + 0.5) * w)) < w * 0.36
        g = (within & (v > 0.0) & (v < style.get('h', 0.16)) & m).astype(float)
        return g, None
    return None, None


# ------------------------------------------------------------------ items
class Box:
    def __init__(self, x0, y0, x1, y1, h, wall, roof, win=None, win_w=None, parapet=True,
                 roof_detail=None, z0=0.0, label=None, label_col=None, label_size=0.5, label_font=None,
                 shadow=True, glass=None, rim=None, ao=True):
        self.__dict__.update(locals())
        del self.__dict__['self']
        self.win_w = win_w if win_w is not None else win

    def key(self):
        return ((self.y0 + self.y1) / 2 - (self.x0 + self.x1) / 2, self.z0)

    def shadow_poly(self):
        x0, y0, x1, y1, h = self.x0, self.y0, self.x1, self.y1, self.h + self.z0
        foot = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        sx, sy = SHADOW_DIR * h
        return hull(foot + [(x + sx, y + sy) for x, y in foot])

    def draw(self, cv):
        x0, y0, x1, y1, h, z0 = self.x0, self.y0, self.x1, self.y1, self.h, self.z0
        zt = z0 + h
        wall = np.asarray(self.wall, float)
        glass = PAL['glass'] if self.glass is None else self.glass
        # west face
        O = P(x0, y1, z0)
        U = (0.0, -1.0)
        V = (OX, -OY)
        poly = [P(x0, y0, z0), P(x0, y1, z0), P(x0, y1, zt), P(x0, y0, zt)]
        m = cv.poly(poly)
        u, v = face_uv(cv, O, U, V)
        lu, lv = y1 - y0, h
        col = wall * LIGHT_W * (0.92 + 0.10 * np.clip(v / max(lv, 1e-3), 0, 1))[..., None]
        if self.ao:
            col = col * (1 - 0.25 * np.exp(-(v + z0) / 0.05))[..., None]
        cv.paint(col, m)
        self._windows(cv, m, u, v, lu, lv, self.win_w, lit=True, glass=glass)
        # south face
        O = P(x0, y1, z0)
        U = (1.0, 0.0)
        poly = [P(x0, y1, z0), P(x1, y1, z0), P(x1, y1, zt), P(x0, y1, zt)]
        m = cv.poly(poly)
        u, v = face_uv(cv, O, U, V)
        lu = x1 - x0
        col = wall * LIGHT_S * (0.92 + 0.12 * np.clip(v / max(lv, 1e-3), 0, 1))[..., None]
        if self.ao:
            col = col * (1 - 0.25 * np.exp(-(v + z0) / 0.05))[..., None]
        cv.paint(col, m)
        self._windows(cv, m, u, v, lu, lv, self.win, lit=False, glass=glass)
        # edge highlight on the south-west vertical corner
        a, b = P(x0, y1, z0), P(x0, y1, zt)
        cv.light(cv.cov(sd_segment(cv.X, cv.Y, a[0], a[1], b[0], b[1]) - 0.004, 1.0) * m.max(), 0.25)
        # roof
        rx0, ry0 = P(x0, y0, zt)
        rx1, ry1 = P(x1, y1, zt)
        rm = cv.poly([(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)])
        roof = self.roof
        if callable(roof):
            rc = roof(cv, rx0, ry0, rx1, ry1)
        else:
            rn = cached_noise(cv)
            rg = cached_grain(cv)
            rc = np.asarray(roof, float) * LIGHT_ROOF * (0.95 + 0.10 * (rn - 0.5) * 2 + 0.07 * (rg - 0.5) * 2)[..., None]
            # weathering: slightly lighter toward the lit north-west corner
            gx = np.clip((cv.X - rx0) / max(rx1 - rx0, 1e-3), 0, 1)
            gy = np.clip((cv.Y - ry0) / max(ry1 - ry0, 1e-3), 0, 1)
            rc = rc * (1.04 - 0.08 * (gx + gy) / 2)[..., None]
        cv.paint(rc, rm)
        # seams of the roofing sheets
        if not callable(roof) and self.parapet:
            seam = (np.abs(((cv.X - rx0) / 0.16) % 1 - 0.5) > 0.47).astype(float)
            cv.shade(seam * rm, 0.10)
        if self.parapet:
            t = 0.018
            inner = sd_box(cv.X, cv.Y, rx0 + t, ry0 + t, rx1 - t, ry1 - t)
            rim = cv.cov(-inner, 1.0) * rm
            rimc = np.asarray(self.rim if self.rim is not None else (np.asarray(roof if not callable(roof) else wall) * 1.25), float)
            cv.paint(np.clip(rimc, 0, 1), rim)
            # inner shadow cast by the parapet onto the roof (light from upper left)
            sh = cv.cov(sd_box(cv.X, cv.Y, rx0 + t, ry0 + t, rx0 + t + 0.02, ry1 - t), 2) + cv.cov(sd_box(cv.X, cv.Y, rx0 + t, ry0 + t, rx1 - t, ry0 + t + 0.02), 2)
            cv.shade(np.clip(sh, 0, 1) * rm * (1 - rim), 0.30)
        if self.roof_detail:
            self.roof_detail(cv, rx0, ry0, rx1, ry1)
        if self.label:
            m = cv.text_mask(self.label, (rx0 + rx1) / 2, (ry0 + ry1) / 2, self.label_size, self.label_font or FONT_SERIF)
            sh = np.roll(np.roll(m, int(0.012 * cv.n), 0), int(0.016 * cv.n), 1)
            cv.shade(sh * rm, 0.6)
            cv.paint(self.label_col, m * rm)
            e = np.clip(m - np.roll(np.roll(m, 2, 0), 2, 1), 0, 1)
            cv.light(e * rm, 0.45)

    def _windows(self, cv, m, u, v, lu, lv, style, lit, glass):
        if style is None:
            return
        g, fr = windows(u, v, lu, lv, style)
        if g is None:
            if fr is not None:
                cv.shade(fr * m, 0.22 if lit else 0.3)
                hl = np.roll(fr, -2, 1) * (1 - fr)
                cv.light(hl * m, 0.12)
            return
        if style.get('glass') is not None:
            glass = style['glass']
        # glass: sky reflection, lighter toward the top, darker on the shaded face
        t = (0.30 if not lit else 0.55) + 0.30 * np.clip(v / max(lv, 1e-3), 0, 1) + 0.12 * np.clip(1 - u / max(lu, 1e-3), 0, 1)
        gc = glass(t)
        if style.get('warm'):
            rng = cached_rand(cv)
            warm = (rng > 0.82)
            gc = np.where(warm[..., None], hx('#f6d27a') * (0.8 if not lit else 0.95), gc)
        cv.paint(gc, g * m)
        if style.get('sill', True) and style.get('kind', 'grid') == 'grid':
            sill = np.roll(g, -2, 0) * (1 - g)
            cv.light(sill * m, 0.35)
        if fr is not None:
            cv.paint(np.asarray(style.get('frame', (0.75, 0.77, 0.80))) * (0.9 if lit else 0.6), fr * m)


_noise_cache = {}


def cached_noise(cv):
    k = ('rn', cv.W, cv.H)
    if k not in _noise_cache:
        _noise_cache[k] = pnoise(cv.n, 48, 501, cv.wt, cv.ht)
    return _noise_cache[k]


def cached_grain(cv):
    k = ('rg', cv.W, cv.H)
    if k not in _noise_cache:
        _noise_cache[k] = pnoise(cv.n, 160, 502, cv.wt, cv.ht)
    return _noise_cache[k]


def cached_rand(cv):
    k = ('rr', cv.W, cv.H)
    if k not in _noise_cache:
        rng = np.random.default_rng(5)
        cells = rng.random((cv.H // 6 + 1, cv.W // 6 + 1))
        _noise_cache[k] = np.kron(cells, np.ones((6, 6)))[:cv.H, :cv.W]
    return _noise_cache[k]


class Gable:
    """Pitched-roof house: walls to h, ridge rh above, ridge along 'x' or 'y'."""

    def __init__(self, x0, y0, x1, y1, h, rh, wall, roof, ridge='x', win=None, door=True):
        self.__dict__.update(locals())
        del self.__dict__['self']

    def key(self):
        return ((self.y0 + self.y1) / 2 - (self.x0 + self.x1) / 2, 0)

    def shadow_poly(self):
        x0, y0, x1, y1 = self.x0, self.y0, self.x1, self.y1
        h = self.h + self.rh * 0.6
        foot = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        sx, sy = SHADOW_DIR * h
        return hull(foot + [(x + sx, y + sy) for x, y in foot])

    def draw(self, cv):
        x0, y0, x1, y1, h, rh = self.x0, self.y0, self.x1, self.y1, self.h, self.rh
        wall = np.asarray(self.wall, float)
        # walls
        b = Box(x0, y0, x1, y1, h, wall, wall, win=self.win, parapet=False)
        b.draw(cv)
        roof = PAL[self.roof] if isinstance(self.roof, str) else self.roof
        tex = cached_noise(cv)
        if self.ridge == 'x':
            ym = (y0 + y1) / 2
            e = 0.02
            north = [P(x0 - e, y0 - e, h), P(x1 + e, y0 - e, h), P(x1 + e, ym, h + rh), P(x0 - e, ym, h + rh)]
            south = [P(x0 - e, ym, h + rh), P(x1 + e, ym, h + rh), P(x1 + e, y1 + e, h), P(x0 - e, y1 + e, h)]
            gable = [P(x0, y0, h), P(x0, y1, h), P(x0, ym, h + rh)]
            cv.paint(wall * LIGHT_W, cv.poly(gable))
            mN = cv.poly(north)
            mS = cv.poly(south)
            # tile courses
            courses = (np.abs(((cv.Y * 16) % 1) - 0.5) > 0.36).astype(float)
            cv.paint(roof(0.70 + 0.1 * (tex - 0.5)), mN)
            cv.shade(courses * mN, 0.12)
            cv.paint(roof(0.42 + 0.1 * (tex - 0.5)), mS)
            cv.shade(courses * mS, 0.15)
            a, b2 = P(x0 - e, ym, h + rh), P(x1 + e, ym, h + rh)
            cv.paint(roof(0.9), cv.cov(sd_segment(cv.X, cv.Y, a[0], a[1], b2[0], b2[1]) - 0.006, 1.0))
        else:
            xm = (x0 + x1) / 2
            e = 0.02
            west = [P(x0 - e, y0 - e, h), P(xm, y0 - e, h + rh), P(xm, y1 + e, h + rh), P(x0 - e, y1 + e, h)]
            east = [P(xm, y0 - e, h + rh), P(x1 + e, y0 - e, h), P(x1 + e, y1 + e, h), P(xm, y1 + e, h + rh)]
            gable = [P(x0, y1, h), P(x1, y1, h), P(xm, y1, h + rh)]
            courses = (np.abs(((cv.X * 16) % 1) - 0.5) > 0.36).astype(float)
            mE = cv.poly(east)
            cv.paint(roof(0.40 + 0.1 * (tex - 0.5)), mE)
            cv.shade(courses * mE, 0.15)
            mW = cv.poly(west)
            cv.paint(roof(0.74 + 0.1 * (tex - 0.5)), mW)
            cv.shade(courses * mW, 0.12)
            cv.paint(wall * LIGHT_S, cv.poly(gable))
            a, b2 = P(xm, y0 - e, h + rh), P(xm, y1 + e, h + rh)
            cv.paint(roof(0.9), cv.cov(sd_segment(cv.X, cv.Y, a[0], a[1], b2[0], b2[1]) - 0.006, 1.0))


class Cylinder:
    def __init__(self, cx, cy, r, h, col, top=None, z0=0.0, hollow=False, bands=None):
        self.__dict__.update(locals())
        del self.__dict__['self']

    def key(self):
        return (self.cy - self.cx, self.z0)

    def shadow_poly(self):
        n = 16
        h = self.h + self.z0
        pts = []
        for k in range(n):
            a = 2 * math.pi * k / n
            x, y = self.cx + self.r * math.cos(a), self.cy + self.r * math.sin(a)
            pts += [(x, y), (x + SHADOW_DIR[0] * h, y + SHADOW_DIR[1] * h)]
        return hull(pts)

    def draw(self, cv):
        bx, by = P(self.cx, self.cy, self.z0)
        tx, ty = P(self.cx, self.cy, self.z0 + self.h)
        r = self.r
        d = sd_segment(cv.X, cv.Y, bx, by, tx, ty)
        m = cv.cov(d - r)
        # normal across the axis
        ax, ay = tx - bx, ty - by
        L = math.hypot(ax, ay) + 1e-9
        nx, ny = -ay / L, ax / L   # perpendicular (points to upper-left for an up-right axis)
        side = ((cv.X - bx) * nx + (cv.Y - by) * ny) / r
        lam = np.clip(0.55 + 0.45 * side, 0, 1) ** 0.9
        col = np.asarray(self.col, float)
        c = col[None, None, :] * (0.45 + 0.65 * lam)[..., None]
        cv.paint(c, m)
        # specular streak on the lit side
        cv.light(np.exp(-((side - 0.55) / 0.12) ** 2) * m, 0.25)
        if self.bands:
            for (z, w, bc) in self.bands:
                cx_, cy_ = P(self.cx, self.cy, self.z0 + z)
                band = cv.cov(sd_circle(cv.X, cv.Y, cx_, cy_, r + 0.002)) * (1 - cv.cov(sd_circle(cv.X, cv.Y, cx_ + OX * w, cy_ - OY * w, r + 0.002)))
                cv.paint(np.asarray(bc) * (0.5 + 0.6 * lam)[..., None], band * m)
        top = np.asarray(self.top if self.top is not None else col * 1.15, float)
        cv.paint(np.clip(top, 0, 1), cv.cov(sd_circle(cv.X, cv.Y, tx, ty, r)))
        if self.hollow:
            cv.paint(hx('#141414'), cv.cov(sd_circle(cv.X, cv.Y, tx + 0.003, ty + 0.003, r * 0.68)))
        else:
            cv.light(cv.cov(sd_circle(cv.X, cv.Y, tx - r * 0.3, ty - r * 0.3, r * 0.5), 3), 0.2)


class Tree:
    def __init__(self, x, y, r, seed=0, hue=0.0):
        self.__dict__.update(locals())
        del self.__dict__['self']

    def key(self):
        return (self.y - self.x, 0.5)

    def shadow_poly(self):
        return None

    def shadow(self, cv):
        return cv.cov(sd_circle(cv.X, cv.Y, self.x + SHADOW_DIR[0] * 0.12, self.y + SHADOW_DIR[1] * 0.12, self.r), 5)

    def draw(self, cv):
        draw_crown(cv, self.x + OX * 0.08, self.y - OY * 0.08, self.r, self.seed, hue=self.hue)


class Custom:
    """Arbitrary drawing callback participating in ordering."""

    def __init__(self, fn, key=(0, 0), shadow=None):
        self.fn, self._key, self._shadow = fn, key, shadow

    def key(self):
        return self._key

    def shadow_poly(self):
        return self._shadow

    def draw(self, cv):
        self.fn(cv)


def render(cv, items, shadow_strength=0.62):
    sh = np.zeros_like(cv.X)
    for it in items:
        if hasattr(it, 'shadow') and callable(getattr(it, 'shadow')) and isinstance(it, Tree):
            sh = np.maximum(sh, it.shadow(cv))
            continue
        p = it.shadow_poly()
        if p:
            sh = np.maximum(sh, cv.poly(p))
    sh = cv.blur(sh, 0.008)
    cv.shade(sh, shadow_strength)
    for it in sorted(items, key=lambda i: i.key()):
        it.draw(cv)
