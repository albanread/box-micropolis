#!/usr/bin/env python3
"""A small synthetic town that uses every redrawn family and signature building.

Tile numbers are derived with the engine's own rules (REdTab, treeTable, Road/Rail/WireTable),
so seams are tested exactly as the game would place tiles.
Writes compare_showcase.png (original x4 | HD) and showcase_hd64.png.
"""
import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
HD = os.path.dirname(HERE)
W, H = 28, 15

REDTAB = [13, 13, 17, 15, 5, 2, 19, 17, 9, 11, 2, 13, 7, 9, 5, 2]
TREETAB = [0, 0, 0, 34, 0, 0, 36, 35, 0, 32, 0, 33, 30, 31, 29, 37]
ROADT = [66, 67, 66, 68, 67, 67, 69, 73, 66, 71, 66, 72, 70, 75, 74, 76]
RAILT = [226, 227, 226, 228, 227, 227, 229, 233, 226, 231, 226, 232, 230, 235, 234, 236]
WIRET = [210, 211, 210, 212, 211, 211, 213, 217, 210, 215, 210, 216, 214, 219, 218, 220]


def build(frame=1):
    water = np.zeros((H, W), bool)
    for x in range(W):
        top = 3 + int(round(1.3 * math.sin(x / 3.2) + 0.6 * math.sin(x / 1.7)))
        for y in range(0, max(1, top)):
            water[y, x] = True
    tree = np.zeros((H, W), bool)
    for y in range(H):
        for x in range(W):
            if ((x - 3.0) / 3.2) ** 2 + ((y - 7.2) / 2.2) ** 2 < 1 or ((x - 25.5) / 2.2) ** 2 + ((y - 1.0) / 1.6) ** 2 < 1:
                tree[y, x] = True
    tree &= ~water
    road = np.zeros((H, W), bool)
    rail = np.zeros((H, W), bool)
    power = np.zeros((H, W), bool)
    road[5, :] = True
    road[:, 8] = True
    road[5:, 16] = True
    road[10, 8:] = True
    rail[:, 20] = True
    power[4, :20] = True
    power[4:, 24] = False
    zones = {}   # (x0, y0) -> (base, w, h)
    zones[(9, 6)] = (333, 3, 3)
    zones[(12, 6)] = (360, 3, 3)
    zones[(9, 11)] = (504, 3, 3)
    zones[(12, 11)] = (761, 3, 3)
    zones[(17, 6)] = (770, 3, 3)
    zones[(17, 11)] = (648, 3, 3)
    zones[(21, 6)] = (745, 4, 4)
    zones[(21, 11)] = (612, 3, 3)
    zones[(25, 11)] = (423, 3, 3)
    zones[(1, 11)] = (240, 3, 3)    # house zone: centre stays FREEZ, ring gets houses
    zones[(4, 11)] = (240, 3, 3)
    occupied = np.zeros((H, W), bool)
    for (x0, y0), (b, w, h) in zones.items():
        occupied[y0:y0 + h, x0:x0 + w] = True
    tree &= ~occupied & ~road & ~rail & ~power
    t = np.zeros((H, W), int)
    def nb(mask, x, y):
        bits = 0
        if y > 0 and mask[y - 1, x]: bits |= 1
        if x < W - 1 and mask[y, x + 1]: bits |= 2
        if y < H - 1 and mask[y + 1, x]: bits |= 4
        if x > 0 and mask[y, x - 1]: bits |= 8
        return bits
    # water edges (REdTab uses W=8,S=4,E=2,N=1 order: bit order differs, recompute)
    wet = water | (road & water) | (rail & water)
    for y in range(H):
        for x in range(W):
            if water[y, x]:
                idx = 0
                for (dx, dy) in ((-1, 0), (0, 1), (1, 0), (0, -1)):
                    idx <<= 1
                    xx, yy = x + dx, y + dy
                    if not (0 <= xx < W and 0 <= yy < H) or water[yy, xx]:
                        idx += 1
                t[y, x] = REDTAB[idx] if REDTAB[idx] == 2 else REDTAB[idx] + ((x * 7 + y * 3) % 2)
            elif tree[y, x]:
                idx = 0
                for (dx, dy) in ((-1, 0), (0, 1), (1, 0), (0, -1)):
                    idx <<= 1
                    xx, yy = x + dx, y + dy
                    if (0 <= xx < W and 0 <= yy < H) and tree[yy, xx]:
                        idx += 1
                v = TREETAB[idx]
                if v and v != 37 and (x + y) & 1:
                    v -= 8
                t[y, x] = v if v else 0
    roadish = road
    for y in range(H):
        for x in range(W):
            if road[y, x] and rail[y, x]:
                t[y, x] = 238 if road[y, x - 1 if x else x] else 237
            elif road[y, x]:
                if water[y, x]:
                    t[y, x] = 64 if (x > 0 and road[y, x - 1]) else 65
                elif power[y, x]:
                    t[y, x] = 77 if (x > 0 and road[y, x - 1] and not road[max(y - 1, 0), x]) else 78
                else:
                    t[y, x] = ROADT[nb(road, x, y)]
            elif rail[y, x]:
                if water[y, x]:
                    t[y, x] = 225 if ((y > 0 and rail[y - 1, x]) or (y < H - 1 and rail[y + 1, x])) else 224
                elif power[y, x]:
                    t[y, x] = 222
                else:
                    t[y, x] = RAILT[nb(rail, x, y)]
            elif power[y, x]:
                if water[y, x]:
                    t[y, x] = 208
                else:
                    t[y, x] = WIRET[nb(power | (road & power) | (rail & power), x, y)]
    # traffic on some roads
    for y in range(H):
        for x in range(W):
            v = t[y, x]
            if 64 <= v <= 78 and road[y, x]:
                if (x * 5 + y * 3) % 4 == 0:
                    t[y, x] = v + 16 * 5 + 16 * (frame % 4) if v + 80 + 16 * (frame % 4) <= 206 else v
                elif (x + y) % 3 == 0:
                    t[y, x] = v + 16 + 16 * (frame % 4)
    houses = [249, 252, 255, 256, 257, 258, 259, 260, 250, 251, 253, 254]
    hk = 0
    for (x0, y0), (b, w, h) in zones.items():
        for j in range(h):
            for i in range(w):
                v = b + j * w + i
                if b == 240 and not (i == 1 and j == 1):
                    v = houses[hk % len(houses)]
                    hk += 1
                if b == 745:
                    smoke = {(2, 0): 916, (3, 0): 920, (2, 1): 924, (3, 1): 928}
                    if (i, j) in smoke:
                        v = smoke[(i, j)] + frame
                if b == 648 and (i, j) == (1, 0):
                    v = 896 + frame
                t[y0 + j, x0 + i] = v
    for (x, y, k) in ((0, 10, 40), (7, 9, 41), (7, 12, 42), (15, 13, 43), (0, 14, 41)):
        if t[y, x] == 0:
            t[y, x] = k
    return t


def render(t, atlas, p):
    a = np.asarray(atlas.convert('RGB'))
    out = np.zeros((H * p, W * p, 3), np.uint8)
    for y in range(H):
        for x in range(W):
            n = int(t[y, x])
            sx, sy = (n % 16) * p, (n // 16) * p
            out[y * p:(y + 1) * p, x * p:(x + 1) * p] = a[sy:sy + p, sx:sx + p]
    return Image.fromarray(out)


def main():
    orig = Image.open(os.path.join(HD, 'shared', 'tiles.png'))
    hd = Image.open(os.path.join(HERE, 'atlas_hd64.png'))
    t = build(1)
    a = render(t, orig, 16).resize((W * 64, H * 64), Image.NEAREST)
    b = render(t, hd, 64)
    b.save(os.path.join(HERE, 'showcase_hd64.png'))
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 28)
    pad, top = 16, 48
    o = Image.new('RGB', (W * 64 * 2 + pad * 3, H * 64 + top + pad), (24, 24, 28))
    o.paste(a, (pad, top))
    o.paste(b, (pad * 2 + W * 64, top))
    d = ImageDraw.Draw(o)
    d.text((pad, 10), 'original 16 px x4 (nearest)  -  synthetic showcase town', font=font, fill=(230, 230, 230))
    d.text((pad * 2 + W * 64, 10), 'HD redraw 64 px', font=font, fill=(230, 230, 230))
    o.save(os.path.join(HERE, 'compare_showcase.png'))
    # animated smoke / traffic strip: 4 frames of the HD view
    frames = [render(build(f), hd, 64) for f in range(4)]
    frames[0].save(os.path.join(HERE, 'showcase_anim.gif'), save_all=True, append_images=frames[1:], duration=250, loop=0)


if __name__ == '__main__':
    main()
