// build.rs -- the Micropolis engine (ports/micropolis/engine, C++) and the
// shim over it, compiled into the engine.  For the box (Linux, musl) it is
// built without exceptions or RTTI and with cxxrt.cpp in place of libc++,
// so the engine links with musl alone; elsewhere (a Mac, for tests) the
// system's C++ library is used.
use std::path::Path;

fn main() {
    let engine = Path::new("../../micropolis/engine");
    let linux = std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("linux");
    let mut b = cc::Build::new();
    b.cpp(true).std("c++17").include(engine).warnings(false).opt_level(2);
    for e in std::fs::read_dir(engine).expect("ports/micropolis/engine") {
        let p = e.unwrap().path();
        if p.extension().is_some_and(|x| x == "cpp") {
            println!("cargo:rerun-if-changed={}", p.display());
            b.file(p);
        }
    }
    b.file("src/shim.cpp");
    println!("cargo:rerun-if-changed=src/shim.cpp");
    b.file("src/materials.cpp");
    println!("cargo:rerun-if-changed=src/materials.cpp");
    if linux {
        b.flag("-fno-exceptions").flag("-fno-rtti").define("_LIBCPP_DISABLE_EXTERN_TEMPLATE", None);
        b.file("src/cxxrt.cpp");
        b.cpp_link_stdlib(None);
        println!("cargo:rerun-if-changed=src/cxxrt.cpp");
    }
    b.compile("micropolis");
    assets();
}

// The content the engine carries in itself (ports/micropolis/content): the
// tiles, the sprites (sprite_TYPE_FRAME.png), the cities (*.cty) and the
// messages (stri.301), so that it is one file in the application.
fn assets() {
    let content = std::fs::canonicalize("../../micropolis/content").expect("ports/micropolis/content");
    let mut out = String::new();
    let inc = |p: &Path| format!("include_bytes!({:?})", p.display().to_string());
    out += &format!("pub static TILES: &[u8] = {};\n", inc(&content.join("images/tiles.png")));
    out += &format!("pub static MESSAGES: &str = include_str!({:?});\n", content.join("data/stri.301.txt").display().to_string());
    // the query tool's words: what a square is (stri.219), and its density,
    // land value, crime, pollution and growth (stri.202), by line from 1
    out += &format!("pub static ZONE_NAMES: &str = include_str!({:?});\n", content.join("data/stri.219.txt").display().to_string());
    out += &format!("pub static ZONE_STATUS: &str = include_str!({:?});\n", content.join("data/stri.202.txt").display().to_string());
    let mut sprites = Vec::new();
    for e in std::fs::read_dir(content.join("images")).unwrap() {
        let p = e.unwrap().path();
        let name = p.file_stem().unwrap().to_string_lossy().to_string();
        let parts: Vec<&str> = name.split('_').collect();
        if parts.len() == 3 && parts[0] == "sprite" && p.extension().is_some_and(|x| x == "png") {
            if let (Ok(t), Ok(f)) = (parts[1].parse::<u32>(), parts[2].parse::<u32>()) {
                sprites.push((t, f, p.clone()));
            }
        }
    }
    sprites.sort();
    out += "pub static SPRITES: &[(u32, u32, &[u8])] = &[\n";
    for (t, f, p) in &sprites {
        out += &format!("    ({t}, {f}, {}),\n", inc(p));
    }
    out += "];\n";
    let mut cities: Vec<_> = std::fs::read_dir(content.join("cities")).unwrap().map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|x| x == "cty")).collect();
    cities.sort();
    out += "pub static CITIES: &[(&str, &[u8])] = &[\n";
    for p in &cities {
        out += &format!("    ({:?}, {}),\n", p.file_name().unwrap().to_string_lossy(), inc(p));
    }
    out += "];\n";
    println!("cargo:rerun-if-changed=../../micropolis/content");
    std::fs::write(Path::new(&std::env::var("OUT_DIR").unwrap()).join("assets.rs"), out).unwrap();
}
