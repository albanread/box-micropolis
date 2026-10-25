#!/usr/bin/env python3
"""The game's fine tiles: the 64-pixel atlas and its variants in one picture.

    make_tiles64.py         after build_atlas.py (which also renders the variants)

Writes ../content/images/tiles_hd64.png: 1024 x 4096, 16 tiles a row, tiles
0..959 the redrawn set in the classic layout and 960..1023 the variants
(variants.json says which the game may draw in place of which).  The engine
loads it as Tiles64 beside itself (Graphics HD).
"""
import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
base = Image.open(os.path.join(HERE, 'atlas_hd64.png')).convert('RGB')
ext = Image.open(os.path.join(HERE, 'atlas_hd64_ext.png')).convert('RGB')
assert base.size == (1024, 3840), base.size
assert ext.size[0] == 1024 and ext.size[1] <= 256, ext.size
out = Image.new('RGB', (1024, 4096), (0, 0, 0))
out.paste(base, (0, 0))
out.paste(ext, (0, 3840))
dest = os.path.join(HERE, '..', 'content', 'images', 'tiles_hd64.png')
out.save(dest, optimize=True)
print(dest, os.path.getsize(dest), 'bytes')
