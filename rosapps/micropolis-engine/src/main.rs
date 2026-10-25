// SPDX-License-Identifier: GPL-3.0-or-later
//
// rosapps-micropolis -- !Micropolis's engine (ROSAPPS): the Micropolis city
// simulation, EA's 2008 GPL release of the original SimCity, run on the
// box's Linux side and drawn into the broker's sprite.
//
// Micropolis, Unix Version.  This game was released for the Unix platform
// in or about 1990 and has been modified for inclusion in the One Laptop
// Per Child program.  Copyright (C) 1989 - 2007 Electronic Arts Inc.  The
// engine (ports/micropolis/engine) is under the GNU General Public License
// version 3 or later with the ADDITIONAL TERMS per GNU GPL Section 7 in
// ports/micropolis/MicropolisGPLLicenseNotice.md; so is this program.
//
// The simulation is the C++ engine, through shim.cpp.  This program keeps
// its clock -- it runs while the user does nothing -- draws the map from
// the 16 x 16 tiles of tiles.png at the page's zoom, with the trains,
// aircraft, ships and disasters over it, and copies into the page only the
// rows whose tiles changed.
//
// The broker starts it with two descriptors, as it starts the others:
//
//   3  a Unix stream socket: lines of text each way
//   4  the shared buffer: a sprite area whose pixels (32 bpp, premultiplied
//      R G B A, top row first) begin at the offset the broker gives
//
// From the shell:
//   new / open PATH / save PATH / page W H PPMM100 OFFSET / shown / view X Y
//   press X Y MODS, drag, release, dclick, pointer X Y   (picture pixels)
//   key CODE MODS / tool NAME / action NAME / menu I S / prop NAME VALUE / quit
//
// To the shell:
//   hello micropolis 0.1 / doc 1 W H W H / title NAME / modified 0|1
//   saved PATH / error TEXT / props ROW|... / inspect DATE|FUNDS|LINE|NEWS / scrollto X Y
//   damage X0 Y0 X1 Y1

use std::ffi::{CStr, CString};
use std::io::Write;
use std::os::raw::{c_char, c_float, c_int, c_void};
use std::os::unix::io::FromRawFd;
use std::os::unix::net::UnixStream;
use std::time::{Duration, Instant};

mod game;
mod variants;

mod assets {
    include!(concat!(env!("OUT_DIR"), "/assets.rs"));
}

const WORLD_W: usize = 120;
const WORLD_H: usize = 100;
const TILE: usize = 16;
const LOMASK: u16 = 0x03ff;
const TOOL_QUERY: c_int = 5;                    // the engine's EditingTool for the query tool
const CHURCH0BASE: u16 = 414;                   // the classic church, tiles 414-422
const CHURCH1BASE: u16 = 956;                   // churches 1-7, 956-1019: no art in the 2008 tiles

/// the fine tile drawn at X Y: a variant (variants.json) in place of the map's
/// woods and water tiles, so that woods do not repeat and every shore has a
/// beach; MAP is the engine's, column by column
fn fine_tile(map: &[u16], x: usize, y: usize) -> u16 {
    let at = |x: i32, y: i32| -> Option<u16> {
        if x < 0 || y < 0 || x >= WORLD_W as i32 || y >= WORLD_H as i32 {
            None
        } else {
            Some(tile_art(map[x as usize * WORLD_H + y as usize]))
        }
    };
    let (xi, yi) = (x as i32, y as i32);
    let v = at(xi, yi).unwrap_or(0);
    if v == variants::WOODS {
        let k = (variants::hash(xi, yi) % 4) as usize;
        return if k == 0 { v } else { variants::WOODS_VARIANTS[k - 1] };
    }
    if !variants::has(&variants::COAST_REPLACES, v) {
        return v;
    }
    // land round it: N NE E SE S SW W NW, off the map counting as water
    const D: [(i32, i32); 8] = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)];
    let mut m = 0usize;
    for (k, (dx, dy)) in D.iter().enumerate() {
        if let Some(n) = at(xi + dx, yi + dy) {
            if !variants::has(&variants::WATER_SET, n) {
                m |= 1 << k;
            }
        }
    }
    // a corner where a bridge or a crossing meets it keeps its water
    let built = |dx: i32, dy: i32| at(xi + dx, yi + dy).is_some_and(|n| variants::has(&variants::STRUCTURES, n));
    for (k, (dx, dy)) in D.iter().enumerate() {
        if k % 2 == 1 && m & (1 << k) != 0 && (built(0, 0) || built(*dx, 0) || built(0, *dy) || built(*dx, *dy)) {
            m &= !(1 << k);
        }
    }
    variants::COAST_TABLE[m]
}

/// the tile drawn for a map value: churches 1 to 7 as the classic church
fn tile_art(v: u16) -> u16 {
    let n = v & LOMASK;
    if n >= CHURCH1BASE { CHURCH0BASE + (n - CHURCH1BASE) % 9 } else { n }
}
const MAX_SPRITES: usize = 64;
/// the shell's pixels to the millimetre at 100% (90 dpi)
const PPMM_100: f64 = 3.54;

// The tile map the presenter draws (rosgd/include/rosgd/tiles.h): its
// block's layout, which this mirrors byte for byte
const TL_MAGIC: u32 = 0x53454C54;
const TL_VERSION: u32 = 3;
const TL_MAP: usize = 128;
const TL_SPRITES: usize = 256;
const TL_CLASSES: usize = 1024;
const TL_SPR_W: usize = 512;
const TL_SPR_H: usize = 512;
const TL_AT_MAP: usize = 64;
const TL_AT_SPRITE: usize = TL_AT_MAP + TL_MAP * TL_MAP * 2;
const TL_AT_OVL: usize = TL_AT_SPRITE + TL_SPRITES * 16;
const TL_AT_CLS: usize = TL_AT_OVL + TL_MAP * TL_MAP * 4;
const TL_AT_SPR: usize = TL_AT_CLS + TL_CLASSES * 4;
const TL_AT_ATLAS: usize = TL_AT_SPR + TL_SPR_W * TL_SPR_H * 4;
/// the whole block for an atlas of W x H: the picture, then its materials
const fn tl_size(w: usize, h: usize) -> usize {
    TL_AT_ATLAS + w * h * 5
}
// the head's fields past the first 48 bytes
const TL_AT_ATLAS_W: usize = 48;
const TL_AT_QUALITY: usize = 52;
const TL_AT_DAYLIGHT: usize = 53;
const TL_AT_RATE: usize = 54;
const TL_AT_OVERLAY: usize = 55;
/// the presenter's drawings (tiles.h's ROS_TILES_Q_*), as the properties name them
const QUALITIES: [&str; 4] = ["Classic", "Smooth", "Enhanced", "HD"];
const Q_RICH: u8 = 2;                           // tiles.h's ROS_TILES_Q_RICH
const Q_HD: u8 = 3;                             // ours: the fine tiles (Tiles64), drawn rich
const SPR_CELL: usize = 48;                     // the sprites' picture: 48-pixel cells

#[repr(C)]
struct Event {
    kind: c_int,
    a: c_int,
    b: c_int,
    c: c_int,
    d: c_int,
    e: c_int,
    f: c_int,
    g: c_int,
    h: c_int,
    text: [c_char; 120],
}

impl Default for Event {
    fn default() -> Event {
        Event { kind: 0, a: 0, b: 0, c: 0, d: 0, e: 0, f: 0, g: 0, h: 0, text: [0; 120] }
    }
}

#[repr(C)]
#[derive(Default, Clone, PartialEq)]
struct Status {
    funds: c_int,
    pop: c_int,
    score: c_int,
    city_class: c_int,
    tax: c_int,
    year: c_int,
    month: c_int,
    speed: c_int,
    paused: c_int,
    level: c_int,
    scenario: c_int,
    disasters: c_int,
    auto_budget: c_int,
    res_demand: c_float,
    com_demand: c_float,
    ind_demand: c_float,
    road_percent: c_float,
    fire_percent: c_float,
    police_percent: c_float,
    road_fund: c_int,
    fire_fund: c_int,
    police_fund: c_int,
    tax_fund: c_int,
}

#[repr(C)]
#[derive(Default, Clone, Copy, PartialEq)]
struct Sprite {
    kind: c_int,
    frame: c_int,
    x: c_int,
    y: c_int,
    width: c_int,
    height: c_int,
    x_offset: c_int,
    y_offset: c_int,
}

const EV_MESSAGE: c_int = 1;
const EV_ZONE: c_int = 2;
const EV_GOTO: c_int = 3;
const EV_BUDGET: c_int = 4;
const EV_WIN: c_int = 5;
const EV_LOSE: c_int = 6;

extern "C" {
    fn mp_new() -> *mut c_void;
    fn mp_generate(c: *mut c_void, level: c_int);
    fn mp_load(c: *mut c_void, path: *const c_char) -> c_int;
    fn mp_scenario(c: *mut c_void, s: c_int);
    fn mp_save(c: *mut c_void, path: *const c_char) -> c_int;
    fn mp_tick(c: *mut c_void);
    fn mp_animate(c: *mut c_void);
    fn mp_map(c: *mut c_void) -> *const u16;
    fn mp_tool(c: *mut c_void, tool: c_int, x: c_int, y: c_int) -> c_int;
    fn mp_set_speed(c: *mut c_void, speed: c_int);
    fn mp_set_tax(c: *mut c_void, tax: c_int);
    fn mp_set_funding(c: *mut c_void, road: c_float, fire: c_float, police: c_float);
    fn mp_set_auto_budget(c: *mut c_void, on: c_int);
    fn mp_set_disasters(c: *mut c_void, on: c_int);
    fn mp_set_auto_goto(c: *mut c_void, on: c_int);
    fn mp_set_clean_name(c: *mut c_void, name: *const c_char);
    fn mp_set_level(c: *mut c_void, level: c_int);
    fn mp_disaster(c: *mut c_void, which: c_int);
    fn mp_status(c: *mut c_void, s: *mut Status);
    fn mp_name(c: *mut c_void, buf: *mut c_char, len: c_int);
    fn mp_next_event(c: *mut c_void, ev: *mut Event) -> c_int;
    fn mp_sprites(c: *mut c_void, out: *mut Sprite, max: c_int) -> c_int;
    fn mp_tile_classes() -> *const u32;
    fn mp_tile_materials(atlas: *const u32, w: c_int, h: c_int, out: *mut u8);
    fn mp_fine_materials(atlas: *const u32, w: c_int, h: c_int, tile: c_int, out: *mut u8);
}

// ── The palette's tools ─────────────────────────────────────────────────

/// name in the shell's palette, the engine's EditingTool, whether a drag
/// lays it along the way (roads, rails, wires, parks, the bulldozer)
const TOOLS: [(&str, c_int, bool); 17] = [
    ("mp_query", 5, false),
    ("rs_pan", -1, false), // the shell's hand: it moves the window, the engine does nothing
    ("mp_bulldozer", 7, true),
    ("mp_road", 9, true),
    ("mp_rail", 8, true),
    ("mp_wire", 6, true),
    ("mp_park", 11, true),
    ("mp_residential", 0, false),
    ("mp_commercial", 1, false),
    ("mp_industrial", 2, false),
    ("mp_police", 4, false),
    ("mp_fire", 3, false),
    ("mp_stadium", 10, false),
    ("mp_seaport", 12, false),
    ("mp_coal", 13, false),
    ("mp_nuclear", 14, false),
    ("mp_airport", 15, false),
];

/// each EditingTool's footprint, in squares (the engine's gToolSize): a
/// building of more than one square has the square clicked one in from its
/// top left corner
const TOOL_SIZE: [i32; 16] = [3, 3, 3, 3, 3, 1, 1, 1, 1, 1, 4, 1, 4, 4, 4, 6];
const OUTLINE: [u8; 4] = [255, 214, 0, 255];

const SCENARIOS: [&str; 8] = [
    "scenario_dullsville.cty",
    "scenario_san_francisco.cty",
    "scenario_hamburg.cty",
    "scenario_bern.cty",
    "scenario_tokyo.cty",
    "scenario_detroit.cty",
    "scenario_boston.cty",
    "scenario_rio_de_janeiro.cty",
];

const MONTHS: [&str; 12] = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const CLASSES: [&str; 6] = ["Village", "Town", "City", "Capital", "Metropolis", "Megalopolis"];
const LEVELS: [&str; 3] = ["Easy", "Medium", "Hard"];
const SPEEDS: [&str; 5] = ["Paused", "Slow", "Medium", "Fast", "Very fast"];
/// simulation ticks a second at each speed (a month is about 16 ticks)
const TICKS_PER_SECOND: [u32; 5] = [0, 2, 6, 12, 30];

// ── Images ────────────────────────────────────────────────────────────────

/// a picture as premultiplied R G B A bytes
struct Image {
    w: usize,
    h: usize,
    px: Vec<u8>,
}

fn decode(png_bytes: &[u8]) -> Option<Image> {
    let mut dec = png::Decoder::new(png_bytes);
    dec.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut r = dec.read_info().ok()?;
    let mut buf = vec![0; r.output_buffer_size()];
    let info = r.next_frame(&mut buf).ok()?;
    let (w, h) = (info.width as usize, info.height as usize);
    let mut px = vec![0u8; w * h * 4];
    for i in 0..w * h {
        let (r_, g, b, a) = match info.color_type {
            png::ColorType::Rgba => (buf[i * 4], buf[i * 4 + 1], buf[i * 4 + 2], buf[i * 4 + 3]),
            png::ColorType::Rgb => (buf[i * 3], buf[i * 3 + 1], buf[i * 3 + 2], 255),
            png::ColorType::GrayscaleAlpha => (buf[i * 2], buf[i * 2], buf[i * 2], buf[i * 2 + 1]),
            _ => (buf[i], buf[i], buf[i], 255),
        };
        let pm = |c: u8| ((c as u32 * a as u32 + 127) / 255) as u8;
        px[i * 4..i * 4 + 4].copy_from_slice(&[pm(r_), pm(g), pm(b), a]);
    }
    Some(Image { w, h, px })
}

// ── The page ──────────────────────────────────────────────────────────────

struct Buffer {
    base: *mut u8,
    len: usize,
}

impl Buffer {
    fn map() -> Option<Buffer> {
        let mut st: libc::stat = unsafe { std::mem::zeroed() };
        if unsafe { libc::fstat(4, &mut st) } != 0 || st.st_size <= 0 {
            return None;
        }
        let len = st.st_size as usize;
        let p = unsafe {
            libc::mmap(std::ptr::null_mut(), len, libc::PROT_READ | libc::PROT_WRITE, libc::MAP_SHARED, 4, 0)
        };
        if p == libc::MAP_FAILED {
            return None;
        }
        Some(Buffer { base: p as *mut u8, len })
    }

    /// the rectangle X0 Y0 X1 Y1 of the frame into the buffer: only the
    /// columns that changed, so that a few squares cost a few squares
    fn rect(&self, px: &[u8], w: usize, offset: usize, (x0, y0, x1, y1): (usize, usize, usize, usize)) {
        let row = w * 4;
        if offset + y1 * row > self.len || x1 > w {
            return;
        }
        for y in y0..y1 {
            let at = y * row + x0 * 4;
            unsafe {
                std::ptr::copy_nonoverlapping(px[at..].as_ptr(), self.base.add(offset + at), (x1 - x0) * 4);
            }
        }
    }
}

impl Drop for Buffer {
    fn drop(&mut self) {
        unsafe { libc::munmap(self.base as *mut c_void, self.len) };
    }
}

// ── The engine ────────────────────────────────────────────────────────────

struct Engine {
    out: UnixStream,
    city: *mut c_void,
    tiles: Image,
    sprites: Vec<(u32, u32, Image)>,
    messages: Vec<String>,
    // the page
    buf: Option<Buffer>,
    offset: usize,
    pw: usize,
    ph: usize,
    px: Vec<u8>,
    zoom: f64,          // map pixels (16 to a square) to the page's
    sx: f64,            // the view's top left in the map, in pixels at the zoom
    sy: f64,
    told_extent: (i64, i64),
    waiting: bool,
    owed: Option<(usize, usize, usize, usize)>, // x0 y0 x1 y1, not yet in the buffer
    // what the page shows
    shown: Vec<u16>,    // each tile as last drawn (0xffff: never)
    shown_sprites: Vec<Sprite>,
    // the game
    speed: usize,
    tool: usize,
    last_tile: Option<(i32, i32)>,
    hover: Option<(i32, i32)>,                  // the square under the pointer
    shown_hover: Option<(i32, i32, i32)>,       // the footprint drawn: left, top, size
    path: Option<String>,
    modified: bool,
    news: String,
    told_props: String,
    told_inspect: String,
    workdir: std::path::PathBuf,
    follow: bool,                               // the view goes to disasters and events
    // the tile map, where the presenter draws it ("tiles OFFSET")
    tiles_at: Option<usize>,
    tiles_art: bool,                            // the pictures are in the block
    quality: u8,                                // the presenter's drawing (QUALITIES)
    fine: Option<Image>,                        // the 64-pixel tiles, if the application has them
    art_gen: u32,                               // the block's art, moved on when it changes
    art_fine: bool,                             // the block holds the fine tiles
    told_ticks: Vec<u8>,                        // the View menu's entries, as last told
    night: bool,
    pub_look: (u8, u8),                         // the quality and daylight in the block
    tiles_owed: bool,                           // the block changed since "tiles" was said
    pub_map: Vec<u16>,                          // the map as last put in the block
    pub_sprites: Vec<Sprite>,
    pub_foot: Option<Option<(i32, i32, i32)>>,
    pub_ovl: Option<bool>,                      // the overlay in the block: shown or not
    ui: game::Ui,
}

impl Engine {
    fn say(&mut self, s: String) {
        let _ = self.out.write_all(s.as_bytes());
        let _ = self.out.write_all(b"\n");
    }

    /// a line of text for the user, in RISC OS Latin-1
    fn say_text(&mut self, kind: &str, text: &str) {
        let mut b = format!("{kind} ").into_bytes();
        b.extend(text.chars().map(|c| if (c as u32) < 256 { c as u8 } else { b'?' }));
        b.push(b'\n');
        let _ = self.out.write_all(&b);
    }

    fn status(&self) -> Status {
        let mut s = Status::default();
        unsafe { mp_status(self.city, &mut s) };
        s
    }

    fn city_name(&self) -> String {
        let mut b = [0 as c_char; 64];
        unsafe { mp_name(self.city, b.as_mut_ptr(), 64) };
        unsafe { CStr::from_ptr(b.as_ptr()) }.to_string_lossy().into_owned()
    }

    // ── documents ──

    /// the map's size at the zoom: the window's work area
    fn tell_extent(&mut self) {
        let k = self.zoom * TILE as f64;
        let e = ((WORLD_W as f64 * k).ceil() as i64, (WORLD_H as f64 * k).ceil() as i64);
        if e != self.told_extent {
            self.told_extent = e;
            self.say(format!("extent {} {}", e.0, e.1));
        }
    }

    fn tell_doc(&mut self) {
        // the extent first: the window opens within it
        self.told_extent = (0, 0);
        self.tell_extent();
        let mm = |px: usize| ((px as f64 / PPMM_100) * 100.0).round() as i64;
        let (w, h) = (mm(WORLD_W * TILE), mm(WORLD_H * TILE));
        self.say(format!("doc 1 {w} {h} {w} {h}"));
    }

    fn fresh(&mut self, title: &str) {
        self.shown.fill(0xffff);
        self.shown_sprites.clear();
        self.modified = false;
        self.say_text("title", title);
        self.say("modified 0".into());
        self.tell_doc();
        self.set_speed(self.speed.max(1));
        self.news.clear();
    }

    fn new_city(&mut self, level: c_int) {
        unsafe { mp_generate(self.city, level) };
        self.path = None;
        self.fresh("New city");
    }

    fn open(&mut self, path: &str) {
        let Ok(c) = CString::new(path) else { return };
        if unsafe { mp_load(self.city, c.as_ptr()) } == 0 {
            self.say_text("error", &format!("{path} is not a city !Micropolis can read."));
            return;
        }
        self.path = Some(path.to_string());
        // the city is its file's leaf, as RISC OS names it: HostFS's
        // ",a9c" type suffix off, and "/" (a RISC OS name's dot) a dot
        let leaf = path.rsplit('/').next().unwrap_or(path);
        let leaf = match leaf.rsplit_once(',') {
            Some((name, t)) if t.len() == 3 && t.chars().all(|c| c.is_ascii_hexdigit()) => name,
            _ => leaf,
        };
        let leaf = leaf.strip_suffix(".cty").unwrap_or(leaf);
        if let Ok(n) = CString::new(leaf) {
            unsafe { mp_set_clean_name(self.city, n.as_ptr()) };
        }
        let name = self.city_name();
        self.fresh(&name);
    }

    fn scenario(&mut self, n: usize) {
        if n >= SCENARIOS.len() || !self.unpack_cities() {
            return;
        }
        // the engine opens cities/scenario_*.cty where it runs
        let _ = std::env::set_current_dir(&self.workdir);
        unsafe { mp_scenario(self.city, n as c_int + 1) };
        self.path = None;
        let name = self.city_name();
        self.fresh(&name);
    }

    /// the cities the engine carries, written where it can open them
    fn unpack_cities(&mut self) -> bool {
        let dir = self.workdir.join("cities");
        if dir.join(SCENARIOS[0]).exists() {
            return true;
        }
        if std::fs::create_dir_all(&dir).is_err() {
            return false;
        }
        assets::CITIES.iter().all(|(name, bytes)| std::fs::write(dir.join(name), bytes).is_ok())
    }

    fn save(&mut self, path: &str) {
        let Ok(c) = CString::new(path) else { return };
        if unsafe { mp_save(self.city, c.as_ptr()) } == 0 {
            self.say_text("error", &format!("{path} could not be written."));
            return;
        }
        self.path = Some(path.to_string());
        self.modified = false;
        self.say("modified 0".into());
        self.say_text("saved", path);
    }

    fn set_speed(&mut self, speed: usize) {
        self.speed = speed.min(SPEEDS.len() - 1);
        // the engine's own speed decides only whether it runs: the clock here
        // decides how fast
        unsafe { mp_set_speed(self.city, if self.speed == 0 { 0 } else { 3 }) };
    }

    fn touched(&mut self) {
        if !self.modified {
            self.modified = true;
            self.say("modified 1".into());
        }
    }

    // ── the pointer ──

    /// the square under a point in the view
    fn tile_at(&self, x: f64, y: f64) -> (i32, i32) {
        let k = self.scale() * TILE as f64;
        (((x + self.sx) / k).floor() as i32, ((y + self.sy) / k).floor() as i32)
    }

    fn scale(&self) -> f64 {
        self.zoom
    }

    /// squares X0 Y0 to X1 Y1 (exclusive) as a box in the view, clipped to it
    fn view_box(&self, x0: i32, y0: i32, x1: i32, y1: i32) -> Option<(usize, usize, usize, usize)> {
        let k = self.scale() * TILE as f64;
        let cx = |v: i32| ((v as f64 * k).floor() - self.sx).clamp(0.0, self.pw as f64) as usize;
        let cy = |v: i32| ((v as f64 * k).floor() - self.sy).clamp(0.0, self.ph as f64) as usize;
        let r = (cx(x0), cy(y0), cx(x1), cy(y1));
        if r.2 > r.0 && r.3 > r.1 { Some(r) } else { None }
    }

    /// the squares in view: left, top, right, bottom (exclusive)
    fn in_view(&self) -> (usize, usize, usize, usize) {
        let k = self.scale() * TILE as f64;
        let t = |v: f64, max: usize| ((v / k).floor().max(0.0) as usize).min(max);
        (t(self.sx, WORLD_W), t(self.sy, WORLD_H),
         t(self.sx + self.pw as f64 + k, WORLD_W), t(self.sy + self.ph as f64 + k, WORLD_H))
    }

    /// the view moved: everything in it is drawn again
    fn set_view(&mut self, sx: f64, sy: f64) {
        if self.tiles_at.is_some() {
            return;                             // the pointer's places include the scroll already
        }
        if (sx, sy) != (self.sx, self.sy) {
            self.sx = sx;
            self.sy = sy;
            self.repaint();
        }
    }

    fn repaint(&mut self) {
        self.px.fill(0);
        self.shown.fill(0xffff);
        self.shown_sprites.clear();
        self.owed = if self.pw > 0 { Some((0, 0, self.pw, self.ph)) } else { None };
    }

    fn apply(&mut self, tx: i32, ty: i32) {
        if tx < 0 || ty < 0 || tx >= WORLD_W as i32 || ty >= WORLD_H as i32 {
            return;
        }
        // the query tool too: the engine reports the zone (EV_ZONE)
        let (_, tool, _) = TOOLS[self.tool];
        if tool < 0 {
            return;
        }
        match unsafe { mp_tool(self.city, tool, tx, ty) } {
            1 if tool != TOOL_QUERY => {
                self.touched();
                self.tool_sound(self.tool);
            }
            -2 => self.set_news("There is not enough money for that."),
            -1 => self.set_news("The ground must be bulldozed first."),
            _ => {}
        }
    }

    fn press(&mut self, x: f64, y: f64) {
        let t = self.tile_at(x, y);
        self.last_tile = Some(t);
        self.apply(t.0, t.1);
    }

    fn drag(&mut self, x: f64, y: f64) {
        if !TOOLS[self.tool].2 {
            return;
        }
        let t = self.tile_at(x, y);
        let Some(from) = self.last_tile else {
            self.last_tile = Some(t);
            self.apply(t.0, t.1);
            return;
        };
        if from == t {
            return;
        }
        // every tile on the way, so that a fast drag leaves no gaps
        let (dx, dy) = (t.0 - from.0, t.1 - from.1);
        let n = dx.abs().max(dy.abs());
        for i in 1..=n {
            let p = (from.0 + dx * i / n, from.1 + dy * i / n);
            self.apply(p.0, p.1);
        }
        self.last_tile = Some(t);
    }

    fn set_tool(&mut self, name: &str) {
        if let Some(i) = TOOLS.iter().position(|t| t.0 == name) {
            self.tool = i;
            self.ui.page = 0;                   // the pane says what the tool is
            self.panes();
        }
    }

    // ── news and the panes ──

    fn set_news(&mut self, text: &str) {
        self.news = text.to_string();
    }

    fn events(&mut self) {
        let mut ev = Event::default();
        while unsafe { mp_next_event(self.city, &mut ev) } != 0 {
            match ev.kind {
                EV_MESSAGE => {
                    let i = ev.a.unsigned_abs() as usize;
                    if i >= 1 && i <= self.messages.len() {
                        let m = self.messages[i - 1].clone();
                        self.set_news(&m);
                        let at = if ev.b >= 0 && ev.c >= 0 { Some((ev.b, ev.c)) } else { None };
                        self.news_add(&m, at);
                    }
                    // a disaster's or an important event's place: the view
                    // goes there, as the original's auto-goto did
                    if self.follow && ev.e != 0 && ev.b >= 0 && ev.c >= 0 {
                        self.go_to(ev.b, ev.c);
                    }
                }
                EV_ZONE => {
                    // the engine's numbers are lines of its string files, from 1
                    let line = |text: &str, n: c_int| {
                        text.lines().nth((n - 1).max(0) as usize).map(|l| l.trim().to_string()).unwrap_or_default()
                    };
                    let st = |n: c_int| line(assets::ZONE_STATUS, n).to_lowercase();
                    // past the names' end is bare ground (the engine's own
                    // comment: "This breaks the program (when you click 'dirt')")
                    let mut what = line(assets::ZONE_NAMES, ev.a);
                    if what.is_empty() {
                        what = "Clear".into();
                    }
                    let text = format!(
                        "{what}: {} density, land value {}, crime {}, pollution {}, {}",
                        st(ev.b), st(ev.c), st(ev.d), st(ev.e), st(ev.f)
                    );
                    self.set_news(&text);
                    let cap = |t: String| {
                        let mut c = t.chars();
                        c.next().map(|f| f.to_uppercase().collect::<String>() + c.as_str()).unwrap_or_default()
                    };
                    let rows = vec![
                        ("Population".to_string(), cap(st(ev.b))),
                        ("Land value".to_string(), cap(st(ev.c))),
                        ("Crime".to_string(), cap(st(ev.d))),
                        ("Pollution".to_string(), cap(st(ev.e))),
                        ("Growth".to_string(), cap(st(ev.f))),
                    ];
                    self.select(ev.g, ev.h, what, rows);
                }
                EV_GOTO => {
                    if self.follow {
                        self.go_to(ev.a, ev.b);
                    }
                }
                EV_BUDGET => self.budget_due(),
                EV_WIN => {
                    self.news_add("The scenario is won.", None);
                    self.say_text("note", "You have won the scenario: the city is a success.");
                }
                EV_LOSE => {
                    self.news_add("The scenario is lost.", None);
                    self.say_text("note", "You have lost the scenario: the city has failed.");
                }
                game::EV_SOUND => {
                    let t = unsafe { CStr::from_ptr(ev.text.as_ptr()) }.to_string_lossy().into_owned();
                    let name = t.split_whitespace().nth(1).unwrap_or("").to_string();
                    self.sound(&name);
                }
                _ => {}
            }
        }
    }

    /// square X Y to the middle of the view
    fn go_to(&mut self, x: c_int, y: c_int) {
        let k = self.scale() * TILE as f64;
        let (cx, cy) = (((x as f64 + 0.5) * k) as i64, ((y as f64 + 0.5) * k) as i64);
        self.say(format!("centre {cx} {cy}"));
    }

    fn menu(&mut self, menu: i64, item: i64) {
        match (menu, item) {
            // the app's own menus come after File, Edit and View: City,
            // Scenarios, Disasters
            (3, 0..=2) => self.new_city(item as c_int),
            (4, 0..=7) => self.scenario(item as usize),
            (5, 0..=5) => unsafe { mp_disaster(self.city, item as c_int) },
            // the View menu's own entries: the drawing, then Night
            (2, 0..=3) if item as u8 != Q_HD || self.fine.is_some() => {
                self.quality = item as u8;
                self.panes();
            }
            (2, 4) => {
                self.night = !self.night;
                self.panes();
            }
            _ => {}
        }
    }

    fn key(&mut self, code: u32) {
        // Space, as in most games, stops and starts the clock
        if code == 32 {
            let s = if self.speed == 0 { 2 } else { 0 };
            self.set_speed(s);
            self.panes();
        }
    }

    // ── drawing ──

    /// the footprint of the tool under the pointer: left, top, size
    fn footprint(&self) -> Option<(i32, i32, i32)> {
        if TOOLS[self.tool].1 == TOOL_QUERY {
            // the query tool: the square chosen, its whole building framed
            let sel = self.ui.sel.as_ref()?;
            return Some(self.footprint_at(sel.x, sel.y));
        }
        let (tx, ty) = self.hover?;
        let tool = TOOLS[self.tool].1;
        if tool < 0 {
            return None;
        }
        let size = TOOL_SIZE[tool as usize];
        let (x, y) = if size > 1 { (tx - 1, ty - 1) } else { (tx, ty) };
        Some((x, y, size))
    }

    /// a frame round squares X Y to X+SIZE, two pixels wide, inside them
    fn draw_outline(&mut self, (x, y, size): (i32, i32, i32)) {
        let k = self.scale() * TILE as f64;
        // the frame's edges in the view, unclipped, so that a frame half out
        // of view has no edge where the view ends
        let fx0 = (x.max(0) as f64 * k).floor() - self.sx;
        let fy0 = (y.max(0) as f64 * k).floor() - self.sy;
        let fx1 = ((x + size).min(WORLD_W as i32) as f64 * k).floor() - self.sx;
        let fy1 = ((y + size).min(WORLD_H as i32) as f64 * k).floor() - self.sy;
        if fx1 <= fx0 + 4.0 || fy1 <= fy0 + 4.0 {
            return;
        }
        let Some((x0, y0, x1, y1)) = self.view_box(x, y, x + size, y + size) else { return };
        let (fx0, fy0, fx1, fy1) = (fx0 as i64, fy0 as i64, fx1 as i64, fy1 as i64);
        for yy in y0..y1 {
            for xx in x0..x1 {
                let (xi, yi) = (xx as i64, yy as i64);
                if yi < fy0 + 2 || yi >= fy1 - 2 || xi < fx0 + 2 || xi >= fx1 - 2 {
                    let d = (yy * self.pw + xx) * 4;
                    self.px[d..d + 4].copy_from_slice(&OUTLINE);
                }
            }
        }
    }

    fn page(&mut self, w: usize, h: usize, ppmm100: f64, offset: usize) {
        self.tiles_at = None;                   // a page: the pixels are ours again
        self.buf = Buffer::map();
        self.offset = offset;
        self.pw = w;
        self.ph = h;
        self.px = vec![0; w * h * 4];
        self.waiting = false;
        let z = ppmm100 / 100.0 / PPMM_100;
        if z > 0.0 && (z - self.zoom).abs() > 1e-6 {
            self.zoom = z;
            self.tell_extent();
        }
        self.repaint();
    }

    /// a square's part of the view
    fn tile_rect(&self, tx: usize, ty: usize) -> Option<(usize, usize, usize, usize)> {
        self.view_box(tx as i32, ty as i32, tx as i32 + 1, ty as i32 + 1)
    }

    fn draw_tile(&mut self, tx: usize, ty: usize, value: u16) {
        let mut n = tile_art(value) as usize;
        if n >= (self.tiles.w / TILE) * (self.tiles.h / TILE) {
            n = 0;
        }
        let (sx0, sy0) = ((n % (self.tiles.w / TILE)) * TILE, (n / (self.tiles.w / TILE)) * TILE);
        // the square in the view, whole, and the part of it in view
        let k = self.scale() * TILE as f64;
        let fx0 = (tx as f64 * k).floor() - self.sx;
        let fy0 = (ty as f64 * k).floor() - self.sy;
        let dw = ((tx + 1) as f64 * k).floor() as i64 - (tx as f64 * k).floor() as i64;
        let dh = ((ty + 1) as f64 * k).floor() as i64 - (ty as f64 * k).floor() as i64;
        if dw <= 0 || dh <= 0 {
            return;
        }
        let Some((x0, y0, x1, y1)) = self.tile_rect(tx, ty) else { return };
        let (fx0, fy0, dw, dh) = (fx0 as i64, fy0 as i64, dw as usize, dh as usize);
        for y in y0..y1 {
            let sy = sy0 + ((y as i64 - fy0) as usize).min(dh - 1) * TILE / dh;
            let srow = sy * self.tiles.w * 4;
            let drow = y * self.pw * 4;
            for x in x0..x1 {
                let sx = sx0 + ((x as i64 - fx0) as usize).min(dw - 1) * TILE / dw;
                let s = srow + sx * 4;
                let d = drow + x * 4;
                self.px[d..d + 4].copy_from_slice(&self.tiles.px[s..s + 4]);
            }
        }
    }

    fn sprite_box(&self, s: &Sprite) -> (i64, i64, i64, i64) {
        let k = self.scale();
        let x = ((s.x + s.x_offset) as f64 * k - self.sx) as i64;
        let y = ((s.y + s.y_offset) as f64 * k - self.sy) as i64;
        (x, y, x + (s.width as f64 * k).ceil() as i64, y + (s.height as f64 * k).ceil() as i64)
    }

    fn draw_sprite(&mut self, s: &Sprite) {
        let Some((_, _, img)) =
            self.sprites.iter().find(|(t, f, _)| *t == s.kind as u32 && *f == (s.frame - 1).max(0) as u32)
        else {
            return;
        };
        let (x0, y0, x1, y1) = self.sprite_box(s);
        let (dw, dh) = ((x1 - x0).max(1) as usize, (y1 - y0).max(1) as usize);
        for dy in 0..dh {
            let y = y0 + dy as i64;
            if y < 0 || y as usize >= self.ph {
                continue;
            }
            let sy = dy * img.h / dh;
            for dx in 0..dw {
                let x = x0 + dx as i64;
                if x < 0 || x as usize >= self.pw {
                    continue;
                }
                let sx = dx * img.w / dw;
                let si = (sy * img.w + sx) * 4;
                let a = img.px[si + 3] as u32;
                if a == 0 {
                    continue;
                }
                let di = (y as usize * self.pw + x as usize) * 4;
                for c in 0..4 {
                    // premultiplied: over
                    let v = img.px[si + c] as u32 + self.px[di + c] as u32 * (255 - a) / 255;
                    self.px[di + c] = v.min(255) as u8;
                }
            }
        }
    }

    // ── the tile map, drawn by the presenter ──

    /// "tiles OFFSET": the presenter draws the map, from the block at that
    /// byte of the buffer; the pixels are no longer this program's
    fn tiles_start(&mut self, at: usize) {
        if self.buf.is_none() {
            self.buf = Buffer::map();
        }
        match self.buf.as_ref() {
            Some(b) if at + tl_size(self.tiles.w, self.tiles.h) <= b.len => {}
            _ => return,
        }
        self.tiles_at = Some(at);
        self.tiles_art = false;
        self.pub_look = (255, 255);
        self.pub_map.fill(0xffff);
        self.pub_sprites.clear();
        self.pub_foot = None;
        self.pub_ovl = None;
        self.waiting = false;
        self.sx = 0.0;                          // the pointer's places include the scroll
        self.sy = 0.0;
    }

    /// "scale PPMM100": the map's zoom, for where the pointer is
    fn set_scale(&mut self, ppmm100: f64) {
        if ppmm100 > 0.0 {
            self.zoom = ppmm100 / 100.0 / PPMM_100;
        }
    }

    /// what changed put in the block: tile numbers, the sprites, the
    /// footprint -- and the pictures, once
    fn render_tiles(&mut self, at: usize) {
        if self.waiting {
            return;                             // the broker is yet to copy the last
        }
        let Some(b) = self.buf.as_ref() else { return };
        let base = unsafe { b.base.add(at) };
        let put16 = |off: usize, v: u16| unsafe { (base.add(off) as *mut u16).write_unaligned(v) };
        let put32 = |off: usize, v: u32| unsafe { (base.add(off) as *mut u32).write_unaligned(v) };
        let mut changed = false;
        let want_fine = self.quality == Q_HD && self.fine.is_some();
        if self.tiles_art && want_fine != self.art_fine {
            self.tiles_art = false;             // the other tiles: the pictures again
            self.pub_sprites.clear();           // and the sprites, at their scale
        }
        if !self.tiles_art {
            let art = if want_fine { self.fine.as_ref().unwrap() } else { &self.tiles };
            let (aw, ah) = (art.w, art.h);
            let tile = if want_fine { 64 } else { TILE };
            if at + tl_size(aw, ah) > b.len {
                return;
            }
            self.art_gen += 1;
            self.art_fine = want_fine;
            self.pub_map.fill(0xffff);          // the map again: its tiles are drawn otherwise
            put32(0, TL_MAGIC);
            put32(4, TL_VERSION);
            put32(12, self.art_gen);            // art: moved on with each new picture
            put16(16, WORLD_W as u16);
            put16(18, WORLD_H as u16);
            put16(20, tile as u16);
            put16(22, (aw / tile) as u16);
            put32(24, ((aw / tile) * (ah / tile)) as u32);
            put32(40, u32::from_le_bytes(OUTLINE));
            put32(44, 0xff707070);
            put16(TL_AT_ATLAS_W, aw as u16);
            put16(TL_AT_ATLAS_W + 2, ah as u16);
            // the tiles' picture, whole, and each texel's material
            unsafe {
                std::ptr::copy_nonoverlapping(art.px.as_ptr(), base.add(TL_AT_ATLAS), aw * ah * 4);
                if want_fine {
                    // the fine tiles are drawn as they are made, but for
                    // their water, which moves; the rich drawing adds the
                    // shadows neighbours cast, and the night
                    mp_fine_materials(
                        base.add(TL_AT_ATLAS) as *const u32,
                        aw as c_int,
                        ah as c_int,
                        tile as c_int,
                        base.add(TL_AT_ATLAS + aw * ah * 4),
                    );
                } else {
                    mp_tile_materials(
                        base.add(TL_AT_ATLAS) as *const u32,
                        aw as c_int,
                        ah as c_int,
                        base.add(TL_AT_ATLAS + aw * ah * 4),
                    );
                }
                std::ptr::copy_nonoverlapping(mp_tile_classes() as *const u8, base.add(TL_AT_CLS), TL_CLASSES * 4);
            }
            // the sprites', a 48-pixel cell each
            let per_row = TL_SPR_W / SPR_CELL;
            for (i, (_, _, img)) in self.sprites.iter().enumerate() {
                let (cx, cy) = ((i % per_row) * SPR_CELL, (i / per_row) * SPR_CELL);
                if cy + SPR_CELL > TL_SPR_H {
                    break;
                }
                for y in 0..img.h.min(SPR_CELL) {
                    let s = &img.px[y * img.w * 4..(y * img.w + img.w.min(SPR_CELL)) * 4];
                    unsafe {
                        std::ptr::copy_nonoverlapping(
                            s.as_ptr(),
                            base.add(TL_AT_SPR + ((cy + y) * TL_SPR_W + cx) * 4),
                            s.len(),
                        );
                    }
                }
            }
            self.tiles_art = true;
            changed = true;
        }
        // the tile numbers: two bytes each, row by row
        let map = unsafe { std::slice::from_raw_parts(mp_map(self.city), WORLD_W * WORLD_H) };
        for y in 0..WORLD_H {
            for x in 0..WORLD_W {
                let v = if self.art_fine { fine_tile(map, x, y) } else { tile_art(map[x * WORLD_H + y]) };
                let i = y * TL_MAP + x;
                if self.pub_map[i] != v {
                    self.pub_map[i] = v;
                    put16(TL_AT_MAP + i * 2, v);
                    changed = true;
                }
            }
        }
        // the sprites, as places in the map and cells of their picture
        let mut sprites = vec![Sprite::default(); MAX_SPRITES];
        let n = unsafe { mp_sprites(self.city, sprites.as_mut_ptr(), MAX_SPRITES as c_int) } as usize;
        sprites.truncate(n);
        if sprites != self.pub_sprites {
            let per_row = TL_SPR_W / SPR_CELL;
            let mut k = 0;
            for s in &sprites {
                let frame = (s.frame - 1).max(0) as u32;
                let Some(i) = self.sprites.iter().position(|(t, f, _)| *t == s.kind as u32 && *f == frame) else {
                    continue;
                };
                let img = &self.sprites[i].2;
                let o = TL_AT_SPRITE + k * 16;
                // in the map's pixels, a tile `tile` of them
                let sc = if self.art_fine { 4 } else { 1 };
                put16(o, ((s.x + s.x_offset) * sc) as i16 as u16);
                put16(o + 2, ((s.y + s.y_offset) * sc) as i16 as u16);
                put16(o + 4, (s.width * sc) as u16);
                put16(o + 6, (s.height * sc) as u16);
                put16(o + 8, ((i % per_row) * SPR_CELL) as u16);
                put16(o + 10, ((i / per_row) * SPR_CELL) as u16);
                put16(o + 12, img.w.min(SPR_CELL) as u16);
                put16(o + 14, img.h.min(SPR_CELL) as u16);
                k += 1;
                if k == TL_SPRITES {
                    break;
                }
            }
            put32(28, k as u32);
            self.pub_sprites = sprites;
            changed = true;
        }
        // how the presenter draws it: the quality, and day or night
        let look = (self.quality.min(Q_RICH), if self.night { 0 } else { 255 });
        if look != self.pub_look {
            unsafe {
                *base.add(TL_AT_QUALITY) = look.0;
                *base.add(TL_AT_DAYLIGHT) = look.1;
                *base.add(TL_AT_RATE) = 20;
            }
            self.pub_look = look;
            changed = true;
        }
        // the overlay: its colours a square at a time, when they change
        let fresh_ovl = self.overlay_colours();
        let show_ovl = self.ui.overlay > 0 && self.ui.overlay_on_city;
        if show_ovl && (fresh_ovl || self.pub_ovl != Some(true)) {
            for y in 0..WORLD_H {
                for x in 0..WORLD_W {
                    put32(TL_AT_OVL + (y * TL_MAP + x) * 4, self.ui.ovl[y * WORLD_W + x]);
                }
            }
            changed = true;
        }
        if self.pub_ovl != Some(show_ovl) {
            unsafe { *base.add(TL_AT_OVERLAY) = show_ovl as u8 };
            self.pub_ovl = Some(show_ovl);
            changed = true;
        }
        // the tool's footprint, a frame round the squares it would cover
        let foot = self.footprint();
        if self.pub_foot != Some(foot) {
            let (x0, y0, x1, y1) = match foot {
                Some((x, y, size)) => (x, y, x + size, y + size),
                None => (0, 0, 0, 0),
            };
            put16(32, x0 as i16 as u16);
            put16(34, y0 as i16 as u16);
            put16(36, x1 as i16 as u16);
            put16(38, y1 as i16 as u16);
            self.pub_foot = Some(foot);
            changed = true;
        }
        if changed {
            self.tiles_owed = true;
        }
    }

    /// the tiles that changed, and those under the sprites that moved, drawn
    /// again; the box round them owed to the page
    fn render(&mut self) {
        if let Some(at) = self.tiles_at {
            self.render_tiles(at);
            return;
        }
        if self.pw == 0 || self.px.is_empty() {
            return;
        }
        let map = unsafe { std::slice::from_raw_parts(mp_map(self.city), WORLD_W * WORLD_H) };
        let mut sprites = vec![Sprite::default(); MAX_SPRITES];
        let n = unsafe { mp_sprites(self.city, sprites.as_mut_ptr(), MAX_SPRITES as c_int) } as usize;
        sprites.truncate(n);

        let (vx0, vy0, vx1, vy1) = self.in_view();
        let mut dirty = vec![false; WORLD_W * WORLD_H];
        for x in vx0..vx1 {
            for y in vy0..vy1 {
                // the map is column by column: map[x][y]
                let v = map[x * WORLD_H + y];
                if self.shown[y * WORLD_W + x] != v {
                    dirty[y * WORLD_W + x] = true;
                }
            }
        }
        // under every sprite, where it was and where it is, if it moved
        let k = self.scale() * TILE as f64;
        let moved: Vec<Sprite> = if sprites != self.shown_sprites {
            self.shown_sprites.iter().chain(sprites.iter()).copied().collect()
        } else {
            Vec::new()
        };
        for s in &moved {
            let (x0, y0, x1, y1) = self.sprite_box(s);
            let tx = |v: i64| (((v as f64 + self.sx) / k).max(0.0) as usize).min(WORLD_W - 1);
            let ty = |v: i64| (((v as f64 + self.sy) / k).max(0.0) as usize).min(WORLD_H - 1);
            for ty in ty(y0)..=ty(y1) {
                for tx in tx(x0)..=tx(x1) {
                    dirty[ty * WORLD_W + tx] = true;
                }
            }
        }
        // the squares under the footprint, where it was and where it is now
        let foot = self.footprint();
        if foot != self.shown_hover {
            for (x, y, size) in [self.shown_hover, foot].into_iter().flatten() {
                for ty in y.max(0)..(y + size).min(WORLD_H as i32) {
                    for tx in x.max(0)..(x + size).min(WORLD_W as i32) {
                        dirty[ty as usize * WORLD_W + tx as usize] = true;
                    }
                }
            }
            self.shown_hover = foot;
        }
        let mut bbox: Option<(usize, usize, usize, usize)> = None;
        for ty in vy0..vy1 {
            for tx in vx0..vx1 {
                if !dirty[ty * WORLD_W + tx] {
                    continue;
                }
                let v = map[tx * WORLD_H + ty];
                self.draw_tile(tx, ty, v);
                self.shown[ty * WORLD_W + tx] = v;
                let Some((x0, y0, x1, y1)) = self.tile_rect(tx, ty) else { continue };
                bbox = Some(match bbox {
                    None => (x0, y0, x1, y1),
                    Some((a, b, c, d)) => (a.min(x0), b.min(y0), c.max(x1), d.max(y1)),
                });
            }
        }
        if bbox.is_none() && self.owed.is_none() {
            return;
        }
        // the sprites over the tiles just drawn (all of them: cheap, and
        // those not over a dirty tile draw what is already there)
        for s in &sprites {
            self.draw_sprite(s);
        }
        self.shown_sprites = sprites;
        // and the footprint over everything, whole, so that the buffer gets
        // all of it whichever of its squares were drawn again
        if let Some(f) = foot {
            self.draw_outline(f);
            let (x, y, size) = f;
            if let Some(r) = self.view_box(x, y, x + size, y + size) {
                bbox = bbox.map(|(a, b, cc, d)| (a.min(r.0), b.min(r.1), cc.max(r.2), d.max(r.3)));
            }
        }
        if let Some((x0, y0, x1, y1)) = bbox {
            self.owed = Some(match self.owed {
                None => (x0, y0, x1, y1),
                Some((a, b, c, d)) => (a.min(x0), b.min(y0), c.max(x1), d.max(y1)),
            });
        }
    }

    fn flush(&mut self) {
        if self.waiting {
            return;
        }
        if self.tiles_at.is_some() {
            if self.tiles_owed {
                self.tiles_owed = false;
                self.say("tiles".into());
                self.waiting = true;
            }
            return;
        }
        if let (Some(b), Some((x0, y0, x1, y1))) = (self.buf.as_ref(), self.owed) {
            if y1 > y0 && x1 > x0 {
                b.rect(&self.px, self.pw, self.offset, (x0, y0, x1, y1));
                self.owed = None;
                self.say(format!("damage {x0} {y0} {x1} {y1}"));
                self.waiting = true;
            }
        }
    }
}

/// the fine tiles, Tiles64 beside the engine (a PNG: 16 tiles a row, 64
/// pixels a tile, as the classic ones are laid out), if they are there
fn fine_tiles() -> Option<Image> {
    let dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    for name in ["Tiles64,b60", "Tiles64.png", "Tiles64"] {
        if let Ok(bytes) = std::fs::read(dir.join(name)) {
            if let Some(img) = decode(&bytes) {
                if img.w == 16 * 64 && img.h % 64 == 0 && img.h <= 4096 {
                    return Some(img);
                }
            }
        }
    }
    None
}

fn main() {
    let sock = unsafe { UnixStream::from_raw_fd(3) };
    let out = sock.try_clone().expect("the socket");
    let tiles = decode(assets::TILES).expect("tiles.png");
    let ui = game::Ui::new(&tiles);
    let sprites = assets::SPRITES.iter().filter_map(|(t, f, b)| decode(b).map(|i| (*t, *f, i))).collect();
    let messages = assets::MESSAGES.lines().map(|l| l.trim().to_string()).collect();
    let workdir = std::env::temp_dir().join(format!("micropolis-{}", std::process::id()));
    let mut e = Engine {
        out,
        city: unsafe { mp_new() },
        tiles,
        sprites,
        messages,
        buf: None,
        offset: 0,
        pw: 0,
        ph: 0,
        px: Vec::new(),
        zoom: 1.0,
        sx: 0.0,
        sy: 0.0,
        told_extent: (0, 0),
        waiting: false,
        owed: None,
        shown: vec![0xffff; WORLD_W * WORLD_H],
        shown_sprites: Vec::new(),
        speed: 2,
        tool: 0, // the palette's first, as the shell shows it chosen
        last_tile: None,
        hover: None,
        shown_hover: None,
        path: None,
        modified: false,
        news: String::new(),
        told_props: String::new(),
        told_inspect: String::new(),
        workdir,
        follow: true,
        tiles_at: None,
        tiles_art: false,
        quality: 2,
        fine: fine_tiles(),
        art_gen: 0,
        art_fine: false,
        told_ticks: Vec::new(),
        night: false,
        pub_look: (255, 255),
        tiles_owed: false,
        pub_map: vec![0xffff; TL_MAP * TL_MAP],
        pub_sprites: Vec::new(),
        pub_foot: None,
        pub_ovl: None,
        ui,
    };
    e.say("hello micropolis 0.1 micropolis-engine".into());

    let fd = 3;
    let mut input: Vec<u8> = Vec::new();
    let start = Instant::now();
    let mut next_tick = start;
    let mut next_anim = start;
    let mut next_panes = start;
    let anim_every = Duration::from_millis(100);
    'run: loop {
        // wait for a line, or the clock
        let now = Instant::now();
        let mut due = next_anim.min(next_panes);
        if e.speed > 0 {
            due = due.min(next_tick);
        }
        let wait = due.saturating_duration_since(now).as_millis().min(1000) as c_int;
        let mut pfd = libc::pollfd { fd, events: libc::POLLIN, revents: 0 };
        let ready = unsafe { libc::poll(&mut pfd, 1, wait) };
        if ready > 0 {
            let mut chunk = [0u8; 4096];
            let n = unsafe { libc::read(fd, chunk.as_mut_ptr() as *mut c_void, chunk.len()) };
            if n <= 0 {
                break;
            }
            input.extend_from_slice(&chunk[..n as usize]);
            while let Some(nl) = input.iter().position(|&c| c == b'\n') {
                let raw: Vec<u8> = input.drain(..=nl).collect();
                // what the user typed comes in RISC OS Latin-1
                let line: String = raw[..raw.len() - 1].iter().map(|&c| c as char).collect();
                let line = line.trim_end_matches('\r');
                let (cmd, rest) = line.split_once(' ').unwrap_or((line, ""));
                let nums: Vec<f64> = rest.split_whitespace().filter_map(|t| t.parse().ok()).collect();
                let at = |i: usize| nums.get(i).copied().unwrap_or(0.0);
                match cmd {
                    "new" => e.new_city(0),
                    "open" => e.open(rest.trim()),
                    "save" => e.save(rest.trim()),
                    "page" if nums.len() == 4 => e.page(nums[0] as usize, nums[1] as usize, nums[2], nums[3] as usize),
                    "view" if nums.len() >= 2 => e.set_view(at(0).max(0.0), at(1).max(0.0)),
                    "tiles" if !nums.is_empty() => e.tiles_start(at(0) as usize),
                    "scale" if !nums.is_empty() => e.set_scale(at(0)),
                    "press" => e.press(at(0), at(1)),
                    "drag" => e.drag(at(0), at(1)),
                    "release" => e.last_tile = None,
                    "pointer" => e.hover = if at(0) < 0.0 { None } else { Some(e.tile_at(at(0), at(1))) },
                    "tool" => e.set_tool(rest.trim()),
                    "menu" if nums.len() == 2 => e.menu(nums[0] as i64, nums[1] as i64),
                    "prop" => e.prop(rest),
                    "pick" => {
                        let mut w = rest.split_whitespace();
                        let name = w.next().unwrap_or("").to_string();
                        let fx = w.next().and_then(|v| v.parse().ok()).unwrap_or(0.0);
                        let fy = w.next().and_then(|v| v.parse().ok()).unwrap_or(0.0);
                        e.pick(&name, fx, fy);
                    }
                    "hover" => e.hover_tool(rest.trim()),
                    // where the pane's pictures are written, and their names' start
                    "scrap" => {
                        let (p, n) = rest.trim().split_once(' ').unwrap_or((rest.trim(), "t"));
                        e.ui.thumb_path = p.to_string();
                        e.ui.thumb_prefix = n.to_string();
                        e.told_props.clear();
                        e.panes();
                    }
                    "key" if !nums.is_empty() => e.key(at(0) as u32),
                    "shown" => e.waiting = false,
                    "quit" => break 'run,
                    _ => {}
                }
            }
        }
        let now = Instant::now();
        if e.speed > 0 && now >= next_tick {
            unsafe { mp_tick(e.city) };
            let every = Duration::from_millis(1000 / TICKS_PER_SECOND[e.speed] as u64);
            next_tick = if now.duration_since(next_tick) > every * 4 { now + every } else { next_tick + every };
        }
        if now >= next_anim {
            if e.speed > 0 {
                unsafe { mp_animate(e.city) };
            }
            next_anim = now + anim_every;
        }
        e.events();
        if now >= next_panes {
            e.panes();
            next_panes = now + Duration::from_millis(500);
        }
        e.render();
        e.flush();
    }
    let _ = std::fs::remove_dir_all(&e.workdir);
}
