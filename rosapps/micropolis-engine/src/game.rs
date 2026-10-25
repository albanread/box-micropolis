// SPDX-License-Identifier: GPL-3.0-or-later
//
// game -- what the player sees of the city besides the map: the properties
// pane's pages (City, Budget, Evaluation, Graphs, Map), what a chosen tool
// costs and needs, the square chosen with the query tool, the news, the
// budget the year asks for, the scenario's goal, the history graphs, the
// small map and its overlays, and the sounds.  Part of the BOX's port of
// Micropolis, under its licence (see main.rs).

use super::*;
use std::path::PathBuf;

// ── what the engine tells us besides the map ─────────────────────────────

#[repr(C)]
#[derive(Default, Clone)]
pub struct Eval {
    pub yes: c_int,
    pub problem: [c_int; 4],
    pub votes: [c_int; 4],
    pub pop: c_int,
    pub pop_delta: c_int,
    pub assessed: c_int,
    pub city_class: c_int,
    pub score: c_int,
    pub score_delta: c_int,
    pub crime_average: c_int,
    pub pollution_average: c_int,
    pub traffic_average: c_int,
    pub land_value_average: c_int,
}

#[repr(C)]
#[derive(Default, Clone)]
pub struct Budget {
    pub tax_fund: c_int,
    pub road_fund: c_int,
    pub fire_fund: c_int,
    pub police_fund: c_int,
    pub road_spend: c_int,
    pub fire_spend: c_int,
    pub police_spend: c_int,
    pub cash_flow: c_int,
    pub funds: c_int,
}

#[repr(C)]
#[derive(Default, Clone)]
pub struct ScenarioClock {
    pub scenario: c_int,
    pub score_wait: c_int,
    pub disaster_wait: c_int,
    pub city_time: c_int,
}

extern "C" {
    fn mp_eval(c: *mut c_void, e: *mut Eval);
    fn mp_budget(c: *mut c_void, b: *mut Budget);
    fn mp_scenario_clock(c: *mut c_void, s: *mut ScenarioClock);
    fn mp_history(c: *mut c_void, kind: c_int, scale: c_int, out: *mut i16);
    fn mp_overlay(c: *mut c_void, kind: c_int, out: *mut i16);
    fn mp_set_auto_bulldoze(c: *mut c_void, on: c_int);
    fn mp_auto_bulldoze(c: *mut c_void) -> c_int;
}

pub const EV_SOUND: c_int = 8;

// ── the pages ─────────────────────────────────────────────────────────────

pub const PAGES: [&str; 6] = ["City", "Budget", "Evaluation", "Graphs", "Map", "Options"];
const P_CITY: usize = 0;
const P_BUDGET: usize = 1;
const P_EVAL: usize = 2;
const P_GRAPHS: usize = 3;
const P_MAP: usize = 4;
const P_OPTIONS: usize = 5;

pub const OVERLAYS: [&str; 10] = [
    "None", "Population", "Growth", "Land value", "Crime", "Pollution", "Traffic", "Power", "Fire cover", "Police cover",
];
const SERIES: [(&str, [u8; 3]); 6] = [
    ("Residential", [40, 170, 60]),
    ("Commercial", [60, 110, 230]),
    ("Industrial", [220, 170, 30]),
    ("Money", [30, 150, 150]),
    ("Crime", [210, 50, 50]),
    ("Pollution", [140, 100, 60]),
];
const PROBLEMS: [&str; 7] = ["Crime", "Pollution", "Housing costs", "Taxes", "Traffic", "Unemployment", "Fires"];

/// a tool as the pane describes it, in rows short enough for its values:
/// its name, what it costs (and whether for each square), its size, what
/// it needs, what it does for the city and what it costs it
struct ToolInfo {
    title: &'static str,
    cost: i64,
    per_square: bool,
    size: i32,
    needs: &'static str,
    gives: &'static str,
    but: &'static str,
    sound: &'static str,
}

const fn t(
    title: &'static str, cost: i64, per_square: bool, size: i32, needs: &'static str, gives: &'static str,
    but: &'static str, sound: &'static str,
) -> ToolInfo {
    ToolInfo { title, cost, per_square, size, needs, gives, but, sound }
}

const TOOL_INFO: [ToolInfo; 17] = [
    t("Query", 0, false, 1, "", "What a square is", "", "query"),
    t("Move the map", 0, false, 0, "", "Drag to look round", "", ""),
    t("Bulldozer", 1, true, 1, "", "Clears the ground", "", "bulldozer"),
    t("Road", 10, true, 1, "", "Zones need a road", "Road upkeep", "road"),
    t("Rail", 20, true, 1, "", "Less traffic", "Rail upkeep", "rail"),
    t("Power line", 5, true, 1, "", "Carries power", "", "wire"),
    t("Park", 10, true, 1, "", "Land value", "", "park"),
    t("Residential zone", 100, false, 3, "Power, a road", "Homes", "", "res"),
    t("Commercial zone", 100, false, 3, "Power, a road", "Shops, jobs", "", "com"),
    t("Industrial zone", 100, false, 3, "Power, a road", "Factories, jobs", "Pollution", "ind"),
    t("Police station", 500, false, 3, "Power", "Less crime", "Police fund", "police"),
    t("Fire station", 500, false, 3, "Power", "Fewer fires", "Fire fund", "fire"),
    t("Stadium", 5000, false, 4, "Power, a road", "Happier people", "", "stadium"),
    t("Seaport", 3000, false, 4, "The coast", "Industry grows", "", "seaport"),
    t("Coal power", 3000, false, 4, "Power lines out", "700 squares' power", "Pollution", "coal"),
    t("Nuclear power", 5000, false, 4, "Power lines out", "2000 squares' power", "Meltdown risk", "nuclear"),
    t("Airport", 10000, false, 6, "Power, a road", "Commerce grows", "Crash risk", "airport"),
];

/// the square chosen with the query tool, as the engine described it
#[derive(Clone, Default)]
pub struct Selected {
    pub x: i32,
    pub y: i32,
    pub what: String,
    pub rows: Vec<(String, String)>,
}

pub struct Ui {
    pub page: usize,
    pub sel: Option<Selected>,
    pub news: Vec<(String, Option<(i32, i32)>)>,
    pub budget_wait: Option<usize>, // paused for the year's budget: the speed to go back to
    pub graph_on: [bool; 6],
    pub graph_long: bool,
    pub overlay: usize,
    pub overlay_on_city: bool,
    pub hover_tool: Option<usize>,
    pub thumb_path: String,
    pub thumb_prefix: String,
    pub told_pics: String,
    pub pics_due: Instant,
    pub tile_avg: Vec<[u8; 3]>,
    pub ovl: Vec<u32>,              // the overlay's colours, a word a square, row by row
    pub ovl_due: Instant,
    pub sounds: Option<PathBuf>,
    pub last_sound: Instant,
    pub classes: Vec<u32>,
}

impl Ui {
    pub fn new(tiles: &Image) -> Ui {
        // each tile's colour, for the small map
        let cols = tiles.w / TILE;
        let n = cols * (tiles.h / TILE);
        let mut tile_avg = vec![[0u8; 3]; n];
        for (t, avg) in tile_avg.iter_mut().enumerate() {
            let (x0, y0) = ((t % cols) * TILE, (t / cols) * TILE);
            let mut sum = [0u32; 3];
            for y in y0..y0 + TILE {
                for x in x0..x0 + TILE {
                    let p = (y * tiles.w + x) * 4;
                    for c in 0..3 {
                        sum[c] += tiles.px[p + c] as u32;
                    }
                }
            }
            for c in 0..3 {
                avg[c] = (sum[c] / (TILE * TILE) as u32) as u8;
            }
        }
        let sounds = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.join("Sounds")))
            .filter(|d| d.is_dir());
        let classes = unsafe { std::slice::from_raw_parts(mp_tile_classes(), 1024) }.to_vec();
        Ui {
            page: P_CITY,
            sel: None,
            news: Vec::new(),
            budget_wait: None,
            graph_on: [true, true, true, false, false, false],
            graph_long: false,
            overlay: 0,
            overlay_on_city: true,
            hover_tool: None,
            thumb_path: String::new(),
            thumb_prefix: String::new(),
            told_pics: String::new(),
            pics_due: Instant::now(),
            tile_avg,
            ovl: vec![0; WORLD_W * WORLD_H],
            ovl_due: Instant::now(),
            sounds,
            last_sound: Instant::now(),
            classes,
        }
    }
}

/// thousands with commas, and a dollar sign if money
pub fn money(v: i64) -> String {
    let t = v.abs().to_string();
    let mut o = String::new();
    for (i, c) in t.chars().enumerate() {
        if i > 0 && (t.len() - i) % 3 == 0 {
            o.push(',');
        }
        o.push(c);
    }
    if v < 0 { format!("-${o}") } else { format!("${o}") }
}

fn count(v: i64) -> String {
    money(v).replacen('$', "", 1)
}

fn signed(v: i64, f: impl Fn(i64) -> String) -> String {
    if v > 0 { format!("+{}", f(v)) } else { f(v) }
}

/// REST names NAME: its value after a space, or "" if just the name
fn arg<'a>(rest: &'a str, name: &str) -> Option<&'a str> {
    if rest == name {
        Some("")
    } else {
        rest.strip_prefix(name).and_then(|r| r.strip_prefix(' ')).map(|r| r.trim())
    }
}

impl Engine {
    fn eval(&self) -> Eval {
        let mut e = Eval::default();
        unsafe { mp_eval(self.city, &mut e) };
        e
    }

    fn budget(&self) -> Budget {
        let mut b = Budget::default();
        unsafe { mp_budget(self.city, &mut b) };
        b
    }

    fn clock(&self) -> ScenarioClock {
        let mut c = ScenarioClock::default();
        unsafe { mp_scenario_clock(self.city, &mut c) };
        c
    }

    // ── the news, the selection, the budget and the sounds ──

    /// a message for the news list, and where it happened if it says
    pub fn news_add(&mut self, text: &str, at: Option<(i32, i32)>) {
        if self.ui.news.first().is_some_and(|(t, _)| t == text) {
            if at.is_some() {
                self.ui.news[0].1 = at;
            }
            return;
        }
        self.ui.news.insert(0, (text.to_string(), at));
        self.ui.news.truncate(6);
    }

    /// the engine's account of a square, chosen with the query tool
    pub fn select(&mut self, x: i32, y: i32, what: String, rows: Vec<(String, String)>) {
        let map = unsafe { std::slice::from_raw_parts(mp_map(self.city), WORLD_W * WORLD_H) };
        let mut rows = rows;
        if (0..WORLD_W as i32).contains(&x) && (0..WORLD_H as i32).contains(&y) {
            let (cx, cy, size) = self.footprint_at(x, y);
            let centre = if size > 1 { (cx + 1, cy + 1) } else { (cx, cy) };
            let v = map[centre.0.clamp(0, WORLD_W as i32 - 1) as usize * WORLD_H + centre.1.clamp(0, WORLD_H as i32 - 1) as usize];
            if v & 0x4000 != 0 {
                rows.push(("Power".into(), if v & 0x8000 != 0 { "Yes".into() } else { "No".into() }));
            }
        }
        rows.push(("Where".into(), format!("{x}, {y}")));
        self.ui.sel = Some(Selected { x, y, what, rows });
        self.ui.page = P_CITY;
    }

    /// the square X Y's building: its top left square and its size
    pub fn footprint_at(&self, x: i32, y: i32) -> (i32, i32, i32) {
        if !(0..WORLD_W as i32).contains(&x) || !(0..WORLD_H as i32).contains(&y) {
            return (x, y, 1);
        }
        let map = unsafe { std::slice::from_raw_parts(mp_map(self.city), WORLD_W * WORLD_H) };
        let n = tile_art(map[x as usize * WORLD_H + y as usize]) as usize;
        let w = self.ui.classes.get(n).copied().unwrap_or(0x100);
        let size = ((w >> 8) & 7).max(1) as i32;
        let (lx, ly) = (((w >> 16) & 15) as i32, ((w >> 20) & 15) as i32);
        if size > 1 { (x - lx, y - ly, size) } else { (x, y, 1) }
    }

    /// the year's budget is due (auto budget off): the game waits for it
    pub fn budget_due(&mut self) {
        if self.ui.budget_wait.is_none() {
            self.ui.budget_wait = Some(self.speed.max(1));
            self.set_speed(0);
        }
        self.ui.page = P_BUDGET;
        self.news_add("The budget is due: set it, then Continue.", None);
    }

    /// a sound by the engine's name ("HonkHonkMed") or ours ("road")
    pub fn sound(&mut self, name: &str) {
        let Some(dir) = self.ui.sounds.clone() else { return };
        if self.ui.last_sound.elapsed() < Duration::from_millis(120) {
            return;                             // a drag's every square would be a din
        }
        let lower = name.to_ascii_lowercase();
        let mut cands = vec![lower.clone()];
        for end in ["high", "low", "med", "hi"] {
            if let Some(stem) = lower.strip_suffix(end) {
                cands.push(format!("{stem}-{end}"));
            }
        }
        for c in cands {
            let p = dir.join(format!("{c}.wav"));
            if p.is_file() {
                self.say(format!("sound {}", p.display()));
                self.ui.last_sound = Instant::now();
                return;
            }
        }
    }

    pub fn tool_sound(&mut self, tool: usize) {
        let s = TOOL_INFO[tool].sound;
        if !s.is_empty() {
            self.sound(s);
        }
    }

    // ── the panes ──

    pub fn panes(&mut self) {
        let s = self.status();
        let mut rows: Vec<String> = PAGES
            .iter()
            .enumerate()
            .map(|(i, p)| format!("*{}{p}", if i == self.ui.page { "=" } else { "" }))
            .collect();
        match self.ui.page {
            P_BUDGET => self.budget_rows(&s, &mut rows),
            P_EVAL => self.eval_rows(&s, &mut rows),
            P_GRAPHS => self.graph_rows(&mut rows),
            P_MAP => self.map_rows(&mut rows),
            P_OPTIONS => self.option_rows(&s, &mut rows),
            _ => self.city_rows(&s, &mut rows),
        }
        let line = rows.join("|");
        if line != self.told_props {
            self.told_props = line.clone();
            // a long pane in parts: "propsmore" then "props"
            let mut parts: Vec<String> = Vec::new();
            let mut cur = String::new();
            for r in &rows {
                if !cur.is_empty() && cur.len() + r.len() > 900 {
                    parts.push(std::mem::take(&mut cur));
                }
                if !cur.is_empty() {
                    cur.push('|');
                }
                cur.push_str(r);
            }
            for p in &parts {
                self.say_text("propsmore", p);
            }
            self.say_text("props", &cur);
        }
        // the status bar: the date and the funds on the left, the
        // population and the city's news across the rest; a palette tool
        // under the pointer says what it is there
        let news = match self.ui.hover_tool {
            Some(t) => {
                let i = &TOOL_INFO[t];
                let cost = if i.cost == 0 { String::new() } else if i.per_square { format!(", {} a square", money(i.cost)) } else { format!(", {}", money(i.cost)) };
                let what = [i.gives, i.but].iter().filter(|x| !x.is_empty()).copied().collect::<Vec<_>>().join("; ");
                format!("{}{cost}: {what}", i.title)
            }
            None => self.news.clone(),
        };
        let inspect = format!(
            "{} {}|{}|Population {}   score {}|{}",
            MONTHS.get(s.month as usize).copied().unwrap_or(""),
            s.year,
            money(s.funds as i64),
            count(s.pop as i64),
            s.score,
            news
        );
        if inspect != self.told_inspect {
            self.told_inspect = inspect.clone();
            self.say_text("inspect", &inspect);
        }
        // the View menu's ticks: the drawing chosen, HD greyed without its
        // tiles, and Night
        let ticks: Vec<u8> = (0..4u8)
            .map(|q| if q == self.quality { 1 } else if q == Q_HD && self.fine.is_none() { 2 } else { 0 })
            .chain(std::iter::once(self.night as u8))
            .collect();
        if ticks != self.told_ticks {
            for (i, t) in ticks.iter().enumerate() {
                self.say(format!("tick 2 {i} {t}"));
            }
            self.told_ticks = ticks;
        }
        self.pictures();
    }

    fn pic(&self, name: &str, w: u32, h: u32) -> Option<String> {
        if self.ui.thumb_path.is_empty() {
            None
        } else {
            Some(format!("^{}{name}@{w}x{h}", self.ui.thumb_prefix))
        }
    }

    fn city_rows(&self, s: &Status, rows: &mut Vec<String>) {
        let tool = self.tool;
        // the tool chosen: what it is, costs and needs
        if tool >= 2 {
            let i = &TOOL_INFO[tool];
            rows.push(format!("#{}", i.title));
            rows.push(format!("Cost:{}{}", money(i.cost), if i.per_square { " a square" } else { "" }));
            if i.size > 1 {
                rows.push(format!("Size:{} by {} squares", i.size, i.size));
            }
            if !i.needs.is_empty() {
                rows.push(format!("Needs:{}", i.needs));
            }
            rows.push(format!("Gives:{}", i.gives));
            if !i.but.is_empty() {
                rows.push(format!("But:{}", i.but));
            }
        } else if tool == 0 {
            // the square chosen with the query tool
            match &self.ui.sel {
                Some(sel) => {
                    rows.push(format!("#{}", sel.what));
                    for (k, v) in &sel.rows {
                        rows.push(format!("{k}:{v}"));
                    }
                    rows.push("*Bulldoze it".into());
                    rows.push("*Go there".into());
                }
                None => {
                    rows.push("#Query".into());
                    rows.push("Note:Click a square".into());
                }
            }
        }
        rows.push("#City".into());
        rows.push(format!("City name={}", self.city_name().replace('|', " ")));
        rows.push(format!("Population:{}", count(s.pop as i64)));
        rows.push(format!("Funds:{}", money(s.funds as i64)));
        rows.push(format!("Score:{}", s.score));
        rows.push(format!("Class:{}", CLASSES.get(s.city_class as usize).copied().unwrap_or("")));
        rows.push("#Demand".into());
        match self.pic("demand", 210, 60) {
            Some(p) => rows.push(p),
            None => {
                let demand = |d: f32| if d > 0.5 { "Strong" } else if d > 0.1 { "Some" } else if d < -0.5 { "Falling" } else if d < -0.1 { "Weak" } else { "Steady" };
                rows.push(format!("Residential:{}", demand(s.res_demand)));
                rows.push(format!("Commercial:{}", demand(s.com_demand)));
                rows.push(format!("Industrial:{}", demand(s.ind_demand)));
            }
        }
        rows.push(format!("Speed?{}?{}", SPEEDS[self.speed], SPEEDS.join(",")));
        if !self.ui.news.is_empty() {
            rows.push("#News".into());
            for (i, (t, _)) in self.ui.news.iter().enumerate() {
                rows.push(format!("*{}. {}", i + 1, short(t, 34)));
            }
        }
    }

    fn option_rows(&self, s: &Status, rows: &mut Vec<String>) {
        rows.push("#Game".into());
        rows.push(format!("Speed?{}?{}", SPEEDS[self.speed], SPEEDS.join(",")));
        rows.push(format!("Level?{}?{}", LEVELS.get(s.level as usize).copied().unwrap_or("Easy"), LEVELS.join(",")));
        rows.push(format!("Disasters!{}", if s.disasters != 0 { "on" } else { "off" }));
        rows.push(format!("Go to events!{}", if self.follow { "on" } else { "off" }));
        rows.push(format!("Auto bulldoze!{}", if unsafe { mp_auto_bulldoze(self.city) } != 0 { "on" } else { "off" }));
        rows.push("#View".into());
        rows.push(format!(
            "Graphics?{}?{}",
            QUALITIES[self.quality as usize],
            QUALITIES[..if self.fine.is_some() { 4 } else { 3 }].join(",")
        ));
        rows.push(format!("Night!{}", if self.night { "on" } else { "off" }));
    }

    fn budget_rows(&self, s: &Status, rows: &mut Vec<String>) {
        let b = self.budget();
        let pct = |v: f32| format!("{}%", (v * 100.0).round() as i32);
        let fund_menu = "0%,10%,20%,30%,40%,50%,60%,70%,80%,90%,100%";
        if self.ui.budget_wait.is_some() {
            rows.push("#The budget is due".into());
            rows.push("Note:Set next year's".into());
            rows.push("*Continue".into());
        }
        rows.push("#Income".into());
        rows.push(format!("Tax rate?{}%?{}", s.tax, (0..=20).map(|t| format!("{t}%")).collect::<Vec<_>>().join(",")));
        rows.push(format!("Taxes collected:{}", money(b.tax_fund as i64)));
        rows.push("#Spending".into());
        rows.push(format!("Roads?{}?{fund_menu}", pct(s.road_percent)));
        rows.push(format!("Road cost:{} of {}", money(b.road_spend as i64), money(b.road_fund as i64)));
        rows.push(format!("Fire?{}?{fund_menu}", pct(s.fire_percent)));
        rows.push(format!("Fire cost:{} of {}", money(b.fire_spend as i64), money(b.fire_fund as i64)));
        rows.push(format!("Police?{}?{fund_menu}", pct(s.police_percent)));
        rows.push(format!("Police cost:{} of {}", money(b.police_spend as i64), money(b.police_fund as i64)));
        rows.push("#Cash".into());
        rows.push(format!("Cash flow:{}", signed(b.cash_flow as i64, money)));
        rows.push(format!("Previous funds:{}", money((b.funds - b.cash_flow) as i64)));
        rows.push(format!("Current funds:{}", money(b.funds as i64)));
        rows.push(format!("Auto budget!{}", if s.auto_budget != 0 { "on" } else { "off" }));
    }

    fn eval_rows(&self, s: &Status, rows: &mut Vec<String>) {
        let e = self.eval();
        rows.push("#Public opinion".into());
        rows.push(format!("Approval:{}%", e.yes));
        rows.push("#Worst problems".into());
        let mut any = false;
        for i in 0..4 {
            if let Some(name) = usize::try_from(e.problem[i]).ok().and_then(|p| PROBLEMS.get(p)) {
                rows.push(format!("{name}:{}%", e.votes[i]));
                any = true;
            }
        }
        if !any {
            rows.push("Note:None worth mentioning".into());
        }
        rows.push("#Statistics".into());
        rows.push(format!("Population:{}", count(e.pop as i64)));
        rows.push(format!("Migration:{}", signed(e.pop_delta as i64, count)));
        rows.push(format!("Worth:{}", money(e.assessed as i64)));
        rows.push(format!("Category:{}", CLASSES.get(e.city_class as usize).copied().unwrap_or("")));
        rows.push(format!("Game level:{}", LEVELS.get(s.level as usize).copied().unwrap_or("")));
        rows.push(format!("Score:{} ({})", e.score, signed(e.score_delta as i64, |v| v.to_string())));
        // the scenario's goal, and how long is left to reach it
        let c = self.clock();
        if c.scenario > 0 {
            let (goal, now) = match c.scenario {
                1 | 2 | 3 => ("A metropolis".to_string(), CLASSES.get(s.city_class as usize).copied().unwrap_or("").to_string()),
                4 => ("Traffic below 80".to_string(), format!("traffic {}", e.traffic_average)),
                6 => ("Crime below 60".to_string(), format!("crime {}", e.crime_average)),
                _ => ("Score above 500".to_string(), format!("score {}", e.score)),
            };
            rows.push(format!("#Scenario: {}", SCENARIO_NAMES.get(c.scenario as usize - 1).copied().unwrap_or("")));
            rows.push(format!("Goal:{goal}"));
            rows.push(format!("Now:{now}"));
            if c.score_wait > 0 {
                rows.push(format!("Time left:{} y {} m", c.score_wait / 48, (c.score_wait % 48) / 4));
            } else {
                rows.push("Time left:the time is up".into());
            }
        }
    }

    fn graph_rows(&self, rows: &mut Vec<String>) {
        rows.push(format!("#The last {} years", if self.ui.graph_long { 120 } else { 10 }));
        if let Some(p) = self.pic("graph", 210, 140) {
            rows.push(p);
        }
        rows.push(format!("Range?{}?10 years,120 years", if self.ui.graph_long { "120 years" } else { "10 years" }));
        for (i, (name, _)) in SERIES.iter().enumerate() {
            rows.push(format!("{name}!{}", if self.ui.graph_on[i] { "on" } else { "off" }));
        }
    }

    fn map_rows(&self, rows: &mut Vec<String>) {
        rows.push("#The whole city".into());
        if let Some(p) = self.pic("map", 210, 175) {
            rows.push(p);
            rows.push("Note:Click to go there".into());
        }
        rows.push(format!("Overlay?{}?{}", OVERLAYS[self.ui.overlay], OVERLAYS.join(",")));
        if self.ui.overlay > 0 {
            rows.push(format!("Over the city!{}", if self.ui.overlay_on_city { "on" } else { "off" }));
            let legend = match self.ui.overlay {
                2 => "Red falls, green grows",
                7 => "Yellow on, red off",
                8 | 9 => "Bluer is better",
                _ => "Green low, red high",
            };
            rows.push(format!("Colours:{legend}"));
        }
    }

    // ── what the user did in the pane ──

    pub fn prop(&mut self, rest: &str) {
        let s = self.status();
        let percent = |v: &str| v.trim_end_matches('%').trim().parse::<f32>().ok().map(|v| v / 100.0);
        if let Some(p) = PAGES.iter().position(|p| rest == *p) {
            self.ui.page = p;
            self.ui.pics_due = Instant::now();
            self.ui.told_pics.clear();
        } else if rest == "Continue" {
            if let Some(sp) = self.ui.budget_wait.take() {
                self.set_speed(sp);
            }
            self.ui.page = P_CITY;
        } else if let Some(v) = arg(rest, "Tax rate") {
            if let Ok(t) = v.trim_end_matches('%').parse::<c_int>() {
                unsafe { mp_set_tax(self.city, t.clamp(0, 20)) };
            }
        } else if let Some(v) = arg(rest, "Roads") {
            if let Some(v) = percent(v) {
                unsafe { mp_set_funding(self.city, v, s.fire_percent, s.police_percent) }
            }
        } else if let Some(v) = arg(rest, "Fire") {
            if let Some(v) = percent(v) {
                unsafe { mp_set_funding(self.city, s.road_percent, v, s.police_percent) }
            }
        } else if let Some(v) = arg(rest, "Police") {
            if let Some(v) = percent(v) {
                unsafe { mp_set_funding(self.city, s.road_percent, s.fire_percent, v) }
            }
        } else if let Some(v) = arg(rest, "Speed") {
            if let Some(i) = SPEEDS.iter().position(|x| *x == v) {
                self.ui.budget_wait = None;
                self.set_speed(i);
            }
        } else if let Some(v) = arg(rest, "Level") {
            if let Some(i) = LEVELS.iter().position(|x| *x == v) {
                unsafe { mp_set_level(self.city, i as c_int) };
            }
        } else if arg(rest, "Disasters").is_some() {
            unsafe { mp_set_disasters(self.city, (s.disasters == 0) as c_int) };
        } else if arg(rest, "Go to events").is_some() {
            self.follow = !self.follow;
            unsafe { mp_set_auto_goto(self.city, self.follow as c_int) };
        } else if arg(rest, "Auto bulldoze").is_some() {
            let on = unsafe { mp_auto_bulldoze(self.city) } != 0;
            unsafe { mp_set_auto_bulldoze(self.city, (!on) as c_int) };
        } else if arg(rest, "Auto budget").is_some() {
            unsafe { mp_set_auto_budget(self.city, (s.auto_budget == 0) as c_int) };
        } else if let Some(v) = arg(rest, "Graphics") {
            if let Some(i) = QUALITIES.iter().position(|x| *x == v) {
                if i as u8 != Q_HD || self.fine.is_some() {
                    self.quality = i as u8;
                }
            }
        } else if arg(rest, "Night").is_some() {
            self.night = !self.night;
        } else if let Some(v) = arg(rest, "City name") {
            let v = v.trim();
            if !v.is_empty() {
                if let Ok(n) = CString::new(v) {
                    unsafe { mp_set_clean_name(self.city, n.as_ptr()) };
                }
                self.say_text("title", v);
                self.touched();
            }
        } else if rest == "Bulldoze it" {
            if let Some(sel) = self.ui.sel.clone() {
                let (x, y, size) = self.footprint_at(sel.x, sel.y);
                let at = if size > 1 { (x + 1, y + 1) } else { (x, y) };
                match unsafe { mp_tool(self.city, 7, at.0, at.1) } {
                    1 => {
                        self.touched();
                        self.sound("bulldozer");
                        self.ui.sel = None;
                    }
                    -2 => self.set_news("There is not enough money for that."),
                    _ => {}
                }
            }
        } else if rest == "Go there" {
            if let Some(sel) = self.ui.sel.clone() {
                self.go_to(sel.x, sel.y);
            }
        } else if let Some(v) = arg(rest, "Range") {
            self.ui.graph_long = v.starts_with("120");
            self.ui.told_pics.clear();
        } else if let Some(i) = SERIES.iter().position(|(n, _)| arg(rest, n).is_some()) {
            self.ui.graph_on[i] = !self.ui.graph_on[i];
            self.ui.told_pics.clear();
        } else if let Some(v) = arg(rest, "Overlay") {
            if let Some(i) = OVERLAYS.iter().position(|x| *x == v) {
                self.ui.overlay = i;
                self.ui.ovl_due = Instant::now();
                self.ui.told_pics.clear();
            }
        } else if arg(rest, "Over the city").is_some() {
            self.ui.overlay_on_city = !self.ui.overlay_on_city;
            self.ui.ovl_due = Instant::now();
        } else if let Some(k) = rest.split_once(". ").and_then(|(n, _)| n.parse::<usize>().ok()) {
            // a news item: the view goes to where it happened
            if let Some((_, Some((x, y)))) = self.ui.news.get(k.wrapping_sub(1)).cloned() {
                self.go_to(x, y);
            }
        }
        self.panes();
    }

    /// a click in one of the pane's pictures, in thousandths of it
    pub fn pick(&mut self, name: &str, fx: f64, fy: f64) {
        if name.ends_with("map") {
            let (x, y) = ((fx / 1000.0 * WORLD_W as f64) as i32, (fy / 1000.0 * WORLD_H as f64) as i32);
            self.go_to(x.clamp(0, WORLD_W as i32 - 1), y.clamp(0, WORLD_H as i32 - 1));
        }
    }

    pub fn hover_tool(&mut self, name: &str) {
        self.ui.hover_tool = TOOLS.iter().position(|t| t.0 == name);
        self.panes();
    }

    // ── the overlay ──

    /// the overlay's colour at each square, made again now and then
    pub fn overlay_colours(&mut self) -> bool {
        if self.ui.overlay == 0 || self.ui.ovl_due > Instant::now() {
            return false;
        }
        self.ui.ovl_due = Instant::now() + Duration::from_secs(1);
        let mut v = vec![0i16; WORLD_W * WORLD_H];
        unsafe { mp_overlay(self.city, self.ui.overlay as c_int, v.as_mut_ptr()) };
        let max = v.iter().map(|x| x.unsigned_abs()).max().unwrap_or(0).max(1) as f32;
        let pm = |r: f32, g: f32, b: f32, a: f32| -> u32 {
            let c = |x: f32| ((x * a * 255.0).round().clamp(0.0, 255.0)) as u32;
            c(r) | c(g) << 8 | c(b) << 16 | (((a * 255.0).round().clamp(0.0, 255.0)) as u32) << 24
        };
        let heat = |t: f32| -> (f32, f32, f32) {
            if t < 0.5 { (t * 2.0, 0.8, 0.1) } else { (1.0, 0.8 * (1.0 - (t - 0.5) * 2.0), 0.1) }
        };
        let out: Vec<u32> = v
            .iter()
            .map(|&x| {
                let t = (x as f32 / max).clamp(-1.0, 1.0);
                match self.ui.overlay {
                    2 => {
                        if t > 0.02 { pm(0.1, 0.8, 0.2, 0.55 * t.min(1.0) + 0.15) } else if t < -0.02 { pm(0.9, 0.1, 0.1, 0.55 * (-t).min(1.0) + 0.15) } else { 0 }
                    }
                    7 => match x {
                        1 => pm(1.0, 0.85, 0.1, 0.55),
                        2 => pm(0.95, 0.1, 0.1, 0.65),
                        _ => 0,
                    },
                    8 | 9 => if t > 0.02 { pm(0.1, 0.35, 1.0, 0.15 + 0.55 * t) } else { 0 },
                    _ => {
                        if t <= 0.02 {
                            0
                        } else {
                            let (r, g, b) = heat(t);
                            pm(r, g, b, 0.25 + 0.4 * t)
                        }
                    }
                }
            })
            .collect();
        let changed = out != self.ui.ovl;
        self.ui.ovl = out;
        changed
    }

    // ── the pane's pictures ──

    /// the demand bars, the graph and the small map, written as a sprite
    /// file the shell merges into the Wimp's pool when they have changed
    pub fn pictures(&mut self) {
        if self.ui.thumb_path.is_empty() || Instant::now() < self.ui.pics_due {
            return;
        }
        self.ui.pics_due = Instant::now() + Duration::from_millis(1500);
        let s = self.status();
        let mut pics: Vec<(String, u32, u32, Vec<u8>)> = Vec::new();
        let mut key = String::new();
        match self.ui.page {
            P_CITY => {
                let d = [s.res_demand, s.com_demand, s.ind_demand];
                key = format!("d{:.2}{:.2}{:.2}", d[0], d[1], d[2]);
                pics.push(("demand".into(), 210, 60, demand_bars(d)));
            }
            P_GRAPHS => {
                let mut series = Vec::new();
                for (i, (_, col)) in SERIES.iter().enumerate() {
                    if self.ui.graph_on[i] {
                        let mut h = vec![0i16; 120];
                        unsafe { mp_history(self.city, i as c_int, self.ui.graph_long as c_int, h.as_mut_ptr()) };
                        series.push((h, *col));
                    }
                }
                key = format!("g{}{:?}{}", self.ui.graph_long, self.ui.graph_on, s.month + s.year * 12);
                pics.push(("graph".into(), 210, 140, graph(&series)));
            }
            P_MAP => {
                let map = unsafe { std::slice::from_raw_parts(mp_map(self.city), WORLD_W * WORLD_H) };
                let px = small_map(map, &self.ui.tile_avg, if self.ui.overlay > 0 { Some(&self.ui.ovl) } else { None });
                key = format!("m{}", hash(&px));
                pics.push(("map".into(), 210, 175, px));
            }
            _ => {}
        }
        if pics.is_empty() || key == self.ui.told_pics {
            return;
        }
        let named: Vec<(String, u32, u32, Vec<u8>)> =
            pics.into_iter().map(|(n, w, h, px)| (format!("{}{n}", self.ui.thumb_prefix), w, h, px)).collect();
        if std::fs::write(&self.ui.thumb_path, sprite_file(&named)).is_ok() {
            self.ui.told_pics = key;
            self.say(format!("thumbs {}", named.len()));
        }
    }
}

pub const SCENARIO_NAMES: [&str; 8] =
    ["Dullsville 1900", "San Francisco 1906", "Hamburg 1944", "Bern 1965", "Tokyo 1957", "Detroit 1972", "Boston 2010", "Rio de Janeiro 2047"];

fn short(t: &str, n: usize) -> String {
    let t = t.replace('|', " ");
    if t.chars().count() <= n {
        t
    } else {
        format!("{}...", t.chars().take(n - 3).collect::<String>().trim_end())
    }
}

fn hash(px: &[u8]) -> u64 {
    let mut h: u64 = 1469598103934665603;
    for b in px.iter().step_by(7) {
        h = (h ^ *b as u64).wrapping_mul(1099511628211);
    }
    h
}

// ── drawing the pictures (R G B A, premultiplied, top row first) ─────────

fn canvas(w: u32, h: u32, rgb: [u8; 3]) -> Vec<u8> {
    let mut v = Vec::with_capacity((w * h * 4) as usize);
    for _ in 0..w * h {
        v.extend_from_slice(&[rgb[0], rgb[1], rgb[2], 255]);
    }
    v
}

fn fill(px: &mut [u8], w: u32, x0: i32, y0: i32, x1: i32, y1: i32, rgb: [u8; 3]) {
    let h = px.len() as i32 / 4 / w as i32;
    for y in y0.max(0)..y1.min(h) {
        for x in x0.max(0)..x1.min(w as i32) {
            let p = ((y as u32 * w + x as u32) * 4) as usize;
            px[p..p + 3].copy_from_slice(&rgb);
        }
    }
}

/// the residential, commercial and industrial demand: a bar each, up from
/// the middle line when it grows, down when it falls
fn demand_bars(d: [f32; 3]) -> Vec<u8> {
    let (w, h) = (210u32, 60u32);
    let mut px = canvas(w, h, [236, 236, 236]);
    let mid = h as i32 / 2;
    fill(&mut px, w, 0, mid, w as i32, mid + 1, [120, 120, 120]);
    let cols = [[40, 170, 60], [60, 110, 230], [220, 170, 30]];
    for (i, v) in d.iter().enumerate() {
        let x0 = 20 + i as i32 * 66;
        let len = (v.clamp(-1.0, 1.0) * (mid - 4) as f32) as i32;
        let (a, b) = if len >= 0 { (mid - len, mid) } else { (mid + 1, mid + 1 - len) };
        fill(&mut px, w, x0, a, x0 + 40, b.max(a + 1), cols[i]);
        // its letter beside it
        letter(&mut px, w, x0 + 44, mid - 8, b"RCI"[i], cols[i]);
    }
    px
}

/// a letter of five by seven blocks, each block two pixels: R, C or I
fn letter(px: &mut [u8], w: u32, x: i32, y: i32, ch: u8, rgb: [u8; 3]) {
    let rows: [u8; 7] = match ch {
        b'R' => [0b11110, 0b10001, 0b10001, 0b11110, 0b10100, 0b10010, 0b10001],
        b'C' => [0b01110, 0b10001, 0b10000, 0b10000, 0b10000, 0b10001, 0b01110],
        _ => [0b01110, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    };
    for (r, bits) in rows.iter().enumerate() {
        for c in 0..5 {
            if bits >> (4 - c) & 1 != 0 {
                let (bx, by) = (x + c * 2, y + r as i32 * 2);
                fill(px, w, bx, by, bx + 2, by + 2, rgb);
            }
        }
    }
}

/// the history: a line for each series, each scaled to its own largest
/// value, oldest on the left
fn graph(series: &[(Vec<i16>, [u8; 3])]) -> Vec<u8> {
    let (w, h) = (210u32, 140u32);
    let mut px = canvas(w, h, [250, 250, 250]);
    for k in 1..4 {
        let y = k * h as i32 / 4;
        fill(&mut px, w, 0, y, w as i32, y + 1, [220, 220, 220]);
    }
    for (vals, col) in series {
        let max = vals.iter().map(|v| v.unsigned_abs()).max().unwrap_or(0).max(1) as f32;
        let mut last: Option<(i32, i32)> = None;
        for i in 0..vals.len() {
            // newest first in the engine's history: the right end is now
            let v = vals[vals.len() - 1 - i] as f32 / max;
            let x = (i as f32 * (w - 1) as f32 / (vals.len() - 1).max(1) as f32) as i32;
            let y = (h as f32 - 3.0 - v.clamp(0.0, 1.0) * (h as f32 - 6.0)) as i32;
            if let Some((lx, ly)) = last {
                let steps = (x - lx).abs().max((y - ly).abs()).max(1);
                for s in 0..=steps {
                    let (px_, py) = (lx + (x - lx) * s / steps, ly + (y - ly) * s / steps);
                    fill(&mut px, w, px_, py - 1, px_ + 1, py + 1, *col);
                }
            }
            last = Some((x, y));
        }
    }
    px
}

/// the whole city small: each square its tile's colour, the overlay over it
fn small_map(map: &[u16], avg: &[[u8; 3]], ovl: Option<&Vec<u32>>) -> Vec<u8> {
    let (w, h) = (210u32, 175u32);
    let mut px = vec![0u8; (w * h * 4) as usize];
    for y in 0..h {
        for x in 0..w {
            let (tx, ty) = (x as usize * WORLD_W / w as usize, y as usize * WORLD_H / h as usize);
            let n = tile_art(map[tx * WORLD_H + ty]) as usize;
            let mut c = avg.get(n).copied().unwrap_or([0, 0, 0]);
            if let Some(o) = ovl {
                let o = o[ty * WORLD_W + tx];
                let a = (o >> 24) as u32;
                for (k, ch) in c.iter_mut().enumerate() {
                    let ov = (o >> (8 * k)) & 255;
                    *ch = (ov + *ch as u32 * (255 - a) / 255).min(255) as u8;
                }
            }
            let p = ((y * w + x) * 4) as usize;
            px[p..p + 4].copy_from_slice(&[c[0], c[1], c[2], 255]);
        }
    }
    px
}

/// pictures as a RISC OS sprite file (PRM 1, Sprites): 32 bpp at 90 dpi
fn sprite_file(sprites: &[(String, u32, u32, Vec<u8>)]) -> Vec<u8> {
    let mut f = Vec::new();
    let word = |f: &mut Vec<u8>, v: u32| f.extend_from_slice(&v.to_le_bytes());
    let total: usize = sprites.iter().map(|(_, w, h, _)| 44 + (w * h * 4) as usize).sum();
    word(&mut f, sprites.len() as u32);
    word(&mut f, 16);
    word(&mut f, (16 + total) as u32);
    for (name, w, h, px) in sprites {
        word(&mut f, 44 + w * h * 4);
        let mut n = [0u8; 12];
        for (i, c) in name.to_ascii_lowercase().bytes().take(12).enumerate() {
            n[i] = c;
        }
        f.extend_from_slice(&n);
        word(&mut f, w - 1);
        word(&mut f, h - 1);
        word(&mut f, 0);
        word(&mut f, 31);
        word(&mut f, 44);
        word(&mut f, 44);
        word(&mut f, (6 << 27) | (90 << 14) | (90 << 1) | 1);
        for p in px.chunks_exact(4).take((w * h) as usize) {
            let inv = 255 - p[3] as u32;
            let c = |v: u8| (v as u32 + inv).min(255) as u8;
            f.extend_from_slice(&[c(p[0]), c(p[1]), c(p[2]), 0]);
        }
    }
    f
}
