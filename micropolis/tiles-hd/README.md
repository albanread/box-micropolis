# The fine tiles: Micropolis's city drawn again at 64 pixels a tile

Every tile the game draws, redrawn by code in this folder: the same layout,
view, colours and letters as the 1989 art, with each of its 14 colours
turned into a ramp of shades, one light from the north west, and soft
shadows. Nothing here is copied from any other game's art. The style is set
out in `STYLE.md`.

| File | What it draws |
|---|---|
| `hdlib.py` | the palette ramps, the canvas, noise, shapes |
| `terrain.py` | dirt, water and coast, woods, parks, rubble, flood, radiation, fire |
| `transport.py` | roads with traffic, bridges, rail, power lines, their crossings |
| `buildings.py`, `scene3d.py` | how a building is drawn: blocks, roofs, windows, shadows, cut into cells |
| `blocks_res.py`, `blocks_com.py`, `blocks_ind.py`, `blocks_special.py` | each residential, commercial and industrial block, the hospital and church, and the stadium, seaport, airport and nuclear plant |
| `anims.py` | the other animations: drawbridges, explosion, fountain, radar and smoke frames |
| `variants.py`, `variants.json` | tiles 960 up: more woods, and water with beaches on every side and corner that meets land; the rules the game picks them by |
| `build_atlas.py` | all of it: `atlas_hd32/64/128.png` and the variants (about a minute) |
| `make_tiles64.py` | the game's file: `../content/images/tiles_hd64.png`, 64 pixels, variants included |
| `make_variants_rs.py` | `variants.json` as the engine's Rust (`micropolis-engine/src/variants.rs`) |
| `seamcheck.py` | every pair of tiles the game can put side by side, compared along the shared edge |
| `compare.py`, `vcompare.py`, `render_city.py` | side-by-side views of real cities, classic beside HD |
| `classes.json` | what each of the 960 tiles is (made when the tiles were catalogued) |

To build, with numpy and Pillow:

    python3 build_atlas.py && python3 make_tiles64.py
    python3 make_variants_rs.py > ../../rosapps/micropolis-engine/src/variants.rs

The game shows these as Graphics HD (the View menu): the engine loads
`Tiles64` from its application folder (`ports/rosapps/shell/build.sh` puts
it there), draws woods and coast variants by `variants.json`'s rules, and the
presenter shades the water and casts the shadows over it, as Enhanced does.

They are part of the BOX's port of Micropolis, under its licence (the GNU
GPL version 3 or later with Electronic Arts' additional terms).
