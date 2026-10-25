"""hdlib: primitives for the Micropolis HD tile redraw.

Everything is drawn in tile units (one tile = 1.0) on a supersampled canvas
(RS px per tile) and box-filtered down to 128/64/32 px at the end.

Conventions (see STYLE.md):
  * light from the upper left (west-north-west), high sun;
  * height is drawn as an oblique offset up and to the right (OX, -OY per unit);
  * visible walls are the west face (lit) and the south face (shade);
  * drop shadows fall to the right and slightly down (SHADOW_DIR per unit height);
  * every texture is periodic with period 1 tile, so any two tiles that agree
    on what crosses an edge join exactly.
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

RS = 256            # supersampled pixels per tile
OX, OY = 0.50, 0.50  # oblique projection of one unit of height
SHADOW_DIR = np.array([0.80, 0.42])  # ground offset of a shadow per unit height
SHADOW_COL = np.array([0.40, 0.41, 0.54])  # multiplier at full shade (cool, slightly blue)


def hx(s):
    s = s.lstrip('#')
    return np.array([int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


class Ramp:
    """A material: an ordered list of shades, dark to light."""

    def __init__(self, hexes):
        self.c = np.array([hx(h) for h in hexes])

    def __call__(self, t):
        t = np.clip(np.asarray(t, float), 0, 1) * (len(self.c) - 1)
        i = np.clip(np.floor(t).astype(int), 0, len(self.c) - 2)
        f = (t - i)[..., None]
        return self.c[i] * (1 - f) + self.c[i + 1] * f

    def __getitem__(self, k):
        return self.c[k]

    def hexes(self):
        return ['#%02x%02x%02x' % tuple(int(round(v * 255)) for v in c) for c in self.c]


# ---------------------------------------------------------------- palette
PAL = {
    # anchor: original #cc7f66 is index 5
    'dirt':    Ramp(['#4a2a20', '#6a3d2f', '#8a513e', '#a7634c', '#bc7259', '#cc7f66', '#d78e74', '#e2a287', '#ecb99f']),
    # wet sand / beach; original shore brown #997f4c is index 2
    'sand':    Ramp(['#6d5734', '#866c42', '#997f4c', '#b39a63', '#cbb37d', '#dccb9a', '#ebdfba']),
    # water: original #6666e6 (index 5) and dot blue #0000e6
    'water':   Ramp(['#14146a', '#1c1c8c', '#2626ac', '#3636c6', '#4c4cd8', '#6666e6', '#8282ee', '#a3a6f4', '#c8ccfa', '#eef0ff']),
    'shallow': Ramp(['#4c58d8', '#5c70e0', '#6e88e6', '#86a2ec', '#a2bcf0', '#c2d6f4']),
    # grass: original #00e600 / #007f00, pulled to a calmer, deeper green
    'grass':   Ramp(['#0b3410', '#124a16', '#1a621d', '#237b25', '#30942d', '#44ad38', '#5fc447', '#85d665', '#b0e690']),
    'leaf':    Ramp(['#06200c', '#0b3313', '#11481a', '#195e21', '#227529', '#2e8c31', '#41a33c', '#5cb94b', '#85cf68', '#b4e494']),
    # original #3f3f3f
    'asphalt': Ramp(['#18181b', '#212125', '#2a2a2f', '#333338', '#3d3d43', '#47474e', '#53535b', '#62626a']),
    # original #7f7f7f / #bfbfbf
    'concrete': Ramp(['#4a4a50', '#5e5e65', '#73737a', '#89898f', '#a0a0a5', '#b6b6ba', '#cbcbce', '#dfdfe1', '#f2f2f3']),
    'ballast': Ramp(['#3b342d', '#4d453b', '#5f564a', '#72685a', '#867c6c', '#9a917f', '#b0a895']),
    # original #997f4c
    'timber':  Ramp(['#3a2a17', '#523c22', '#6c512f', '#86683c', '#997f4c', '#b0965f', '#c6ad78']),
    'steel':   Ramp(['#2a2c33', '#41444d', '#5b5f69', '#7a7f8a', '#9ca1ab', '#c3c7ce', '#e8eaee']),
    # zone identities (frames and letters)
    'res':     Ramp(['#063d0e', '#0b5a16', '#12801f', '#1aa52a', '#22c435', '#3fdc4f', '#7aec82', '#b8f6bc']),
    'com':     Ramp(['#1a1a6e', '#262696', '#3636b8', '#4c4cd2', '#6666e6', '#8686ee', '#a8a8f4', '#d0d0fa']),
    'ind':     Ramp(['#5a4a00', '#7f6a00', '#a68b00', '#ccae00', '#e8cc10', '#ffe23a', '#fff07a', '#fffac0']),
    # roofs
    'roof_red': Ramp(['#4a1712', '#6a2219', '#8c2f21', '#ad3e2b', '#c85338', '#da6e4f', '#e78f72', '#f0b39b']),
    'roof_slate': Ramp(['#20242c', '#2c323c', '#3a414d', '#4a525f', '#5c6573', '#717a88', '#8a93a0', '#a8b0bb']),
    'roof_tar': Ramp(['#2a2a2a', '#363636', '#444444', '#555555', '#686868', '#7d7d7d', '#959595', '#b0b0b0']),
    'glass':   Ramp(['#0e1a3a', '#16264f', '#203568', '#2d4884', '#3e5fa0', '#557bbb', '#7499d2', '#9dbbe6', '#cfe0f6']),
    'brick':   Ramp(['#3d140f', '#5c1d15', '#7c271b', '#9c3322', '#b8432d', '#cf5a40', '#e07a5f', '#ec9f88']),
    'fire':    Ramp(['#5a0a00', '#9a1a00', '#d43000', '#f05a00', '#ff8a00', '#ffb320', '#ffd860', '#fff2b0', '#ffffff']),
}


# ---------------------------------------------------------------- noise
def pnoise(n, period, seed, wt=1, ht=1, ox=0.0, oy=0.0):
    """Value noise, periodic with period 1 tile (period lattice cells per tile)."""
    rng = np.random.default_rng(seed)
    L = rng.random((period, period))
    u = ((np.arange(wt * n) + 0.5) / n + ox) * period
    v = ((np.arange(ht * n) + 0.5) / n + oy) * period
    i0 = np.floor(u).astype(int)
    fu = u - i0
    j0 = np.floor(v).astype(int)
    fv = v - j0
    fu = fu * fu * fu * (fu * (fu * 6 - 15) + 10)
    fv = fv * fv * fv * (fv * (fv * 6 - 15) + 10)
    i1 = (i0 + 1) % period
    i0 = i0 % period
    j1 = (j0 + 1) % period
    j0 = j0 % period
    a = L[np.ix_(j0, i0)]
    b = L[np.ix_(j0, i1)]
    c = L[np.ix_(j1, i0)]
    d = L[np.ix_(j1, i1)]
    fv = fv[:, None]
    return (a * (1 - fu) + b * fu) * (1 - fv) + (c * (1 - fu) + d * fu) * fv


def fbm(n, seed, periods=(2, 4, 8, 16, 32), gain=0.55, wt=1, ht=1):
    tot = 0.0
    amp = 1.0
    norm = 0.0
    for k, p in enumerate(periods):
        tot = tot + amp * pnoise(n, p, seed * 101 + k, wt, ht)
        norm += amp
        amp *= gain
    return tot / norm


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def smin(a, b, k):
    """Polynomial smooth minimum (k in tile units)."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


# ---------------------------------------------------------------- SDFs (tile units)
def sd_circle(X, Y, cx, cy, r):
    return np.hypot(X - cx, Y - cy) - r


def sd_box(X, Y, x0, y0, x1, y1, r=0.0):
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hw, hh = (x1 - x0) / 2 - r, (y1 - y0) / 2 - r
    qx = np.abs(X - cx) - hw
    qy = np.abs(Y - cy) - hh
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def sd_segment(X, Y, ax, ay, bx, by):
    px, py = X - ax, Y - ay
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    h = np.clip((px * dx + py * dy) / L2, 0, 1) if L2 > 0 else 0
    return np.hypot(px - dx * h, py - dy * h)


def sd_polyline(X, Y, pts):
    d = None
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        s = sd_segment(X, Y, ax, ay, bx, by)
        d = s if d is None else np.minimum(d, s)
    return d


# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, wt=1, ht=1, n=RS, base=None):
        self.n, self.wt, self.ht = n, wt, ht
        self.W, self.H = wt * n, ht * n
        u = (np.arange(self.W) + 0.5) / n
        v = (np.arange(self.H) + 0.5) / n
        self.X, self.Y = np.meshgrid(u, v)
        self.img = np.zeros((self.H, self.W, 3)) if base is None else base.copy()

    # coverage from a signed distance (negative inside), anti-aliased over ~1.2 px
    def cov(self, sd, soft=1.2):
        return np.clip(0.5 - sd * self.n / soft, 0, 1)

    def paint(self, col, a):
        a = np.clip(a, 0, 1)[..., None]
        col = np.asarray(col, float)
        self.img = self.img * (1 - a) + col * a

    def shade(self, a, strength=0.45, tint=SHADOW_COL):
        """Darken toward a cool shadow colour (multiplicative), a in 0..1."""
        a = np.clip(a, 0, 1)[..., None] * strength
        self.img = self.img * (1 - a) + (self.img * tint) * a

    def light(self, a, strength=0.3, col=(1.0, 0.97, 0.88)):
        a = np.clip(a, 0, 1)[..., None] * strength
        self.img = self.img * (1 - a) + np.asarray(col) * a

    def poly(self, pts, ss=1):
        """Binary->AA mask of a polygon (tile-unit points). ss extra supersampling."""
        m = Image.new('L', (self.W * ss, self.H * ss), 0)
        ImageDraw.Draw(m).polygon([(x * self.n * ss, y * self.n * ss) for x, y in pts], fill=255)
        a = np.asarray(m, float) / 255
        if ss > 1:
            a = a.reshape(self.H, ss, self.W, ss).mean(axis=(1, 3))
        return a

    def blur(self, a, sigma, wrap=False):
        return ndimage.gaussian_filter(a, sigma * self.n, mode='wrap' if wrap else 'nearest')

    def text_mask(self, ch, cx, cy, size, font=None):
        font = font or FONT_SERIF
        f = ImageFont.truetype(font, int(size * self.n))
        m = Image.new('L', (self.W, self.H), 0)
        d = ImageDraw.Draw(m)
        d.text((cx * self.n, cy * self.n), ch, font=f, fill=255, anchor='mm')
        return np.asarray(m, float) / 255

    def out(self, px):
        f = self.n // px * 1
        f = self.W // (self.wt * px)
        a = np.clip(self.img, 0, 1)
        a = a.reshape(self.H // f, f, self.W // f, f, 3).mean(axis=(1, 3))
        return a

    def cells(self, px):
        """Cut into tiles at px resolution: list row-major of (px,px,3) arrays."""
        a = self.out(px)
        res = []
        for j in range(self.ht):
            for i in range(self.wt):
                res.append(a[j * px:(j + 1) * px, i * px:(i + 1) * px])
        return res


def to_u8(a):
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


FONT_SERIF = '/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf'
FONT_SANS = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'


def pnoise2(n, px, py, seed, wt=1, ht=1):
    """Anisotropic periodic value noise: px cells across, py cells down per tile."""
    rng = np.random.default_rng(seed)
    L = rng.random((py, px))
    u = (np.arange(wt * n) + 0.5) / n * px
    v = (np.arange(ht * n) + 0.5) / n * py
    i0 = np.floor(u).astype(int)
    fu = u - i0
    j0 = np.floor(v).astype(int)
    fv = v - j0
    fu = fu * fu * (3 - 2 * fu)
    fv = (fv * fv * (3 - 2 * fv))[:, None]
    i1, i0 = (i0 + 1) % px, i0 % px
    j1, j0 = (j0 + 1) % py, j0 % py
    a = L[np.ix_(j0, i0)]; b = L[np.ix_(j0, i1)]
    c = L[np.ix_(j1, i0)]; d = L[np.ix_(j1, i1)]
    return (a * (1 - fu) + b * fu) * (1 - fv) + (c * (1 - fu) + d * fu) * fv


def wrap_points(pts, wt=1, ht=1):
    """Periodic copies of points in [0,1)^2 covering a wt x ht canvas plus margin."""
    out = []
    for (x, y, *rest) in pts:
        for i in range(-1, wt + 1):
            for j in range(-1, ht + 1):
                out.append((x + i, y + j, *rest))
    return out
