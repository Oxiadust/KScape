# kscape

A Kodi 21 (Omega) movie cover wall in the style of the Kaleidescape movie library: an
edge-to-edge wall of posters you glide across with a remote, where pausing on a movie shows
its synopsis and then shuffles related titles into place around it.

It is an original implementation built only from Kodi's own skinning and Python APIs and your
own library artwork. It is not affiliated with Kaleidescape and uses none of its code or assets.

## What it does

- **Cover wall.** Opens at startup. About 9 × 3.6 covers are visible, bleeding off every edge,
  in title order running down the columns and across to the right.
- **Camera follow.** The amber focus frame glides to the next cover with a soft overshoot
  (0.42 s), and the wall follows with a long ease-out (0.6 s) that settles gently.
- **Synopsis panel.** About 1.1 s after you stop on a movie, a blue panel with its title and
  synopsis opens beside it (on whichever side has room).
- **Related-cover shuffle.** About 3.2 s after you stop, every cover flies to a new cell so the
  most related movies end up closest to the one you picked. That movie and its panel stay put;
  covers leaving the screen fly off and newcomers fly in from the edges.
- **Quality badges.** Covers show **HDR** or **UHD** when Kodi has stream details for the file.
- **Library aware.** The wall reloads itself after a library scan or clean, keeping your place.
- **Remembers where you were**, across Kodi restarts.
- **One cover per movie.** Duplicate copies (same title and year) show as one cover by default;
  the copy with a resume point, then the best quality, is the one kept and played.
- **Playback controls** in the same style: play/pause, back/forward 30 s, audio track, subtitles
  (both cycle in place), stop, plus a title strip and an info screen.

### Remote / keyboard

| Key | Action |
| --- | --- |
| Arrows | Move across the wall (stops at the edges, no wrap-around) |
| Select / Enter | Play the movie (resumes from the last position if there is one) |
| Back / Esc | Undo the last shuffle; with nothing left to undo, leave the wall |
| Menu / C / Info | Wall menu: shuffle now, automatic shuffle on/off, reduce motion on/off, show duplicates once on/off, reload library, switch skin, exit |

During playback: **OK / Menu** opens the controls, **Info** shows the movie's details, **Back** closes them,
and the usual Kodi playback keys (pause, seek, stop) keep working.

## Install

Requires Kodi 21 Omega. Both add-ons are needed for the animated wall; without
`script.kscape.wall` the skin falls back to a static poster grid.

### From ZIP (recommended)

```sh
tools/build_zips.sh          # writes dist/skin.kscape-<ver>.zip and dist/script.kscape.wall-<ver>.zip
```

In Kodi: **Settings → Add-ons → Install from zip file**, install `script.kscape.wall` first, then
`skin.kscape`, and accept when Kodi asks to switch skins. (Allow "Unknown sources" if Kodi asks.)

### By copying (development)

Copy both folders into Kodi's `addons/` directory (macOS: `~/Library/Application Support/Kodi/addons/`).
Kodi registers hand-copied add-ons as **disabled**; enable them in Kodi, or with Kodi closed:

```sh
sqlite3 ~/Library/Application\ Support/Kodi/userdata/Database/Addons33.db \
  "update installed set enabled=1 where addonID in ('skin.kscape','script.kscape.wall');"
```

then set `lookandfeel.skin` to `skin.kscape` in `userdata/guisettings.xml`.

## Switching back to another skin

kscape has no Kodi Settings screens of its own. To leave it:

- **Wall menu → Switch to another skin…**, or **Home → Switch skin** (Back from the wall).
  Kodi loads the chosen skin and asks whether to keep it; if you do not answer, it reverts.
- Or, from this repository: `tools/revert_kodi_skin.sh [skin-id]` (default `skin.aeon.nox.silvo`).
  It quits Kodi if needed and edits `guisettings.xml`.

## Settings

Stored as add-on settings of `script.kscape.wall` and toggled from the wall menu:

- **Shuffle related covers automatically** (on). Off: use *Shuffle related covers now*.
- **Show each movie once** (on). Off: every library entry gets its own cover.
- **Reduce motion** (off). On: no glide or flight; covers swap in place.

Motion timings and easing (`FRAME_TWEEN`: `back` for one soft overshoot, or `elastic` for a
bouncier settle), sizes and the pool size live in
[`script.kscape.wall/resources/lib/geometry.py`](script.kscape.wall/resources/lib/geometry.py).

## How the shuffle works

1. **Ranking** ([`ranking.py`](script.kscape.wall/resources/lib/ranking.py)). Every other movie is
   scored against the one you stopped on: same movie set 100, shared director 40, each shared
   actor up to 20 (weighted down by billing position in both films), each shared genre 8, each
   shared tag 6, same decade 4, and up to 3 more for release years within six years. Ties break
   on year distance, sort title, then movie id, so the result is deterministic.
2. **Placement** ([`wallmodel.py`](script.kscape.wall/resources/lib/wallmodel.py)). The selected
   movie keeps its cell. All other cells are ordered by on-screen distance from it (cells under
   the synopsis panel count as farther away) and filled in rank order, so the closest neighbours
   are the most related titles and relatedness fades outward across the whole wall.
3. **Animation** ([`window.py`](script.kscape.wall/resources/lib/window.py)). Kodi cannot move items
   inside its list controls, so the wall is a recycled pool of cover slots the window positions
   itself. Motion uses animations created at runtime (`Control.setAnimations`) whose conditions
   watch a Home window property. Two slot pools double-buffer the shuffle: the new arrangement
   is bound into the hidden pool, then a single property change hides the old covers, flies the
   departing ones out and flies every new cover from its previous position (or the nearest
   screen edge) into place, with staggered timing and a mid-flight shrink.

Back undoes shuffles from a history stack.

## Project layout

```
skin.kscape/              Kodi skin: startup routing, minimal Home, dialogs, playback controls,
                          fallback poster grid
script.kscape.wall/       The cover wall add-on (Python + generated window XML)
  resources/lib/          geometry, model, ranking, wallmodel (pure Python), library, skins, state,
                          window
  tests/                  unit tests for ranking, placement, badges
tools/
  gen_wall_xml.py         generates the wall window XML from geometry.py (do not hand-edit the XML)
  build_zips.sh           installable ZIPs into dist/
  kodi_smoke_test.sh      launches an isolated test Kodi (temporary HOME, JSON-RPC port 9091)
  kodi_nav_test.py        drives the test Kodi over JSON-RPC
  kodi_rpc.py             one-off JSON-RPC calls (KSCAPE_RPC_PORT=9090 for a real Kodi)
  revert_kodi_skin.sh     switch the real profile back to another skin
```

## Development

```sh
(cd script.kscape.wall && python3 -m unittest discover -s tests)   # unit tests
python3 tools/gen_wall_xml.py                                       # after changing geometry.py
tools/kodi_smoke_test.sh                                            # isolated Kodi with both add-ons
python3 -I tools/kodi_nav_test.py                                   # scripted navigation checks
```

The smoke test runs a second Kodi under `HOME=/tmp/kscape-home` on JSON-RPC port 9091 and only
ever stops the instance it started, so it is safe to run while a real Kodi is open. Copy a
library into that profile's `userdata/Database/` (and `Thumbnails/` for offline artwork) to test
against real data. Kodi screenshots take about a second, so check motion with slowed timings.

## Known limitations

- No Kodi Settings or add-on browser screens, and no audio/subtitle settings dialogs (the playback
  controls cycle tracks instead): kscape is only the wall. Use another skin for system
  configuration (see *Switching back*).
- Duplicates are matched on title and year, the only thing Kodi's metadata offers. Entries the
  scraper misidentified as the same film (for example several different films all matched to
  one title) are merged too; fix the match in Kodi (*Refresh* on the item) or turn the option off.
- Badges depend on Kodi's stream details, which it records only after reading the files.
- Tested on macOS with Kodi 21.3 at 1080p and a 384-movie library. Not yet tested at 4K, on
  low-power devices, or with a real 5,000-movie library (ranking and placement for 5,000 movies
  take about 55 ms on the development Mac).
- A key press during a camera glide may show a one-frame jump; not observed, not ruled out.
- The reference video used to match the motion is kept out of the repository.
