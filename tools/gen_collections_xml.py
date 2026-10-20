"""Generate script.kscape.wall's Collections view XML: script-kscape-collections.xml (2:3
posters: movies, TV shows) and script-kscape-collections-square.xml (album covers).

Usage: python3 tools/gen_collections_xml.py
Layout after the Kaleidescape collections screen (prompts/assets/collections.png): a tab bar of
collections along the bottom, the selected collection's movies on the left with the focused one
in a tall blue band fading out to the right, its poster on the right.

Control ids:
  9100   tab bar (horizontal list): one tab per collection, New / Paused / Played first
  9200   the collection's movies (fixedlist), the focused one in the band
  901    never-visible target for edge actions (lists stop at their ends)

Window properties (CollectionsWindow sets them):
  heading, count, kindlabel   the selected collection's name, "N movies", built in or yours
  preview0..3, previews       posters of its first movies, and how many there are (0..4)
  empty                       what to do when it is empty
  moving                      '1' while a movie is carried to a new place (Move)
  status                      loading text
Item properties: tabs - count, builtin, divider (after the last built-in tab); movies - sub (when
added / paused / played), poster, badge, fav.
"""
import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(TOOLS, '..', 'script.kscape.wall')
sys.path.insert(0, TOOLS)
import np_chip
import wrap_display  # noqa: E402

W, H = 1920, 1080
BG = 'kscape_bg'
BAND = 'kscape_blue'
BAND_QUIET = 'kscape_blue_quiet'          # the band while the tab bar has focus
BAR = 'kscape_blue_bar'
TAB_FOCUS = 'kscape_blue_focus'
TAB_HEAD = 'kscape_blue_head'
AMBER = 'kscape_amber'
TEXT = 'kscape_text'
TEXT_DIM = 'kscape_text_dim'
ROW_COLOR = 'kscape_tint_row'
SUB_COLOR = 'kscape_tint_sub'
CARD = 'FF1A1A1F'

TAB_TOP, TAB_H, TAB_W, TAB_LEFT = 984, 96, 300, 60
LIST_TOP, LIST_W, LIST_H = 176, 1240, 808
ROW_H, BAND_H, FOCUS_POS = 54, 168, 3
TEXT_X, SUB_X = 150, 190
BAND_SOLID = 620                  # the band is solid this far, then fades out to LIST_W
POSTER = (1310, 150, 540, 810)    # x, y, w, h (2:3), below the now-playing chip
SQUARE = (1310, 200, 540, 540)    # album cover


def art_rect(square):
    return SQUARE if square else POSTER
GRID_GAP = 8
HEAD_X, HEAD_Y = TEXT_X, 40
BADGE_W, BADGE_H = 58, 28

LIST_FOCUS = 'Control.HasFocus(9200)'
MOVING = 'String.IsEqual(Window.Property(moving),1)'


def img(x, y, w, h, color, tex='kscape-white.png', extra='', ind='\t\t', flip=False):
    f = ' flipy="true"' if flip else ''
    return (f'{ind}<control type="image">\n{ind}\t<left>{x}</left>\n{ind}\t<top>{y}</top>\n'
            f'{ind}\t<width>{w}</width>\n{ind}\t<height>{h}</height>\n'
            f'{ind}\t<texture colordiffuse="{color}"{f}>{tex}</texture>\n{extra}{ind}</control>\n')


def lab(x, y, w, h, text, font, color, extra='', ind='\t\t', kind='label'):
    return (f'{ind}<control type="{kind}">\n{ind}\t<left>{x}</left>\n{ind}\t<top>{y}</top>\n'
            f'{ind}\t<width>{w}</width>\n{ind}\t<height>{h}</height>\n{ind}\t<font>{font}</font>\n'
            f'{ind}\t<textcolor>{color}</textcolor>\n{ind}\t<label>{text}</label>\n{extra}{ind}</control>\n')


def vis(cond, ind):
    return f'{ind}\t<visible>{cond}</visible>\n'


def fade_anims(ind):
    return (f'{ind}\t<animation effect="fade" start="0" end="100" time="220">Visible</animation>\n'
            f'{ind}\t<animation effect="fade" start="100" end="0" time="160">Hidden</animation>\n')


def band(color, ind):
    """Solid from the left edge, then fading out (kscape-hfade.png) as in the reference."""
    return (img(0, 0, BAND_SOLID, BAND_H, color, ind=ind)
            + img(BAND_SOLID, 0, LIST_W - BAND_SOLID, BAND_H, color, 'kscape-hfade.png', ind=ind))


def heart(x, y, ind):
    return img(x, y, 24, 24, AMBER, 'kscape-heart.png', vis('String.IsEqual(ListItem.Property(fav),1)', ind), ind)


def movie_list():
    i5 = '\t\t\t\t'
    moving_frame = ''.join(img(x, y, w, h, AMBER, ind='\t\t\t\t\t')
                           for x, y, w, h in ((0, 0, LIST_W, 5), (0, BAND_H - 5, LIST_W, 5)))
    return f'''		<control type="fixedlist" id="9200">
			<description>The selected collection's movies</description>
			<left>0</left>
			<top>{LIST_TOP}</top>
			<width>{LIST_W}</width>
			<height>{LIST_H}</height>
			<onup>901</onup>
			<ondown>9100</ondown>
			<onleft>901</onleft>
			<onright>901</onright>
			<focusposition>{FOCUS_POS}</focusposition>
			<movement>{FOCUS_POS}</movement>
			<scrolltime tween="cubic" easing="out">200</scrolltime>
			<itemlayout width="{LIST_W}" height="{ROW_H}">
{lab(TEXT_X, 0, LIST_W - TEXT_X - 80, ROW_H, '$INFO[ListItem.Label]', 'kscape_list_row', ROW_COLOR, f'{i5}<aligny>center</aligny>{chr(10)}', i5)}{heart(TEXT_X - 38, (ROW_H - 24) // 2, i5)}			</itemlayout>
			<focusedlayout width="{LIST_W}" height="{BAND_H}">
				<control type="group">
{vis(LIST_FOCUS, i5)}{band(BAND, i5 + chr(9))}				</control>
				<control type="group">
{vis('!' + LIST_FOCUS, i5)}{band(BAND_QUIET, i5 + chr(9))}				</control>
				<control type="group">
{vis(MOVING, i5)}{moving_frame}				</control>
{lab(TEXT_X, 22, LIST_W - TEXT_X - 120, 62, '$INFO[ListItem.Label]', 'kscape_list_title', 'FFFFFFFF', f'{i5}<scroll>false</scroll>{chr(10)}', i5)}{lab(SUB_X, 88, LIST_W - SUB_X - 120, 40, '$INFO[ListItem.Property(sub)]', 'kscape_list_row', SUB_COLOR, '', i5)}{lab(SUB_X, 126, LIST_W - SUB_X - 120, 32, '$ADDON[script.kscape.wall 32180]', 'kscape_list_head', AMBER, vis(MOVING, i5), i5)}{heart(TEXT_X - 38, 42, i5)}			</focusedlayout>
		</control>
'''


def poster_box(texture, x, y, w, h, ind, badge=False):
    out = img(x, y, w, h, CARD, ind=ind)
    out += (f'{ind}<control type="image">\n{ind}\t<left>{x}</left>\n{ind}\t<top>{y}</top>\n'
            f'{ind}\t<width>{w}</width>\n{ind}\t<height>{h}</height>\n{ind}\t<aspectratio>scale</aspectratio>\n'
            f'{ind}\t<fadetime>160</fadetime>\n{ind}\t<texture background="true">{texture}</texture>\n{ind}</control>\n')
    if badge:
        bx, by = x + w - BADGE_W - 14, y + h - BADGE_H - 14
        cond = '!String.IsEmpty(Container(9200).ListItem.Property(badge))'
        out += (f'{ind}<control type="group">\n{vis(cond, ind)}'
                + img(bx, by, BADGE_W, BADGE_H, AMBER, ind=ind + '\t')
                + img(bx + 2, by + 2, BADGE_W - 4, BADGE_H - 4, 'F0141210', ind=ind + '\t')
                + lab(bx, by, BADGE_W, BADGE_H, '$INFO[Container(9200).ListItem.Property(badge)]', 'kscape_badge',
                      AMBER, f'{ind}\t\t<align>center</align>\n{ind}\t\t<aligny>center</aligny>\n', ind + '\t')
                + f'{ind}</control>\n')
    return out


def right_side(square):
    x, y, w, h = art_rect(square)
    gw, gh = (w - GRID_GAP) // 2, (h - GRID_GAP) // 2
    grid = ''.join(poster_box(f'$INFO[Window.Property(preview{i})]', x + (i % 2) * (gw + GRID_GAP),
                              y + (i // 2) * (gh + GRID_GAP), gw, gh, '\t\t\t')
                   for i in range(4))
    previews = 'Window.Property(previews)'
    return f'''		<control type="group">
			<description>The focused movie's poster</description>
{vis(LIST_FOCUS, chr(9) * 2)}{fade_anims(chr(9) * 2)}{poster_box('$INFO[Container(9200).ListItem.Property(poster)]', x, y, w, h, chr(9) * 3, badge=True)}		</control>
		<control type="group">
			<description>Tab bar focused: a preview of the collection, one poster or four</description>
{vis('!' + LIST_FOCUS + ' + String.IsEqual(' + previews + ',1)', chr(9) * 2)}{fade_anims(chr(9) * 2)}{poster_box('$INFO[Window.Property(preview0)]', x, y, w, h, chr(9) * 3)}		</control>
		<control type="group">
{vis('!' + LIST_FOCUS + ' + Integer.IsGreater(' + previews + ',1)', chr(9) * 2)}{fade_anims(chr(9) * 2)}{grid}		</control>
'''


def tabs():
    i4 = '\t\t\t\t'
    center = f'{i4}\t<align>center</align>\n{i4}\t<aligny>center</aligny>\n'
    builtin_mark = img((TAB_W - 44) // 2, TAB_H - 16, 44, 4, AMBER,
                       extra=vis('String.IsEqual(ListItem.Property(builtin),1)', i4), ind=i4)
    divider = img(TAB_W - 2, 20, 2, TAB_H - 40, 'kscape_text_faint',
                  extra=vis('String.IsEqual(ListItem.Property(divider),1)', i4), ind=i4)
    return f'''		<control type="image">
			<top>{TAB_TOP}</top>
			<width>{W}</width>
			<height>{TAB_H}</height>
			<texture colordiffuse="{BAR}">kscape-white.png</texture>
		</control>
		<control type="list" id="9100">
			<description>Collections: New, Paused, Played (built in, amber mark), then yours</description>
			<left>{TAB_LEFT}</left>
			<top>{TAB_TOP}</top>
			<width>{W - 2 * TAB_LEFT}</width>
			<height>{TAB_H}</height>
			<orientation>horizontal</orientation>
			<onup condition="Integer.IsGreater(Container(9200).NumItems,0)">9200</onup>
			<onup condition="!Integer.IsGreater(Container(9200).NumItems,0)">901</onup>
			<ondown>901</ondown>
			<onleft>901</onleft>
			<onright>901</onright>
			<scrolltime tween="cubic" easing="out">240</scrolltime>
			<itemlayout width="{TAB_W}" height="{TAB_H}">
{lab(0, 0, TAB_W, TAB_H, '$INFO[ListItem.Label]', 'kscape_bar', TEXT_DIM, center, i4)}{builtin_mark}{divider}			</itemlayout>
			<focusedlayout width="{TAB_W}" height="{TAB_H}">
{img(0, 0, TAB_W, TAB_H, TAB_FOCUS, extra=vis('Control.HasFocus(9100)', i4) + f'{i4}{chr(9)}<animation effect="fade" start="0" end="100" time="140">Visible</animation>{chr(10)}', ind=i4)}{img(0, 0, TAB_W, TAB_H, TAB_HEAD, extra=vis('!Control.HasFocus(9100)', i4), ind=i4)}{lab(0, 0, TAB_W, TAB_H, '$INFO[ListItem.Label]', 'kscape_bar', 'FFFFFFFF', center, i4)}{builtin_mark}{divider}			</focusedlayout>
		</control>
'''


def build(square=False):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERATED by tools/gen_collections_xml.py. Do not edit by hand. -->
<window>
	<defaultcontrol always="true">9100</defaultcontrol>
	<controls>
{img(0, 0, W, H, BG)}		<control type="button" id="901">
			<description>Edge target: never visible, so the lists stop at their ends</description>
			<left>-200</left>
			<top>-200</top>
			<width>1</width>
			<height>1</height>
			<texturefocus/>
			<texturenofocus/>
			<visible>false</visible>
		</control>
{movie_list()}{img(0, LIST_TOP, LIST_W, 70, BG, 'kscape-fade.png')}{img(0, TAB_TOP - 110, LIST_W, 110, BG, 'kscape-fade.png', flip=True)}{lab(HEAD_X, HEAD_Y, 1000, 30, '$INFO[Window.Property(kindlabel)]', 'kscape_list_head', AMBER)}{lab(HEAD_X, HEAD_Y + 30, 1060, 56, '$INFO[Window.Property(heading)]', 'kscape_title', 'FFFFFFFF')}{lab(HEAD_X, HEAD_Y + 86, 1000, 34, '$INFO[Window.Property(count)]', 'kscape_small', TEXT_DIM)}{lab(TEXT_X, 420, 1040, 200, '$INFO[Window.Property(empty)]', 'kscape_title', 'FFE6E6EA', chr(9) * 3 + '<wrapmultiline>true</wrapmultiline>' + chr(10) + vis('!String.IsEmpty(Window.Property(empty))', chr(9) * 2))}{lab(TEXT_X, 420, 1040, 120, '$INFO[Window.Property(status)]', 'kscape_title', 'FFE6E6EA')}{right_side(square)}{tabs()}{np_chip.chip()}	</controls>
</window>
'''


def main():
    for square, name in ((False, 'script-kscape-collections.xml'), (True, 'script-kscape-collections-square.xml')):
        out = os.path.join(ROOT, 'resources', 'skins', 'Default', '1080i', name)
        with open(out, 'w') as f:
            f.write(wrap_display.wrap(build(square)))   # display & aspect ratio root
        print(f'wrote {out}')


if __name__ == '__main__':
    main()
