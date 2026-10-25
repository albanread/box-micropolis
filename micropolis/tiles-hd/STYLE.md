# Micropolis HD tiles: style note

## 1. The original's visual language

These observations come from studying tiles.png at 6 to 12 times magnification.

* **Palette.** The whole set uses 14 flat colours. Seven of them do nearly all the work.
  The ground is terracotta `#cc7f66` (about a fifth of all pixels). Asphalt is `#3f3f3f`.
  Concrete comes in two greys, `#7f7f7f` and `#bfbfbf`. Water is lavender `#6666e6`
  dotted with deep blue `#0000e6`. Grass is `#00e600` and `#007f00`. The shore and
  ballast brown is `#997f4c`. Black is used for edges. Red, orange, yellow and white are
  kept for accents: fire, signals, letters and lights. There is no shading beyond
  two-tone dithering.
* **Projection.** Buildings use an oblique cabinet view. The footprint stays where it is
  on the map, and height is drawn as an offset up and to the right at 45 degrees, so
  tall chimneys come out as diagonal sticks. The viewer therefore sees the **west** and
  **south** walls. The west wall is the lighter of the two (light blue `#6666e6`, light
  grey) and the south wall the darker (`#0000e6`, dark grey).
* **Light.** The light comes from the upper left. Where the art draws drop shadows (brown
  `#997f4c` under the coal plant and the industrial tanks), they fall to the right. Roads
  have a black edge on the south and west sides. This is the kerb face seen from the
  south-west, not a shadow.
* **Outlines.** There are 1-pixel black edges on the south and west of roads and walls.
  Coloured zone frames identify the zone type: green for residential (R), lavender for
  commercial (C), yellow for industrial (I), and red or blue for fire (FD) and police
  (PD). An empty zone shows a large serif letter in the frame colour. A developed zone
  puts the letter on the roof of its main building.
* **Water and coast.** Open water is flat lavender with a scatter of dark dots. A coast
  tile shows land as a terracotta strip about 4 pixels deep, edged in brown. A corner
  tile cuts the coast diagonally across the tile. There are two random variants of each.
* **Trees.** Woods are random two-green speckle. An edge tile keeps the speckle on the
  sides that face other trees and fades to dirt with brown specks elsewhere.
* **Roads.** Roads are wide, about 11 of 16 pixels, with white centre dashes. A curve is
  a quarter disc. A junction has dotted crossings. A crossroads has a red and green
  signal in the middle. Traffic is drawn as grey and white blocks, in 4 frames each of
  light and heavy traffic.
* **Rail and power.** Rail is grey rails on brown sleepers with black shadows. Power is
  two dark wires with a pole mark and a brown diagonal stroke for the pole, drawn
  obliquely like the chimneys.

## 2. The HD style: same identity, more depth

**The rule: keep every colour identity, every layout and every glyph, and add material
and light.** Each flat colour becomes a ramp of 7 to 10 shades. The original colour sits
in the middle of the ramp, so the map still reads as the same city at a glance.
Swatches are in `palette.png`, and the code is `hdlib.PAL`.

| material | ramp (dark to light; the original colour is in **bold**) |
|---|---|
| dirt | #4a2a20 #6a3d2f #8a513e #a7634c #bc7259 **#cc7f66** #d78e74 #e2a287 #ecb99f |
| sand / shore | #6d5734 #866c42 **#997f4c** #b39a63 #cbb37d #dccb9a #ebdfba |
| water (deep) | #14146a #1c1c8c #2626ac #3636c6 #4c4cd8 **#6666e6** #8282ee #a3a6f4 #c8ccfa #eef0ff |
| shallow water | #4c58d8 #5c70e0 #6e88e6 #86a2ec #a2bcf0 #c2d6f4 |
| grass | #0b3410 … #44ad38 … #b0e690 (9 shades, a calmer version of #00e600) |
| tree canopy | #06200c … #2e8c31 … #b4e494 (10 shades) |
| asphalt | #18181b … **#3d3d43** … #62626a (8) |
| concrete | #4a4a50 … **#89898f** … **#b6b6ba** … #f2f2f3 (9) |
| rail ballast | #3b342d … #b0a895 (7) |
| timber (sleepers, poles) | #3a2a17 … **#997f4c** … #c6ad78 (7) |
| steel | #2a2c33 … #e8eaee (7) |
| zone R / C / I | green #063d0e…#b8f6bc, lavender #1a1a6e…**#6666e6**…#d0d0fa, yellow #5a4a00…#fffac0 (8 each) |
| roofs | red tile, slate, tar (8 each); glass 9; brick 8; fire 9 |

The light and projection rules apply to every tile:

* **One light.** It comes from the upper left (west-north-west) and is high. Lit
  surfaces face north-west.
  * West walls are at 100% of their colour and south walls at 64%. Roofs are at 106%
    and are slightly brighter toward their north-west corner.
  * Drop shadows fall to the right and a little down (0.80, 0.42 per unit of height).
    They are soft-edged and multiply the ground by a cool grey (0.40, 0.41, 0.54) at
    full strength.
* **One projection.** It is the original's: a height h moves a point by (+0.5h, -0.5h)
  tile units. Chimneys, power poles and tall towers therefore keep the original's
  diagonal look.
* **Texture.** Texture is gentle and periodic. Every ground and surface texture is value
  noise whose lattice divides the tile, so it repeats exactly every tile. Contrast is
  kept low (about 5 to 10% of the ramp) so the repeat does not show as a grid.
* **Shapes.** All shapes are signed-distance fields in tile units, drawn on a 4-times
  supersampled canvas (256 pixels per tile) and box-filtered down. The same source
  therefore gives 128, 64 and 32 pixel atlases with natural anti-aliasing.

## 3. Seams: principles

Every tile must meet its neighbours exactly.

1. **Shared ground.** All land tiles start from the same periodic dirt layer, and all
   water tiles from the same periodic water layer. Any feature drawn on top meets the
   edge only through a fixed **edge contract**:
   * Road: asphalt within 0.30 of the centreline, a kerb from 0.30 to 0.328, and centre
     dashes centred at 0.25 and 0.75, so every edge falls in a gap.
   * Rail: ballast within 0.21 of the centreline. Sleepers sit at (k+0.5)/8 along a
     straight and 6 per quarter-curve, so edges always fall between sleepers. Rails are
     at ±0.075.
   * Power: the pole is at the centre and its top at (+0.16, -0.16). The wires are
     ±0.07 about the pole-top line, so they cross the edge at the same place in every
     tile.
   * Coast: the coastline is the edge distance minus 0.24, plus one periodic noise
     field. Corner tiles use a smooth minimum of two edges, which only bends the line
     away from the tile edges.
   * Woods: each tree crown is kept or dropped by evaluating the tile's own
     forest-field formula at the crown's centre, even when that centre lies beyond the
     edge. The crowns come from one periodic set, so two neighbours agree on every crown
     that crosses their edge.
2. **Randomness.** Random detail stays at least 0.05 tile from the edges (rocks, rubble,
   flowers, houses and cars), or it is periodic.
3. **Paths.** Everything that runs along a path takes its arc length from global
   coordinates. This covers sleepers, dashes and car slots, so the phase is the same in
   every tile.
4. **Traffic.** Cars move a quarter of the lane length per frame and never straddle a
   tile edge. The 4 frames therefore loop and neighbouring tiles never cut a car in
   half.
5. **Buildings.** A building is drawn as **one picture** (3×3 or 4×4) and then cut into
   cells, so its internal seams cannot exist. Its outer edge is the zone frame on
   periodic ground. An animated cell (smoke) is the same picture rendered once per
   frame. The plume is masked so it fades out before it reaches the edge of the
   animated cells.
6. **Seam test.** `seamcheck.py` compares the touching pixel columns of every pair of
   tiles that the engine's rules allow side by side. Roads, rail, power and coast all
   measure at or below the normal difference between two adjacent columns inside one
   tile:

   | pair | edge difference | inside a tile |
   |---|---|---|
   | road/power/land | 2.2 | 2.2 |
   | rail | 5.9 | 6 to 10 |
   | coast | 3.0 | 3.6 to 8.4 |
   | woods | 10.6 | 13 to 15 |

   No seam is visible.

## 4. Known limits, all inherited from the original map data

* **Concave coast corners.** A water tile whose land is only diagonal is plain RIVER, so
  the neighbouring coast tiles' land strips stop with a small step there. Scenario maps
  also often place open water directly against dirt with no coast tile, which gives
  staircase banks. The original has exactly the same steps.

  The fix is not more art but an 8-neighbour (47-variant "blob") autotile chosen by the
  renderer at draw time. The generator can produce those variants unchanged, because
  the coast field takes any set of land edges and corners.
* **Repeated woods.** Woods repeat every tile, because there is a single tile number. The
  same renderer-side hash could choose among 2 to 4 generated canopy variants.
