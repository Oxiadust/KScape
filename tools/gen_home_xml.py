"""Generate skin.kscape's Home view cards (1080i/Includes_Home.xml).

Usage: python3 tools/gen_home_xml.py

Above the Movies, Music and TV Shows tabs, Home shows a column of 320 x 192 cards, one per view.
Each card is the real view drawn at 1/6 scale from the same geometry the views use
(script.kscape.wall's geometry.py, listmodel.py and tools/gen_list_xml.py), filled live from the
library:

  List        the list view's rows, blue band, poster and columns
  Covers      the cover wall: covers bleeding off every edge, the focused one in the amber frame
              with the blue synopsis panel beside it
  Favourites  the wall dimmed, with the amber heart favourites are marked with
  Now Playing (music) the playing album, title and progress

Kodi clips a container's items to the container, so covers could only bleed off the right and
bottom edges of a panel container. Instead each cover is its own image control whose artwork
comes from a hidden source container (Container(id).ListItemAbsolute(n)); covers cut by the card
edge get a smaller box and keep their visible part (aspectratio scale + align), so the wall
bleeds evenly on all four sides. Frames are solid bars, so their edges stay crisp.

Includes written: KScapeHomeCards (the dimming, the three card columns and their edge target),
KScapeHomeNowPlaying (what is playing, top left of Home).
"""
import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(TOOLS, '..')
sys.path.insert(0, os.path.join(ROOT, 'script.kscape.wall'))
sys.path.insert(0, TOOLS)
from resources.lib import geometry as G  # noqa: E402
from resources.lib import listmodel as L  # noqa: E402
import gen_list_xml as LX  # noqa: E402

S = 320 / 1920.0               # card scale
CARD_W, CARD_H = 320, 192
VOFF = (CARD_H - 1080 * S) / 2  # the 16:9 view sits centred in the slightly taller card
CARD_PITCH = 216
BOTTOM = 952                    # bottom of the lowest card, just above the bar (984)
HAIRLINE = 3                    # unfocused card border
AMBER_T = 16                    # focused card frame, outside the card
AMBER_OUT = 14
MICRO_LINE = 7.5                # line pitch of kscape_micro (6 px)

PANEL_BLUE = 'FF1F5BD3'
CARD_BG = 'FF1A1A1F'
WALL_BG = 'FF060607'

KINDS = [
    # name, tab x, layout, art, list spec, list columns -> info label, band art, extra card
    dict(name='movies', x=120, layout=G.POSTER, art='Art(poster)', spec=L.MOVIES, title='Label',
         cols={'genre': 'Genre', 'cast': 'Writer', 'director': 'Director', 'year': 'Year'},
         path='videodb://movies/titles/', sort='title', body='Plot'),
    dict(name='music', x=440, layout=G.SQUARE, art='Art(thumb)', spec=L.MUSIC, title='Artist',
         cols={'album': 'Label', 'genre': 'Genre', 'year': 'Year'},
         path='musicdb://albums/', sort='artist', body='Artist', nowplaying=True),
    dict(name='tv', x=760, layout=G.POSTER, art='Art(poster)', spec=L.TV, title='Label',
         cols={'genre': 'Genre', 'cast': 'Studio', 'network': 'Studio', 'year': 'Year'},
         path='videodb://tvshows/titles/', sort='title', body='Plot'),
]
IDS = {'movies': 1, 'music': 2, 'tv': 3}     # source containers 904x (list) and 905x (covers)
LIST_IDS = {'movies': 9021, 'music': 9022, 'tv': 9023}


def n(v):
    """Positions to one decimal (Kodi reads fractional positions)."""
    r = round(v, 1)
    return str(int(r)) if r == int(r) else str(r)


def image(x, y, w, h, texture, diffuse='', extra='', ind='\t\t\t\t'):
    d = f' colordiffuse="{diffuse}"' if diffuse else ''
    return (f'{ind}<control type="image">\n{ind}\t<left>{n(x)}</left>\n{ind}\t<top>{n(y)}</top>\n'
            f'{ind}\t<width>{n(w)}</width>\n{ind}\t<height>{n(h)}</height>\n'
            f'{ind}\t<texture{d}>{texture}</texture>\n{extra}{ind}</control>\n')


def label(x, y, w, h, text, font, color, extra='', ind='\t\t\t\t', kind='label'):
    return (f'{ind}<control type="{kind}">\n{ind}\t<left>{n(x)}</left>\n{ind}\t<top>{n(y)}</top>\n'
            f'{ind}\t<width>{n(w)}</width>\n{ind}\t<height>{n(h)}</height>\n{ind}\t<font>{font}</font>\n'
            f'{ind}\t<textcolor>{color}</textcolor>\n{ind}\t<label>{text}</label>\n{extra}{ind}</control>\n')


def bars(x, y, w, h, t, diffuse, ind='\t\t\t\t', extra=''):
    """A hollow frame of four solid bars (crisp at any size, unlike a stretched border texture)."""
    out = ''
    for bx, by, bw, bh in ((x, y, w, t), (x, y + h - t, w, t), (x, y + t, t, h - 2 * t),
                           (x + w - t, y + t, t, h - 2 * t)):
        out += image(bx, by, bw, bh, 'white.png', diffuse, extra, ind)
    return out


def group(content, x=0, y=0, visible=None, ind='\t\t\t'):
    v = f'{ind}\t<visible>{visible}</visible>\n' if visible else ''
    return f'{ind}<control type="group">\n{ind}\t<left>{n(x)}</left>\n{ind}\t<top>{n(y)}</top>\n{v}{content}{ind}</control>\n'


def art_layers(k):
    """Artwork drawn bottom to top: the thumb under the poster, so an item without a poster
    still shows its thumb (as the views fall back)."""
    return ['Art(thumb)', k['art']] if k['art'] != 'Art(thumb)' else ['Art(thumb)']


def item(src, i, info):
    return f'$INFO[Container({src}).ListItemAbsolute({i}).{info}]'


def has(src, i):
    return f'Integer.IsGreater(Container({src}).NumItems,{i})'


# ---- the cover wall ----------------------------------------------------------------------------

def wall_cells(lay, panel):
    """(x, y, w, h, align, aligny, index) of every cover visible on the card, the focused cover
    (index 0) centred, as the wall centres the camera on it. Cells under the panel are skipped."""
    cw, ch = lay.cover_w * S, lay.cover_h * S
    px, py = lay.pitch_x * S, lay.pitch_y * S
    fx, fy = CARD_W / 2 - cw / 2, CARD_H / 2 - ch / 2
    cells = []
    for r in range(-4, 5):
        for c in range(-7, 8):
            if panel and r == 0 and -lay.panel_cells <= c <= -1:
                continue
            x, y = fx + c * px, fy + r * py
            x0, y0, x1, y1 = max(0, x), max(0, y), min(CARD_W, x + cw), min(CARD_H, y + ch)
            if x1 - x0 < 2 or y1 - y0 < 2:
                continue
            align = 'right' if x < 0 else ('left' if x + cw > CARD_W else 'center')
            aligny = 'bottom' if y < 0 else ('top' if y + ch > CARD_H else 'center')
            cells.append((x0, y0, x1 - x0, y1 - y0, align, aligny, abs(c) + abs(r) * 0.5, (c, r)))
    # Index 0 is the focused cover; the rest by distance, so a small library fills the middle.
    cells.sort(key=lambda t: (t[7] != (0, 0), t[6], t[7][1], t[7][0]))
    return [(x, y, w, h, a, ay, i) for i, (x, y, w, h, a, ay, _, _) in enumerate(cells)], (fx, fy, cw, ch)


def covers(k, src, panel=True, dim=False):
    lay = k['layout']
    cells, (fx, fy, cw, ch) = wall_cells(lay, panel)
    out = image(0, 0, CARD_W, CARD_H, 'white.png', WALL_BG)
    tint = '60FFFFFF' if dim else ''
    for x, y, w, h, align, aligny, i in cells:
        cover = image(x, y, w, h, 'white.png', CARD_BG, ind='\t\t\t\t\t')
        art = f'\t\t\t\t\t\t<aspectratio align="{align}" aligny="{aligny}">scale</aspectratio>\n'
        d = f' colordiffuse="{tint}"' if tint else ''
        for a in art_layers(k):
            cover += (f'\t\t\t\t\t<control type="image">\n\t\t\t\t\t\t<left>{n(x)}</left>\n\t\t\t\t\t\t<top>{n(y)}</top>\n'
                      f'\t\t\t\t\t\t<width>{n(w)}</width>\n\t\t\t\t\t\t<height>{n(h)}</height>\n{art}'
                      f'\t\t\t\t\t\t<texture background="true"{d}>{item(src, i, a)}</texture>\n\t\t\t\t\t</control>\n')
        out += f'\t\t\t\t<control type="group">\n\t\t\t\t\t<visible>{has(src, i)}</visible>\n{cover}\t\t\t\t</control>\n'
    if panel:
        fr = max(3.0, lay.frame * S)
        pw = lay.panel_cells * lay.pitch_x * S - fr
        x, y, h = fx - lay.panel_cells * lay.pitch_x * S, fy - fr, ch + 2 * fr
        body = 'textbox' if k['body'] == 'Plot' else 'label'
        out += group(image(0, 0, pw, h, 'white.png', PANEL_BLUE)
                     + label(5, fr + 3, pw - 10, 11, item(src, 0, 'Label'), 'kscape_tiny_bold', 'FFFFFFFF')
                     + label(5, fr + 16, pw - 10, MICRO_LINE * int((h - fr - 20) // MICRO_LINE), item(src, 0, k['body']), 'kscape_micro',
                             'FFF0F4FF', kind=body),
                     x, y, has(src, 0), ind='\t\t\t\t')
        out += group(bars(0, 0, cw + 2 * fr, ch + 2 * fr, fr, 'kscape_amber', ind='\t\t\t\t\t'),
                     fx - fr, fy - fr, has(src, 0), ind='\t\t\t\t')
    if dim:
        out += image(CARD_W / 2 - 34, CARD_H / 2 - 34, 68, 68, 'heart.png', 'kscape_amber')
    return out


# ---- the list view -----------------------------------------------------------------------------

def list_rows(k, src, band):
    """The list at 1/6 scale with item `band` under the band and the items before it above."""
    spec = k['spec']
    row_h, band_h = LX.ROW_H * S, LX.BAND_H * S
    top = VOFF + LX.LIST_TOP * S
    title_x, title_w = LX.TEXT_X * S, LX.TITLE_W * S
    offsets = L.column_offsets(spec)
    cols = [(title_w + offsets[c.key] * S + 20 * S, c.width * S - 32 * S, k['cols'][c.key]) for c in spec.columns
            if c.key in k['cols'] and title_w + offsets[c.key] * S < CARD_W]

    def row(i, y, color='FFE6EAF2'):
        out = label(title_x, y, title_w - title_x - 4, row_h, item(src, i, k['title']), 'kscape_micro', color,
                    ind='\t\t\t\t\t')
        for x, w, info in cols:
            out += label(x, y, min(w, CARD_W - x), row_h, item(src, i, info), 'kscape_micro', 'FFA9C6FF',
                         ind='\t\t\t\t\t')
        return f'\t\t\t\t<control type="group">\n\t\t\t\t\t<visible>{has(src, i)}</visible>\n{out}\t\t\t\t</control>\n'

    out = ''
    for j in range(band):
        out += row(j, top + (LX.FOCUS_POS - band + j) * row_h)
    by = top + LX.FOCUS_POS * row_h
    bx = LX.BAND_X * S
    px, py, pw, ph = (LX.SQUARE if spec.square else LX.POSTER)
    b = image(bx, by, CARD_W - bx, band_h, 'white.png', LX.BAND, ind='\t\t\t\t\t')
    b += image(bx, by, title_w - bx, band_h, 'white.png', LX.CELL, ind='\t\t\t\t\t')
    b += image(px * S, by + py * S, pw * S, ph * S, 'white.png', CARD_BG, ind='\t\t\t\t\t')
    for a in art_layers(k):
        b += (f'\t\t\t\t\t<control type="image">\n\t\t\t\t\t\t<left>{n(px * S)}</left>\n\t\t\t\t\t\t<top>{n(by + py * S)}</top>\n'
              f'\t\t\t\t\t\t<width>{n(pw * S)}</width>\n\t\t\t\t\t\t<height>{n(ph * S)}</height>\n'
              f'\t\t\t\t\t\t<aspectratio>scale</aspectratio>\n'
              f'\t\t\t\t\t\t<texture background="true">{item(src, band, a)}</texture>\n\t\t\t\t\t</control>\n')
    b += label(title_x, by + 6, title_w - title_x - 4, 10, item(src, band, k['title']), 'kscape_tiny_bold',
               'FFFFFFFF', ind='\t\t\t\t\t')
    for x, w, info in cols:
        b += label(x, by + 8, min(w, CARD_W - x), band_h - 10, item(src, band, info), 'kscape_micro_bold',
                   'FFFFFFFF', ind='\t\t\t\t\t')
    out += f'\t\t\t\t<control type="group">\n\t\t\t\t\t<visible>{has(src, band)}</visible>\n{b}\t\t\t\t</control>\n'
    y, i = by + band_h, band + 1
    while y + row_h <= CARD_H - 2:
        out += row(i, y)
        y += row_h
        i += 1
    return out


def list_card(k, src):
    out = image(0, 0, CARD_W, CARD_H, 'white.png', 'kscape_bg')
    # Rows above the band when the library has them (as in the middle of the list); a short
    # library shows its first item under the band, like the list does when it opens at the top.
    out += group(list_rows(k, src, 5), visible=has(src, 5), ind='\t\t\t\t')
    out += group(list_rows(k, src, 0), visible=f'!{has(src, 5)}', ind='\t\t\t\t')
    out += image(0, 0, CARD_W, 150 * S, 'fade.png', 'kscape_bg')
    out += image(0, CARD_H - 190 * S, CARD_W, 190 * S, 'fade.png', 'kscape_bg',
                 extra='').replace('<texture colordiffuse="kscape_bg">', '<texture colordiffuse="kscape_bg" flipy="true">')
    return out


NOW_PLAYING_CARD = '''				<control type="image">
					<width>320</width>
					<height>192</height>
					<texture colordiffuse="kscape_bg">white.png</texture>
				</control>
				<control type="group">
					<visible>Player.HasAudio</visible>
					<control type="image">
						<left>14</left>
						<top>14</top>
						<width>120</width>
						<height>120</height>
						<texture colordiffuse="FF1A1A1F">white.png</texture>
					</control>
					<control type="image">
						<left>14</left>
						<top>14</top>
						<width>120</width>
						<height>120</height>
						<aspectratio>scale</aspectratio>
						<texture background="true">$INFO[Player.Art(thumb)]</texture>
					</control>
					<control type="textbox">
						<left>146</left>
						<top>14</top>
						<width>162</width>
						<height>66</height>
						<font>kscape_small</font>
						<textcolor>white</textcolor>
						<label>$INFO[MusicPlayer.Title]</label>
					</control>
					<control type="label">
						<left>146</left>
						<top>86</top>
						<width>162</width>
						<height>24</height>
						<font>kscape_badge</font>
						<textcolor>kscape_text_dim</textcolor>
						<label>$INFO[MusicPlayer.Artist]</label>
					</control>
					<control type="progress">
						<left>14</left>
						<top>154</top>
						<width>292</width>
						<height>6</height>
						<texturebg colordiffuse="kscape_blue_dark">white.png</texturebg>
						<midtexture colordiffuse="kscape_amber">white.png</midtexture>
						<info>Player.Progress</info>
					</control>
				</control>
				<control type="label">
					<width>320</width>
					<height>192</height>
					<align>center</align>
					<aligny>center</aligny>
					<font>kscape_small</font>
					<textcolor>kscape_text_off</textcolor>
					<label>$LOCALIZE[31054]</label>
					<visible>!Player.HasAudio</visible>
				</control>
'''


def sources(k):
    """Hidden source containers: on screen (off to the left) because Kodi only fills visible
    containers; never focusable."""
    i = IDS[k['name']]
    out = ''
    for cid, sort, limit in ((9040 + i, k['sort'], 30), (9050 + i, 'random', 80)):
        out += f'''			<control type="list" id="{cid}">
				<left>-4000</left>
				<width>10</width>
				<height>10</height>
				<scrolltime>0</scrolltime>
				<itemlayout width="10" height="10"/>
				<focusedlayout width="10" height="10"/>
				<content sortby="{sort}" limit="{limit}">{k["path"]}</content>
			</control>
'''
    return out


def card_list(k, top, count):
    lid = LIST_IDS[k['name']]
    views = [('31050', 'list'), ('31051', 'covers'), ('31052', 'favorites')]
    if k.get('nowplaying'):
        views.append(('31053', 'nowplaying'))
    content = ''.join(f'''
					<item>
						<label>$LOCALIZE[{sid}]</label>
						<onclick>RunScript(script.kscape.wall,{k["name"]},{view})</onclick>
					</item>''' for sid, view in views)
    # Kodi clips a container's items to the container, so the list starts AMBER_OUT further left
    # and up than the cards and everything in an item is shifted back by as much: the amber frame
    # round the selected card then lies wholly inside the list and is drawn on every side.
    o = AMBER_OUT
    thin = bars(o, o, CARD_W, CARD_H, HAIRLINE, 'kscape_blue_focus', ind='\t\t\t\t\t')
    thin_unfocused = bars(o, o, CARD_W, CARD_H, HAIRLINE, 'kscape_blue_focus', ind='\t\t\t\t\t\t')
    amber = bars(0, 0, CARD_W + 2 * o, CARD_H + 2 * o, AMBER_T, 'kscape_amber', ind='\t\t\t\t\t\t')
    lab = lambda color, ind: label(o + 352, o, 540, CARD_H, '$INFO[ListItem.Label]', 'kscape_list_title', color,
                                   extra=f'{ind}\t<aligny>center</aligny>\n', ind=ind)
    return f'''			<control type="list" id="{lid}">
				<left>{k["x"] - o}</left>
				<top>{top - o}</top>
				<width>{900 + o}</width>
				<height>{count * CARD_PITCH + 2 * o}</height>
				<orientation>vertical</orientation>
				<onup>9029</onup>
				<ondown>9000</ondown>
				<onleft>9029</onleft>
				<onright>9029</onright>
				<onback>9000</onback>
				<scrolltime>0</scrolltime>
				<itemlayout width="{900 + o}" height="{CARD_PITCH}">
{thin}{lab('kscape_text', chr(9) * 5)}				</itemlayout>
				<focusedlayout width="{900 + o}" height="{CARD_PITCH}">
					<control type="group">
						<visible>!Control.HasFocus({lid})</visible>
{thin_unfocused}					</control>
					<control type="group">
						<description>The cover wall's amber frame round the selected card</description>
						<visible>Control.HasFocus({lid})</visible>
						<animation effect="zoom" start="96" end="100" center="{160 + o},{96 + o}" time="200" tween="back" easing="out">Visible</animation>
{amber}					</control>
{lab('white', chr(9) * 5)}				</focusedlayout>
				<content>{content}
				</content>
			</control>
'''


def stack(k):
    i = IDS[k['name']]
    count = 4 if k.get('nowplaying') else 3
    top = BOTTOM - CARD_H - (count - 1) * CARD_PITCH
    x = k['x']
    cards = [list_card(k, 9040 + i), covers(k, 9050 + i), covers(k, 9050 + i, panel=False, dim=True)]
    if k.get('nowplaying'):
        cards.append(NOW_PLAYING_CARD)
    body = sources(k)
    for j, c in enumerate(cards):
        body += group(c, x, top + j * CARD_PITCH)
    body += card_list(k, top, count)
    title = {'movies': 'Movies', 'music': 'Music', 'tv': 'TV Shows'}[k['name']]
    return f'''		<control type="group">
			<description>{title}: view cards above the tab</description>
			<visible>String.IsEqual(Container(9000).ListItem.Property(id),{k["name"]}) + System.AddonIsEnabled(script.kscape.wall)</visible>
			<animation effect="fade" start="0" end="100" time="220">Visible</animation>
			<animation effect="slide" start="0,40" end="0,0" time="260" tween="cubic" easing="out">Visible</animation>
			<animation effect="fade" start="100" end="0" time="150">Hidden</animation>
{body}		</control>
'''


NOW_PLAYING = '''	<!-- What is playing, top left of Home (the clock is top right). -->
	<include name="KScapeHomeNowPlaying">
		<definition>
			<control type="group">
				<left>80</left>
				<top>40</top>
				<visible>Player.HasMedia</visible>
				<animation effect="fade" start="0" end="100" time="300">Visible</animation>
				<animation effect="fade" start="100" end="0" time="200">Hidden</animation>
				<control type="image">
					<width>112</width>
					<height>112</height>
					<texture colordiffuse="FF1A1A1F">white.png</texture>
					<visible>Player.HasAudio</visible>
				</control>
				<control type="image">
					<width>112</width>
					<height>112</height>
					<aspectratio>scale</aspectratio>
					<texture background="true">$INFO[Player.Art(thumb)]</texture>
					<visible>Player.HasAudio</visible>
				</control>
				<control type="image">
					<left>18</left>
					<width>75</width>
					<height>112</height>
					<texture colordiffuse="FF1A1A1F">white.png</texture>
					<visible>Player.HasVideo</visible>
				</control>
				<control type="image">
					<left>18</left>
					<width>75</width>
					<height>112</height>
					<aspectratio>scale</aspectratio>
					<texture background="true">$VAR[KScapePlayerPoster]</texture>
					<visible>Player.HasVideo</visible>
				</control>
				<control type="label">
					<left>132</left>
					<top>0</top>
					<width>620</width>
					<height>28</height>
					<font>kscape_list_head</font>
					<textcolor>kscape_amber</textcolor>
					<label>$VAR[KScapePlayerState]</label>
				</control>
				<control type="label">
					<left>132</left>
					<top>28</top>
					<width>620</width>
					<height>40</height>
					<font>kscape_sub</font>
					<textcolor>white</textcolor>
					<label>$INFO[Player.Title]</label>
				</control>
				<control type="label">
					<left>132</left>
					<top>66</top>
					<width>620</width>
					<height>30</height>
					<font>kscape_small</font>
					<textcolor>kscape_text_dim</textcolor>
					<label>$VAR[KScapePlayerSubtitle]</label>
				</control>
				<control type="progress">
					<left>132</left>
					<top>102</top>
					<width>420</width>
					<height>6</height>
					<texturebg colordiffuse="kscape_blue_dark">white.png</texturebg>
					<midtexture colordiffuse="kscape_amber">white.png</midtexture>
					<info>Player.Progress</info>
				</control>
				<control type="label">
					<left>566</left>
					<top>90</top>
					<width>186</width>
					<height>28</height>
					<font>kscape_badge</font>
					<textcolor>kscape_text_dim</textcolor>
					<label>$INFO[Player.Time]$INFO[Player.Duration, / ]</label>
				</control>
			</control>
		</definition>
	</include>
	<variable name="KScapePlayerState">
		<value condition="Player.Paused">$LOCALIZE[31056]</value>
		<value>$LOCALIZE[31055]</value>
	</variable>
	<variable name="KScapePlayerSubtitle">
		<value condition="Player.HasAudio">$INFO[MusicPlayer.Artist]$INFO[MusicPlayer.Album,  ·  ]</value>
		<value condition="VideoPlayer.Content(episodes)">$INFO[VideoPlayer.TVShowTitle]$INFO[VideoPlayer.Season,  ·  S]$INFO[VideoPlayer.Episode,E]</value>
		<value>$INFO[VideoPlayer.Year]</value>
	</variable>
	<variable name="KScapePlayerPoster">
		<value condition="VideoPlayer.Content(episodes) + !String.IsEmpty(Player.Art(tvshow.poster))">$INFO[Player.Art(tvshow.poster)]</value>
		<value condition="!String.IsEmpty(Player.Art(poster))">$INFO[Player.Art(poster)]</value>
		<value>$INFO[Player.Art(thumb)]</value>
	</variable>
'''


def main():
    stacks = ''.join(stack(k) for k in KINDS)
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERATED by tools/gen_home_xml.py from the views' geometry. Do not edit by hand. -->
<includes>
	<!-- The view cards above Movies / Music / TV Shows: List, Covers, Favourites (and Now Playing
	     for music), each the real view at 1/6 scale. Up from the tab enters the cards; Down from
	     the bottom card or Back returns to the bar. -->
	<include name="KScapeHomeCards">
		<definition>
		<control type="image">
			<description>Darken the artwork while cards show, so the miniatures read</description>
			<width>1920</width>
			<height>1080</height>
			<texture colordiffuse="D8000000">white.png</texture>
			<visible>String.IsEqual(Container(9000).ListItem.Property(hasstack),true) + System.AddonIsEnabled(script.kscape.wall)</visible>
			<animation effect="fade" start="0" end="100" time="220">Visible</animation>
			<animation effect="fade" start="100" end="0" time="150">Hidden</animation>
		</control>
{stacks}		<control type="button" id="9029">
			<description>Edge target: never visible, so the card lists stop at their ends</description>
			<left>-200</left>
			<top>-200</top>
			<width>1</width>
			<height>1</height>
			<texturefocus/>
			<texturenofocus/>
			<visible>false</visible>
		</control>
		</definition>
	</include>

{NOW_PLAYING}</includes>
'''
    out = os.path.join(ROOT, 'skin.kscape', '1080i', 'Includes_Home.xml')
    with open(out, 'w') as f:
        f.write(xml)
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
