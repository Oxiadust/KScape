"""Generate script.kscape.wall's list view XML from its column model (resources/lib/listmodel.py),
once per media kind: script-kscape-list.xml (movies), -list-music.xml (albums), -list-tv.xml.

Usage: python3 tools/gen_list_xml.py
Control ids:
  9000   fixedlist: one row per movie, the focused row is a tall blue band at a fixed height
  901    never-visible target for the list's edge actions (stops wrap-around at the ends)
  (no id) now-playing chip top right while something plays (tools/np_chip.py)

The window drives the layouts through Home window properties:
  kscape.list.col      focused column key (lighter cell in the band)
  kscape.list.off      horizontal scroll of the columns right of the title (one of scroll_stops)
  kscape.list.settled  '1' once the list has rested briefly: the band then shows the poster and
                       full values; while moving it shows one line per column, as in the reference
  kscape.list.jump     '1' while the list scrolls to a far row (a value step or re-sort): dimmed
  kscape.list.heading  search results: what was searched and how many matched (else empty)
  kscape.list.empty    search results: the no-match message when nothing matched
Item properties: <col>, <col>_full, <col>_mark (line of the ▶ marker), see listmodel.row_values;
poster; fav = '1' for items in Kodi's favourites (amber heart before the title).
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), '..', 'script.kscape.wall')
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from resources.lib import listmodel as L  # noqa: E402
import np_chip
import wrap_display  # noqa: E402

W, H = 1920, 1080
# Rows are laid out wider than the screen: Kodi skips layout controls that start outside the
# item's width, so columns scrolled in from the right would never appear otherwise.
ROW_H = 58
BAND_H = 236
FOCUS_POS = 5
LIST_TOP = 8
TITLE_W = 860                  # title column; the scrolling columns start here
TEXT_X = 244                   # title text (rows and band line up)
BAND_X = 40
POSTER = (62, 14, 138, 207)    # x, y, w, h inside the band (2:3)
SQUARE = (62, 30, 138, 138)    # album cover
HEART = 22                     # favourite marker, left of the title text
HEART_X = TEXT_X - 34

BG = 'kscape_bg'
BAND = 'kscape_blue'
CELL = 'kscape_blue_focus'              # focused column
TITLE_COLOR = 'FFFFFFFF'
ROW_COLORS = {'cast': 'kscape_tint_cast', 'director': 'kscape_tint_director'}
ROW_COLOR = 'kscape_tint_row'
SLIDE_MS = 360
# Band value lines (kscape_list_value, measured in Kodi 21.3 from screenshots of all four lines:
# centre of the first line's capitals, and the line pitch), for the ▶ marker beside the value the
# list is sorted by. The marker is centred in the 20 px gutter left of the values.
LINE0_CY, LINE_PITCH = 72.0, 31.4
MARKER_W, MARKER_H = 12, 15
VALUE_X = 20                   # values start this far into their column


def prop(name):
    return f'Window(Home).Property(kscape.list.{name})'


def is_(name, value):
    return f'String.IsEqual({prop(name)},{value})'


SETTLED = is_('settled', 1)


def row_w(spec):
    return max(W, TITLE_W + sum(c.width for c in spec.columns) + 40)


def scroll_anims(indent, spec):
    out = []
    for stop in L.scroll_stops(spec):
        if stop:
            out.append(f'{indent}<animation effect="slide" start="0,0" end="-{stop},0" time="{SLIDE_MS}" '
                       f'tween="cubic" easing="out" condition="{is_("off", stop)}">Conditional</animation>')
    return '\n'.join(out)


def columns_row(spec):
    offsets = L.column_offsets(spec)
    out = []
    for col in spec.columns:
        out.append(f'''					<control type="label">
						<left>{offsets[col.key] + 20}</left>
						<width>{col.width - 32}</width>
						<height>{ROW_H}</height>
						<aligny>center</aligny>
						<font>kscape_list_row</font>
						<textcolor>{ROW_COLORS.get(col.key, ROW_COLOR)}</textcolor>
						<label>$INFO[ListItem.Property({col.key})]</label>
					</control>''')
    return '\n'.join(out)


def markers(key, x):
    out = []
    for i in range(L.FULL_LINES):
        top = int(round(LINE0_CY + i * LINE_PITCH - MARKER_H / 2))
        out.append(f'''
					<control type="image">
						<left>{x + (VALUE_X - MARKER_W) // 2}</left>
						<top>{top}</top>
						<width>{MARKER_W}</width>
						<height>{MARKER_H}</height>
						<texture colordiffuse="{L.AMBER}">kscape-marker.png</texture>
						<visible>{SETTLED} + String.IsEqual(ListItem.Property({key}_mark),{i})</visible>
						<animation effect="fade" start="0" end="100" time="220">Visible</animation>
					</control>''')
    return ''.join(out)


def columns_band(spec):
    offsets = L.column_offsets(spec)
    out = []
    for col in spec.columns:
        x = offsets[col.key]
        multi = col.key in spec.multi
        full = f'''
					<control type="label">
						<left>{x + 20}</left>
						<top>50</top>
						<width>{col.width - 32}</width>
						<height>{BAND_H - 60}</height>
						<font>kscape_list_value</font>
						<textcolor>FFFFFFFF</textcolor>
						<wrapmultiline>true</wrapmultiline>
						<scroll>false</scroll>
						<label>$INFO[ListItem.Property({col.key}_full)]</label>
						<visible>{SETTLED}</visible>
						<animation effect="fade" start="0" end="100" time="220">Visible</animation>
					</control>''' + markers(col.key, x) if multi else ''
        short_visible = f'\n\t\t\t\t\t\t<visible>!{SETTLED}</visible>' if multi else ''
        out.append(f'''					<control type="image">
						<left>{x}</left>
						<width>{col.width}</width>
						<height>{BAND_H}</height>
						<texture colordiffuse="{CELL}">kscape-white.png</texture>
						<visible>{is_("col", col.key)}</visible>
					</control>
					<control type="label">
						<left>{x + 20}</left>
						<top>14</top>
						<width>{col.width - 32}</width>
						<height>32</height>
						<font>kscape_list_head</font>
						<textcolor>FFFFFFFF</textcolor>
						<label>$ADDON[script.kscape.wall {col.label}]</label>
					</control>
					<control type="label">
						<left>{x + 20}</left>
						<top>50</top>
						<width>{col.width - 32}</width>
						<height>40</height>
						<font>kscape_list_value</font>
						<textcolor>FFFFFFFF</textcolor>
						<scroll>false</scroll>
						<label>$INFO[ListItem.Property({col.key})]</label>{short_visible}
					</control>{full}''')
    return '\n'.join(out)


def heart(top):
    return f'''				<control type="image">
					<left>{HEART_X}</left>
					<top>{top}</top>
					<width>{HEART}</width>
					<height>{HEART}</height>
					<texture colordiffuse="{L.AMBER}">kscape-heart.png</texture>
					<visible>String.IsEqual(ListItem.Property(fav),1)</visible>
				</control>'''


def build(spec):
    px, py, pw, ph = SQUARE if spec.square else POSTER
    ROW_W = row_w(spec)
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERATED by tools/gen_list_xml.py from resources/lib/listmodel.py ({spec.name}). Do not edit by hand. -->
<window>
	<defaultcontrol always="true">9000</defaultcontrol>
	<controls>
		<control type="image">
			<width>{W}</width>
			<height>{H}</height>
			<texture colordiffuse="{BG}">kscape-white.png</texture>
		</control>
		<control type="button" id="901">
			<description>Edge target: never visible, so the list stops at its ends</description>
			<left>-200</left>
			<top>-200</top>
			<width>1</width>
			<height>1</height>
			<texturefocus/>
			<texturenofocus/>
			<visible>false</visible>
		</control>
		<control type="fixedlist" id="9000">
			<left>0</left>
			<top>{LIST_TOP}</top>
			<width>{ROW_W}</width>
			<height>{H - LIST_TOP}</height>
			<onup>901</onup>
			<ondown>901</ondown>
			<onleft>901</onleft>
			<onright>901</onright>
			<focusposition>{FOCUS_POS}</focusposition>
			<animation effect="fade" start="100" end="35" time="90" condition="{is_("jump", 1)}">Conditional</animation>
			<scrolltime tween="cubic" easing="out">200</scrolltime>
			<itemlayout width="{ROW_W}" height="{ROW_H}">
				<control type="group">
					<left>{TITLE_W}</left>
{scroll_anims('					', spec)}
{columns_row(spec)}
				</control>
				<control type="image">
					<width>{TITLE_W}</width>
					<height>{ROW_H}</height>
					<texture colordiffuse="{BG}">kscape-white.png</texture>
				</control>
				<control type="label">
					<left>{TEXT_X}</left>
					<width>{TITLE_W - TEXT_X - 30}</width>
					<height>{ROW_H}</height>
					<aligny>center</aligny>
					<font>kscape_list_row</font>
					<textcolor>{TITLE_COLOR}</textcolor>
					<label>$INFO[ListItem.Label]</label>
				</control>
{heart((ROW_H - HEART) // 2)}
			</itemlayout>
			<focusedlayout width="{ROW_W}" height="{BAND_H}">
				<control type="image">
					<left>{BAND_X}</left>
					<width>{ROW_W - BAND_X}</width>
					<height>{BAND_H}</height>
					<texture colordiffuse="{BAND}">kscape-white.png</texture>
				</control>
				<control type="group">
					<left>{TITLE_W}</left>
{scroll_anims('					', spec)}
{columns_band(spec)}
				</control>
				<control type="image">
					<width>{BAND_X}</width>
					<height>{BAND_H}</height>
					<texture colordiffuse="{BG}">kscape-white.png</texture>
				</control>
				<control type="image">
					<left>{BAND_X}</left>
					<width>{TITLE_W - BAND_X}</width>
					<height>{BAND_H}</height>
					<texture colordiffuse="{BAND}">kscape-white.png</texture>
				</control>
				<control type="image">
					<left>{BAND_X}</left>
					<width>{TITLE_W - BAND_X}</width>
					<height>{BAND_H}</height>
					<texture colordiffuse="{CELL}">kscape-white.png</texture>
					<visible>{is_("col", "title")}</visible>
				</control>
				<control type="group">
					<visible>{SETTLED}</visible>
					<animation effect="fade" start="0" end="100" time="220">Visible</animation>
					<control type="image">
						<left>{px}</left>
						<top>{py}</top>
						<width>{pw}</width>
						<height>{ph}</height>
						<texture colordiffuse="FF1A1A1F">kscape-white.png</texture>
					</control>
					<control type="image">
						<left>{px}</left>
						<top>{py}</top>
						<width>{pw}</width>
						<height>{ph}</height>
						<aspectratio>scale</aspectratio>
						<texture background="true">$INFO[ListItem.Property(poster)]</texture>
					</control>
				</control>
				<control type="label">
					<left>{TEXT_X}</left>
					<top>14</top>
					<width>300</width>
					<height>32</height>
					<font>kscape_list_head</font>
					<textcolor>FFFFFFFF</textcolor>
					<label>$ADDON[script.kscape.wall {spec.title.label}]</label>
				</control>
				<control type="textbox">
					<description>Title, wrapping to a second line (list labels only truncate)</description>
					<left>{TEXT_X}</left>
					<top>46</top>
					<width>{TITLE_W - TEXT_X - 30}</width>
					<height>116</height>
					<font>kscape_list_title</font>
					<textcolor>FFFFFFFF</textcolor>
					<label>$INFO[ListItem.Label]</label>
				</control>
{heart(60)}
			</focusedlayout>
		</control>
		<control type="image">
			<description>Fade the rows into the background at the top and bottom</description>
			<width>{W}</width>
			<height>150</height>
			<texture colordiffuse="{BG}">kscape-fade.png</texture>
		</control>
		<control type="image">
			<top>{H - 190}</top>
			<width>{W}</width>
			<height>190</height>
			<texture colordiffuse="{BG}" flipy="true">kscape-fade.png</texture>
		</control>
		<control type="group">
			<description>Search results: what was searched, and the count</description>
			<visible>!String.IsEmpty({prop('heading')})</visible>
			<control type="image">
				<width>{W}</width>
				<height>96</height>
				<texture colordiffuse="{BG}">kscape-white.png</texture>
			</control>
			<control type="label">
				<left>{TEXT_X}</left>
				<top>20</top>
				<width>{W - TEXT_X - 80}</width>
				<height>56</height>
				<aligny>center</aligny>
				<font>kscape_panel_title</font>
				<textcolor>{L.AMBER}</textcolor>
				<label>$INFO[{prop('heading')}]</label>
			</control>
		</control>
		<control type="label">
			<description>Search results: nothing matched</description>
			<left>260</left>
			<top>460</top>
			<width>1400</width>
			<height>120</height>
			<align>center</align>
			<aligny>center</aligny>
			<font>kscape_title</font>
			<textcolor>FFE6E6EA</textcolor>
			<wrapmultiline>true</wrapmultiline>
			<label>$INFO[{prop('empty')}]</label>
			<visible>!String.IsEmpty({prop('empty')})</visible>
		</control>
{np_chip.chip()}	</controls>
</window>
'''
    return xml


def main():
    for spec in L.SPECS.values():
        out = os.path.join(ROOT, 'resources', 'skins', 'Default', '1080i', spec.xml)
        with open(out, 'w') as f:
            f.write(wrap_display.wrap(build(spec)))   # display & aspect ratio root
        print(f'wrote {out}')


if __name__ == '__main__':
    main()
