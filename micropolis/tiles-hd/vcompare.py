#!/usr/bin/env python3
"""HD base atlas vs HD with the extension variants applied (variants.apply_variants).
usage: vcompare.py  -> compare_variants_*.png"""
import os, sys, importlib.util
import numpy as np
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import variants as V
HD = os.path.dirname(HERE)
CITIES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'content', 'cities')
spec = importlib.util.spec_from_file_location('rc', os.path.join(HERE, 'render_city.py'))
rc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rc)
FONT = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 28)
VIEWS = [('tokyo_coast', 'scenario_tokyo', 34, 42, 24, 16), ('rio_coast', 'scenario_rio_de_janeiro', 92, 30, 24, 16),
         ('detroit_80_38', 'scenario_detroit', 80, 38, 24, 16), ('rio_38_4', 'scenario_rio_de_janeiro', 38, 4, 24, 16)]
base = Image.open(os.path.join(HERE, 'atlas_hd64.png')).convert('RGB')
ext = Image.open(os.path.join(HERE, 'atlas_hd64_ext.png')).convert('RGB')
full = Image.new('RGB', (1024, 64 * 64)); full.paste(base, (0, 0)); full.paste(ext, (0, 60 * 64))
for name, city, x, y, w, h in VIEWS:
    t = rc.load_map(os.path.join(CITIES, city + '.cty'))
    tv = V.apply_variants(t)
    a = rc.render(t, base, 64, x, y, w, h).convert('RGB')
    b = rc.render(tv, full, 64, x, y, w, h).convert('RGB')
    pad, top = 16, 48
    o = Image.new('RGB', (w * 64 * 2 + pad * 3, h * 64 + top + pad), (24, 24, 28))
    o.paste(a, (pad, top)); o.paste(b, (pad * 2 + w * 64, top))
    d = ImageDraw.Draw(o)
    d.text((pad, 10), 'HD base atlas - %s %d,%d' % (city, x, y), font=FONT, fill=(230, 230, 230))
    d.text((pad * 2 + w * 64, 10), 'HD + variants (blob coast, woods)', font=FONT, fill=(230, 230, 230))
    o.save(os.path.join(HERE, 'compare_variants_%s.png' % name)); print(name)
