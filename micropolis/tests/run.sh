#!/bin/sh
# run.sh -- the engine's regression test, on this Mac
#
#   ports/micropolis/tests/run.sh [--update]
#
# Every city in content/cities is run for 20000 ticks with the random
# generator seeded 7, and the census each simulated year must be what
# tests/expected holds, to the byte; then each city is saved, loaded back
# and its fields checked.  --update writes tests/expected afresh, after a
# change meant to alter the simulation.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
port=$(cd "$here/.." && pwd)
rosgd=$(cd "$port/../.." && pwd)
sh "$port/build.sh" host > /dev/null
if [ -d "$rosgd/.cache" ]; then run=$rosgd/.cache/micropolis/host/headless; else run=$port/build/host/headless; fi
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
bad=0 n=0
for city in "$port"/content/cities/*.cty; do
    name=$(basename "$city" .cty)
    n=$((n + 1))
    "$run" "$city" 20000 7 > "$scratch/$name.txt"
    if [ "${1:-}" = --update ]; then
        cp "$scratch/$name.txt" "$here/expected/$name.txt"
    elif ! cmp -s "$scratch/$name.txt" "$here/expected/$name.txt"; then
        echo "run.sh: $name: the simulation differs"
        diff "$here/expected/$name.txt" "$scratch/$name.txt" | head -4
        bad=$((bad + 1))
    fi
    "$run" --roundtrip "$city" "$scratch/$name.cty" > "$scratch/rt.txt" || {
        cat "$scratch/rt.txt"
        bad=$((bad + 1))
    }
done
echo "run.sh: $n cities, $bad failed"
[ "$bad" -eq 0 ]
