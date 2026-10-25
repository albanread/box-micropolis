"""The tile class table the HD map shader reads (texture `cls`, RGBA8UI 1024x1).

  R  class (C_* below)
  G  footprint edge in tiles (1, 3, 4, 6)
  B  position in the footprint: lx | ly << 4
  A  height, in 64ths of a tile (for shadows)

The table is Micropolis's; the presenter is generic, so the engine supplies
it in the block (tiles.h's cls).  `table()` returns a (1024, 4) uint8 array;
`c_array()` prints it as C: the table in ../src/materials.cpp.
"""
import numpy as np

C_DIRT, C_WATER, C_SHORE, C_TREE, C_RUBBLE, C_FLOOD, C_RAD, C_FIRE = range(8)
C_ROAD, C_BRIDGE, C_POWER, C_RAIL, C_LOT, C_HOUSE, C_BUILD, C_MISC = range(8, 16)


def table():
    t = np.zeros((1024, 4), np.uint8)
    t[:, 0] = C_MISC
    t[:, 1] = 1

    def put(lo, hi, c, size=1, base=None, h=0.0):
        for n in range(lo, hi + 1):
            t[n, 0] = c
            t[n, 1] = size
            if size > 1:
                k = (n - (lo if base is None else base)) % (size * size)
                t[n, 2] = (k % size) | ((k // size) << 4)
            t[n, 3] = int(round(min(h, 3.9) * 64))

    put(0, 1, C_DIRT)
    put(2, 4, C_WATER)
    put(5, 20, C_SHORE)
    put(21, 43, C_TREE, h=0.18)
    put(44, 47, C_RUBBLE)
    put(48, 51, C_FLOOD)
    put(52, 52, C_RAD)
    put(53, 55, C_DIRT)
    put(56, 63, C_FIRE)
    for n in range(64, 208):
        put(n, n, C_BRIDGE if (n - 64) % 16 in (0, 1, 15) else C_ROAD)
    put(208, 222, C_POWER)
    put(208, 209, C_BRIDGE)          # power lines over water
    put(223, 223, C_MISC)
    put(224, 238, C_RAIL)
    put(224, 225, C_BRIDGE)          # rail over water
    put(239, 239, C_ROAD)
    put(240, 248, C_LOT, 3)
    put(249, 260, C_HOUSE, h=0.22)
    # residential 3x3: group g = value*4 + pop
    for g in range(16):
        put(261 + 9 * g, 269 + 9 * g, C_BUILD, 3, h=0.30 + 0.22 * (g % 4))
    put(405, 413, C_BUILD, 3, h=0.55)    # hospital
    put(414, 422, C_BUILD, 3, h=0.55)    # church
    put(423, 431, C_LOT, 3)
    for g in range(20):                  # commercial: value*5 + pop
        put(432 + 9 * g, 440 + 9 * g, C_BUILD, 3, h=0.35 + 0.32 * (g % 5))
    put(612, 620, C_LOT, 3)
    for g in range(8):                   # industrial: value*4 + pop
        put(621 + 9 * g, 629 + 9 * g, C_BUILD, 3, h=0.40 + 0.15 * (g % 4))
    put(693, 708, C_BUILD, 4, h=0.30)    # seaport
    put(709, 744, C_BUILD, 6, h=0.15)    # airport
    put(745, 760, C_BUILD, 4, h=0.75)    # coal
    put(761, 769, C_BUILD, 3, h=0.40)    # fire station
    put(770, 778, C_BUILD, 3, h=0.40)    # police
    put(779, 794, C_BUILD, 4, h=0.60)    # stadium
    put(795, 810, C_BUILD, 4, h=0.60)    # full stadium
    put(811, 826, C_BUILD, 4, h=0.85)    # nuclear
    put(828, 831, C_BRIDGE)              # drawbridge
    put(832, 839, C_BUILD, 1, h=0.20)    # radar (airport)
    put(840, 843, C_LOT)                 # fountain (its green is grass)
    put(844, 859, C_BUILD, 1, h=0.45)    # industrial animations, smoke
    put(916, 959, C_BUILD, 1, h=0.75)    # power plant smoke, etc.
    put(948, 949, C_BRIDGE)              # bridge over water (animation)
    # the fine tiles' variants (ports/micropolis/tiles-hd/variants.json)
    put(960, 962, C_TREE, h=0.18)        # woods
    put(963, 1008, C_SHORE)              # water with beaches
    return t


def c_array(name='tl_class'):
    t = table()
    rows = []
    for i in range(0, 1024, 8):
        rows.append('    ' + ', '.join('0x%08x' % (int(a) | int(b) << 8 | int(c) << 16 | int(d) << 24)
                                       for a, b, c, d in t[i:i + 8]) + ',')
    return 'static const uint32_t %s[1024] = {  /* R32UI: class | size << 8 | (lx | ly << 4) << 16 | height/64 << 24 */\n%s\n};\n' % (
        name, '\n'.join(rows))


if __name__ == '__main__':
    print(c_array())
