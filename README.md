# KScape

A cinematic movie skin for Kodi 21 (Omega), built around an edge-to-edge wall of posters you
glide across with a remote. Pause on a movie and its synopsis appears, then related titles
shuffle into place around it. A list view, a full movie info screen and a Home screen with
rotating artwork complete it.

KScape is built only from Kodi's own skinning and Python APIs and your own library artwork.

## What it does

- **Home screen.** Back from the wall. Random fanart from your movie library fills the screen
  and crossfades to another movie every ~11 s (the movie's title shows bottom right), with a
  KScape-blue navigation bar along the bottom: **Movies** (opens the wall), **System** and
  **Power**. As in Aeon Nox: SiLVO, the focused item shows a submenu strip (here above the bar):
  **Up** enters it, **Down** or **Back** return, Left/Right wrap around.
  - *System* opens Kodi Settings; its submenu is SiLVO's: System info, Power options, Skin
    settings, File manager, Profiles, Event log (when enabled), plus KScape's Switch skin.
  - *Power* opens the power dialog (SiLVO's list: Exit, Power off, shutdown timer, Suspend,
    Hibernate, Reboot, Log off, master mode, idle shutdown, Favourites, Reload skin, Skin
    settings, Settings); its submenu is SiLVO's: Power off, Reboot, Suspend, Hibernate, Log off,
    Quit. Entries the system cannot do are hidden, as in SiLVO.
- **Cover wall.** Opens at startup. About 9 × 3.6 covers are visible, bleeding off every edge,
  in title order running down the columns and across to the right.
- **Focus frame.** A thick amber frame hugs the selected cover, in front of the wall, filling
  the gutter to its neighbours.
- **Camera follow.** The focus frame glides to the next cover with a soft overshoot
  (0.42 s), and the wall follows with a long ease-out (0.6 s) that settles gently.
- **Synopsis panel.** About 1.1 s after you stop on a movie, a blue panel with its title and
  synopsis opens beside it (on whichever side has room).
- **Related-cover shuffle.** About 3.2 s after you stop, every cover flies to a new cell so the
  most related movies end up closest to the one you picked. That movie and its panel stay put;
  covers leaving the screen fly off and newcomers fly in from the edges.
- **Movie info.** Select on a cover slides up a large panel over the wall: poster, the
  rating and facts line (runtime, video quality, aspect ratio, country, year), synopsis, genres,
  cast, director and collection, with **Return / Resume Movie / Play Movie / Play Trailer**.
  Resume and Trailer only appear when Kodi has a resume point or trailer for that movie.
- **List view.** The library as a table: the focused movie sits in a tall blue band with its
  poster and up to four genres, cast members and directors; the other rows show one line per
  column. Left/Right move between the Title, Genre, Cast, Director, Year, Time, Rating and
  Quality columns, scrolling the columns sideways. The first Up/Down in a newly focused column
  re-sorts the list by it, keeping the movie under the band. In title order, the letter each
  title sorts by is amber (a leading "The" is skipped, as Kodi sorts). Genre, Cast and Director
  list a movie under each of its values (cast: the four names shown); Up/Down first step
  through the movie's own values, marked ▶ and amber, regrouping the list around it, then move
  on to the next movie.
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
| Select / Enter | Open the movie info screen |
| Play | Play the movie (resumes from the last position if there is one) |
| Back / Esc | Undo the last shuffle; with nothing left to undo, leave the wall |
| Menu / C / Info | Wall menu: list view, shuffle now, automatic shuffle on/off, reduce motion on/off, show duplicates once on/off, reload library, switch skin, exit |

In the **list view**: Up/Down move through movies, Left/Right between columns, Select opens the
info screen, Play plays, Back returns to the cover wall on the same movie, and Menu offers
cover wall / switch skin / exit. The view you were in is remembered across restarts.

On the **info screen**: Up/Down choose an action, Select runs it, Back returns.

During playback: **OK / Menu** opens the controls, **Info** shows the movie's details, **Back** closes them,
and the usual Kodi playback keys (pause, seek, stop) keep working.

## Install

Requires Kodi 21 Omega. Both add-ons are needed for the animated wall; without
`script.kscape.wall` the skin falls back to a static poster grid.

### From ZIP (recommended)

Download `script.kscape.wall-<version>.zip` and `skin.kscape-<version>.zip` from the
[latest release](https://github.com/Oxiadust/kscape/releases/latest), or build them yourself:

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

- **Wall menu → Switch to another skin…**, or **Home → System → Switch skin**, or Kodi's own
  **Settings → Interface → Skin**.
  Kodi loads the chosen skin and asks whether to keep it; if you do not answer, it reverts.
- Or, from this repository: `tools/revert_kodi_skin.sh [skin-id]` (default `skin.aeon.nox.silvo`).
  It quits Kodi if needed and edits `guisettings.xml`.

## Settings

KScape has its own versions of Kodi's settings screens (Settings, its category pages, System info, Profiles,
File manager, Event log, add-on browser/information/settings, keyboard and the other dialogs they
open), drawn in KScape's blue. **Skin settings** offers: Reduce motion, and hiding the Home
screen's background artwork, clock or movie title.

The wall's own options are stored as add-on settings of `script.kscape.wall` and toggled from the wall menu:

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
skin.kscape/              Kodi skin: startup routing, Home (artwork + navigation), Kodi's
                          settings/system windows and dialogs (Includes_System.xml holds their
                          shared look), playback controls, fallback poster grid
script.kscape.wall/       The cover wall add-on (Python + window XML)
  resources/lib/          geometry, model, ranking, wallmodel, info, listmodel (pure Python);
                          library, cache, skins, state, window (wall), details (info screen),
                          listwindow (list view)
  tests/                  unit tests for ranking, placement, badges, info text, list sorting
tools/
  gen_wall_xml.py         generates the wall window XML from geometry.py (do not hand-edit the XML)
  gen_list_xml.py         generates the list view XML from listmodel.py (likewise)
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
python3 tools/gen_list_xml.py                                       # after changing listmodel.py
tools/kodi_smoke_test.sh                                            # isolated Kodi with both add-ons
python3 -I tools/kodi_nav_test.py                                   # scripted navigation checks
```

The smoke test runs a second Kodi under `HOME=/tmp/kscape-home` on JSON-RPC port 9091 and only
ever stops the instance it started, so it is safe to run while a real Kodi is open. Copy a
library into that profile's `userdata/Database/` (and `Thumbnails/` for offline artwork) to test
against real data. Kodi screenshots take about a second, so check motion with slowed timings.

## Known limitations

- Not every Kodi window has a KScape version: music, pictures, TV/PVR, games, weather and the
  playback audio/subtitle settings dialogs still need another skin
  (the playback controls cycle tracks instead). Kodi's default icons (folders, add-on
  placeholders) are not bundled, so items without their own icon show none. The slider dialog
  has not been checked in Kodi (it needs a playing video).
- The Home submenu sits above the bar rather than below it as in SiLVO, so Up (not Down) enters
  it. SiLVO's skinshortcuts-only "Master user" profile condition is not copied.
- Duplicates are matched on title and year, the only thing Kodi's metadata offers. Entries the
  scraper misidentified as the same film (for example several different films all matched to
  one title) are merged too; fix the match in Kodi (*Refresh* on the item) or turn the option off.
- Badges depend on Kodi's stream details, which it records only after reading the files.
- Tested on macOS with Kodi 21.3 at 1080p, with a real 757-movie library and a synthetic
  5,000-movie library (ranking and placement for 5,000 movies take about 55 ms on the
  development Mac). Not yet tested at 4K, on low-power devices, or on Linux/Android/Windows.
- The info screen lays out its right-hand column from estimated line counts (Kodi cannot
  measure text for scripts): a long synopsis scrolls inside its box, and an unusually long cast
  list is cut at three lines.
- The video aspect ratio on the info screen is the encoded video's, as Kodi reports it, so a
  letterboxed 2.39 film encoded at 16:9 shows 1.78.
- Re-sorting a 5,000-movie list by cast takes about 3.5 s the first time on the development
  Mac (Kodi's list item API costs ~0.2 ms per row and each movie appears under four names);
  genre is prepared in the background when the list opens, and recent sorts are kept.
- The list view takes a snapshot of the library when it opens; library changes made while it is
  open appear the next time you open it.
- The info screen offers no *Play Scene* entry: Kodi has no chapter list outside playback.
- A key press during a camera glide may show a one-frame jump; not observed, not ruled out.
- The reference video used to match the motion is kept out of the repository.
