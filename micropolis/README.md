# MICROPOLIS — the city simulation, for the BOX and RISC OS 5

*Started 24 October 2026.* Micropolis is the open-source release of the
original SimCity, made by Electronic Arts in 2008 for the One Laptop Per
Child project. This port takes its C++ engine and runs it on the BOX
(x86-64 and arm64) and on RISC OS 5 (32-bit ARM), drawn as a game surface
with an interface of our own.

## Where it comes from

| What | From |
| --- | --- |
| `engine/` | SimHacker/MicropolisCore, `packages/micropolis-engine/src`, at commit `1e1e038` (github.com/SimHacker/MicropolisCore), without its web glue (`emscripten.cpp`, the JavaScript `callback.cpp`, `js_callback.h`) |
| `content/` | the same commit's `content/micropolis`: `cities` (32, the eight scenarios among them), `data` (XML and the original strings), `images` (the classic `tiles.png`, sprites, icons; no Photoshop or Flash files), `sounds` (52, as MP3, under the names the engine's sound callbacks use) |
| `content/sounds-wav/` | SimHacker/micropolis (the 2008 release), `micropolis-activity/res/sounds` at commit `c98f6b0`: 50 sounds as 16-bit mono 22 kHz WAV, which need no decoder; a few names differ from the MP3 set |
| `LICENSE`, `gpl-3.0.txt`, `MicropolisGPLLicenseNotice.md`, `MicropolisPublicNameLicense.md` | the same commit, unchanged |

The add-on city sets in upstream's `content/micropolis/tilesets` (Windows
SimCity Classic's Ancient Asia, Wild West, Moon Colony and others) are not
here. We have no notice that they were released under the GPL, so they will
be an optional pack, kept apart from the game.

## Licences

The code and the 2008 assets are under the GNU GPL version 3 or later, with
Electronic Arts' additional terms (GPL section 7, in
`MicropolisGPLLicenseNotice.md`): no right to the SimCity name or any EA
trademark, modified versions marked as such, and the notice carried with
every copy. The name "Micropolis" is a trademark of Micropolis GmbH; its use
is governed by `MicropolisPublicNameLicense.md` (an attribution on the title
page and in the credits). Whatever we call the finished game, it must never
be called SimCity.

## Our changes to the engine

Each is marked `BOX:` in the source.

| Where | Change | Why |
| --- | --- | --- |
| `data_types.h` | `Quad` and `UQuad` are 32 bits (`int32_t`, `uint32_t`), not `long` | as on the original Unix and upstream's own wasm32 build: a 64-bit host now simulates exactly as a 32-bit one |
| `fileio.cpp` | the file's 32-bit fields are read and written as two 16-bit words (`get_long`, `put_long`) | upstream cast `short *` to `Quad *`: unaligned, which RISC OS 5 faults on, and on 64-bit hosts each store wrote over the next field |
| `fileio.cpp` | a second, raw read of the three funding levels taken out | it undid the first on little-endian hosts; it made no difference, since `initFundingLevel()` sets full funding on every load, as upstream does |
| `fileio.cpp` | `loadScenario()`'s `std::string name = NULL` | a `std::string` built from a null pointer: undefined, and a crash on most libraries |
| `micropolis.h`, `random.cpp` | `setFixedRandomSeed()`: every reseed (loading a city reseeds) uses the fixed seed instead of the clock | repeatable runs, for tests and replays |
| `evaluate.cpp` | `voteProblems()`: `problem >= PROBNUM`, not `>` | it read one past the problem table on the stack and wrote one past `problemVotes`; the stack's contents decided how many random numbers were drawn, so no two runs were alike |
| `sprite.cpp` | `newSprite()` constructs the sprite (`new SimSprite()`) | it was `malloc`'d memory with a `std::string` in it, never constructed |
| `simulate.cpp` | `totalPop` converted through `int` | a float too big for a `short` converts differently on x86 and ARM; through `int` it is defined everywhere |
| `zone.cpp` | `setSmoke()` puts each chimney's smoke on its own cell (dx2/dy2, declared and never used) | a block with two chimneys smoked from one: the second smoke was written over the first |
| `zone.cpp` | `makeHospital()` builds the classic church only (the random number is still drawn) | churches 1 to 7 (tiles 956-1019) are MicropolisCore's later art, which the 2008 tiles do not have; the front end draws any in an old city as the classic church |
| `allocate.cpp`, `micropolis.cpp` | two debugging `printf`s commented out | standard output is the program's |

With these, every city gives the same result on every run, and AddressSanitizer
and UBSan are quiet but for the invalid city class some files carry, which
the engine already corrects.

## Layout

| Path | Contents |
| --- | --- |
| `engine/` | the simulation, 10,400 lines of C++ without comments; it draws nothing and reads no input, and tells its front end what happens through the `Callback` class (`callback.h`) |
| `content/` | cities, data, images and sounds, as above |
| `tools/headless.cpp` | the engine with no interface: runs a city for a number of ticks with a fixed seed and prints the census each simulated year, or (`--roundtrip`) saves a city, loads it back and checks its fields |
| `build.sh` | builds `headless` for this Mac (`host`), the BOX (`x86_64-linux-musl`, `aarch64-linux-musl`) and RISC OS 5 (`arm-linux-musleabihf`, strict alignment) with zig 0.15; output in `rosgd/.cache/micropolis/<target>` |
| `tests/run.sh` | the regression test: all 32 cities, 20,000 ticks each (about a century of the city's time), seed 7, the census compared byte for byte with `tests/expected`; then every city saved and loaded back |

The whole test takes a few seconds: the engine simulates a century of a large
city in under a tenth of a second on the Mac Studio.

## Stages

| Stage | Work | Status |
| --- | --- | --- |
| 1 | the engine in our tree, its defects fixed, building for the BOX and RISC OS 5, the regression test | done on the Mac (24 October 2026); the box and RISC OS builds compile, and are still to be run against `tests/expected` |
| 2 | the map drawn as a game surface (16 × 16 tiles from `tiles.png`, sprites over them; OpenGL on Mesa, Metal on the Mac through the presenter), and the sounds | not started |
| 3 | our own interface: tools, budget, graphs, evaluation, overlays, the small map | not started |
| 4 | the engine in Rust, checked tick by tick against this one until they agree on every city | not started |
| 5 | packaging: the classic tiles, the optional city-set pack, the licence notices and the name | not started |
