"""Special buildings: stadium (empty / full + football), seaport, airport (+ radar),
nuclear power plant (+ reactor swirl).

GROUPS / ANIM follow BRIEF.md. Animated groups return {tile: image}; every frame is the
whole building drawn again with the moving part at that frame's phase (the static parts
use the same code path), and only the animated cell is taken.
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hdlib import *
from terrain import dirt_layer, grass_layer, draw_crown
from scene3d import Box, Gable, Cylinder, Tree, Custom, P, hull, LIGHT_W, LIGHT_S
from buildings import zone_frame, paving, lawn, rect, vehicle, roof_units, roof_skylights, cell_clip

GROUPS = []
ANIM = {}

EDGE = 0.06   # projected roofs and shadows stay this far inside the block


# ------------------------------------------------------------------ shared helpers
def anim_clip(cv, cells, margin):
    """cell_clip that is exactly 0 on the outermost pixels of the animated cells."""
    return np.clip(cell_clip(cv, cells, margin) * 1.25 - 0.25, 0, 1)


def ground(wt, ht):
    """The shared dirt layer. It is periodic per tile, so tiling the 1x1 layer is identical
    to dirt_layer(wt, ht) and far quicker for the 6x6 airport."""
    return np.tile(dirt_layer(1, 1), (ht, wt, 1))


def inner_mask(cv, m=EDGE):
    return rect(cv, m, m, cv.wt - m, cv.ht - m)


def render_in(cv, items, shadow_strength=0.62):
    """scene3d.render, but drop shadows are kept inside the block (EDGE margin)."""
    sh = np.zeros_like(cv.X)
    for it in items:
        if isinstance(it, Tree):
            sh = np.maximum(sh, it.shadow(cv))
            continue
        p = it.shadow_poly()
        if p:
            sh = np.maximum(sh, cv.poly(p))
    sh = cv.blur(sh, 0.008) * inner_mask(cv)
    cv.shade(sh, shadow_strength)
    for it in sorted(items, key=lambda i: i.key()):
        it.draw(cv)


def text_rot(cv, s, cx, cy, size, angle=0, font=FONT_SANS):
    """Text mask centred at (cx, cy), rotated by angle degrees (counter-clockwise)."""
    f = ImageFont.truetype(font, max(4, int(size * cv.n)))
    pad = int(size * cv.n * 2)
    m = Image.new('L', (pad * 2, pad * 2), 0)
    ImageDraw.Draw(m).text((pad, pad), s, font=f, fill=255, anchor='mm')
    m = m.rotate(angle, resample=Image.BICUBIC)
    out = Image.new('L', (cv.W, cv.H), 0)
    out.paste(m, (int(cx * cv.n) - pad, int(cy * cv.n) - pad))
    return np.asarray(out, float) / 255


def shrub(cv, x, y, r, seed):
    cv.shade(cv.cov(sd_circle(cv.X, cv.Y, x + r * 0.7, y + r * 0.4, r), 4), 0.45)
    draw_crown(cv, x, y, r, seed)


def disc_stack(cv, cx, cy, h, rfun, colfun, n=40, z0=0.0):
    """A solid of revolution about a vertical axis, drawn as stacked discs bottom to top.
    rfun(t) radius at t = z/h; colfun(lam) wall colour for lighting lam in 0..1."""
    for k in range(n + 1):
        t = k / n
        z = z0 + t * h
        x, y = P(cx, cy, z)
        r = rfun(t)
        d = np.hypot(cv.X - x, cv.Y - y)
        m = cv.cov(d - r)
        if not m.any():
            continue
        nx = (cv.X - x) / max(r, 1e-6)
        ny = (cv.Y - y) / max(r, 1e-6)
        lam = np.clip(0.55 - 0.50 * nx - 0.10 * ny, 0, 1)
        cv.paint(colfun(lam), m)


def plane(cv, x, y, ang, L=0.62, col='#f2f2ee', stripe='#3050b8', z=0.0):
    """Airliner seen from above, nose toward angle ang (radians; 0 = east, pi/2 = north)."""
    tx, ty = math.cos(ang), -math.sin(ang)
    nx, ny = -ty, tx

    def pt(a, b):   # a along the nose axis, b to the left wing
        return (x + tx * a * L + nx * b * L, y + ty * a * L + ny * b * L)
    fus = sd_segment(cv.X, cv.Y, *pt(-0.46, 0), *pt(0.42, 0)) - 0.055 * L
    wings = [pt(0.10, 0.0), pt(-0.12, 0.50), pt(-0.22, 0.50), pt(-0.10, 0.0), pt(-0.22, -0.50), pt(-0.12, -0.50)]
    tail = [pt(-0.34, 0.0), pt(-0.46, 0.20), pt(-0.52, 0.20), pt(-0.46, 0.0), pt(-0.52, -0.20), pt(-0.46, -0.20)]
    m = np.maximum(np.maximum(cv.cov(fus), cv.poly(wings)), cv.poly(tail))
    sx, sy = SHADOW_DIR * (0.05 + z)
    ms = np.roll(np.roll(m, int(sy * cv.n), 0), int(sx * cv.n), 1)
    cv.shade(cv.blur(ms, 0.004), 0.55)
    c = hx(col)
    cv.paint(c * 0.86, m)
    cv.paint(c, cv.cov(fus + 0.01 * L))
    cv.paint(hx(stripe), cv.cov(sd_segment(cv.X, cv.Y, *pt(-0.40, 0), *pt(0.30, 0)) - 0.012 * L) * 0.85)
    for sgn in (1, -1):   # engines
        ex, ey = pt(-0.04, 0.24 * sgn)
        cv.paint(hx('#8a8e96'), cv.cov(sd_segment(cv.X, cv.Y, ex - tx * 0.05 * L, ey - ty * 0.05 * L, ex + tx * 0.05 * L, ey + ty * 0.05 * L) - 0.022 * L))
    cv.paint(hx('#1d2533'), cv.cov(sd_circle(cv.X, cv.Y, *pt(0.37, 0), 0.025 * L)))
    cv.light(cv.cov(sd_segment(cv.X, cv.Y, *pt(-0.4, 0.02), *pt(0.36, 0.02)) - 0.01 * L, 1.5), 0.35)


# ================================================================== stadium
ST_PITCH = (2.52, 2.00, 0.43, 0.68)      # centre x, y, half width, half height (ground)
ST_OUT = (2.44, 2.06, 1.08, 1.80)        # footprint ellipse
ST_H = 0.30
GREEN_FRAME = Ramp(['#06300c', '#0a4a14', '#0e601a', '#147a22', '#1a8f28', '#2fa83c', '#5cc466', '#9ee0a4'])


def _stand_shape(cv, s, z):
    """Superellipse between the pitch rectangle (s=0) and the outer ellipse (s=1), raised to z."""
    pcx, pcy, pa, pb = ST_PITCH
    ocx, ocy, oa, ob = ST_OUT
    cx = pcx + (ocx - pcx) * s + OX * z
    cy = pcy + (ocy - pcy) * s - OY * z
    a = pa + 0.07 + (oa - pa - 0.07) * s
    b = pb + 0.09 + (ob - pb - 0.09) * s
    p = 6.0 + (2.0 - 6.0) * s ** 0.6
    v = np.abs((cv.X - cx) / a) ** p + np.abs((cv.Y - cy) / b) ** p
    return np.clip((1 - v) * min(a, b) * cv.n / p / 1.0 + 0.5, 0, 1)


def stand_z(s):
    return 0.04 + (ST_H - 0.04) * min(s / 0.84, 1.0)


def stadium(full, frame=None):
    cv = Canvas(4, 4, RS, ground(4, 4))
    X, Y = cv.X, cv.Y
    # car park on the west, with its access stubs
    lot = np.maximum.reduce([rect(cv, 0.24, 0.28, 1.34, 3.58, 0.04), rect(cv, 0.06, 0.60, 0.40, 0.84),
                             rect(cv, 0.06, 3.00, 0.40, 3.24), rect(cv, 0.74, 3.40, 1.02, 3.96)])
    paving(cv, lot, 0.42, 4)
    for k in range(4):
        x = 0.46 + 0.22 * k
        for j in range(7):
            y = 0.62 + 0.42 * j
            cv.paint(PAL['concrete'][7], rect(cv, x - 0.006, y, x + 0.006, y + 0.16) * 0.85)
    paving(cv, rect(cv, 1.34, 1.05, 1.62, 3.05, 0.03), 0.62, 6)     # forecourt by the west gate
    zone_frame(cv, GREEN_FRAME)
    # parked cars (full house)
    if full:
        rng = np.random.default_rng(779)
        cols = ['#c0392b', '#2c4f9e', '#e8e4dc', '#f0c419', '#2e8b57', '#d9822b', '#3a3d42', '#7d8ea6']
        for k in range(4):
            for j in range(7):
                for side in (0, 1):
                    if rng.random() < 0.18:
                        continue
                    x = 0.46 + 0.22 * k + (0.11 if side else -0.11) * 0.5 + (0.055 if side else -0.055)
                    y = 0.70 + 0.42 * j
                    if x > 1.30:
                        continue
                    vehicle(cv, x, y, 0.13, 0.075, cols[rng.integers(len(cols))], horizontal=False)
    # shrubs on the dirt, as the original's green specks
    for (x, y, r, sd) in ((0.20, 3.75, 0.07, 1), (0.42, 3.82, 0.06, 2), (1.62, 3.70, 0.08, 3), (1.82, 3.82, 0.06, 4),
                          (1.50, 0.22, 0.06, 5), (1.82, 0.30, 0.05, 6), (3.80, 3.80, 0.06, 7), (3.82, 0.55, 0.05, 8),
                          (0.18, 1.45, 0.05, 9), (3.85, 1.75, 0.05, 10), (0.56, 0.18, 0.05, 11)):
        shrub(cv, x, y, r, 780 + sd)
    # ---- the bowl: drop shadow, outer wall, stands, roof ring
    ocx, ocy, oa, ob = ST_OUT
    shp = []
    for k in range(48):
        a = 2 * math.pi * k / 48
        x, y = ocx + oa * math.cos(a), ocy + ob * math.sin(a)
        shp += [(x, y), (x + SHADOW_DIR[0] * ST_H, y + SHADOW_DIR[1] * ST_H)]
    sh = cv.blur(cv.poly(hull(shp)), 0.01) * inner_mask(cv)
    cv.shade(sh, 0.62)
    wall = hx('#c4c4c8')
    for k in range(31):
        z = ST_H * k / 30
        cx, cy = P(ocx, ocy, z)
        d = ((X - cx) / oa) ** 2 + ((Y - cy) / ob) ** 2
        m = np.clip((1 - d) * min(oa, ob) * cv.n / 2 + 0.5, 0, 1)
        nx, ny = (X - cx) / oa, (Y - cy) / ob
        nl = np.hypot(nx, ny) + 1e-6
        nx, ny = nx / nl, ny / nl
        lam = np.clip(np.maximum(-nx, 0) * 1.0 + np.maximum(ny, 0) * 0.64 + np.maximum(nx, 0) * 0.55 * (1 - np.maximum(ny, 0)) + np.maximum(-ny, 0) * 0.8 * (1 - np.maximum(-nx, 0)), 0.45, 1.0)
        lam = lam / np.maximum(1e-6, np.maximum(np.abs(nx), np.abs(ny))) ** 0.0
        col = wall[None, None, :] * lam[..., None]
        # pillars of the facade
        ang = np.arctan2(ny, nx)
        pil = (np.abs(((ang / (2 * math.pi) * 64) % 1) - 0.5) > 0.40)
        col = col * (1 - 0.18 * pil)[..., None]
        if 6 < k < 26:   # gate openings / concourse windows band
            col = col * (1 - 0.35 * ((k > 14) & (k < 20)) * (~pil))[..., None]
        cv.paint(col, m)
    # pitch (ground level, inside the bowl)
    pcx, pcy, pa, pb = ST_PITCH
    pit = rect(cv, pcx - pa - 0.07, pcy - pb - 0.09, pcx + pa + 0.07, pcy + pb + 0.09)
    cv.paint(PAL['grass'][2], pit)
    pm = rect(cv, pcx - pa, pcy - pb, pcx + pa, pcy + pb)
    stripes = (np.floor((Y - (pcy - pb)) / (2 * pb / 12)) % 2).astype(float)
    cv.paint(PAL['grass'](0.62 + 0.10 * stripes), pm)
    lw = 0.006
    white = hx('#f2f4ee')
    lines = cv.cov(np.abs(sd_box(X, Y, pcx - pa + 0.03, pcy - pb + 0.03, pcx + pa - 0.03, pcy + pb - 0.03)) - lw)
    lines = np.maximum(lines, cv.cov(np.abs(Y - pcy) - lw) * rect(cv, pcx - pa + 0.03, pcy - 1, pcx + pa - 0.03, pcy + 1))
    lines = np.maximum(lines, cv.cov(np.abs(np.hypot(X - pcx, Y - pcy) - 0.11) - lw))
    for sgn in (-1, 1):
        yb = pcy + sgn * (pb - 0.03)
        lines = np.maximum(lines, cv.cov(np.abs(sd_box(X, Y, pcx - 0.20, min(yb, yb - sgn * 0.17), pcx + 0.20, max(yb, yb - sgn * 0.17))) - lw))
        lines = np.maximum(lines, cv.cov(np.abs(sd_box(X, Y, pcx - 0.09, min(yb, yb - sgn * 0.06), pcx + 0.09, max(yb, yb - sgn * 0.06))) - lw))
        # goal: frame and net just beyond the line
        g0, g1 = (yb, yb + sgn * 0.035)
        cv.paint(hx('#dfe2e6') * 0.9, rect(cv, pcx - 0.055, min(g0, g1), pcx + 0.055, max(g0, g1)) * 0.8)
        gx, gy = P(pcx, yb, 0.03)
        cv.paint(white, cv.cov(np.abs(Y - (yb - 0.012)) - 0.006) * rect(cv, pcx - 0.058, yb - 0.03, pcx + 0.058, yb + 0.01))
    cv.paint(white, lines * 0.9)
    cv.paint(white, cv.cov(sd_circle(X, Y, pcx, pcy, 0.012)))
    # stands, inner (low) to outer (high); the near (south-west) side covers the low rows correctly
    N = 44
    seat = PAL['asphalt'](0.30)
    seat2 = PAL['asphalt'](0.62)
    prev = None
    rng = np.random.default_rng(795)
    crowd_cells = rng.random((cv.H // 9 + 2, cv.W // 9 + 2))
    crowd_cols = np.array([hx(c) for c in ('#d8322a', '#2b4fc8', '#f2d22a', '#f4f4f0', '#3aa64a', '#ef8a2a', '#8a5ad0', '#e86aa0')])
    ci = rng.integers(0, len(crowd_cols), crowd_cells.shape)
    cgrid = np.kron(crowd_cells, np.ones((9, 9)))[:cv.H, :cv.W]
    cidx = np.kron(ci, np.ones((9, 9), int))[:cv.H, :cv.W]
    for k in range(N):
        s0, s1 = k / N, (k + 1.3) / N
        z = stand_z((s0 + s1) / 2)
        ring = np.clip(_stand_shape(cv, min(s1, 1.0), z) - _stand_shape(cv, s0, z), 0, 1)
        if s0 < 0.86:
            col = seat if (k % 2 == 0) else seat2
            cv.paint(col, ring)
            if k % 2 == 1:
                cv.light(ring, 0.06)
            if full and 0.03 < s0 < 0.82:
                if k % 2 == 0:
                    on = (cgrid > 0.42) * ring
                    cv.paint(crowd_cols[cidx] * 0.85, on * 0.85)
            if not full and k % 6 == 3:
                cv.paint(PAL['asphalt'](0.95), ring * 0.7)   # aisles / gangway rows
        else:
            cv.paint(PAL['concrete'](0.80 - 0.15 * (s0 - 0.86) / 0.14), ring)
    # a black lip where the stands meet the pitch (the original's black ring)
    lip = np.clip(_stand_shape(cv, 0.035, 0.04) - _stand_shape(cv, 0.0, 0.0), 0, 1)
    cv.paint(hx('#151518'), lip * 0.9)
    if frame is not None:
        football(cv, frame)
    return cv


def football(cv, f):
    """Players of two teams and the ball, an 8-frame loop, clipped to cells (2,1)+(2,2)."""
    pcx, pcy, pa, pb = ST_PITCH
    clip = anim_clip(cv, [(2, 1), (2, 2)], 0.05)
    a = 2 * math.pi * f / 8
    acc = np.zeros_like(cv.X)
    colimg = np.zeros(cv.img.shape)
    sh = np.zeros_like(cv.X)
    # base formation (relative to pitch centre), each with its own loop
    reds = [(-0.20, -0.25), (0.18, -0.30), (0.0, -0.10), (-0.26, 0.10), (0.24, 0.05), (0.0, -0.52)]
    yels = [(-0.18, 0.25), (0.20, 0.30), (0.02, 0.12), (-0.24, -0.06), (0.26, -0.12), (0.0, 0.52)]
    ball = (0.13 * math.sin(a), 0.22 * math.sin(a + 0.8))
    for team, pts, col in ((0, reds, hx('#e0281e')), (1, yels, hx('#f6d21c'))):
        for i, (px, py) in enumerate(pts):
            ph = i * 1.3 + team * 0.7
            keeper = abs(py) > 0.45
            amp = 0.05 if keeper else 0.12
            x = pcx + px + amp * math.cos(a + ph) * 0.8 + (0.0 if keeper else 0.25 * (ball[0] - px) * 0.4)
            y = pcy + py + amp * math.sin(a + ph) + (0.0 if keeper else 0.25 * (ball[1] - py) * 0.4)
            x = min(max(x, pcx - pa + 0.06), pcx + pa - 0.08)
            y = min(max(y, pcy - pb + 0.04), pcy + pb - 0.04)
            sh = np.maximum(sh, cv.cov(sd_circle(cv.X, cv.Y, x + 0.018, y + 0.012, 0.030), 2))
            body = cv.cov(sd_circle(cv.X, cv.Y, x, y, 0.032))
            colimg = colimg * (1 - body[..., None]) + col * body[..., None]
            acc = np.maximum(acc, body)
            head = cv.cov(sd_circle(cv.X, cv.Y, x - 0.004, y - 0.005, 0.013))
            colimg = colimg * (1 - head[..., None]) + hx('#e8b890') * head[..., None]
    bx, by = pcx + ball[0], pcy + ball[1]
    sh = np.maximum(sh, cv.cov(sd_circle(cv.X, cv.Y, bx + 0.02, by + 0.012, 0.012), 2))
    bm = cv.cov(sd_circle(cv.X, cv.Y, bx, by, 0.016))
    colimg = colimg * (1 - bm[..., None]) + hx('#ffffff') * bm[..., None]
    acc = np.maximum(acc, bm)
    cv.shade(sh * clip, 0.45)
    a3 = (acc * clip)[..., None]
    cv.img = cv.img * (1 - a3) + colimg * a3


def stadium_empty():
    return stadium(False)


def stadium_full_group():
    out = {}
    base = stadium(True)
    cl = base.cells(RS)
    for i in range(16):
        out[795 + i] = cl[i]
    for f in range(8):
        cvf = Canvas(4, 4, RS, base.img)     # the same picture, players at frame f on top
        football(cvf, f)
        c = cvf.cells(RS)
        out[932 + f] = c[1 * 4 + 2]
        out[940 + f] = c[2 * 4 + 2]
    return out


GROUPS.append((779, 4, 4, stadium_empty))
GROUPS.append((795, 4, 4, stadium_full_group))
for _f in range(8):
    ANIM[932 + _f] = 801
    ANIM[940 + _f] = 805


# ================================================================== seaport
def lattice(cv, a, b, w, col, dark='#1c1c1e', step=0.05):
    """A lattice boom from screen point a to b: coloured bar with dark cross-bracing."""
    X, Y = cv.X, cv.Y
    d = sd_segment(X, Y, a[0], a[1], b[0], b[1])
    m = cv.cov(d - w)
    cv.paint(hx(col), m)
    L = math.hypot(b[0] - a[0], b[1] - a[1]) + 1e-9
    tx, ty = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    u = (X - a[0]) * tx + (Y - a[1]) * ty
    v = -(X - a[0]) * ty + (Y - a[1]) * tx
    br = np.minimum(np.abs(((u + v) / step) % 1 - 0.5), np.abs(((u - v) / step) % 1 - 0.5))
    cv.paint(hx(dark), cv.cov(br * step - 0.0055) * m * 0.85)
    cv.light(cv.cov(np.abs(v + w * 0.6) - w * 0.25) * m, 0.25)


def crane(cv, base, h, jib_a, jib_b, col='#f07a1a'):
    """Quay crane: oblique tower from base to height h; jib between two screen points at the top."""
    bx, by = base
    top = P(bx, by, h)
    X, Y = cv.X, cv.Y
    # shadows of tower and jib on the ground
    s = SHADOW_DIR * h
    sh = cv.cov(sd_segment(X, Y, bx, by, bx + s[0], by + s[1]) - 0.018, 3)
    ja = (jib_a[0] - OX * h + s[0], jib_a[1] + OY * h + s[1])
    jb = (jib_b[0] - OX * h + s[0], jib_b[1] + OY * h + s[1])
    sh = np.maximum(sh, cv.cov(sd_segment(X, Y, ja[0], ja[1], jb[0], jb[1]) - 0.014, 3))
    cv.shade(cv.blur(sh, 0.004) * inner_mask(cv), 0.5)
    cv.paint(PAL['concrete'][2], rect(cv, bx - 0.06, by - 0.05, bx + 0.06, by + 0.05, 0.01))
    lattice(cv, (bx, by), top, 0.030, col)
    lattice(cv, jib_a, jib_b, 0.026, col)
    cv.paint(PAL['steel'][1], rect(cv, top[0] - 0.045, top[1] - 0.035, top[0] + 0.045, top[1] + 0.035, 0.008))
    cv.paint(PAL['glass'][6], rect(cv, top[0] - 0.035, top[1] - 0.02, top[0] + 0.0, top[1] + 0.015, 0.004))


def anchor(cv, cx, cy, s, col):
    X, Y = cv.X, cv.Y
    d = sd_segment(X, Y, cx, cy - 0.30 * s, cx, cy + 0.38 * s) - 0.035 * s          # shank
    d = np.minimum(d, sd_segment(X, Y, cx - 0.16 * s, cy - 0.17 * s, cx + 0.16 * s, cy - 0.17 * s) - 0.03 * s)   # stock
    d = np.minimum(d, np.abs(np.hypot(X - cx, Y - (cy - 0.38 * s)) - 0.07 * s) - 0.025 * s)  # ring
    r = 0.36 * s
    arc = np.abs(np.hypot(X - cx, Y - (cy + 0.02 * s)) - r) - 0.035 * s
    d = np.minimum(d, np.maximum(arc, -(Y - (cy + 0.10 * s))))                      # arms (lower arc)
    for sg in (-1, 1):                                                              # flukes
        fx, fy = cx + sg * 0.33 * s, cy + 0.18 * s
        d = np.minimum(d, sd_segment(X, Y, fx, fy, fx - sg * 0.02 * s, fy - 0.16 * s) - 0.03 * s)
        d = np.minimum(d, sd_segment(X, Y, fx, fy, fx + sg * 0.09 * s, fy - 0.07 * s) - 0.03 * s)
    m = cv.cov(d)
    sh = np.roll(np.roll(m, int(0.014 * cv.n), 0), int(0.018 * cv.n), 1)
    return m, sh


def container_stack(cv, x0, y0, nx, ny, seed, cols=('#e8b81c', '#c8351f', '#2f5fae', '#d9822b', '#8c9096', '#2f8a4a')):
    """Shipping containers in rows (long side along x), height by random stack."""
    rng = np.random.default_rng(seed)
    items = []
    L, W = 0.20, 0.075
    for j in range(ny):
        for i in range(nx):
            x, y = x0 + i * (L + 0.02), y0 + j * (W + 0.018)
            hgt = 0.04 * rng.integers(1, 3)
            col = hx(cols[rng.integers(len(cols))])
            items.append(Box(x, y, x + L, y + W, hgt, col, col * 1.05, win={'kind': 'ribs', 'col': 0.012},
                             win_w={'kind': 'ribs', 'col': 0.012}, parapet=False, ao=False))
    return items


def seaport():
    from terrain import water_layer
    cv = Canvas(4, 4, RS, ground(4, 4))
    X, Y = cv.X, cv.Y
    # paved quay, the yards and the roads
    paving(cv, rect(cv, 0.24, 0.30, 3.28, 3.72, 0.03), 0.52, 4)
    paving(cv, rect(cv, 2.55, 0.08, 2.85, 0.32), 0.52, 4)                    # north gate road
    paving(cv, rect(cv, 3.28, 2.05, 3.88, 2.30), 0.52, 4)                    # east road
    paving(cv, rect(cv, 0.62, 3.70, 1.00, 3.95), 0.52, 4)                    # south slipway
    cv.paint(PAL['dirt'][4], rect(cv, 0.30, 3.18, 0.70, 3.62, 0.04) * 0.6)  # crane foot gravel
    # quay channel along the west and south (the original's blue and black water edge)
    wl = water_layer(4, 4)
    wm = np.maximum(rect(cv, 0.07, 0.18, 0.22, 3.90), rect(cv, 0.07, 3.76, 3.86, 3.90))
    a = np.clip(wm, 0, 1)[..., None]
    cv.img = cv.img * (1 - a) + wl * a
    qe = np.maximum(cv.cov(np.abs(X - 0.225) - 0.012) * rect(cv, 0.20, 0.18, 0.26, 3.78),
                    cv.cov(np.abs(Y - 3.755) - 0.012) * rect(cv, 0.21, 3.72, 3.86, 3.78))
    cv.paint(PAL['concrete'][1], qe)
    cv.light(cv.cov(np.abs(X - 0.235) - 0.003) * rect(cv, 0.2, 0.18, 0.26, 3.75), 0.3)
    cv.shade(cv.cov(np.abs(X - 0.205) - 0.008) * rect(cv, 0.0, 0.18, 0.21, 3.76), 0.5)
    cv.shade(cv.cov(np.abs(Y - 3.775) - 0.008) * rect(cv, 0.21, 3.76, 3.86, 3.80), 0.5)
    for k in range(9):            # bollards
        y = 0.40 + 0.40 * k
        cv.paint(hx('#202022'), cv.cov(sd_circle(X, Y, 0.255, y, 0.010)))
    for k in range(9):
        x = 0.45 + 0.38 * k
        cv.paint(hx('#202022'), cv.cov(sd_circle(X, Y, x, 3.735, 0.010)))
    # yellow lane markings on the quay
    cv.paint(PAL['ind'][5], cv.cov(np.abs(X - 0.32) - 0.005) * rect(cv, 0.3, 0.4, 0.34, 3.6) * 0.8)
    cv.paint(PAL['ind'][5], cv.cov(np.abs(Y - 3.64) - 0.005) * rect(cv, 0.4, 3.6, 3.2, 3.68) * 0.8)
    # the port's frame: water blue, as the original
    zone_frame(cv, PAL['com'], width=0.04)
    # a tug moored in the west channel
    def tug(c):
        bx0, by0, bx1, by1 = 0.105, 2.28, 0.19, 2.66
        hullm = c.cov(sd_box(c.X, c.Y, bx0, by0 + 0.04, bx1, by1, 0.03)) + c.poly([(bx0, by0 + 0.06), ((bx0 + bx1) / 2, by0), (bx1, by0 + 0.06)])
        c.shade(c.blur(np.roll(np.roll(np.clip(hullm, 0, 1), 4, 0), 6, 1), 0.004), 0.45)
        c.paint(hx('#b8262a'), np.clip(hullm, 0, 1))
        c.paint(hx('#ecebe6'), rect(c, bx0 + 0.015, by0 + 0.14, bx1 - 0.015, by0 + 0.27, 0.01))
        c.paint(PAL['glass'][3], rect(c, bx0 + 0.02, by0 + 0.15, bx1 - 0.02, by0 + 0.18))
        c.paint(hx('#202022'), c.cov(sd_circle(c.X, c.Y, (bx0 + bx1) / 2, by0 + 0.31, 0.018)))
    light_grey = hx('#c4c4c6')
    warehouse = Box(0.74, 1.46, 2.62, 2.86, 0.70, light_grey, PAL['concrete'][3],
                    win={'kind': 'doors', 'n': 4, 'h': 0.24, 'glass': Ramp(['#2a2c30', '#3a3d42', '#4a4e54'])},
                    win_w={'kind': 'grid', 'floor': 0.16, 'col': 0.16, 'wfrac': 0.4, 'hfrac': 0.3, 'margin': 0.06},
                    rim=PAL['concrete'][7])

    def roof_anchor(c, rx0, ry0, rx1, ry1):
        roof_units([(0.06, 0.10, 0.07, 0.06), (0.86, 0.10, 0.07, 0.06), (0.06, 0.82, 0.07, 0.06), (0.86, 0.82, 0.07, 0.06)])(c, rx0, ry0, rx1, ry1)
        m, sh = anchor(c, (rx0 + rx1) / 2, (ry0 + ry1) / 2 + 0.02, 1.15, None)
        c.shade(sh, 0.5)
        c.paint(PAL['com'][3], m)
        e = np.clip(m - np.roll(np.roll(m, 3, 0), 3, 1), 0, 1)
        c.light(e, 0.45)
    warehouse.roof_detail = roof_anchor
    sheds = [Gable(x0, 0.50, x1, 1.02, 0.20, 0.14, light_grey, PAL['concrete'], ridge='y',
                   win={'kind': 'doors', 'n': 1, 'h': 0.14, 'glass': Ramp(['#2a2c30', '#3a3d42'])})
             for (x0, x1) in ((0.86, 1.30), (1.36, 1.80), (1.86, 2.30))]
    office = Box(0.32, 1.16, 0.70, 2.02, 0.26, hx('#9a9ca2'), PAL['roof_tar'][3], win={'kind': 'grid', 'floor': 0.1, 'col': 0.08, 'wfrac': 0.5, 'hfrac': 0.4},
                 win_w={'kind': 'grid', 'floor': 0.1, 'col': 0.08, 'wfrac': 0.5, 'hfrac': 0.4}, roof_detail=roof_units([(0.2, 0.15, 0.25, 0.08), (0.55, 0.7, 0.2, 0.1)]))
    eoff = Box(3.40, 0.98, 3.76, 1.46, 0.18, hx('#b4b6ba'), PAL['roof_tar'][4], win={'kind': 'grid', 'floor': 0.1, 'col': 0.08, 'wfrac': 0.5, 'hfrac': 0.4},
               win_w={'kind': 'grid', 'floor': 0.1, 'col': 0.08, 'wfrac': 0.5, 'hfrac': 0.4})
    items = [warehouse, office, eoff] + sheds
    items += container_stack(cv, 3.36, 2.42, 2, 5, 693)
    items += container_stack(cv, 2.62, 0.42, 3, 2, 694)
    items += container_stack(cv, 1.06, 3.00, 4, 3, 695)
    items += [Tree(3.46, 1.66, 0.10, 701), Tree(3.70, 1.74, 0.10, 702), Tree(3.52, 1.88, 0.09, 703), Tree(3.76, 3.40, 0.09, 704), Tree(3.50, 3.55, 0.08, 705)]
    items.append(Custom(tug, key=(-20, 0)))
    items.append(Custom(lambda c: vehicle(c, 3.55, 2.17, 0.30, 0.10, '#2f5fae'), key=(2.17 - 3.55, 0)))
    items.append(Custom(lambda c: vehicle(c, 2.70, 0.22, 0.28, 0.10, '#d9822b', horizontal=False), key=(0.22 - 2.70, 0)))
    render_in(cv, items)
    # quay cranes (drawn last: tall, nothing stands in front of them)
    crane(cv, (0.48, 3.50), 0.76, (0.12, 3.12), (1.12, 3.12))
    crane(cv, (2.36, 3.70), 0.74, (2.73, 2.98), (2.73, 3.86))
    crane(cv, (3.44, 0.82), 0.56, (3.72, 0.16), (3.72, 0.80))
    return cv


GROUPS.append((693, 4, 4, seaport))


# ================================================================== airport
RADAR_BASE = (2.44, 0.60)
RADAR_H = 0.34


def radar_dish(cv, theta, clip=None):
    """Rotating radar reflector on its mast top. theta = facing angle (radians)."""
    bx, by = RADAR_BASE
    zc = RADAR_H + 0.06
    e = np.array([math.cos(theta), math.sin(theta)])      # across the reflector (ground x, y)
    f = np.array([-math.sin(theta), math.cos(theta)])     # the way it faces
    Lv = np.array([-0.55, -0.45, 0.70])
    Lv = Lv / np.linalg.norm(Lv)
    quads = []
    n = 18
    for i in range(n):
        u0, u1 = -1 + 2 * i / n, -1 + 2 * (i + 1) / n
        pts = []
        for (u, v) in ((u0, -1), (u1, -1), (u1, 1), (u0, 1)):
            g = e * u * 0.27 - f * 0.10 * (1 - u * u) + f * v * 0.03
            pts.append(P(bx + g[0], by + g[1], zc + v * 0.085))
        um = (u0 + u1) / 2
        nrm = np.array([*(f + e * um * 0.9), 0.25])
        nrm = nrm / np.linalg.norm(nrm)
        gm = e * um * 0.27 - f * 0.10 * (1 - um * um)
        depth = gm[1] - gm[0]
        quads.append((depth, pts, nrm))
    sh = np.zeros_like(cv.X)
    s = SHADOW_DIR * zc
    for (_, pts, _) in quads:
        sp = [(x - OX * zc + s[0], y + OY * zc + s[1]) for (x, y) in pts]
        sh = np.maximum(sh, cv.poly(sp))
    sh = cv.blur(sh, 0.005)
    if clip is not None:
        sh = sh * clip
    cv.shade(sh, 0.5)
    acc = np.zeros_like(cv.X)
    col = np.zeros(cv.img.shape)
    for (_, pts, nrm) in sorted(quads, key=lambda q: q[0]):
        m = cv.poly(pts, ss=2)
        # the concave face toward the light is bright, the back is dark steel
        lam = 0.5 + 0.5 * float(np.dot(nrm, Lv))
        c = PAL['steel'](0.05 + 0.70 * lam)
        col = col * (1 - m[..., None]) + c * m[..., None]
        acc = np.maximum(acc, m)
        # rim line
    # feed arm and horn
    fx, fy = bx + f[0] * 0.13, by + f[1] * 0.13
    a, b = P(bx, by, zc - 0.03), P(fx, fy, zc)
    arm = cv.cov(sd_segment(cv.X, cv.Y, a[0], a[1], b[0], b[1]) - 0.008)
    col = col * (1 - arm[..., None]) + PAL['steel'][1] * arm[..., None]
    horn = cv.cov(sd_circle(cv.X, cv.Y, b[0], b[1], 0.016))
    col = col * (1 - horn[..., None]) + PAL['steel'][5] * horn[..., None]
    acc = np.maximum(acc, np.maximum(arm, horn))
    if clip is not None:
        acc = acc * clip
    cv.img = cv.img * (1 - acc[..., None]) + col * acc[..., None]


def runway(cv, x0, y0, x1, y1, horizontal, nums):
    X, Y = cv.X, cv.Y
    n = pnoise(cv.n, 32, 711, cv.wt, cv.ht)
    m = rect(cv, x0, y0, x1, y1)
    cv.paint(PAL['asphalt'](0.42 + 0.10 * (n - 0.5)), m)
    white = hx('#ecedef')
    if horizontal:
        cy = (y0 + y1) / 2
        w = y1 - y0
        cv.paint(white, cv.cov(np.abs(Y - (y0 + 0.035)) - 0.006) * rect(cv, x0 + 0.05, y0, x1 - 0.05, y1) * 0.85)
        cv.paint(white, cv.cov(np.abs(Y - (y1 - 0.035)) - 0.006) * rect(cv, x0 + 0.05, y0, x1 - 0.05, y1) * 0.85)
        dash = (np.abs(((X - x0) / 0.36) % 1 - 0.5) < 0.30)
        cv.paint(white, cv.cov(np.abs(Y - cy) - 0.010) * dash * rect(cv, x0 + 0.65, y0, x1 - 0.65, y1))
        for (ex, sg) in ((x0, 1), (x1, -1)):
            for k in range(6):   # piano keys
                yy = y0 + 0.08 + k * (w - 0.16) / 5.0
                cv.paint(white, rect(cv, min(ex + sg * 0.07, ex + sg * 0.25), yy - 0.025, max(ex + sg * 0.07, ex + sg * 0.25), yy + 0.025) * (abs(yy - cy) > 0.06))
            for k in range(2):   # touchdown marks
                xx = ex + sg * (0.95 + 0.25 * k)
                for yy in (cy - 0.17, cy + 0.17):
                    cv.paint(white, rect(cv, xx - 0.08, yy - 0.025, xx + 0.08, yy + 0.025) * 0.85)
    else:
        cx = (x0 + x1) / 2
        w = x1 - x0
        cv.paint(white, cv.cov(np.abs(X - (x0 + 0.035)) - 0.006) * rect(cv, x0, y0 + 0.05, x1, y1 - 0.05) * 0.85)
        cv.paint(white, cv.cov(np.abs(X - (x1 - 0.035)) - 0.006) * rect(cv, x0, y0 + 0.05, x1, y1 - 0.05) * 0.85)
        dash = (np.abs(((Y - y0) / 0.36) % 1 - 0.5) < 0.30)
        cv.paint(white, cv.cov(np.abs(X - cx) - 0.010) * dash * rect(cv, x0, y0 + 0.65, x1, y1 - 0.65))
        for (ey, sg) in ((y0, 1), (y1, -1)):
            for k in range(6):
                xx = x0 + 0.08 + k * (w - 0.16) / 5.0
                cv.paint(white, rect(cv, xx - 0.025, min(ey + sg * 0.07, ey + sg * 0.25), xx + 0.025, max(ey + sg * 0.07, ey + sg * 0.25)) * (abs(xx - cx) > 0.06))
            for k in range(2):
                yy = ey + sg * (0.95 + 0.25 * k)
                for xx in (cx - 0.17, cx + 0.17):
                    cv.paint(white, rect(cv, xx - 0.025, yy - 0.08, xx + 0.025, yy + 0.08) * 0.85)
    for (s, x, y, ang) in nums:
        cv.paint(white, text_rot(cv, s, x, y, 0.26, ang) * 0.95)


def taxi_line(cv, pts):
    cv.paint(PAL['ind'][5], cv.cov(sd_polyline(cv.X, cv.Y, pts) - 0.006) * 0.9)


def airport_base():
    cv = Canvas(6, 6, RS, ground(6, 6))
    X, Y = cv.X, cv.Y
    # taxiways and aprons (concrete), service roads
    for r in ((0.36, 1.50, 0.90, 2.30), (3.58, 1.50, 4.40, 2.25), (3.58, 0.30, 4.40, 0.82),
              (0.20, 2.18, 2.95, 2.78), (2.40, 2.98, 4.40, 5.02), (2.95, 2.18, 3.95, 3.02)):
        paving(cv, rect(cv, *r, 0.03), 0.52, 4)
    for pts in (((0.16, 0.47), (1.62, 0.47), (1.62, 0.70)), ((2.05, 2.0), (2.85, 2.0), (2.85, 2.2)), ((2.05, 1.7), (2.05, 2.2)),
                ((5.48, 1.86), (5.48, 4.86), (5.10, 4.86)), ((5.48, 3.44), (5.12, 3.44)), ((3.45, 0.82), (3.6, 0.62))):
        cv.paint(PAL['concrete'][3], cv.cov(sd_polyline(X, Y, pts) - 0.022))
        cv.paint(PAL['concrete'][5], cv.cov(sd_polyline(X, Y, pts) - 0.016))
    # car park with its loop road (south-west)
    paving(cv, rect(cv, 0.14, 3.86, 1.74, 5.76, 0.08), 0.50, 6)
    paving(cv, rect(cv, 1.56, 5.40, 2.02, 5.95), 0.50, 6)
    cv.paint(PAL['sand'][3], rect(cv, 0.40, 4.10, 1.56, 5.58, 0.05))
    cv.paint(PAL['asphalt'](0.45), rect(cv, 0.62, 4.16, 1.52, 5.12, 0.03))
    for k in range(6):
        x = 0.70 + 0.15 * k
        for y in (4.30, 4.62, 4.94):
            cv.paint(PAL['concrete'][7], rect(cv, x - 0.004, y - 0.06, x + 0.004, y + 0.06) * 0.8)
    rng = np.random.default_rng(709)
    for k in range(5):
        for y in (4.30, 4.62, 4.94):
            if rng.random() < 0.7:
                vehicle(cv, 0.775 + 0.15 * k, y, 0.11, 0.065, ['#c0392b', '#2c4f9e', '#e8e4dc', '#f0c419', '#3a3d42', '#7d8ea6'][rng.integers(6)], horizontal=False)
    # runways: the east-west one first, the north-south one crosses over it
    runway(cv, 0.10, 0.78, 5.90, 1.56, True, [('09', 0.48, 1.17, 90), ('27', 5.52, 1.17, -90)])
    runway(cv, 4.36, 0.12, 5.12, 5.88, False, [('18', 4.74, 0.50, 180), ('36', 4.74, 5.50, 0)])
    # yellow taxi centre lines
    taxi_line(cv, [(0.63, 1.60), (0.63, 2.48), (2.0, 2.48)])
    taxi_line(cv, [(3.80, 1.60), (3.80, 2.10)])
    taxi_line(cv, [(4.30, 4.72), (3.75, 4.72), (3.75, 3.10)])
    taxi_line(cv, [(3.95, 0.86), (3.95, 0.40), (4.32, 0.40)])
    zone_frame(cv, 'ind', width=0.045)
    # runway edge lights and threshold lights
    for k in range(13):
        x = 0.30 + 0.45 * k
        if 4.2 < x < 5.3:
            continue
        for y in (0.72, 1.62):
            cv.paint(hx('#e0e6ff'), cv.cov(sd_circle(X, Y, x, y, 0.016), 2) * 0.5)
            cv.paint(hx('#4c5cf0'), cv.cov(sd_circle(X, Y, x, y, 0.011)))
    for k in range(13):
        y = 0.30 + 0.45 * k
        if 0.6 < y < 1.7:
            continue
        for x in (4.30, 5.18):
            cv.paint(hx('#e0e6ff'), cv.cov(sd_circle(X, Y, x, y, 0.016), 2) * 0.5)
            cv.paint(hx('#4c5cf0'), cv.cov(sd_circle(X, Y, x, y, 0.011)))
    for k in range(6):
        y = 0.84 + 0.13 * k
        cv.paint(hx('#e8281e'), cv.cov(sd_circle(X, Y, 0.125, y, 0.013)))
        cv.paint(hx('#e8281e'), cv.cov(sd_circle(X, Y, 5.875, y, 0.013)))
        x = 4.42 + 0.13 * k
        cv.paint(hx('#e8281e'), cv.cov(sd_circle(X, Y, x, 0.13, 0.013)))
        cv.paint(hx('#e8281e'), cv.cov(sd_circle(X, Y, x, 5.87, 0.013)))
    # ---- buildings
    term = hx('#cfd0d4')
    win = {'kind': 'bands', 'floor': 0.07, 'col': 0.05}
    def redlights(pts):
        def fn(c, rx0, ry0, rx1, ry1):
            roof_units([(0.1, 0.3, 0.12, 0.12)])(c, rx0, ry0, rx1, ry1)
            for (fx, fy) in pts:
                x, y = rx0 + fx * (rx1 - rx0), ry0 + fy * (ry1 - ry0)
                c.paint(hx('#ff6a50'), c.cov(sd_circle(c.X, c.Y, x, y, 0.022), 2.5) * 0.5)
                c.paint(hx('#e8201a'), c.cov(sd_circle(c.X, c.Y, x, y, 0.013)))
        return fn
    blue_glass = Ramp(['#0a0a5a', '#10108a', '#1a1ab4', '#2a2ad8', '#5a5ae8', '#9a9af4'])
    items = [
        Box(0.22, 2.80, 0.82, 3.48, 0.18, term, PAL['concrete'][5], win=win, win_w=win, roof_detail=redlights([(0.2, 0.2), (0.2, 0.85)])),
        Box(0.88, 2.80, 1.48, 3.48, 0.18, term, PAL['concrete'][5], win=win, win_w=win, roof_detail=redlights([(0.2, 0.2), (0.2, 0.85)])),
        Box(1.54, 2.86, 2.44, 3.48, 0.18, term, PAL['concrete'][5], win=win, win_w=win, roof_detail=redlights([(0.2, 0.15), (0.2, 0.85), (0.8, 0.15)])),
        Box(0.16, 3.50, 2.44, 3.70, 0.12, blue_glass[3], blue_glass[2], win={'kind': 'curtain', 'col': 0.06, 'floor': 0.06, 'frame': (0.6, 0.62, 0.7)},
            win_w={'kind': 'curtain', 'col': 0.06, 'floor': 0.06, 'frame': (0.6, 0.62, 0.7)}, glass=blue_glass, parapet=False),
        Box(2.30, 3.70, 2.44, 5.56, 0.12, blue_glass[3], blue_glass[2], win={'kind': 'curtain', 'col': 0.06, 'floor': 0.06, 'frame': (0.6, 0.62, 0.7)},
            win_w={'kind': 'curtain', 'col': 0.06, 'floor': 0.06, 'frame': (0.6, 0.62, 0.7)}, glass=blue_glass, parapet=False),
        Box(2.46, 3.66, 3.22, 4.62, 0.16, term, PAL['concrete'][5], win=win, win_w=win, roof_detail=redlights([(0.08, 0.92), (0.85, 0.92)])),
        Box(2.46, 4.70, 3.22, 5.08, 0.14, term, PAL['concrete'][5], win=win, win_w=win, roof_detail=redlights([(0.08, 0.85), (0.85, 0.85)])),
        Box(2.46, 5.14, 3.22, 5.56, 0.14, term, PAL['concrete'][5], win=win, win_w=win, roof_detail=redlights([(0.08, 0.85), (0.85, 0.85)])),
    ]
    # jet bridges from the concourse
    for x in (0.55, 1.20, 1.95):
        items.append(Box(x, 3.18 - 0.40, x + 0.06, 3.0 - 0.20, 0.06, PAL['concrete'][4], PAL['concrete'][5], parapet=False, z0=0.0))
    # hangar with a barrel roof and doors on the south side
    def barrel(c, rx0, ry0, rx1, ry1):
        t = np.clip((c.X - rx0) / (rx1 - rx0), 0, 1)
        lam = 0.55 + 0.45 * np.cos((t - 0.3) * math.pi * 0.9)
        rib = (np.abs(((c.Y - ry0) / 0.08) % 1 - 0.5) > 0.44)
        return PAL['concrete'](0.35 + 0.5 * lam)[..., :] * (1 - 0.12 * rib)[..., None]
    items.append(Box(3.00, 2.30, 3.88, 3.02, 0.26, hx('#b8babe'), barrel, win={'kind': 'doors', 'n': 2, 'h': 0.22, 'glass': Ramp(['#2a2c30', '#3a3d42'])},
                     win_w={'kind': 'ribs', 'col': 0.04}, parapet=False))
    # tower-side small sheds and the beacons on the east
    items.append(Box(5.28, 1.90, 5.60, 2.10, 0.10, hx('#9a9ca2'), PAL['roof_tar'][3]))
    for y in (3.58, 3.84, 4.10):
        items.append(Box(5.30, y, 5.62, y + 0.12, 0.06, hx('#9a9ca2'), PAL['roof_tar'][2], parapet=False))
    items.append(Box(1.80, 5.52, 1.94, 5.68, 0.10, hx('#f07a1a'), hx('#f29040'), parapet=False))   # toll booth
    # radar mast: brown tripod and the platform
    def mast(c):
        bx, by = RADAR_BASE
        top = P(bx, by, RADAR_H)
        for (dx, dy) in ((-0.10, 0.06), (0.10, 0.06), (0.0, -0.10)):
            c.shade(c.cov(sd_segment(c.X, c.Y, bx + dx, by + dy, bx + SHADOW_DIR[0] * RADAR_H, by + SHADOW_DIR[1] * RADAR_H) - 0.008, 2), 0.4)
        for (dx, dy) in ((0.0, -0.10), (-0.10, 0.06), (0.10, 0.06)):
            c.paint(PAL['timber'][2], c.cov(sd_segment(c.X, c.Y, bx + dx, by + dy, top[0], top[1]) - 0.010))
            c.light(c.cov(sd_segment(c.X, c.Y, bx + dx - 0.004, by + dy, top[0] - 0.004, top[1]) - 0.003), 0.2)
        c.paint(PAL['concrete'][2], c.cov(sd_circle(c.X, c.Y, top[0], top[1], 0.035)))
    items.append(Custom(mast, key=(-30, 0)))
    trees = [Tree(0.30, 4.30, 0.09, 721), Tree(0.28, 4.70, 0.09, 722), Tree(0.30, 5.12, 0.08, 723), Tree(1.98, 4.80, 0.09, 724),
             Tree(5.70, 2.80, 0.09, 725), Tree(5.72, 5.40, 0.09, 726), Tree(0.30, 1.95, 0.09, 727), Tree(3.30, 1.85, 0.08, 728)]
    items += trees
    render_in(cv, items)
    # aircraft
    plane(cv, 1.18, 2.46, math.pi / 2, L=0.62)
    plane(cv, 2.32, 2.46, 0.0, L=0.34, col='#f4f4f0', stripe='#c8351f')
    plane(cv, 3.76, 4.26, math.pi / 2, L=0.62, stripe='#c8351f')
    return cv


RADAR_FRAMES = [2 * math.pi * k / 8 for k in range(8)]


def airport_group():
    out = {}
    base = airport_base()
    clip = anim_clip(base, [(2, 0)], 0.06)
    for f in range(8):
        cvf = Canvas(6, 6, RS, base.img)
        radar_dish(cvf, RADAR_FRAMES[f], clip)
        cells = cvf.cells(RS)
        if f == 0:
            for i in range(36):
                out[709 + i] = cells[i]
        out[832 + f] = cells[2]
    return out


GROUPS.append((709, 6, 6, airport_group))
for _f in range(8):
    ANIM[832 + _f] = 711


# ================================================================== nuclear power plant
NUKE_TOWERS = [((1.48, 1.10), 0.54, 0.84), ((2.88, 1.10), 0.50, 0.84)]   # base centre, base radius, height
ATOM = (1.52, 2.50)          # centre of the reactor-roof atom (cell (1,2) is the swirl cell)


def cooling_tower(cv, base, r0, h):
    """Hyperboloid cooling tower: waisted shell of concrete, dark open top with a little vapour."""
    bx, by = base
    conc = hx('#d2d0cc')

    def rf(t):
        return r0 * (1.0 - 0.28 * (1 - ((t - 0.75) / 0.75) ** 2) if t < 0.75 else 0.72 + 0.10 * ((t - 0.75) / 0.25) ** 2) if t < 0.75 else r0 * (0.72 + 0.10 * ((t - 0.75) / 0.25) ** 2)
    disc_stack(cv, bx, by, h, rf, lambda lam: conc[None, None, :] * (0.42 + 0.66 * lam)[..., None], n=64)
    tx, ty = P(bx, by, h)
    rt = rf(1.0)
    X, Y = cv.X, cv.Y
    # rim, then the dark throat with the inner wall lit on the far (north-east) side
    cv.paint(conc * 1.08, cv.cov(sd_circle(X, Y, tx, ty, rt)))
    inner = sd_circle(X, Y, tx, ty, rt - 0.03)
    cv.paint(hx('#3a3a3e'), cv.cov(inner))
    # the far (north-east) inner wall is seen lit; the near one hides the floor
    far = cv.cov(sd_circle(X, Y, tx - 0.22 * rt, ty + 0.22 * rt, rt - 0.03), 6)
    cv.paint(hx('#8c8a86'), cv.cov(inner) * (1 - far))
    cv.paint(hx('#18181b'), cv.cov(inner) * far)
    # a faint haze of vapour over the throat (static)
    hz = np.clip(1 - np.hypot(X - tx + 0.05 * rt, Y - ty + 0.05 * rt) / rt, 0, 1)
    cv.paint(hx('#c8c8cc'), cv.cov(inner) * 0.22 * hz)
    # red warning lights on the rim at north, east, south, west
    for (dx, dy) in ((0, -1), (1, 0), (0, 1), (-1, 0)):
        x, y = tx + dx * (rt - 0.012), ty + dy * (rt - 0.012)
        cv.paint(hx('#ff6a50'), cv.cov(sd_circle(X, Y, x, y, 0.028), 3) * 0.5)
        cv.paint(hx('#e8201a'), cv.cov(sd_circle(X, Y, x, y, 0.016)))


def tower_shadow(base, r0, h):
    pts = []
    bx, by = base
    for k in range(24):
        a = 2 * math.pi * k / 24
        x, y = bx + r0 * math.cos(a), by + r0 * math.sin(a)
        pts += [(x, y), (x + SHADOW_DIR[0] * h, y + SHADOW_DIR[1] * h)]
    return hull(pts)


def atom_static(cv, rx0, ry0, rx1, ry1):
    """The reactor roof: a light square with the atom orbits, as the original's swirl tile."""
    X, Y = cv.X, cv.Y
    ax, ay = ATOM
    cv.paint(PAL['concrete'][3], rect(cv, ax - 0.40, ay - 0.40, ax + 0.40, ay + 0.40, 0.03))
    cv.paint(PAL['concrete'][4], rect(cv, ax - 0.37, ay - 0.37, ax + 0.37, ay + 0.37, 0.025))
    for sg in (1, -1):
        d = _orbit_sdf(X, Y, sg)
        cv.shade(cv.cov(np.abs(d) - 0.016, 2), 0.25)
        cv.paint(PAL['concrete'][1], cv.cov(np.abs(d) - 0.010))
    # nucleus: the original's red cross with an orange heart, glowing
    g = np.clip(1 - np.hypot(X - ax, Y - ay) / 0.14, 0, 1) ** 2
    cv.paint(hx('#ff8a20'), g * 0.6)
    cr = np.minimum(sd_box(X, Y, ax - 0.075, ay - 0.025, ax + 0.075, ay + 0.025, 0.01), sd_box(X, Y, ax - 0.025, ay - 0.075, ax + 0.025, ay + 0.075, 0.01))
    cv.paint(hx('#e8201a'), cv.cov(cr))
    cv.paint(hx('#ff9a1a'), cv.cov(sd_circle(X, Y, ax, ay, 0.025)))
    cv.light(cv.cov(sd_circle(X, Y, ax - 0.008, ay - 0.008, 0.01), 2), 0.6)


ORB_A, ORB_B = 0.35, 0.13


def _orbit_xy(t, sg):
    """Point on orbit sg (+1 / -1: the two diagonals) at phase t in 0..1."""
    ax, ay = ATOM
    a = 2 * math.pi * t
    u, v = ORB_A * math.cos(a), ORB_B * math.sin(a)
    c = math.sqrt(0.5)
    return ax + (u - sg * v) * c, ay + (sg * u + v) * c


def _orbit_sdf(X, Y, sg):
    ax, ay = ATOM
    c = math.sqrt(0.5)
    dx, dy = X - ax, Y - ay
    u = (dx + sg * dy) * c
    v = (-sg * dx + dy) * c
    k = np.hypot(u / ORB_A, v / ORB_B)
    return (k - 1) * min(ORB_A, ORB_B) * 1.3


def electrons(cv, f, clip):
    """Four electrons, two on each orbit, an eighth of an orbit per frame: a 4-frame loop."""
    X, Y = cv.X, cv.Y
    acc = np.zeros_like(X)
    col = np.zeros(cv.img.shape)
    for sg in (1, -1):
        for k in range(2):
            t0 = k * 0.5 + (0.25 if sg < 0 else 0.0) + f / 8.0
            for tr in range(5, 0, -1):       # fading trail behind
                x, y = _orbit_xy(t0 - tr * 0.022, sg)
                m = cv.cov(sd_circle(X, Y, x, y, 0.020 - tr * 0.002), 2) * (0.40 - tr * 0.07)
                col = col * (1 - m[..., None]) + hx('#ffe23a') * m[..., None]
                acc = acc + m * (1 - acc)
            x, y = _orbit_xy(t0, sg)
            gm = cv.cov(sd_circle(X, Y, x, y, 0.040), 6) * 0.45
            col = col * (1 - gm[..., None]) + hx('#fff07a') * gm[..., None]
            acc = acc + gm * (1 - acc)
            m = cv.cov(sd_circle(X, Y, x, y, 0.030))
            col = col * (1 - m[..., None]) + hx('#ffd21a') * m[..., None]
            acc = acc + m * (1 - acc)
            hl = cv.cov(sd_circle(X, Y, x - 0.007, y - 0.007, 0.008), 2)
            col = col * (1 - hl[..., None]) + hx('#fffbe0') * hl[..., None]
    a = (np.clip(acc, 0, 1) * clip)[..., None]
    cv.img = cv.img * (1 - a) + np.clip(col / np.maximum(acc, 1e-6)[..., None] * 1.0, 0, 1) * a if False else cv.img * (1 - a) + col * a


def nuclear_base():
    cv = Canvas(4, 4, RS, ground(4, 4))
    X, Y = cv.X, cv.Y
    # dark asphalt plant ground inside a dirt margin, as the original
    site = rect(cv, 0.46, 0.16, 3.72, 3.66, 0.04)
    paving(cv, site, 0.22, 4)
    paving(cv, rect(cv, 0.90, 1.88, 2.25, 3.30, 0.02), 0.50, 6)      # reactor apron
    paving(cv, rect(cv, 2.85, 2.90, 3.90, 3.80, 0.03), 0.62, 6)      # admin forecourt
    paving(cv, rect(cv, 0.46, 3.30, 2.80, 3.48), 0.40, 8)             # pipe trench
    zone_frame(cv, 'ind')
    hallc = hx('#c8c9cc')
    items = []
    # long low auxiliary building down the west side
    items.append(Box(0.20, 0.30, 0.44, 2.02, 0.14, hallc, PAL['concrete'][5], win={'kind': 'grid', 'floor': 0.1, 'col': 0.12, 'wfrac': 0.4, 'hfrac': 0.4},
                     win_w={'kind': 'grid', 'floor': 0.1, 'col': 0.12, 'wfrac': 0.4, 'hfrac': 0.4},
                     roof_detail=roof_units([(0.2, 0.1, 0.5, 0.05), (0.2, 0.4, 0.5, 0.05), (0.2, 0.7, 0.5, 0.05)])))
    # reactor building: a low square block whose roof carries the atom
    items.append(Box(0.92, 2.04, 2.08, 3.20, 0.14, hx('#b8b9bc'), PAL['concrete'][5], win={'kind': 'grid', 'floor': 0.1, 'col': 0.1, 'wfrac': 0.3, 'hfrac': 0.3},
                     win_w={'kind': 'grid', 'floor': 0.1, 'col': 0.1, 'wfrac': 0.3, 'hfrac': 0.3}, roof_detail=atom_static, rim=PAL['concrete'][7]))
    # turbine hall with the yellow bolt, as the original
    def bolt(c, rx0, ry0, rx1, ry1):
        cx, cy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
        pts = [(cx + x, cy + y) for (x, y) in ((0.04, -0.42), (0.22, -0.42), (0.06, -0.08), (0.20, -0.08), (-0.16, 0.42), (-0.03, 0.04), (-0.16, 0.04))]
        c.shade(c.poly([(x + 0.02, y + 0.015) for x, y in pts]), 0.5)
        c.paint(hx('#ffd21a'), c.poly(pts))
    items.append(Box(2.16, 2.16, 2.92, 3.24, 0.20, hx('#8e9196'), PAL['roof_slate'][2], win={'kind': 'ribs', 'col': 0.04},
                     win_w={'kind': 'ribs', 'col': 0.04}, roof_detail=bolt, rim=PAL['roof_slate'][4]))
    # admin / control building in the south-east
    items.append(Box(3.00, 3.04, 3.80, 3.66, 0.14, hx('#cfd0d4'), PAL['concrete'][6], win={'kind': 'bands', 'floor': 0.07, 'col': 0.05},
                     win_w={'kind': 'bands', 'floor': 0.07, 'col': 0.05}, roof_detail=roof_units([(0.1, 0.2, 0.12, 0.15)])))
    items.append(Custom(lambda c: vehicle(c, 3.18, 3.75, 0.13, 0.075, '#2e8b57'), key=(9, 0)))
    items.append(Custom(lambda c: vehicle(c, 3.36, 3.75, 0.13, 0.075, '#2c4f9e'), key=(9, 0)))
    items.append(Custom(lambda c: vehicle(c, 3.54, 3.75, 0.13, 0.075, '#d9822b'), key=(9, 0)))
    for (base, r0, h) in NUKE_TOWERS:
        items.append(Custom((lambda b=base, r=r0, hh=h: (lambda c: cooling_tower(c, b, r, hh)))(), key=(base[1] - base[0], 0.1), shadow=tower_shadow(base, r0, h)))
    items += [Tree(0.30, 2.95, 0.08, 811), Tree(0.42, 3.22, 0.08, 812), Tree(0.30, 3.48, 0.08, 813), Tree(3.82, 2.02, 0.07, 814)]
    render_in(cv, items)
    return cv


def nuclear_group():
    out = {}
    base = nuclear_base()
    clip = anim_clip(base, [(1, 2)], 0.05)
    for f in range(4):
        cvf = Canvas(4, 4, RS, base.img)
        electrons(cvf, f, clip)
        cells = cvf.cells(RS)
        if f == 0:
            for i in range(16):
                out[811 + i] = cells[i]
        out[952 + f] = cells[2 * 4 + 1]
    return out


GROUPS.append((811, 4, 4, nuclear_group))
for _f in range(4):
    ANIM[952 + _f] = 820
