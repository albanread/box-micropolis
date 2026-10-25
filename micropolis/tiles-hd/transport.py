"""Transport families: roads (+traffic frames, bridges), rail, power lines, crossings.

Edge contracts (tile units, shared by every tile of the family):
  road  : asphalt |c-0.5| <= HW, kerb HW..HW+KW, centre dashes centred 0.25/0.75
  rail  : ballast |c-0.5| <= BW, sleepers every 1/8 (centred (k+.5)/8), rails at +-GA
  power : two wires at +-WG about the pole-top line, which is the centreline
          shifted by the oblique height (OX*PH, -OY*PH)
"""
import math
import numpy as np
from hdlib import *
from terrain import dirt_layer, water_layer, cached

HW = 0.30     # road half width (asphalt)
KW = 0.028    # kerb
BW = 0.21     # ballast half width
SLL = 0.17    # sleeper half length
GA = 0.075    # half gauge
PH = 0.32     # pole height (tile units)
WG = 0.07     # wire half spacing

ARMS = {'N': (0, -1), 'E': (1, 0), 'S': (0, 1), 'W': (-1, 0)}
CORNER = {frozenset('NE'): (1, 0), frozenset('ES'): (1, 1), frozenset('SW'): (0, 1), frozenset('NW'): (0, 0)}


def is_corner(arms):
    return frozenset(arms) in CORNER


def arm_box(X, Y, a, hw):
    if a == 'E':
        return sd_box(X, Y, 0.5 - hw, 0.5 - hw, 1.6, 0.5 + hw)
    if a == 'W':
        return sd_box(X, Y, -0.6, 0.5 - hw, 0.5 + hw, 0.5 + hw)
    if a == 'N':
        return sd_box(X, Y, 0.5 - hw, -0.6, 0.5 + hw, 0.5 + hw)
    return sd_box(X, Y, 0.5 - hw, 0.5 - hw, 0.5 + hw, 1.6)


def band_sdf(X, Y, arms, hw, k=0.10):
    """Signed distance of a road/rail band with the given arms (centreline offset 0.5)."""
    arms = ''.join(sorted(arms))
    if is_corner(arms):
        cx, cy = CORNER[frozenset(arms)]
        return np.abs(np.hypot(X - cx, Y - cy) - 0.5) - hw
    if set(arms) == set('EW') or arms == '':
        return np.abs(Y - 0.5) - hw
    if set(arms) == set('NS'):
        return np.abs(X - 0.5) - hw
    sd = None
    for a in arms:
        b = arm_box(X, Y, a, hw)
        sd = b if sd is None else smin(sd, b, k)
    return sd


# ------------------------------------------------------------------ paths (for rails, lanes, cars)
class Path:
    """A centreline: straight from p0 to p1, or a circular arc."""

    def __init__(self, kind, **kw):
        self.kind = kind
        self.__dict__.update(kw)

    def field(self, X, Y):
        """(signed perpendicular offset, arc-length s, inside-span mask)."""
        if self.kind == 'line':
            (x0, y0), (x1, y1) = self.p0, self.p1
            L = math.hypot(x1 - x0, y1 - y0)
            tx, ty = (x1 - x0) / L, (y1 - y0) / L
            s = (X - x0) * tx + (Y - y0) * ty
            d = -(X - x0) * ty + (Y - y0) * tx
            return d, s + self.s0, (s >= -1e-6) & (s <= L + 1e-6)
        cx, cy, r = self.c[0], self.c[1], self.r
        ang = np.arctan2(Y - cy, X - cx)
        a0, a1 = self.a0, self.a1
        # angles span within a quarter; normalise relative to a0
        rel = (ang - a0 + 3 * math.pi) % (2 * math.pi) - math.pi
        span = a1 - a0
        s = rel * r if span > 0 else -rel * r
        inside = (rel >= -1e-6) & (rel <= span + 1e-6) if span > 0 else (rel <= 1e-6) & (rel >= span - 1e-6)
        d = np.hypot(X - cx, Y - cy) - r
        return d, s, inside

    def length(self):
        if self.kind == 'line':
            return math.hypot(self.p1[0] - self.p0[0], self.p1[1] - self.p0[1])
        return abs(self.a1 - self.a0) * self.r

    def point(self, s, off=0.0):
        """Point and unit tangent at arc length s (0..length), offset sideways by off."""
        if self.kind == 'line':
            (x0, y0), (x1, y1) = self.p0, self.p1
            L = self.length()
            tx, ty = (x1 - x0) / L, (y1 - y0) / L
            return (x0 + tx * s - ty * off, y0 + ty * s + tx * off), (tx, ty)
        sg = 1 if self.a1 > self.a0 else -1
        a = self.a0 + sg * s / self.r
        rr = self.r + off
        px, py = self.c[0] + rr * math.cos(a), self.c[1] + rr * math.sin(a)
        tx, ty = -math.sin(a) * sg, math.cos(a) * sg
        return (px, py), (tx, ty)


def edge_pt(a):
    return {'N': (0.5, 0.0), 'S': (0.5, 1.0), 'E': (1.0, 0.5), 'W': (0.0, 0.5)}[a]


def corner_arc(a, b):
    """Quarter arc of radius 0.5 joining edge midpoints a -> b, around their shared corner."""
    c = CORNER[frozenset(a + b)]
    pa, pb = edge_pt(a), edge_pt(b)
    a0 = math.atan2(pa[1] - c[1], pa[0] - c[0])
    a1 = math.atan2(pb[1] - c[1], pb[0] - c[0])
    d = (a1 - a0 + 3 * math.pi) % (2 * math.pi) - math.pi
    return Path('arc', c=c, r=0.5, a0=a0, a1=a0 + d)


def straight(a, b):
    """Line from edge a to edge b (opposite), with s = global x or y so phases agree."""
    p0, p1 = edge_pt(a), edge_pt(b)
    # s0 aligns arc length with absolute coordinate along the line
    if a in 'WE':
        s0 = 0.0 if a == 'W' else 0.0
    return Path('line', p0=p0, p1=p1, s0=0.0)


def stub(a):
    """Line from the tile centre to edge a."""
    p1 = edge_pt(a)
    return Path('line', p0=(0.5, 0.5), p1=p1, s0=0.5)


def track_paths(arms):
    arms = ''.join(a for a in 'NESW' if a in arms)
    if arms in ('', 'E', 'W', 'EW'):
        return [straight('W', 'E')]
    if arms in ('N', 'S', 'NS'):
        return [straight('N', 'S')]
    if is_corner(arms):
        return [corner_arc(arms[0], arms[1])]
    if len(arms) == 3:
        missing = [a for a in 'NESW' if a not in arms][0]
        opp = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}[missing]
        through = [a for a in arms if a != opp]
        p = [straight(*sorted(through, key='WNES'.index))]
        for t in through:
            p.append(corner_arc(opp, t))
        return p
    return [straight('W', 'E'), straight('N', 'S')]


# ------------------------------------------------------------------ road surface
def asphalt_tex(n=RS):
    def make():
        a = fbm(n, 61, (4, 8, 16), 0.6)
        g = pnoise(n, 96, 62) * 0.5 + pnoise(n, 160, 63) * 0.5
        t = 0.47 + 0.10 * (a - 0.5) * 2 + 0.12 * (g - 0.5) * 2
        return PAL['asphalt'](t)
    return cached(('asph', n), make)


def lane_coord(X, Y, arms):
    """Offset from the road centreline and along-road coordinate (for straights/curves)."""
    arms = ''.join(sorted(arms))
    if is_corner(arms):
        cx, cy = CORNER[frozenset(arms)]
        r = np.hypot(X - cx, Y - cy)
        ang = np.arctan2(Y - cy, X - cx)
        return r - 0.5, np.abs(ang) * 0.5
    if set(arms) == set('NS'):
        return X - 0.5, Y
    return Y - 0.5, X


def draw_road(cv, arms, on_water=False, power=None):
    X, Y = cv.X, cv.Y
    arms = ''.join(a for a in 'NESW' if a in arms)
    sd = band_sdf(X, Y, arms, HW)
    gy, gx = np.gradient(sd)
    gn = np.hypot(gx, gy) + 1e-9
    nx, ny = gx / gn, gy / gn
    junction = len(arms) >= 3
    # kerb / railing outer edge, its shadow onto ground or water (right/down)
    outer = sd - KW
    sh_sd = band_sdf(X - SHADOW_DIR[0] * (0.10 if on_water else 0.025), Y - SHADOW_DIR[1] * (0.10 if on_water else 0.025), arms, HW + KW)
    cv.shade(cv.cov(sh_sd, 3 if not on_water else 6) * (1 - cv.cov(outer)), 0.55 if on_water else 0.35)
    # kerb: concrete; south-facing kerb faces darker, north-west lit
    kerb = cv.cov(outer)
    face = np.clip(ny * 0.8 + nx * 0.4, -1, 1)
    kc = PAL['concrete'](0.62 - 0.30 * np.clip(face, 0, 1) + 0.15 * np.clip(-face, 0, 1))
    if on_water:
        kc = PAL['concrete'](0.70 - 0.35 * np.clip(face, 0, 1))
    cv.paint(kc, kerb)
    # asphalt
    asp = cv.cov(sd)
    tex = asphalt_tex(cv.n)
    cv.paint(tex, asp)
    # wheel-path wear and a soft gutter darkening along the kerb
    if not junction:
        v, s = lane_coord(X, Y, arms)
        for c in (-HW / 2, HW / 2):
            for w in (-0.06, 0.06):
                cv.shade(asp * np.exp(-((v - c - w) / 0.018) ** 2), 0.18)
    cv.shade(asp * smoothstep(-0.03, 0.0, sd), 0.35)
    # inner lip of the kerb: a fine bright line on lit edges
    lip = cv.cov(np.abs(sd - 0.004) - 0.003, 1.0)
    cv.light(lip * np.clip(-face, 0, 1), 0.35)
    # markings
    white = hx('#ecebe4')
    if not junction:
        v, s = lane_coord(X, Y, arms)
        if is_corner(arms):
            ang = s / 0.5  # 0..pi/2 measured from the x axis
            ph = (ang / (math.pi / 2)) % 0.5
            dash = (np.abs(ph - 0.25) < 0.105)
        else:
            ph = s % 0.5
            dash = (np.abs(ph - 0.25) < 0.11)
        line = cv.cov(np.abs(v) - 0.011, 1.0) * dash
        cv.paint(white, line * 0.92 * asp)
    else:
        # zebra crossings on each arm, between the box and the tile edge
        for a in arms:
            if a in 'EW':
                along = X if a == 'E' else 1 - X
                across = Y
            else:
                along = Y if a == 'S' else 1 - Y
                across = X
            zone = (along > 0.5 + HW + 0.035) & (along < 0.5 + HW + 0.135)
            stripes = (np.abs(((across - 0.5) / 0.06) % 1 - 0.5) < 0.27) & (np.abs(across - 0.5) < HW - 0.03)
            cv.paint(white, zone * stripes * 0.85 * asp)
            # stop line
            stop = (np.abs(along - (0.5 + HW + 0.02)) < 0.007) & (np.abs(across - 0.5) < HW - 0.02)
            cv.paint(white, stop * 0.8 * asp)
        if len(arms) == 4:
            # signal post in the centre: red / green lamps
            cv.shade(cv.cov(sd_circle(X, Y, 0.5 + 0.03, 0.5 + 0.016, 0.03), 3), 0.5)
            cv.paint(PAL['steel'][1], cv.cov(sd_box(X, Y, 0.47, 0.47, 0.53, 0.53, 0.012)))
            for (dx, dy, c) in ((0, -0.017, '#ff3b2f'), (0, 0.017, '#ff3b2f'), (-0.017, 0, '#2ee86a'), (0.017, 0, '#2ee86a')):
                cv.paint(hx(c), cv.cov(sd_circle(X, Y, 0.5 + dx, 0.5 + dy, 0.009), 1.2))
                cv.light(cv.cov(sd_circle(X, Y, 0.5 + dx, 0.5 + dy, 0.02), 6) * 0.5, 0.25, hx(c))
    return sd


# ------------------------------------------------------------------ traffic
CAR_COLS = ['#d8d8d4', '#c0392b', '#2c4f9e', '#e8c33a', '#3d8b4f', '#8a8f99', '#f2f2ee', '#6b2d82', '#1e1e22', '#d9822b']


def lane_paths(arms):
    """Driving paths (right-hand traffic) with direction; list of (Path, offset sign)."""
    arms = ''.join(a for a in 'NESW' if a in arms)
    out = []
    if is_corner(arms):
        p = corner_arc(arms[0], arms[1])
        out.append((p, 'L'))
        out.append((p, 'R'))
        return out
    for p in track_paths(arms if len(arms) != 3 else arms)[:1] if len(arms) == 3 else track_paths(arms):
        out.append((p, 'L'))
        out.append((p, 'R'))
    if len(arms) == 3:
        missing = [a for a in 'NESW' if a not in arms][0]
        opp = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}[missing]
        p = stub(opp)
        out.append((p, 'L'))
        out.append((p, 'R'))
    return out


def draw_car(cv, cx, cy, tx, ty, col, L=0.13, W=0.072):
    nx, ny = -ty, tx
    def rect(l, w, ox=0.0, oy=0.0):
        return [(cx + ox + tx * l + nx * w, cy + oy + ty * l + ny * w),
                (cx + ox + tx * l - nx * w, cy + oy + ty * l - ny * w),
                (cx + ox - tx * l - nx * w, cy + oy - ty * l - ny * w),
                (cx + ox - tx * l + nx * w, cy + oy - ty * l + ny * w)]
    cv.shade(cv.blur(cv.poly(rect(L / 2, W / 2, 0.018, 0.012)), 0.006), 0.6)
    body = hx(col)
    cv.paint(body * 0.72, cv.poly(rect(L / 2, W / 2)))
    cv.paint(body, cv.poly(rect(L / 2 - 0.006, W / 2 - 0.007, -0.003, -0.003)))
    # cabin glass toward the front, roof
    cv.paint(hx('#1d2533'), cv.poly([(cx + tx * L * 0.30 + nx * W * 0.36, cy + ty * L * 0.30 + ny * W * 0.36),
                                     (cx + tx * L * 0.30 - nx * W * 0.36, cy + ty * L * 0.30 - ny * W * 0.36),
                                     (cx - tx * L * 0.22 - nx * W * 0.36, cy - ty * L * 0.22 - ny * W * 0.36),
                                     (cx - tx * L * 0.22 + nx * W * 0.36, cy - ty * L * 0.22 + ny * W * 0.36)]))
    cv.paint(body * 1.05, cv.poly(rect(L * 0.17, W * 0.30, -tx * L * 0.03, -ty * L * 0.03)))
    cv.light(cv.poly(rect(L * 0.12, W * 0.12, -tx * L * 0.05 - 0.004, -ty * L * 0.05 - 0.004)), 0.5)
    # head lamps (front) and tail lamps (rear)
    for sgn in (1, -1):
        fx, fy = cx + tx * L * 0.47 + nx * W * 0.32 * sgn, cy + ty * L * 0.47 + ny * W * 0.32 * sgn
        cv.paint(hx('#fff6c8'), cv.cov(sd_circle(cv.X, cv.Y, fx, fy, 0.006), 1.0))
        bx, by = cx - tx * L * 0.47 + nx * W * 0.32 * sgn, cy - ty * L * 0.47 + ny * W * 0.32 * sgn
        cv.paint(hx('#e0201a'), cv.cov(sd_circle(cv.X, cv.Y, bx, by, 0.005), 1.0))


def draw_traffic(cv, arms, frame, heavy, seed):
    arms = ''.join(a for a in 'NESW' if a in arms)
    rng = np.random.default_rng(seed)
    junction = len(arms) >= 3
    L = 0.13
    for pi_, (p, side) in enumerate(lane_paths(arms)):
        length = p.length()
        step = length / 4
        off = HW / 2 * (1 if side == 'R' else -1)
        forward = side == 'R'   # right lane drives along the path direction
        base = rng.uniform(L / 2 + 0.01, step - L / 2 - 0.01) if step > L + 0.02 else step / 2
        slots = [0, 1, 2, 3]
        filled = rng.permutation(4)[: (3 if heavy else 1)]
        if not heavy and rng.random() < 0.35:
            filled = []
        for k in filled:
            ss = (base + k * step + (frame if forward else -frame) * step) % length
            (x, y), (tx, ty) = p.point(ss, off)
            if not forward:
                tx, ty = -tx, -ty
            if junction and abs(x - 0.5) < HW + 0.03 + L / 2 and abs(y - 0.5) < HW + 0.03 + L / 2:
                continue
            ex = abs(tx) * L / 2 + abs(ty) * 0.04 + 0.005
            ey = abs(ty) * L / 2 + abs(tx) * 0.04 + 0.005
            if x - ex < 0 or x + ex > 1 or y - ey < 0 or y + ey > 1:
                continue
            col = CAR_COLS[(seed * 7 + pi_ * 3 + k * 5) % len(CAR_COLS)]
            draw_car(cv, x, y, tx, ty, col)


# ------------------------------------------------------------------ rail
def ballast_tex(n=RS):
    def make():
        g = pnoise(n, 110, 71) * 0.6 + pnoise(n, 200, 72) * 0.4
        lo = fbm(n, 73, (4, 8), 0.6)
        return PAL['ballast'](0.62 + 0.55 * (g - 0.5) * 2 + 0.1 * (lo - 0.5))
    return cached(('ballast', n), make)


def draw_rail(cv, arms, on_water=False, road_cut=None):
    X, Y = cv.X, cv.Y
    paths = track_paths(arms)
    fields = [p.field(X, Y) for p in paths]
    if on_water:
        # steel deck: shadow on the water, girders each side
        dsd = None
        for (d, s, ins) in fields:
            v = np.where(ins, np.abs(d), 9) - (BW + 0.03)
            dsd = v if dsd is None else np.minimum(dsd, v)
        shs = None
        for p in paths:
            d, s, ins = p.field(X - SHADOW_DIR[0] * 0.12, Y - SHADOW_DIR[1] * 0.12)
            v = np.where(ins, np.abs(d), 9) - (BW + 0.03)
            shs = v if shs is None else np.minimum(shs, v)
        cv.shade(cv.cov(shs, 6), 0.55)
        cv.paint(PAL['steel'][2], cv.cov(dsd))
        for (d, s, ins) in fields:
            for sg in (-1, 1):
                g = cv.cov(np.abs(d - sg * (BW + 0.01)) - 0.022) * ins
                cv.paint(PAL['steel'](0.85 if sg < 0 else 0.62), g)
                # truss: diagonal members as dark ticks
                ph = ((s * 8 + (d - sg * (BW + 0.01)) / 0.044 * 0.5 * sg) % 1)
                tick = (np.abs(ph - 0.5) < 0.12) * g
                cv.shade(tick, 0.55)
    else:
        bsd = None
        for (d, s, ins) in fields:
            v = np.where(ins, np.abs(d), 9) - BW
            bsd = v if bsd is None else np.minimum(bsd, v)
        gy, gx = np.gradient(bsd)
        gn = np.hypot(gx, gy) + 1e-9
        face = np.clip((gy * 0.8 + gx * 0.5) / gn, -1, 1)
        # shoulder shadow on the ground
        cv.shade(cv.cov(bsd - 0.02, 4) * (1 - cv.cov(bsd)), 0.25)
        bal = ballast_tex(cv.n)
        cv.paint(bal, cv.cov(bsd))
        # shoulders: lit on the north-west slope, shaded south-east
        sh = smoothstep(-0.05, 0.0, bsd) * cv.cov(bsd)
        cv.shade(sh * np.clip(face, 0, 1), 0.45)
        cv.light(sh * np.clip(-face, 0, 1), 0.18)
    if road_cut is not None:
        keep = 1 - road_cut
    else:
        keep = 1.0
    # sleepers
    for p, (d, s, ins) in zip(paths, fields):
        if p.kind == 'arc':
            n_sl = 6
            ph = (s / p.length() * n_sl) % 1
        else:
            ph = ((s if p.p0[0] != p.p1[0] else s) * 8) % 1
        sl = (np.abs(ph - 0.5) < 0.21) & (np.abs(d) < SLL) & ins
        slm = ndimage.uniform_filter(sl.astype(float), 3)
        cv.shade(np.roll(np.roll(slm, 4, 0), 6, 1) * keep, 0.35)
        tim = PAL['timber'](0.42 + 0.30 * (pnoise(cv.n, 64, 74) - 0.5) + 0.25 * np.clip(-d / SLL, -1, 1) * 0.3)
        if on_water:
            tim = PAL['timber'](0.30 + 0.2 * (pnoise(cv.n, 64, 74) - 0.5))
        cv.paint(tim, slm * keep)
    # rails: shadow, web, polished head
    for p, (d, s, ins) in zip(paths, fields):
        for sg in (-1, 1):
            r = np.abs(d - sg * GA)
            shd = np.abs(d - sg * GA - 0.012) - 0.008
            cv.shade(cv.cov(shd, 1.5) * ins, 0.35)
            cv.paint(PAL['steel'][1], cv.cov(r - 0.012) * ins)
            cv.paint(PAL['steel'][6], cv.cov(np.abs(d - sg * GA + 0.003) - 0.005) * ins)


# ------------------------------------------------------------------ power
def pole_top(): return (0.5 + OX * PH, 0.5 - OY * PH)


def wire_paths(arms):
    """Wire polylines (elevated, already projected) for the given arms, extended past edges."""
    arms = ''.join(a for a in 'NESW' if a in arms) or 'EW'
    if arms in ('E', 'W'):
        arms = 'EW'
    if arms in ('N', 'S'):
        arms = 'NS'
    tx, ty = pole_top()
    out = []
    for a in arms:
        if a in 'EW':
            ex = 1.6 if a == 'E' else -0.6
            for sg in (-1, 1):
                out.append([(tx, ty + sg * WG), (ex, ty + sg * WG)])
        else:
            ey = 1.6 if a == 'S' else -0.6
            for sg in (-1, 1):
                out.append([(tx + sg * WG, ty), (tx + sg * WG, ey)])
    return out


def draw_power(cv, arms, on_water=False, pole=True):
    X, Y = cv.X, cv.Y
    arms = ''.join(a for a in 'NESW' if a in arms) or 'EW'
    wires = wire_paths(arms)
    # wire shadows on the ground: un-project to ground then cast by SHADOW_DIR*PH
    dx = -OX * PH + SHADOW_DIR[0] * PH
    dy = OY * PH + SHADOW_DIR[1] * PH
    for w in wires:
        d = sd_polyline(X, Y, [(x + dx, y + dy) for x, y in w])
        cv.shade(cv.cov(d - 0.008, 2.5), 0.5)
    if pole:
        bx, by = 0.5, 0.5
        tx, ty = pole_top()
        # pole shadow: from base along SHADOW_DIR
        d = sd_segment(X, Y, bx, by, bx + SHADOW_DIR[0] * PH, by + SHADOW_DIR[1] * PH)
        cv.shade(cv.cov(d - 0.010, 2.5), 0.45)
        # crossarm shadow
        cx, cy = bx + SHADOW_DIR[0] * PH, by + SHADOW_DIR[1] * PH
        horiz = all(a in 'EW' for a in arms)
        vert = all(a in 'NS' for a in arms)
        ca = [(0, 1)] if horiz else [(1, 0)] if vert else [(0.7071, 0.7071)] if frozenset(arms) in (frozenset('NE'), frozenset('SW')) else [(0.7071, -0.7071)]
        if len(arms) >= 3:
            ca = [(0, 1), (1, 0)]
        for (ux, uy) in ca:
            d = sd_segment(X, Y, cx - ux * 0.11, cy - uy * 0.11, cx + ux * 0.11, cy + uy * 0.11)
            cv.shade(cv.cov(d - 0.009, 2.5), 0.35)
        if on_water:
            cv.shade(cv.cov(sd_circle(X, Y, bx + 0.03, by + 0.02, 0.06), 4), 0.4)
            cv.paint(PAL['concrete'][5], cv.cov(sd_circle(X, Y, bx, by, 0.05)))
            cv.paint(PAL['concrete'][7], cv.cov(sd_circle(X, Y, bx - 0.012, by - 0.012, 0.03), 2) * 0.6)
        # pole body (oblique), lit on its west side
        d = sd_segment(X, Y, bx, by, tx, ty)
        cv.paint(PAL['timber'][0], cv.cov(d - 0.022))
        d2 = sd_segment(X, Y, bx - 0.008, by - 0.006, tx - 0.008, ty - 0.006)
        cv.paint(PAL['timber'][5], cv.cov(d2 - 0.008, 1.0))
        cv.paint(PAL['timber'][2], cv.cov(sd_circle(X, Y, bx, by, 0.018)))
    # wires (dark, with a faint highlight)
    for w in wires:
        d = sd_polyline(X, Y, w)
        cv.paint(hx('#121216'), cv.cov(d - 0.0105, 1.0))
        d2 = sd_polyline(X, Y, [(x - 0.003, y - 0.003) for x, y in w])
        cv.paint(hx('#8a8f9c'), cv.cov(d2 - 0.0025, 1.0) * 0.8)
    if pole:
        tx, ty = pole_top()
        for (ux, uy) in ca:
            d = sd_segment(X, Y, tx - ux * 0.12, ty - uy * 0.12, tx + ux * 0.12, ty + uy * 0.12)
            cv.paint(PAL['timber'][1], cv.cov(d - 0.014))
            cv.paint(PAL['timber'][5], cv.cov(sd_segment(X, Y, tx - ux * 0.11 - 0.004, ty - uy * 0.11 - 0.004, tx + ux * 0.11 - 0.004, ty + uy * 0.11 - 0.004) - 0.003, 1.0) * 0.8)
        # insulators where wires meet the arm
        pts = set()
        for w in wires:
            pts.add((round(w[0][0], 4), round(w[0][1], 4)))
        for (x, y) in pts:
            cv.paint(hx('#dfe6ea'), cv.cov(sd_circle(X, Y, x, y, 0.011), 1.0))
            cv.paint(hx('#7d8b92'), cv.cov(sd_circle(X, Y, x + 0.003, y + 0.003, 0.005), 1.0))
