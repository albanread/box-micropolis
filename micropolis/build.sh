#!/bin/sh
# build.sh -- the Micropolis engine and its headless test driver
#
#   ports/micropolis/build.sh [TARGET...]
#
#   host                   this Mac (clang++), the default; tests/run.sh uses it
#   x86_64-linux-musl      the Intel box
#   aarch64-linux-musl     the Arm box
#   arm-linux-musleabihf   RISC OS 5, 32-bit ARM, strict alignment (design 48)
#
# The cross builds use zig 0.15 (ZIG, default ~/zig015/zig).  Output goes
# to rosgd/.cache/micropolis/TARGET/headless in the BOX's tree, else to
# build/TARGET/headless beside this script.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
rosgd=$(cd "$here/../.." && pwd)
if [ -d "$rosgd/.cache" ]; then outs=$rosgd/.cache/micropolis; else outs=$here/build; fi
ZIG=${ZIG:-$HOME/zig015/zig}
[ $# -gt 0 ] || set -- host
for target do
    out=$outs/$target
    mkdir -p "$out"
    case $target in
        host) cxx="clang++" ;;
        x86_64-linux-musl|aarch64-linux-musl) cxx="$ZIG c++ -target $target" ;;
        arm-linux-musleabihf) cxx="$ZIG c++ -target $target -mcpu=cortex_a72+strict_align -marm" ;;
        *) echo "build.sh: no target $target" >&2; exit 2 ;;
    esac
    # upstream's own warnings (unused variables and the like) are left as
    # they are; anything else is ours to see
    $cxx -std=c++17 -O2 -Wall -Wno-unused-parameter -Wno-unused-variable -Wno-unused-but-set-variable \
        -Wno-unused-function -I"$here/engine" "$here"/engine/*.cpp "$here/tools/headless.cpp" -o "$out/headless"
    echo "== micropolis: $out/headless ($(wc -c < "$out/headless" | tr -d ' ') bytes)"
done
