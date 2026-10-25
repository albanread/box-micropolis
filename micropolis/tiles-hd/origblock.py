#!/usr/bin/env python3
"""Magnify an original block with a coordinate grid, to read layouts in tile units.

usage: origblock.py BASE W H [OUT] [--sub CELL_TILE=FRAME_TILE ...]
Each original pixel is 1/16 tile. Thin lines every 1/4 tile, bold lines every tile,
labels in tile units along the top and left. Writes OUT (default orig_BASE.png).
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = Image.open(os.path.join(HERE, '..', 'content', 'images', 'tiles.png')).convert('RGB')
Z = 12
M = 34

args = [a for a in sys.argv[1:] if not a.startswith('--') and '=' not in a]
base, w, h = int(args[0]), int(args[1]), int(args[2])
out = args[3] if len(args) > 3 else os.path.join(HERE, 'orig_%d.png' % base)
sub = dict(tuple(map(int, a.split('='))) for a in sys.argv[1:] if '=' in a)
img = Image.new('RGB', (w * 16 * Z + M, h * 16 * Z + M), (255, 255, 255))
for j in range(h):
    for i in range(w):
        t = base + j * w + i
        t = sub.get(t, t)
        c = SRC.crop(((t % 16) * 16, (t // 16) * 16, (t % 16) * 16 + 16, (t // 16) * 16 + 16)).resize((16 * Z, 16 * Z), Image.NEAREST)
        img.paste(c, (M + i * 16 * Z, M + j * 16 * Z))
d = ImageDraw.Draw(img)
f = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 12)
for k in range(w * 4 + 1):
    x = M + k * 4 * Z
    d.line([(x, M), (x, img.height)], fill=(0, 0, 0) if k % 4 == 0 else (255, 255, 255), width=2 if k % 4 == 0 else 1)
    d.text((x - 8, 4 + (k % 2) * 14), '%g' % (k / 4), font=f, fill=(0, 0, 0))
for k in range(h * 4 + 1):
    y = M + k * 4 * Z
    d.line([(M, y), (img.width, y)], fill=(0, 0, 0) if k % 4 == 0 else (255, 255, 255), width=2 if k % 4 == 0 else 1)
    d.text((2, y - 7), '%g' % (k / 4), font=f, fill=(0, 0, 0))
img.save(out)
print(out)
