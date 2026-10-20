# KScape

A cinematic skin for Kodi 21 (Omega), built around an edge-to-edge wall of covers you glide
across with a remote. Pause on a movie, album or TV show and its synopsis appears, then related
titles shuffle into place around it. Movies, Music and TV Shows each have a cover wall, a list
view and Collections; music adds Now Playing. Bookmark scenes in movies and episodes and chain
them into Demo Scripts that play from movie to movie by themselves. Kodi's own favourites and a
search scoped to each library are one press of C away.

KScape is built only from Kodi's own skinning and Python APIs and your own library artwork.

## What it does

- **Home screen.** Back from the wall. Random fanart from your movie library fills the screen
  and crossfades to another movie every ~11 s (the movie's title shows bottom right), with a
  navigation bar in the theme colour along the bottom: **Movies**, **Music**, **TV Shows**, **System**
  and **Power**. Left/Right wrap around.
  - *Movies*, *Music* and *TV Shows* open their wall (or list, whichever you used last). Above
    the focused tab, a column of cards shows the views it offers - **List**, **Covers**,
    **Collections**, and **Now Playing** for music - each the real view
    at 1/6 scale, drawn live from your own library.
    **Up** enters the cards at the bottom one, nearest the bar (the selected one gets the wall's highlight-coloured frame), **Select** opens that
    view, **Down** past the last card or **Back** returns to the bar. **Left/Right** on a card go
    straight to the next category with its cards (or submenu) open.
  - While something plays, the top right, under the clock, shows it: a video live in a small
    window (Kodi's own video window, in the video's aspect ratio), music by its cover, with the
    title, artist and album (or show and episode), play state and progress. The views (walls,
    lists, collections) show the same in a small chip top right, so you can browse the libraries
    while it plays.
  - **Back** or **Esc** on Home while something plays returns to it: full-screen video where it
    was, or KScape's Now Playing for music. With nothing playing they do what they did before.
  - As in Aeon Nox: SiLVO, *System* and *Power* show a submenu strip above the bar: **Up** enters
    it, **Down** or **Back** return, **Left/Right** past either end switch category.
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
  synopsis eases in beside it (on whichever side has room) - a fade with a short slide out from
  the cover and a slight scale, and a quicker ease out when you move on (a plain fade with
  Reduce motion); under the synopsis, the movie's resolution badge (**4K**, **1080p**, **720p**,
  **SD**), its TMDB score and its Rotten Tomatoes Tomatometer, each only when known.
- **Related-cover shuffle.** About 3.2 s after you stop, every cover flies to a new cell so the
  most related movies end up closest to the one you picked. That movie and its panel stay put;
  covers leaving the screen fly off and newcomers fly in from the edges. No cover flies across the
  selected one: paths that would are steered round its frame.
- **Movie info.** Select on a cover slides up a large panel over the wall: poster, synopsis,
  then the facts line (runtime, aspect ratio, country, year: `2h 43m · 2.39:1 · USA · 2021`)
  with badges for the resolution, dynamic range (SDR, HDR10, HDR10+, Dolby Vision, HLG) and the
  best audio track (Dolby Atmos, DTS:X, Dolby TrueHD, DTS-HD MA, Dolby Digital Plus, DTS, Dolby
  Digital, PCM, FLAC, AAC), a **Ratings** row (certificate, TMDB, Rotten Tomatoes), then genres,
  cast, director and collection. The menu: **Return / Resume Movie / Play Movie / Play Trailer
  / Play Scenes / Explore**. Resume and Trailer only appear when Kodi has a resume point or
  trailer for that movie. Everything comes from Kodi's library (stream details measured from the
  file, scraped ratings); anything missing is left out, never guessed.
- **Explore** (movie info → Explore, Right or Select): beside the poster, **Related Movies**, the
  movie's collection, director, cast, genres, year and country, each with how many of your
  movies it leads to. Select one and the info screen closes on the library filtered by it, in
  the view you were using (cover wall or list view). Related Movies are movies of your library
  only: the same collection first, then shared genres, directors, cast and tags, most related
  first. **Back** returns to the movie's Explore panel, then to the whole library.
- **Filters.** **C → Filter…** on a movie wall or list view: add filters by genre, actor,
  director, year (or a range of years), decade, country, resolution, video format, audio format,
  TMDB rating, Rotten Tomatoes, duration (short, medium, long), watched status; they combine
  (Sci-Fi + 4K + Dolby Vision). Only categories and values your library has are offered, each
  with how many movies have it. The active filters and the count show along the bottom of the
  wall (the heading of the list view), stay when you switch between the two, and each can be
  removed, or **Clear all filters**; Back clears them too. Actor filters use Kodi's own library
  filter, so the whole cast counts. In Favourites or a collection, filters narrow what that wall
  shows, and Explore opens a filtered wall of the whole library over it.
- **Play Scenes** (movie info → Play Scenes): **Play All Scenes** and the movie's scenes with
  their lengths (favourites marked with a heart), as on Kaleidescape. Select plays a scene from
  its start to its end in Kodi's own player, then the info screen returns to the scene list;
  Play All Scenes plays them one after another, skipping what lies between. Pause, seek and
  Stop work as usual (seeking out of the scene, or Keep watching in the controls, lets the movie
  play on). **C** on a scene: Play, Edit (name, start, end, description), Rename, Add to /
  Remove from favourite scenes, Add to Demo Script…, Delete. **Create scene…** makes one without
  playing the movie (name, then start and end typed as H:MM:SS); **Import chapters…** reads the
  chapters embedded in the file (MKV, MP4/MOV; or those Kodi reports while the movie plays),
  offers them with their times, keeps the file's chapter names (numbered or timestamp names
  become "Chapter 1", "Chapter 2"…) and skips chapters already saved. With no scenes yet, the
  page says how to make one.
- **List view.** The library as a table: the focused movie sits in a tall blue band with its
  poster and up to four genres, cast members and directors; the other rows show one line per
  column. Left/Right move between the Title, Genre, Cast, Director, Year, Time, Rating and
  Formats columns (Formats: every format the movie is available in, `4K · 1080p · 3D`; sorted
  best first), scrolling the columns sideways. The first Up/Down in a newly focused column
  re-sorts the list by it, keeping the movie under the band. In title order, the letter each
  title sorts by is amber (a leading "The" is skipped, as Kodi sorts). Genre, Cast and Director
  list a movie under each of its values (cast: the four names shown); Up/Down first step
  through the movie's own values, marked ▶ and amber, regrouping the list around it, then move
  on to the next movie.
- **Format badges.** Movie covers carry one compact amber badge listing every format the movie
  is available in - **4K**, **1080p**, **720p**, **3D**, **SD** or **DVD** - across all its
  versions, bottom right, only when Kodi has measured the files. Skin settings → Movie versions
  hides them. (TV show and album covers keep their own markers.)
- **Ratings.** TMDB from Kodi's scraper. Rotten Tomatoes when the library has it (an NFO
  `tomatometerallcritics` / `rottentomatoes` rating, or a scraper that stores one). Kodi's TMDB
  scraper stores none, so the add-on settings can take your own free OMDb API key: KScape then
  asks OMDb for the Tomatometer of the movie you are looking at (one at a time, by its IMDb id),
  keeps the answer for a month (`ratings.json`) and never writes it into Kodi's library.
- **Library aware.** The wall reloads itself after a library scan or clean, keeping your place.
- **Remembers where you were**, across Kodi restarts.
- **One cover per movie** (movie versions). A movie appears once on the wall and in the list,
  however many versions it has:
  - *Kodi's own versions* (Kodi 21: Manage versions → Add version, e.g. 4K, 1080p, 3D,
    Director's Cut) are one movie in Kodi already. KScape reads them from Kodi's library (no
    file scanning, cached with the library) and shows their formats.
  - *Separate library entries of one film* (copies added as different movies) show as one cover
    when they share the same TMDB or IMDb id, title, year and edition; titles alone never merge
    two entries, and different editions (Director's Cut, Extended, Theatrical, IMAX...) named in
    the title or file name stay apart. The copies then count as versions of that cover.
    Optional: add-on settings → Show duplicates once.
  - **Play** starts the version KScape prefers: the resolution chosen in Skin settings → Movie
    versions → *Version Play starts* (4K first by default, then 1080p, 720p, SD; or Kodi's
    default version), never a 3D version over a 2D one unless *Prefer 3D versions* is on.
    **Resume** resumes the version you were watching: Kodi keeps a resume point per version.
  - **Play Version** (movie info, when there are two or more) lists each version with its name,
    resolution, 3D, dynamic range and audio - `Director's Cut — 4K Ultra HD · 2160p · Dolby
    Vision · Dolby TrueHD` - the one Play would start first; one with a resume point asks
    whether to resume it.
- **Music.** The same wall with square album covers (missing artwork shows the album and artist
  on a dark card); the panel shows album and artist, and related albums (same artist, shared
  artists, genres, styles, era) shuffle around the one you pick. The list view's columns are
  **Artist** (amber sort letter, leading "The" skipped), **Album**, **Genre** and **Year**.
  Select opens the album: cover, facts, review, **Play Album** and its tracks (Select on a track
  plays the album from there, in Kodi's own music player).
- **Now Playing.** Cover, title, artist, album and year, progress, play state, **Previous /
  Play-Pause / Stop / Next** (Kodi's own player controls), and the queue (Select jumps to a
  track). Opens by itself when you start an album.
- **TV Shows.** A poster wall and a list view (Title, Genre, Cast, Network, Year, Seasons,
  Episodes, Rating). Select opens the show: poster, facts, plot and its seasons; Select on a
  season lists its episodes (unwatched ones marked amber; Back returns to the seasons); Select on
  an episode plays it, asking whether to resume if Kodi has a resume point. Shows with a single
  season open straight on its episodes. **Play** on a show starts the first unwatched episode.
- **Favourites.** Kodi's own favourites (`favourites.xml`), no separate list: KScape writes the
  same entries Kodi's context menu does, so favourites added in either place show in both.
  Favourite covers and list rows carry an amber heart. **C → Favourites** on a cover wall opens
  the wall of just your favourites of that kind (Back returns), updated as soon as one is added
  or removed (here or in Kodi's own favourites window); with none it explains how to add one.
- **Collections** for movies, music and TV shows, each from its Home card. Laid out like
  Kaleidescape's collections screen: a tab bar of collections along the bottom, the selected
  collection's titles on the left with the focused one in a tall blue band, its poster (or album
  cover) on the right; while the tab bar has focus, the right side previews the collection (one
  poster, or four) and the heading gives its name and how many titles it holds.
  - Built-in collections always come first, marked amber and never renamed or deleted, worked
    out from Kodi's library and followed while open (watch a movie and it moves from Paused to
    Played; play a song and its album joins Played):
    - **New**: added in the last 30 days, newest first (for a show, its latest episode). The
      period is in the C menu on the New tab and in the add-on settings.
    - **Paused**: movies with a resume point, not watched; shows with an episode part-watched
      ("Paused on January 5 at 7:27 pm"). Not for music: Kodi keeps no resume point for songs.
    - **Played**: watched movies, albums with any song played, shows with any episode watched.
  - Then your own, separate for each library: **C** on a tab offers New collection…, Rename and
    Delete; **C** on any title (here, on the walls and in the list view) offers **Add to
    collection…**, a list of your collections ticked where it already is, so it can join or
    leave several at once. In one of your collections, **C → Move** lets Up/Down carry the
    title to a new place (Select or Back put it down) and **Remove** takes it out. Kept in the
    add-on's profile folder (`collections.json`, `collections-music.json`, `collections-tv.json`):
    movies by file, as Kodi's favourites are, shows by folder, albums by artist and title.
  - **Left/Right** choose a collection, **Up** enters its titles, **Select** on a tab opens it as
    the cover wall (C: as the list view), **Select** on a title opens it (movie info, album,
    show), **Play** plays it, **Down** past the last one or **Back** return to the tabs.
- **Scenes and Demo Scripts** (movies and TV episodes), after Kaleidescape's scene bookmarks and
  scripted demos.
  - *Making a scene*: during a library movie or episode, open the controls (**OK / Menu**) and
    choose **Mark scene start**; later (keep watching or seek) choose **Mark scene end**. Playback
    pauses and the scene editor opens: name, start, end (typed as H:MM:SS, so they can be
    adjusted), the length, an optional description. Save checks the times (the end must come
    after the start, at least a second, within the video). The movie's own C menu offers the
    same as **Create Scene** while it plays. Scenes point at the library file and are never
    copied; they are kept in the add-on's profile folder (`scenes.json`), apart from Kodi's
    metadata.
  - *The Scenes collection* (built in, after Played, in the Movies and TV Shows Collections):
    every scene, grouped by movie (or episode) in order, with its artwork, the scene name, the
    movie and the length. **Select** or **Play** plays the scene from its start and stops at
    its end. **C**: Play / Edit / Rename Scene, Add to Demo Script… (one or several), Delete
    Scene. A movie's (or show's) C menu offers **View Scenes** and **Add Scene to Demo Script…**
    when it has scenes.
  - *The Demo Scripts collection* (built in, next to Scenes): ordered playlists of scenes from
    any movies and episodes. **C** on the tab: New demo script…; on a script: Play, Edit,
    Rename, Duplicate, Delete Demo Script (scenes and videos stay). **Select** opens the
    script's screen: its cover, how many scenes and how long, its playback options and
    description, **Play / Edit… / Duplicate / Delete**, and the scenes in order - **Select** on
    one plays the script from there; **C** on one: Preview Scene, Move up / down, Remove from
    Demo Script (the scene stays), Add scenes….
  - *Playback options* (Edit…): transition - **Cut**, **Fade to black** or **Black pause**, with
    its length (0.5-8 s) - and **Play once**, **Loop the script** or **Loop one scene** (that
    scene repeats until you press Next).
  - *Playing a script*: KScape opens the first movie straight at the scene's start, plays to its
    end, moves to the next movie and scene, and so on, with no input. While the next scene loads,
    its artwork card fills the screen instead of black - the movie's fanart and poster (for a TV
    episode, the show's), "Up next", the title and the scene's name - until the scene plays; with
    Fade to black or Black pause, the card is what the transition shows. Play All Scenes on a
    movie's info screen does the same. **Play/Pause** and **Stop**
    work as usual; the remote's **Next / Previous** (or **Next scene / Previous scene** in the
    controls) move between scenes; **Keep watching** in the controls, or seeking outside the
    scene, leaves demo mode and the movie plays on normally. The controls show the scene, the
    movie and "Scene 2 of 4"; nothing is drawn over the movie otherwise. Missing files are
    skipped (and said so). Watching scenes does not leave resume points or play counts behind:
    KScape puts back what they were.
- **Search.** From the C menu. Kodi's on-screen keyboard (KScape-styled) asks what to look for;
  results open as a list view of that library only - movies match titles, then cast and
  directors; albums match album and artist (then genre); shows match titles, then cast - with a
  heading saying what was searched and how many matched, or a message when nothing did. C on
  the results searches again.
- **Playback controls** in the same style: play/pause, back/forward 30 s, audio track, subtitles
  (both cycle in place), stop, plus a title strip and an info screen.

### Remote / keyboard

| Key | Action |
| --- | --- |
| Arrows | Move across the wall (stops at the edges, no wrap-around) |
| Select / Enter | Open the movie info screen |
| Play | Play the movie (resumes from the last position if there is one) |
| Back / Esc | Leave the wall, straight back to Home (the shuffles can be undone from the menu) |
| Menu / C / Info | Menu: **Add to / Remove from Favourites** (labelled for the selected item), **Search…**, **Add to collection…**, then **Undo shuffle** (after a shuffle), list view, shuffle now, automatic shuffle on/off, reduce motion on/off, show duplicates once on/off (movies), **Favourites** (the wall of your favourites), reload library, switch skin, exit |

In the **list view**: Up/Down move through items, Left/Right between columns, Select opens the
info, album or show screen, Play plays, Back goes back to Home (or, when the list was opened
from the wall's menu, returns to the wall on the same item), and
Menu offers favourites / search / cover wall / switch skin / exit. The view you were in is
remembered across restarts, per library.

On the **info, album and show screens**: Up/Down choose, Left/Right move between the menu and
the track, season or episode list, Select runs it, Back returns (from episodes, to the seasons),
and C offers favourites and search.

On **Now Playing**: Left/Right/Up/Down move between the buttons and the queue, Back returns, C
offers favourites (for the playing album) and search.

Leaving a view with the remote's Home key (or a long press on Back) while a movie plays no longer
blocks the libraries: the view left open underneath is closed when you next open one from Home.

During a scene or Demo Script the controls also offer **Previous scene / Next scene / Keep watching**
(the remote's Next / Previous skip scenes too); otherwise **Mark scene start / end** for library
movies and episodes.

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
open), drawn in the theme colour. **Skin settings** has five categories, chosen on the left:
**General** (Reduce motion), **Colours**, **Home screen** (hide the background artwork, clock
or movie title), **Movie versions** (format badges on covers, the version Play starts, prefer
3D) and **Display & aspect ratio** (see *Ultrawide and CinemaScope*).

**Colours.** KScape is drawn in two colours, and Skin settings lets you pick each:

- **Theme colour** - Blue (default), Crimson, Emerald, Violet, Teal or Graphite: the panels,
  the list band, tabs and bars, and the tint of text on dark backgrounds.
- **Highlight colour** - Amber (default), White, Cyan, Lime or Rose: the selection frame,
  sort letters, markers, hearts and badges.

Each pair is one of Kodi's skin colour themes (`skin.kscape/colors/`, generated by
`tools/gen_colors.py`), so the choice also shows in Kodi's **Settings → Interface → Skin →
Colours**, and Kodi reloads the skin when it changes. Every view, the add-on's included, takes
its colours from the theme.

The wall's own options are stored as add-on settings of `script.kscape.wall` and toggled from the wall menu:

- **Shuffle related covers automatically** (on). Off: use *Shuffle related covers now*.
- **Show each movie once** (on). Off: every library entry gets its own cover.
- **Reduce motion** (off). On: no glide or flight; covers swap in place.

Add-on settings → **Ratings**: an optional **OMDb API key** for Rotten Tomatoes scores (empty by
default: OMDb is never contacted).

Motion timings and easing (`FRAME_TWEEN`: `back` for one soft overshoot, or `elastic` for a
bouncier settle), sizes and the pool size live in
[`script.kscape.wall/resources/lib/geometry.py`](script.kscape.wall/resources/lib/geometry.py).

## Ultrawide and CinemaScope

Skin settings → **Display & aspect ratio**:

- **Interface aspect ratio**: Auto (recommended), 16:9 Standard, 21:9 Ultrawide, 2.35:1, 2.39:1
  or 2.40:1 CinemaScope. Auto follows the screen Kodi draws on; the list shows what it detected.
- **CinemaScope poster wall**: automatic, two or three poster rows inside a CinemaScope band.
- **Vertical / Horizontal UI offset** (±300 px, steps of 20): move the interface to line it up
  with a projector screen.
- **Safe area / overscan** (0-10 % on every side): shrink the interface so nothing is cut off.
- **Preview layout**: an amber frame around exactly the area KScape now uses, its centre and a
  row of sample covers.

Every change applies at once and asks *Keep this layout?*; without an answer it goes back after
15 seconds, as Kodi does after a resolution change. Settings are skin settings, so they persist.

**Two situations.**

- *A native ultrawide screen* (Kodi runs at, say, 2560 × 1080 or 3440 × 1440). Auto handles it:
  the cover walls spread across the whole width with more columns, covers keeping their true
  2:3 shape; the other screens simply get wider.
- *A CinemaScope projector screen fed a 16:9 signal* (1920 × 1080 or 3840 × 2160, the projector
  zoomed so that the middle band fills a 2.35 / 2.39 / 2.40 screen). Nothing in the signal says
  so, so choose the screen's ratio by hand. KScape then draws inside that band: the cover walls
  lay out natively across it (two or three rows, black above and below so nothing spills onto
  the wall), every other screen - Home, menus, dialogs, the info screen, the playback controls -
  is scaled into it, and the offsets move it to where your projector's zoom puts the band.
  This is *interface* positioning only: KScape never changes Kodi's video output, the playing
  video's zoom or its aspect ratio, nor the projector's zoom.

**How it works in Kodi 21, and why.** Checked in the test Kodi, not assumed:

- Every KScape window - the skin's and the add-on's - uses 1920 × 1080 coordinates. Estuary
  adapts to other screens by declaring several coordinate spaces (`<res>` entries such as
  2560 × 1080 for 21:9, sharing one XML folder written with relative positions). KScape does not:
  the add-on's windows (cover walls, list views, info screen, Collections...) cannot use a
  skin's coordinate spaces - Kodi only looks for their XML in the add-on, at a fixed resolution -
  so the skin and the add-on would have needed two different corrections.
- On a screen of another shape, Kodi stretches those coordinates to fill it but draws text and
  artwork (images with an aspect ratio) in their true proportions. So a wide screen gets a wider
  layout with correct text; only boxes that must keep a shape are corrected: the walls' cover
  cells, frames and badges, the info screen's poster and badges. The cover wall builds its XML for
  the screen when it opens (`wallxml.py`, written to the add-on's profile folder), so nothing is
  resized control by control.
- A CinemaScope band on a 16:9 signal: every window's controls sit in one root group carrying
  `KScapeDisplay` (`Includes_Display.xml`, generated): zero-length conditional zoom and slide
  animations, one per possible value, waiting for Home window properties that the KScape service
  sets from the settings. Kodi animations cannot take values from settings, hence the steps
  (1 % zoom, 10 px offsets). ScopeNox (Aeon Nox for CinemaScope, Kodi 21) moves its windows the
  same way - a root group with conditional slides - because a window's `<origin>` stops working
  after ReloadSkin and window-level animations are ignored; it lays every window out by hand
  inside an 800-820 px band instead of scaling. KScape scales the existing layouts (so they stay
  as they are) and adapts only the cover walls natively.
- Video calibration and the mouse pointer are never transformed (Kodi places calibration marks on
  the real screen edges), as in ScopeNox.

**Testing.** Standard TV: Auto - the layout is unchanged (16:9, 1920 × 1080 or 3840 × 2160).
Ultrawide monitor: run Kodi full screen at the monitor's resolution, Auto; the walls show more
columns and covers stay 2:3. CinemaScope projector: keep Kodi at 1920 × 1080 or 3840 × 2160,
choose 2.35 / 2.39 / 2.40, open **Preview layout** and adjust the offsets until the amber frame
fills the screen exactly, then the safe area if an edge is cut; set the poster rows to taste.
Back to Auto or 16:9 restores the original interface.

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

**C → Undo shuffle** steps back through the shuffles (a history stack); Back leaves the wall.

## Project layout

```
skin.kscape/              Kodi skin: startup routing, Home (artwork + navigation), Kodi's
                          settings/system windows and dialogs (Includes_System.xml holds their
                          shared look), playback controls, fallback poster grid, colour
                          themes (colors/)
script.kscape.wall/       The wall add-on: movies, music and TV (Python + window XML)
  resources/lib/          geometry, model, media (albums, shows), ranking, wallmodel, info,
                          listmodel, search (pure Python); kinds (what differs per library),
                          favourites (Kodi's favourites), menu (the C menu), library, cache,
                          skins, state, window (wall), details (movie info), browse (album and
                          show screens), listwindow (list view), nowplaying, collectionmodel
                          (pure), collectionui and collectionwindow (collections), modal (the
                          open windows, closed when Home asks for another view), colours
                          (the colour theme pickers), scenemodel (pure), scenes (scene and
                          script actions), demowindow (a Demo Script's screen), demoservice
                          (the playback service: timed scenes, transitions, metadata restore),
                          streaminfo (resolution, HDR, audio, ratings; pure), explore (filters,
                          Related Movies; pure), exploreui (Filter menu), chapters (MKV / MP4
                          chapter reader; pure), ratings (optional OMDb Tomatometer), badges
                          (generated badge sizes), versions (movie versions, Play's choice;
                          pure), versionsui, display (aspect ratio, CinemaScope band, offsets;
                          pure), displayui (its settings and preview), wallxml (builds the
                          cover wall's XML for any screen), npchip (the now-playing chip)
  service.py              starts demoservice with Kodi and keeps the display properties current
  tests/                  unit tests for ranking, placement, badges, info text, list sorting,
                          albums, shows, favourites, search, collections, colour themes,
                          scenes and Demo Scripts, stream facts, filters and chapters, movie
                          versions and display & aspect ratio
tools/
  gen_wall_xml.py         writes the 16:9 wall window XMLs (poster, square) with wallxml.py (do
                          not hand-edit the XML)
  gen_list_xml.py         generates the movie, music and TV list XMLs from listmodel.py (likewise)
  gen_collections_xml.py  generates the Collections view XML (likewise)
  gen_colors.py           generates the skin's colour themes (skin.kscape/colors/)
  gen_badges.py           generates the format badges and rating icons (needs Pillow)
  gen_calibration.py      generates the video calibration marks (needs Pillow)
  gen_display_xml.py      generates the display transform (skin Includes_Display.xml)
  wrap_display.py         puts every hand-written window's controls in the display transform root
  gen_home_xml.py         generates the Home view cards (skin Includes_Home.xml) from the views'
                          geometry (likewise)
  np_chip.py              re-exports the add-on's now-playing chip (npchip.py) to the generators
  make_test_media.py      a small tagged music and TV library for the test Kodi
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
python3 tools/gen_collections_xml.py                                # the Collections view
python3 tools/gen_colors.py                                         # after changing the palette
python3 tools/gen_badges.py                                         # format badges, rating icons
python3 tools/gen_calibration.py                                    # video calibration marks
python3 tools/gen_display_xml.py                                    # after changing display.py steps
python3 tools/wrap_display.py --check                               # every window has the display root
python3 tools/gen_home_xml.py                                       # after any of those
python3 tools/make_test_media.py                                    # test music + TV library
MEDIA=1 tools/kodi_smoke_test.sh                                    # isolated Kodi, scans it too
python3 -I tools/kodi_nav_test.py                                   # scripted navigation checks
```

The smoke test runs a second Kodi under `HOME=/tmp/kscape-home` on JSON-RPC port 9091 and only
ever stops the instance it started, so it is safe to run while a real Kodi is open. Copy a
library into that profile's `userdata/Database/` (and `Thumbnails/` for offline artwork) to test
against real data. Kodi screenshots take about a second, so check motion with slowed timings.
Kodi keeps skin XML in memory once loaded: restart the test Kodi after editing skin files (the
add-on's window XML and Python are re-read each time a view opens).

## Known limitations

- Kodi 21 records audio as the codec underneath (TrueHD, DTS-HD MA, E-AC-3): it does not tell
  Dolby Atmos or DTS:X apart, so those badges and filters only appear when the stream details
  carry them (NFO files from media managers, later Kodi versions). Rotten Tomatoes needs an NFO
  rating or the optional OMDb key. Movie records keep the top eight billed names, so the
  Filter menu offers those actors (Explore and actor filters still find every film of a person
  through Kodi's library).

- Not every Kodi window has a KScape version: Kodi's own music file browser (only a cover grid,
  used by album favourites opened from Kodi's favourites window), the music visualisation (Kodi's
  Fullscreen key and Back on Home open KScape's Now Playing instead),
  pictures, live TV/PVR, games, weather and the playback audio/subtitle settings dialogs still
  need another skin
  (the playback controls cycle tracks instead). The system windows Kodi opens from Settings,
  Power and playback have KScape versions: the file and folder browser (Add media source →
  Browse, Install from zip, every folder picker), the profile login screen (Power → Log off),
  video calibration, the colour picker, the smart playlist editor and its rules, video
  bookmarks, subtitle search and the player process info. The colour picker has been checked
  against Kodi's control contract but not opened in Kodi (it is reached only from a few
  settings). Kodi's default icons (folders, add-on
  placeholders) are not bundled, so items without their own icon show none. The slider dialog
  has not been checked in Kodi (it needs a playing video).
- The Home submenu sits above the bar rather than below it as in SiLVO, so Up (not Down) enters
  it. SiLVO's skinshortcuts-only "Master user" profile condition is not copied.
- Favourites cover movies, albums and TV shows (the items the walls show), not single songs or
  episodes. A movie is a favourite by its file, as Kodi stores it, so a favourite added for one
  copy of a merged duplicate counts for the cover.
- Scenes and Demo Scripts are played by a service (part of `script.kscape.wall`, starting with
  Kodi): the skin alone cannot stop a video at a given time. After installing or updating the
  add-on, restart Kodi once so the service starts.
  - *Fade to black* fades the picture (a black layer over the paused last frame, then off the
    next scene); Kodi offers no audio fade, so the sound cuts. During a transition's black screen
    the remote talks to that black layer: Back or Stop there end the demo.
  - Scenes start where Kodi can open the file: with sparse keyframes a scene may begin a moment
    before its saved start. A scene counts as started only once playback is inside it; one that
    cannot be reached within 15 s is skipped.
  - Scene artwork is the movie's poster or the show's (Kodi gives add-ons no way to capture a
    video frame).
  - A demo interrupted by quitting Kodi is not resumed; on the next start KScape puts back the
    resume points and play counts it changed.
  - Seeking outside the playing scene is taken as leaving demo mode (the movie plays on).
- Paused and Played dates are Kodi's "last played" date (Kodi keeps no separate date for a
  resume point). Music has no Paused collection. An album renamed or re-tagged (new artist or
  title) drops out of your collections, as they store albums by artist and title. Your own collections are reordered with Move in
  the Collections view; their list view sorts by its columns like any other list.
- The add-on's views take their colours from the KScape skin's colour theme: run under another
  skin (which cannot happen from KScape's own menus) they would draw without them.
- Search looks through what the walls load: album titles, artists and genres, but not song
  titles; movie and show titles and people, but not plots.
- The Home Collections cards show the library's most recently added titles under the New tab,
  not your own collections (a skin cannot read them).
- Duplicates are matched on title and year, the only thing Kodi's metadata offers. Entries the
  scraper misidentified as the same film (for example several different films all matched to
  one title) are merged too; fix the match in Kodi (*Refresh* on the item) or turn the option off.
- Badges depend on Kodi's stream details, which it records only after reading the files.
- Movie versions: JSON-RPC has no version API in Kodi 21, so KScape reads Kodi's own version
  folders (`videodb://movies/videoversions/`). Versions added or removed while a wall is open
  appear at its next full reload (a library scan, Reload library, or after a day). A version on
  an unreachable share fails to play as in Kodi itself (Kodi says so).
- Ultrawide and CinemaScope: the cover walls adapt natively; other screens are scaled into a
  CinemaScope band, so their full-width backgrounds (Home's artwork and bar) become a centred
  16:9 block in it. Auto cannot detect a CinemaScope screen behind a 16:9 signal (nothing in the
  signal says so). A change of screen resolution while a wall is open applies the next time a
  wall opens. Tested in a windowed test Kodi at 1.56:1 (stretch correction) and with manual 2.39
  bands; not on a physical ultrawide monitor or projector.
- Kodi loads a cover's artwork once: if the download fails (a network hiccup), it stays blank.
  The cover wall checks, while idle, which covers on screen are still missing from Kodi's
  texture cache and asks for them again, up to six times, further apart each time. Covers in
  Kodi's own lists (Home cards, list view) are left to Kodi.
- Quitting Kodi while a library scan runs waits for the scan to stop: with network shares that
  answer slowly (a server name that does not always resolve), that can take a long while and
  looks like a freeze. It is Kodi's own behaviour, with any skin; see *Library update on
  startup* in Kodi's media settings.
- Tested on macOS with Kodi 21.3 at 1080p, with a real 757-movie library, a synthetic
  5,000-movie library, and the generated 30-album / 5-show test library (ranking and placement for 5,000 movies take about 55 ms on the
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
- A key press during a camera glide may show a one-frame jump; not observed, not ruled out.
- The reference video used to match the motion is kept out of the repository.

## License

KScape is released under the [MIT License](LICENSE); a copy ships inside each add-on
(`LICENSE.txt`). Kodi itself, and artwork and metadata from your library, keep their own licenses.

**Exception:** two skin files closely follow the control layout of Kodi's Estuary skin (by phil65 /
Team Kodi, code licensed GPL-2.0), so they are distributed under the
[GNU General Public License v2](LICENSES/GPL-2.0.txt) instead of MIT:

- [`skin.kscape/1080i/DialogKeyboard.xml`](skin.kscape/1080i/DialogKeyboard.xml) (on-screen keyboard)
- [`skin.kscape/1080i/DialogNumeric.xml`](skin.kscape/1080i/DialogNumeric.xml) (number pad)

Each carries a GPL-2.0 notice at the top, and the GPL text ships in the skin as
`LICENSES/GPL-2.0.txt`. Everything else is MIT. The skin manifest declares this as
`MIT AND GPL-2.0-only`.
