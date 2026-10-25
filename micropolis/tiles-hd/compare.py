#!/usr/bin/env python3
"""Side-by-side comparisons: original (x4 nearest) | HD redraw, for the shared sample crops.

usage: compare.py [ATLAS64] [--all]
"""
import os
import sys
import importlib.util
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
HD = os.path.dirname(HERE)
CITIES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'content', 'cities')
spec = importlib.util.spec_from_file_location('rc', os.path.join(HERE, 'render_city.py'))
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

FONT = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 28)

# the three headline views asked for, plus the rest of the shared crops with --all
HEAD = [('detroit_downtown', 'scenario_detroit', 31, 44, 24, 16),
        ('rio_coast', 'scenario_rio_de_janeiro', 92, 30, 24, 16),
        ('tokyo_coast', 'scenario_tokyo', 34, 42, 24, 16),
        ('tokyo_downtown', 'scenario_tokyo', 65, 42, 24, 16)]


def crops(all_):
    out = list(HEAD)
    if all_:
        seen = {(c, x, y) for _, c, x, y, _, _ in HEAD}
        for line in open(os.path.join(HERE, 'sample_crops.txt')):
            line = line.split('#')[0].split()
            if len(line) == 5:
                c, x, y, w, h = line[0], *map(int, line[1:])
                if (c, x, y) not in seen:
                    out.append(('%s_%d_%d' % (c.replace('scenario_', ''), x, y), c, x, y, w, h))
    return out


def main():
    atlas_path = os.path.join(HERE, 'atlas_hd64.png')
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if args:
        atlas_path = args[0]
    orig = Image.open(os.path.join(HERE, '..', 'content', 'images', 'tiles.png'))
    hd = Image.open(atlas_path)
    for name, city, x, y, w, h in crops('--all' in sys.argv):
        tiles = rc.load_map(os.path.join(CITIES, city + '.cty'))
        a = rc.render(tiles, orig, 16, x, y, w, h).resize((w * 64, h * 64), Image.NEAREST)
        b = rc.render(tiles, hd, 64, x, y, w, h)
        pad, top = 16, 48
        o = Image.new('RGB', (w * 64 * 2 + pad * 3, h * 64 + top + pad), (24, 24, 28))
        o.paste(a.convert('RGB'), (pad, top))
        o.paste(b.convert('RGB'), (pad * 2 + w * 64, top))
        d = ImageDraw.Draw(o)
        d.text((pad, 10), 'original 16 px x4 (nearest)  -  %s %d,%d' % (city, x, y), font=FONT, fill=(230, 230, 230))
        d.text((pad * 2 + w * 64, 10), 'HD redraw 64 px', font=FONT, fill=(230, 230, 230))
        o.save(os.path.join(HERE, 'compare_%s.png' % name))
        print('compare_%s.png' % name)


if __name__ == '__main__':
    main()


def overviews():
    """Whole-city views: original 16 px | HD (32 px atlas, halved) side by side, plus the HD city at 32 px."""
    import variants as V
    orig = Image.open(os.path.join(HERE, '..', 'content', 'images', 'tiles.png'))
    hd32 = Image.open(os.path.join(HERE, 'atlas_hd32.png')).convert('RGB')
    ext32 = Image.open(os.path.join(HERE, 'atlas_hd32_ext.png')).convert('RGB')
    full = Image.new('RGB', (16 * 32, 64 * 32)); full.paste(hd32, (0, 0)); full.paste(ext32, (0, 60 * 32))
    for city in ('scenario_detroit', 'scenario_tokyo', 'scenario_rio_de_janeiro', 'kowloon'):
        tiles = rc.load_map(os.path.join(CITIES, city + '.cty'))
        a = rc.render(tiles, orig, 16).convert('RGB').resize((120 * 24, 100 * 24), Image.NEAREST)
        b = rc.render(V.apply_variants(tiles), full, 32).convert('RGB')
        b.save(os.path.join(HERE, 'city_hd32_%s.png' % city.replace('scenario_', '')))
        b = b.resize((120 * 24, 100 * 24), Image.LANCZOS)
        pad, top = 16, 48
        o = Image.new('RGB', (a.width * 2 + pad * 3, a.height + top + pad), (24, 24, 28))
        o.paste(a, (pad, top)); o.paste(b, (pad * 2 + a.width, top))
        d = ImageDraw.Draw(o)
        d.text((pad, 10), 'original (whole map) - %s' % city, font=FONT, fill=(230, 230, 230))
        d.text((pad * 2 + a.width, 10), 'HD redraw with variants (32 px atlas, scaled to match)', font=FONT, fill=(230, 230, 230))
        o.save(os.path.join(HERE, 'compare_overview_%s.png' % city.replace('scenario_', '')))
        print('compare_overview_%s.png' % city.replace('scenario_', ''))


if __name__ == '__main__' and '--overview' in sys.argv:
    sys.path.insert(0, HERE)
    overviews()
