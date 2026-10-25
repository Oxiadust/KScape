"""Movie info screen: a large panel that slides up over the wall or list (WindowXMLDialog).

Shows the poster, a Return / Resume / Play / Trailer / Play Scenes / Explore menu, and on the
right one of three pages:

- the movie's facts: synopsis, then runtime, aspect ratio, country and year with resolution,
  dynamic range and audio badges, the ratings (certificate, TMDB, Rotten Tomatoes), genres,
  cast, director and collection;
- Explore: Related Movies, the movie's collection, director, cast, genres, year and country -
  Select on one closes the screen and shows the library filtered by it (explore.py);
- Play Scenes: Play All Scenes, the movie's scenes with their lengths (favourites marked), and
  Create scene… / Import chapters…; C on a scene edits, renames, marks it favourite, adds it to
  a Demo Script or deletes it;
- Cast & Crew: directors, writers and the cast with their portraits; Select opens a person
  (profile.py: biography, their movies in the library);
- Details: every field Kodi has (original title, tagline, studios, languages, ratings, IDs...) and,
  with a TMDB or OMDb key, budget, box office, production companies and awards (metadata.py).

Play Extra, Choose Art and Refresh follow Play Scenes: Kodi's own art and refresh functions
(actions.py), and the trailers, featurettes and other extras found beside the movie.

Right (or Select) on a page entry opens its page; Left or Back returns to the menu.
The dialog only reports what was chosen; the caller closes it and starts playback, so the video
never plays underneath an open dialog.

Kodi gives scripts no way to measure text, so the facts page is laid out from estimated line
counts (info.estimate_lines); the synopsis scrolls if it is longer than its box.
"""
import threading

import xbmcaddon
import xbmcgui

from . import actions as A
from . import badges, collectionmodel as C, collectionui, displayui, info, menu, metadata, modal, people, ratings
from . import profile as PF
from . import s as ST
from . import explore as E
from . import exploreui as X
from . import scenemodel as SM
from . import scenes as S
from . import streaminfo as SI
from . import versions as VS
from .library import fetch_details, fresh_resume, version_settings
from .listmodel import rating_short

ADDON = xbmcaddon.Addon('script.kscape.wall')
BACK = (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU)
PLAY = (xbmcgui.ACTION_PLAYER_PLAY,)
CONTEXT = (xbmcgui.ACTION_CONTEXT_MENU,)
RIGHT = (xbmcgui.ACTION_MOVE_RIGHT,)
UP_DOWN = (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN, xbmcgui.ACTION_PAGE_UP, xbmcgui.ACTION_PAGE_DOWN)

MENU = 100
POSTER_CARD, POSTER_TEXT, POSTER_ART, POSTER_BADGE = 151, 152, 153, 154
EXPLORE_LIST, SCENE_LIST, CAST_LIST, DETAILS_LIST, COLLECT_LIST = 310, 410, 510, 610, 710
PAGE_KEYS = ('explore', 'scenes', 'cast', 'details', 'collections')
PAGE_LISTS = (EXPLORE_LIST, SCENE_LIST, CAST_LIST, DETAILS_LIST, COLLECT_LIST)
FACTS, RES_BADGE, HDR_BADGE, AUDIO_BADGE = 270, 272, 273, 274
MORE_FORMATS = (275, 276, 277)          # further formats of other versions
RATINGS_HEAD, RATINGS, TMDB_ICON, RT_ICON = 280, 285, 287, 289
SECTIONS = [  # (heading control, value control, string id, key)
    (220, 221, 32061, 'plot'),
    (230, 231, 32062, 'genre'),
    (240, 241, 32063, 'cast'),
    (250, 251, 32064, 'director'),
    (260, 261, 32065, 'set'),
]
S_RATINGS = 32339
DIM = 'FF9AB4E6'

# Layout, in panel pixels (see script-kscape-info.xml).
TOP, BOTTOM = 88, 954
BODY_PX, LINE_H = 29, 38
TEXT_W = 1150                  # synopsis width
VALUE_W = 910                  # values beside a heading
HEADING_H = 44
FACT_H = 44                    # the facts / badges line and the ratings line
SECTION_GAP = 26
ROW_GAP = 18
MENU_ROW = 52
POSTER_X, POSTER_Y, POSTER_W, POSTER_H = 30, 88, 420, 630


def tr(string_id):
    return ADDON.getLocalizedString(string_id)


class DetailsDialog(xbmcgui.WindowXMLDialog):

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.movie = kwargs['movie']
        self.details = kwargs.get('details') or {}
        self.favs = kwargs.get('favs')
        self.library = kwargs.get('library')       # the movies Explore filters (counts), if known
        self.start_page = kwargs.get('page')
        self.start_focus = kwargs.get('focus')     # scene id to select on the Play Scenes page
        self.resolver = kwargs.get('resolver') or X.Resolver()
        self.choice = None
        self.extra = {}
        self.page = ''
        self.explore_filters = []
        self.scene_rows = []
        self.cast_people = []
        self.collection_rows = []       # (kind, id) per Collections row; None for a heading
        self.meta = {}                  # budget, revenue... from a provider (metadata.py)
        self.closed = False
        self.store = collectionui.store(type('Kind', (), {'name': 'movies'}))
        # On a screen of another shape, Kodi stretches boxes but not text or artwork: boxes that
        # must keep a shape (the poster, badges) have their widths divided by the stretch.
        self.sx = displayui.current().sx
        m = self.movie
        # Kodi's versions with their resume points as they are now, in the order Play tries them.
        self.versions = fresh_resume(m.versions, m.title) if m.versions else ()
        self.pref = version_settings() if self.versions else ('4K', False)
        self.playing = VS.choose(self.versions, *self.pref) if self.versions else None

    def onInit(self):
        m, d = self.movie, self.details
        self.setProperty('title', d.get('title') or m.title)
        self._mark_favourite()
        self.setProperty('poster', m.poster)
        self.setProperty('badge', m.badge)
        self._layout()
        self._fill_menu()
        self._ask_provider()
        if self.start_page == 'explore':
            self._open_explore()
        elif self.start_page == 'scenes':
            self._open_scenes(self.start_focus)
        else:
            self.setFocusId(MENU)

    # ---- menu and poster ----------------------------------------------------------------------

    def _fill_menu(self, select=None):
        m, d = self.movie, self.details
        items = [('return', tr(32066), '')]
        resume = ((d.get('resume') or {}).get('position') or m.resume_position or 0)
        if self.versions:
            paused = VS.choose(self.versions, *self.pref, resume=True)
            resume = paused.resume if paused else 0
        if resume > 0:
            items.append(('resume', tr(32067), info.clock(resume)))
        items.append(('play', tr(32068), ''))
        if len(self.versions) > 1:
            items.append(('version', tr(32367), tr(32368).format(len(self.versions))))
        if d.get('trailer'):
            items.append(('trailer', tr(32069), ''))
        if m.file:
            items.append(('scenes', tr(32301), '▶'))
        items += [('extra', tr(ST.PLAY_EXTRA), ''), ('art', tr(ST.CHOOSE_ART), ''), ('refresh', tr(ST.REFRESH), '')]
        items.append(('collections', tr(collectionui.S_COLLECTIONS), '▶'))
        items.append(('cast', tr(ST.CAST), '▶'))
        items.append(('details', tr(ST.DETAILS), '▶'))
        items.append(('explore', tr(32300), '▶'))
        menu_ctl = self.getControl(MENU)
        self._size_poster(POSTER_H)               # the menu's own size is fixed in the XML (4 rows)
        menu_ctl.reset()
        listitems = []
        for key, label, label2 in items:
            li = xbmcgui.ListItem(label, label2)
            li.setProperty('action', key)
            listitems.append(li)
        menu_ctl.addItems(listitems)
        keys = [k for k, _, _ in items]
        start = select if select in [k for k, _, _ in items] else (self.start_page if self.start_page in keys else ('resume' if 'resume' in keys else 'play'))
        menu_ctl.selectItem(keys.index(start))

    def _size_poster(self, room):
        h = min(POSTER_H, room)
        w = min(POSTER_W, int(round(h * 2 / 3.0 / self.sx)))
        x = POSTER_X + (POSTER_W - w) // 2
        for cid in (POSTER_CARD, POSTER_ART):
            c = self.getControl(cid)
            c.setPosition(x - POSTER_X, 0)
            c.setWidth(w)
            c.setHeight(h)
        text = self.getControl(POSTER_TEXT)
        text.setPosition(x - POSTER_X + 24, 24)
        text.setWidth(w - 48)
        text.setHeight(h - 48)
        self.getControl(POSTER_BADGE).setPosition(x - POSTER_X + w - 90, h - 42)

    # ---- the facts page -----------------------------------------------------------------------

    def _facts(self):
        """(facts line, resolution, dynamic range, best audio format) from the details, falling
        back on the movie record."""
        m, d = self.movie, self.details
        sd = d.get('streamdetails')
        facts = SI.facts_line(d.get('runtime') or m.runtime, SI.aspect(sd) or m.aspect,
                              d.get('country') or m.country, d.get('year') or m.year)
        res = SI.resolution(sd) if sd else m.resolution
        hdr = SI.hdr(sd) if sd else m.hdr
        audio = (SI.audio_formats(sd) if sd else m.audio)[:1]
        if self.playing:                 # several versions: what Play would start
            hdr, audio = self.playing.hdr, self.playing.audio[:1]
        return facts, res, hdr, audio[0] if audio else ''

    def _set_badges(self):
        facts, res, hdr, audio = self._facts()
        self.setProperty('facts', facts)
        # Every format the movie is available in (all versions); the first takes the usual slot.
        formats = list(VS.formats(self.versions, res, self.movie.stereo, self.movie.file)) or ([res] if res else [])
        res = formats[0] if formats else ''
        for n, cid in enumerate(MORE_FORMATS, start=2):
            key = formats[n - 1] if len(formats) >= n else ''
            self.setProperty(f'b.res{n}', badges.image(key) if key else '')
            if key:
                self.getControl(cid).setWidth(self._w(badges.width(key)))
        for cid, prop, key in ((RES_BADGE, 'b.res', res), (HDR_BADGE, 'b.hdr', hdr), (AUDIO_BADGE, 'b.audio', audio)):
            self.setProperty(prop, badges.image(key) if key else '')
            if key:
                self.getControl(cid).setWidth(self._w(badges.width(key)))
        return bool(facts or res or hdr or audio)

    def _set_ratings(self):
        m, d = self.movie, self.details
        self.setProperty('r.mpaa', rating_short(d.get('mpaa') or m.mpaa))
        tmdb = SI.tmdb_rating(d.get('ratings')) or m.tmdb
        self.setProperty('r.tmdb', f'{tmdb:.1f}' if tmdb else '')
        self.getControl(TMDB_ICON).setWidth(self._w(badges.width('tmdb')))
        self.getControl(RT_ICON).setWidth(self._w(badges.width('rt_fresh')))
        rt = SI.rt_percent(d.get('ratings')) or ratings.lookup(m, self._rt_found)
        self._show_rt(rt)
        return bool(self.getProperty('r.mpaa') or tmdb or rt)

    def _show_rt(self, rt):
        self.setProperty('r.rt', f'{rt}%' if rt else '')
        self.setProperty('r.rticon', badges.image('rt_fresh' if rt >= 60 else 'rt_rotten') if rt else '')

    def _rt_found(self, rt):
        """OMDb answered (ratings.py): show the score if this screen is still open."""
        if not self.closed:
            had = bool(self.getProperty('r.rt') or self.getProperty('r.tmdb') or self.getProperty('r.mpaa'))
            self._show_rt(rt)
            if not had:
                self._layout()

    def _layout(self):
        d = self.details
        values = {
            'plot': ((f'[I]{d["tagline"]}[/I]\n' if d.get('tagline') else '')
                     + (d.get('plot') or self.movie.plot)),
            'genre': ', '.join(d.get('genre') or sorted(self.movie.genres)),
            'cast': ', '.join(info.cast_names(d) if d else self.movie.cast),
            'director': ', '.join(d.get('director') or sorted(self.movie.directors)),
            'set': d.get('set') or '',
        }
        has_facts = self._set_badges()
        has_ratings = self._set_ratings()
        y = TOP

        # Rows below the synopsis come first in the budget; the synopsis gets what is left.
        rows = []
        for heading, value, label, key in SECTIONS[1:]:
            text = values[key]
            lines = min(3, info.estimate_lines(text, VALUE_W, BODY_PX)) if text else 0
            rows.append((heading, value, label, text, lines))
        rows_h = sum(max(1, n) * LINE_H + ROW_GAP for *_, text, n in rows if text)
        rows_h += (FACT_H + ROW_GAP) * (has_facts + has_ratings)

        heading, value, label, key = SECTIONS[0]
        plot = values['plot']
        h_ctl, v_ctl = self.getControl(heading), self.getControl(value)
        if plot:
            room = BOTTOM - y - HEADING_H - SECTION_GAP - rows_h
            lines = max(2, min(info.estimate_lines(plot, TEXT_W, BODY_PX), room // LINE_H))
            h_ctl.setLabel(tr(label))
            h_ctl.setPosition(h_ctl.getX(), y)
            v_ctl.setPosition(v_ctl.getX(), y + HEADING_H)
            v_ctl.setHeight(lines * LINE_H)
            v_ctl.setText(plot)
            y += HEADING_H + lines * LINE_H + SECTION_GAP
        for c in (h_ctl, v_ctl):
            c.setVisible(bool(plot))

        facts = self.getControl(FACTS)
        facts.setVisible(has_facts)
        if has_facts:
            facts.setPosition(facts.getX(), y)
            y += FACT_H + ROW_GAP
        head, line = self.getControl(RATINGS_HEAD), self.getControl(RATINGS)
        for c in (head, line):
            c.setVisible(has_ratings)
        if has_ratings:
            head.setLabel(tr(S_RATINGS))
            head.setPosition(head.getX(), y)
            line.setPosition(line.getX(), y)
            y += FACT_H + ROW_GAP

        for heading, value, label, text, lines in rows:
            h_ctl, v_ctl = self.getControl(heading), self.getControl(value)
            for c in (h_ctl, v_ctl):
                c.setVisible(bool(text) and y + LINE_H <= BOTTOM)
            if not text:
                continue
            lines = max(1, min(lines, (BOTTOM - y) // LINE_H))
            h_ctl.setLabel(tr(label))
            h_ctl.setPosition(h_ctl.getX(), y)
            v_ctl.setPosition(v_ctl.getX(), y)
            v_ctl.setHeight(lines * LINE_H)
            v_ctl.setText(text)
            y += lines * LINE_H + ROW_GAP

    # ---- pages --------------------------------------------------------------------------------

    def _w(self, width):
        return max(1, int(round(width / self.sx)))

    def _set_page(self, page):
        self.page = page
        self.setProperty('page', page)

    def _open_explore(self):
        if not self.explore_filters:
            self._fill_explore()
        self._set_page('explore')
        self.setFocusId(EXPLORE_LIST)

    def _fill_explore(self):
        """Section headings (rows of their own, stepped over) and the movie's filters. How many
        movies each one leaves is worked out afterwards, in the background."""
        items, self.explore_filters = [], []
        library = self.library or ()
        for section, filters in E.explore_sections(self.movie, self.details):
            li = xbmcgui.ListItem('')
            li.setProperty('heading', tr(X.S_SECTION[section]))
            items.append(li)
            self.explore_filters.append(None)
            for f in filters:
                if f.cat == 'related':
                    label = tr(X.S_RELATED_MOVIES)
                elif f.cat == 'set':
                    label = self.details.get('set') or self.movie.setname or X.value_label(f, library)
                else:
                    label = X.value_label(f, library)
                items.append(xbmcgui.ListItem(label))
                self.explore_filters.append(f)
        ctl = self.getControl(EXPLORE_LIST)
        ctl.reset()
        ctl.addItems(items)
        self.explore_pos = 1
        ctl.selectItem(1)
        if self.library is not None:
            threading.Thread(target=self._count_explore, args=(ctl,), daemon=True).start()

    def _count_explore(self, ctl):
        library = self.library
        for i, f in enumerate(list(self.explore_filters)):
            if self.closed:
                return
            if f is None:
                continue
            n = len(E.apply([f], library, library, self.resolver.resolve([f])))
            try:
                ctl.getListItem(i).setLabel2(str(n))
            except RuntimeError:                       # closed meanwhile
                return

    def _skip_headings(self, control_id=EXPLORE_LIST):
        """Up/Down landed on a section heading: go on to the next entry that way (or back)."""
        ctl = self.getControl(control_id)
        rows, attr = ((self.explore_filters, 'explore_pos') if control_id == EXPLORE_LIST
                      else (self.collection_rows, 'collection_pos'))
        pos = ctl.getSelectedPosition()
        last = getattr(self, attr, 1)
        if 0 <= pos < len(rows) and rows[pos] is None:
            step = 1 if pos >= last else -1
            nxt = pos + step
            if not (0 <= nxt < len(rows)) or rows[nxt] is None:
                nxt = last
            ctl.selectItem(nxt)
            pos = nxt
        setattr(self, attr, pos)

    # ---- cast & crew, details, provider data -------------------------------------------------

    def _ask_provider(self):
        """Budget, revenue, companies, original language and awards, if a TMDB / OMDb key is set:
        asked in the background, shown on the Details page when it arrives."""
        ids = self.details.get('uniqueid') or {}
        tmdb = ids.get('tmdb') or ids.get('themoviedb') or ''
        metadata.movie_extra(tmdb, ids.get('imdb') or '', self._provider_found)

    def _provider_found(self, data):
        if self.closed:
            return
        self.meta = data
        if self.page == 'details':
            self._fill_details()

    # ---- collections ---------------------------------------------------------------------------

    def _copy_keys(self):
        """Member keys of the movie and any duplicate copy of it in the library."""
        m = self.movie
        same = [c for c in (self.library or ()) if C.title_key(c) == C.title_key(m)] or [m]
        return collectionui.keys_of(same)

    def _open_collections(self):
        self._fill_collections()
        self._set_page('collections')
        self.setFocusId(COLLECT_LIST)

    def _fill_collections(self, select=None):
        """System collections (Kodi's favourites, played) and the user's own, each with a tick;
        headings are rows of their own, stepped over."""
        self.store.poll()
        keys = self._copy_keys()
        rows = []

        def heading(text):
            li = xbmcgui.ListItem('')
            li.setProperty('heading', text)
            rows.append((None, None, li))

        def entry(kind, cid, label, ticked=None):
            li = xbmcgui.ListItem(label)
            if ticked is not None:
                li.setProperty('check', '1' if ticked else '')
                li.setProperty('box', '1')
            rows.append((kind, cid, li))

        heading(tr(collectionui.S_SYSTEM))
        if self.favs is not None and self.favs.supports(self.movie):
            entry('fav', '', tr(32187), self.favs.contains(self.movie))
        entry('played', '', tr(32153), bool(self.details.get('playcount')))
        heading(tr(collectionui.S_YOURS))
        for c in self.store.items:
            entry('c', c['id'], c['name'], self.store.contains(c['id'], keys))
        entry('new', '', tr(collectionui.S_CREATE))
        self.collection_rows = [(k, cid) if k else None for k, cid, _ in rows]
        ctl = self.getControl(COLLECT_LIST)
        keep = select if select is not None else max(1, ctl.getSelectedPosition())
        ctl.reset()
        ctl.addItems([li for _, _, li in rows])
        pos = min(keep, len(rows) - 1)
        if self.collection_rows[pos] is None:
            pos += 1
        ctl.selectItem(pos)
        self.collection_pos = pos

    def _collection_clicked(self):
        ctl = self.getControl(COLLECT_LIST)
        i = ctl.getSelectedPosition()
        if not 0 <= i < len(self.collection_rows) or self.collection_rows[i] is None:
            return
        kind, cid = self.collection_rows[i]
        if kind == 'fav':
            self.favs.toggle(self.movie)
            self._mark_favourite()
        elif kind == 'played':
            played = bool(self.details.get('playcount'))
            A.set_watched('movie', self.movie.movieid, not played)
            self.details = dict(self.details, playcount=0 if played else 1)
        elif kind == 'c':
            keys = self._copy_keys()
            if self.store.contains(cid, keys):
                self.store.remove(cid, keys)
            else:
                self.store.add(cid, C.member_key(self.movie))
        elif kind == 'new':
            new = collectionui.create(self.store)
            if new:
                self.store.add(new, C.member_key(self.movie))
                i = len(self.collection_rows) - 1
        self._fill_collections(i)

    def _open_cast(self):
        if not self.cast_people:
            self._fill_cast()
        self._set_page('cast')
        self.setFocusId(CAST_LIST)

    def _fill_cast(self):
        self.cast_people = people.cast_rows(self.details, tr)
        items = []
        for r in self.cast_people:
            li = xbmcgui.ListItem(r['name'], people.person_summary(r, tr))
            if r['thumb']:
                li.setArt({'thumb': r['thumb']})
            li.setProperty('initial', ''.join(w[0] for w in r['name'].split()[:2]).upper())
            items.append(li)
        if not items:
            items.append(xbmcgui.ListItem(tr(ST.P_NO_CAST)))
        ctl = self.getControl(CAST_LIST)
        ctl.reset()
        ctl.addItems(items)
        ctl.selectItem(0)

    def _person_clicked(self):
        i = self.getControl(CAST_LIST).getSelectedPosition()
        if not 0 <= i < len(self.cast_people):
            return
        choice = PF.show_person(self.cast_people[i])
        if choice and choice[0] == 'movie':
            self.choice, self.extra = 'movie', {'movieid': choice[1]}
            self._close()
        elif choice and choice[0] == 'explore':
            self.choice, self.extra = 'explore', {'filter': choice[1]}
            self._close()

    def _open_details_page(self):
        self._fill_details()
        self._set_page('details')
        self.setFocusId(DETAILS_LIST)

    def _fill_details(self):
        rows = people.movie_rows(self.details, self.meta, tr, metadata.language_name)
        ctl = self.getControl(DETAILS_LIST)
        keep = max(0, ctl.getSelectedPosition())
        items = [xbmcgui.ListItem(tr(label), value) for label, value in rows]
        if not items:
            items = [xbmcgui.ListItem(tr(ST.P_NO_DETAILS))]
        ctl.reset()
        ctl.addItems(items)
        ctl.selectItem(min(keep, len(items) - 1))

    # ---- Play Extra, Choose Art, Refresh ----------------------------------------------------

    def _title(self):
        return self.details.get('title') or self.movie.title

    def _play_extra(self):
        while True:
            extras = A.find_extras(dict(self.details, movieid=self.movie.movieid))
            pick = A.pick_extra(extras)
            if pick == A.MANAGE:                       # Kodi's own manager; then the list again
                A.manage_extras(dict(self.details, movieid=self.movie.movieid))
                continue
            if pick:
                self.choice, self.extra = 'extra', {'file': pick['file'],
                                                    'title': f'{self._title()} - {pick["label"]}'}
                self._close()
            return

    def _choose_art(self):
        if A.choose_art('movie', self.movie.movieid, self._title()):
            self._reload('art')

    def _refresh(self):
        if A.refresh('movie', self.movie.movieid, self._title()):
            self._reload('refresh')

    def _selected_key(self):
        item = self.getControl(MENU).getSelectedItem()
        return item.getProperty('action') if item else None

    def _reload(self, select):
        """The movie changed in Kodi (art, refresh): read it again and redraw this screen."""
        fresh = fetch_details(self.movie.movieid)
        if not fresh:
            return
        self.details = fresh
        poster = (fresh.get('art') or {}).get('poster') or self.movie.poster
        self.setProperty('title', fresh.get('title') or self.movie.title)
        self.setProperty('poster', poster)
        self.cast_people = []
        self.meta = {}
        self.store.poll()
        self._layout()
        self._fill_menu(select)
        self._ask_provider()

    def _open_scenes(self, focus=None):
        self._fill_scenes(focus)
        self._set_page('scenes')
        self.setFocusId(SCENE_LIST)

    def _runtime(self):
        return float(self.details.get('runtime') or self.movie.runtime or 0)

    def _fill_scenes(self, focus=None):
        st = S.store()
        found = st.scenes_of('movie', self.movie.movieid)
        rows = []
        if found:
            total = sum(SM.duration(s) for s in found)
            rows.append(('all', None, tr(32310), SM.clock(total), False))
            rows += [('scene', s['id'], s['name'], SM.clock(SM.duration(s)), bool(s.get('favourite')))
                     for s in found]
        rows.append(('create', None, f'[COLOR {DIM}]{tr(32311)}[/COLOR]', '', False))
        rows.append(('import', None, f'[COLOR {DIM}]{tr(32312)}[/COLOR]', '', False))
        self.scene_rows = rows
        count = S.count_text(len(found), 32213, 32212)
        self.setProperty('scenes.heading', f'{tr(32301)}  ·  {count}' if found else tr(32301))
        self.setProperty('scenes.empty', '' if found else f'{tr(32313)}[CR][COLOR {DIM}]{tr(32314)}[/COLOR]')
        ctl = self.getControl(SCENE_LIST)
        ctl.setPosition(ctl.getX(), 150 if found else 330)
        ctl.reset()
        items = []
        for _, _, label, label2, fav in rows:
            li = xbmcgui.ListItem(label, label2)
            if fav:
                li.setProperty('fav', '1')
            items.append(li)
        ctl.addItems(items)
        index = next((i for i, r in enumerate(rows) if focus and r[1] == focus), 0)
        ctl.selectItem(index)

    def _scene_row(self):
        i = self.getControl(SCENE_LIST).getSelectedPosition()
        return self.scene_rows[i] if 0 <= i < len(self.scene_rows) else None

    def _play_scenes(self, ids, focus):
        self.choice = 'scenes'
        self.extra = {'ids': ids, 'focus': focus}
        self._close()

    def _scene_clicked(self):
        row = self._scene_row()
        if not row:
            return
        action, sid = row[0], row[1]
        if action == 'all':
            self._play_scenes([r[1] for r in self.scene_rows if r[0] == 'scene'], None)
        elif action == 'scene':
            self._play_scenes([sid], sid)
        elif action == 'create':
            new = S.create_scene(S.store(), self.movie, self._runtime())
            self._fill_scenes(new)
        elif action == 'import':
            S.import_chapters(S.store(), self.movie, self._runtime())
            self._fill_scenes()

    # ---- input --------------------------------------------------------------------------------

    def onFocus(self, control_id):
        # Callbacks arrive late: only a focus that is still on the menu closes the page.
        if control_id == MENU and self.page and self.getFocusId() == MENU:
            self._set_page('')

    def onClick(self, control_id):
        if control_id == MENU:
            item = self.getControl(MENU).getSelectedItem()
            key = item.getProperty('action') if item else 'return'
            if key == 'explore':
                self._open_explore()
            elif key == 'scenes':
                self._open_scenes()
            elif key == 'version':
                self._choose_version()
            elif key == 'play' and len(self.versions) > 1:
                self._choose_version()
            elif key == 'resume' and len([v for v in self.versions if v.resume > 0]) > 1:
                self._choose_version(resume_only=True)
            elif key == 'cast':
                self._open_cast()
            elif key == 'details':
                self._open_details_page()
            elif key == 'collections':
                self._open_collections()
            elif key == 'extra':
                self._play_extra()
            elif key == 'art':
                self._choose_art()
            elif key == 'refresh':
                self._refresh()
            else:
                self.choice = None if key == 'return' else key
                self._close()
        elif control_id == EXPLORE_LIST:
            i = self.getControl(EXPLORE_LIST).getSelectedPosition()
            if 0 <= i < len(self.explore_filters) and self.explore_filters[i] is not None:
                self.choice = 'explore'
                self.extra = {'filter': self.explore_filters[i]}
                self._close()
        elif control_id == SCENE_LIST:
            self._scene_clicked()
        elif control_id == CAST_LIST:
            self._person_clicked()
        elif control_id == COLLECT_LIST:
            self._collection_clicked()

    def onAction(self, action):
        aid = action.getId()
        focus = self.getFocusId()
        if aid in UP_DOWN and focus in (EXPLORE_LIST, COLLECT_LIST):
            self._skip_headings(focus)
        elif aid in BACK:
            if focus in PAGE_LISTS:
                self.setFocusId(MENU)                 # onFocus returns to the facts page
                return
            self.choice = None
            self._close()
        elif aid in RIGHT and focus == MENU:
            item = self.getControl(MENU).getSelectedItem()
            key = item.getProperty('action') if item else ''
            if key == 'explore':
                self._open_explore()
            elif key == 'scenes':
                self._open_scenes()
            elif key == 'cast':
                self._open_cast()
            elif key == 'collections':
                self._open_collections()
            elif key == 'details':
                self._open_details_page()
        elif aid in PLAY:
            row = self._scene_row() if focus == SCENE_LIST else None
            if row and row[0] in ('all', 'scene'):
                self._scene_clicked()
                return
            self.choice = 'resume' if self.movie.resume_position > 0 else 'play'
            self._close()
        elif aid in CONTEXT:
            if focus == SCENE_LIST:
                row = self._scene_row()
                if row and row[0] == 'scene':
                    st = S.store()
                    if S.scene_menu(st, row[1]) == 'play':
                        self._play_scenes([row[1]], row[1])
                    else:
                        self._fill_scenes(row[1])
                return
            watched = bool(self.details.get('playcount'))
            choice = menu.show(self.movie, self.favs,
                               [('watched', tr(ST.MARK_UNWATCHED if watched else ST.MARK_WATCHED)),
                                ('rate', tr(ST.RATE))])
            if choice == 'watched':
                A.set_watched('movie', self.movie.movieid, not watched)
                self._reload(self._selected_key())
            elif choice == 'rate':
                if A.rate('movie', self.movie.movieid, self.details.get('userrating'), self._title()) is not None:
                    self._reload(self._selected_key())
            elif choice == 'favourite':
                self.favs.toggle(self.movie)
                self._mark_favourite()
            elif choice == 'search':
                self.choice = 'search'
                self._close()

    def _choose_version(self, resume_only=False):
        """Pick a version (Play Version, and Play Movie / Resume Movie when there are several):
        every version, labelled with its name, resolution, 3D, dynamic range and audio, and where
        it was left off; the one Play would start is preselected. Resume lists only the versions
        with a resume point and resumes the one picked; Play asks whether to resume one that has
        a resume point."""
        order = VS.order(self.versions, *self.pref)
        names = dict(zip(order, VS.labels(order, self._title())))
        if resume_only:
            paused = VS.choose(self.versions, *self.pref, resume=True)
            order = [v for v in order if v.resume > 0]
        rows = [names[v] + (f'  ({tr(32370).format(info.clock(v.resume))})' if v.resume > 0 else '') for v in order]
        start = order.index(paused) if resume_only and paused in order else 0
        i = xbmcgui.Dialog().select(tr(32369), rows, preselect=start)
        if i < 0:
            return
        v = order[i]
        resume = resume_only
        if v.resume > 0 and not resume_only:
            j = xbmcgui.Dialog().contextmenu([tr(32370).format(info.clock(v.resume)), tr(32371)])
            if j < 0:
                return
            resume = j == 0
        self.choice = 'version'
        self.extra = {'version': v, 'resume': resume}
        self._close()

    def _close(self):
        self.closed = True
        self.close()

    def _mark_favourite(self):
        fav = self.favs is not None and self.favs.contains(self.movie)
        self.setProperty('favourite', '1' if fav else '')


def show_details(movie, favs=None, library=None, page=None, focus=None, resolver=None):
    """Open the info screen for `movie` (on its Explore or Play Scenes page if `page` says so).
    Returns (choice, details, extra): choice is 'play', 'resume', 'trailer', 'search' (from the
    C menu), 'explore' (extra['filter']), 'scenes' (extra['ids'] to play, extra['focus']),
    'extra' (extra['file'], extra['title'] to play), 'movie' (extra['movieid']: another movie,
    chosen on a person's screen) or None for Return/Back; details is the GetMovieDetails dict (or None)."""
    details = fetch_details(movie.movieid)
    dialog = DetailsDialog('script-kscape-info.xml', ADDON.getAddonInfo('path'), 'Default', '1080i',
                           movie=movie, details=details, favs=favs, library=library, page=page,
                           focus=focus, resolver=resolver)
    modal.run(dialog)
    choice, extra = dialog.choice, dialog.extra
    del dialog
    return choice, details, extra
