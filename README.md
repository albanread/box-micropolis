# BOX Micropolis

A port of **Micropolis**, the open-source city simulator, to the BOX: a
version of RISC OS that runs as an application on Linux. In the BOX the
game is a RISC OS desktop program. Its window, menus, tool palette and
properties are an ordinary RISC OS task, and the simulation runs beside it
as a Linux program. The map is drawn on the GPU.

> Micropolis is a registered trademark of Micropolis Corporation (Micropolis
> GmbH) and is licensed here as a courtesy of the owner under the
> [Micropolis Public Name License](micropolis/MicropolisPublicNameLicense.md)
> (<https://www.micropolis.com>).

This is a **modified version** of Micropolis. It is not made, endorsed or
supported by Micropolis GmbH or by Electronic Arts, and it is not SimCity.

## Where it comes from

Micropolis is the GPL release of the original city simulator's source,
which Electronic Arts made in 2008 for the One Laptop Per Child project. This port starts
from **[SimHacker/MicropolisCore](https://github.com/SimHacker/MicropolisCore)
at commit `1e1e038`**. This repository holds only what the port needs:

- **The first commit** is upstream's own files, unchanged:
  - the simulation (`micropolis/engine`, from `packages/micropolis-engine/src`);
  - the cities, strings, tiles and sprites the game builds in (`micropolis/content`);
  - the licences.
- **The second commit** is the BOX's changes and additions, described below.

Upstream's other content (the web front end, the extra tile sets, the
sounds) is not here; it is at the commit above.  The BOX's game plays
upstream's sounds (`content/sounds-wav`) unchanged.

## What the BOX changed

**In the simulation** (`micropolis/engine`), each change is marked `BOX:` in
the source and listed in [micropolis/README.md](micropolis/README.md):

- 32-bit fields for 64-bit hosts, and aligned reads of city files (RISC OS on
  ARM faults on unaligned ones);
- an off-by-one in `voteProblems()` that made no two runs alike;
- sprites constructed properly;
- a fixed random seed for repeatable tests;
- `setSmoke()` putting each chimney's smoke on its own square;
- the classic church only, because the 2008 tiles have no art for the later ones.

**Added:**

| Path | What it is |
|---|---|
| `micropolis/tools`, `micropolis/tests`, `micropolis/build.sh` | a headless driver and a regression test: 32 cities, a century each, compared byte for byte |
| `micropolis/tiles-hd` | the generators for a redrawn tile set at 32, 64 and 128 pixels a tile, drawn by code in the original's layout and style (see its README and STYLE.md) |
| `micropolis/content/images/tiles_hd64.png` | their 64-pixel result, which the game shows as Graphics HD |
| `rosapps/micropolis-engine` | the program the BOX runs: Rust over the C++ simulation (`src/shim.cpp`). It talks to its RISC OS window over a socket (fd 3): the tools and what each costs and gives, the chosen square, the budget, evaluation, graphs, a map of the whole city with its overlays, the news and the sounds. It publishes the map, sprites, overlay colours and art for the GPU through shared memory (fd 4) |
| `rosapps/zigcc` | the compiler wrappers it is built with for the BOX's Linux (zig 0.15, musl) |

The rest of the BOX is not part of this repository: the RISC OS desktop
program and the broker that starts the engine and gives it its window, and
the presenters that draw the map.

## Building

The simulation and its test, for the machine you are on (`micropolis/build.sh`
also cross-builds for the BOX's Linux with zig 0.15):

    sh micropolis/build.sh host
    sh micropolis/tests/run.sh

The engine, for this machine (a test build) or for the BOX
(`x86_64-unknown-linux-musl`, `aarch64-unknown-linux-musl`):

    cd rosapps/micropolis-engine
    cargo build --release
    CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER=rust-lld \
    CC_x86_64_unknown_linux_musl=$PWD/../zigcc/cc-x86_64 \
    CXX_x86_64_unknown_linux_musl=$PWD/../zigcc/cxx-x86_64 \
    AR_x86_64_unknown_linux_musl=$PWD/../zigcc/ar-x86_64 \
        cargo build --release --target x86_64-unknown-linux-musl

The HD tiles, with Python 3, numpy and Pillow:

    cd micropolis/tiles-hd
    python3 build_atlas.py && python3 make_tiles64.py

## Licences

- **The Micropolis code and its 2008 content** are under the GNU General
  Public License, version 3 or later ([micropolis/gpl-3.0.txt](micropolis/gpl-3.0.txt)),
  with Electronic Arts' additional terms under section 7
  ([micropolis/MicropolisGPLLicenseNotice.md](micropolis/MicropolisGPLLicenseNotice.md)).
- **The BOX's changes and additions**, which are built from and with that
  code, are under the same licence and terms: the engine, the generators
  and the tiles they make. The one exception is
  `rosapps/micropolis-engine/src/cxxrt.cpp`, a small C++ runtime that
  contains no Micropolis code; it is MIT, which the GPL allows.
- **The name "Micropolis"** is used under the
  [Micropolis Public Name License](micropolis/MicropolisPublicNameLicense.md),
  with the attribution at the top of this page.

See [NOTICE](NOTICE).
