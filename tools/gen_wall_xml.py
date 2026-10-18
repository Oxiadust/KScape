"""Generate script.kscape.wall's cover wall XML from its geometry module, once per cover layout:
script-kscape-wall.xml (2:3 posters: movies, TV shows) and script-kscape-wall-square.xml
(album covers).

Usage: python3 tools/gen_wall_xml.py
Control ids (k = 0..POOL-1, POOL = the layout's pool_cols x pool_rows):
  900          focus sink (keeps Kodi delivering actions to the window)
  1000         camera group: positioned at -camera, glides via runtime slide animations
  1001         amber focus frame: four bars around the focused cell, in front of the covers
  10000+k      pool A cover slot group; +200 fallback title textbox; +400 poster;
               +600 quality badge group; +800 badge label; +1000 favourite heart
  20000+k      pool B, same offsets
  1900         info panel group; 1901 title (a label; a two-line textbox for albums);
               1902 synopsis (posters) or artist (albums), placed below the title by Python
  1950         status label (loading / empty library), outside the camera group
  (no id)      now-playing chip top right while something plays (tools/np_chip.py)

No <visible> tags on Python-driven controls: a visibility condition overrides setVisible().
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), '..', 'script.kscape.wall')
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from resources.lib import geometry as G  # noqa: E402
import np_chip  # noqa: E402

CARD = 'FF1A1A1F'
AMBER = 'kscape_amber'
PANEL_BLUE = 'kscape_blue'
PANEL_TEXT_H = 152            # four 37.6 px lines of kscape_panel_body; no clipped partial line
BADGE_W, BADGE_H = 58, 28     # reference: small amber-outlined "HDR"/"UHD" tag, bottom right
HEART_BOX, HEART = 40, 26     # favourite marker, top right of the cover


def slot(base, L):
    out = []
    W, H = L.cover_w, L.cover_h
    for k in range(L.pool_cols * L.pool_rows):
        out.append(f'''			<control type="group" id="{base + k}">
				<width>{W}</width>
				<height>{H}</height>
				<control type="image">
					<width>{W}</width>
					<height>{H}</height>
					<texture colordiffuse="{CARD}">kscape-white.png</texture>
				</control>
				<control type="textbox" id="{base + 200 + k}">
					<left>12</left>
					<top>12</top>
					<width>{W - 24}</width>
					<height>{H - 24}</height>
					<align>center</align>
					<aligny>center</aligny>
					<font>kscape_small</font>
					<textcolor>FFC8C8D0</textcolor>
				</control>
				<control type="image" id="{base + 400 + k}">
					<width>{W}</width>
					<height>{H}</height>
					<aspectratio>scale</aspectratio>
					<fadetime>120</fadetime>
				</control>
				<control type="group" id="{base + 600 + k}">
					<left>{W - BADGE_W - 8}</left>
					<top>{H - BADGE_H - 8}</top>
					<control type="image">
						<width>{BADGE_W}</width>
						<height>{BADGE_H}</height>
						<texture colordiffuse="{AMBER}">kscape-white.png</texture>
					</control>
					<control type="image">
						<left>2</left>
						<top>2</top>
						<width>{BADGE_W - 4}</width>
						<height>{BADGE_H - 4}</height>
						<texture colordiffuse="F0141210">kscape-white.png</texture>
					</control>
					<control type="label" id="{base + 800 + k}">
						<width>{BADGE_W}</width>
						<height>{BADGE_H}</height>
						<align>center</align>
						<aligny>center</aligny>
						<font>kscape_badge</font>
						<textcolor>{AMBER}</textcolor>
					</control>
				</control>
				<control type="group" id="{base + 1000 + k}">
					<left>{W - HEART_BOX - 8}</left>
					<top>8</top>
					<control type="image">
						<width>{HEART_BOX}</width>
						<height>{HEART_BOX}</height>
						<texture colordiffuse="C8141210">kscape-white.png</texture>
					</control>
					<control type="image">
						<left>{(HEART_BOX - HEART) // 2}</left>
						<top>{(HEART_BOX - HEART) // 2 + 1}</top>
						<width>{HEART}</width>
						<height>{HEART}</height>
						<texture colordiffuse="{AMBER}">kscape-heart.png</texture>
					</control>
				</control>
			</control>''')
    return '\n'.join(out)


def focus_frame(L):
    """Hollow amber frame hugging the cover (no gap), drawn after the cover slots so it glides
    over them; the info panel follows it and sits flush against its outer edge."""
    w, h, t = L.cover_w + 2 * L.frame, L.cover_h + 2 * L.frame, L.frame
    bars = [(0, 0, w, t), (0, h - t, w, t), (0, t, t, h - 2 * t), (w - t, t, t, h - 2 * t)]
    out = [f'''			<control type="group" id="1001">
				<description>Focus frame</description>
				<width>{w}</width>
				<height>{h}</height>''']
    for x, y, bw, bh in bars:
        out.append(f'''				<control type="image">
					<left>{x}</left>
					<top>{y}</top>
					<width>{bw}</width>
					<height>{bh}</height>
					<texture colordiffuse="{AMBER}">kscape-white.png</texture>
				</control>''')
    out.append('			</control>')
    return '\n'.join(out)


def panel_text(L, panel_w):
    if L is G.SQUARE:
        # Album: title on up to two lines, artist below it (positioned by window.py).
        return f'''				<control type="textbox" id="1901">
					<left>34</left>
					<top>{26 + L.frame}</top>
					<width>{panel_w - 68}</width>
					<height>104</height>
					<font>kscape_panel_title</font>
					<textcolor>FFFFFFFF</textcolor>
				</control>
				<control type="textbox" id="1902">
					<left>34</left>
					<top>{88 + L.frame}</top>
					<width>{panel_w - 68}</width>
					<height>76</height>
					<font>kscape_panel_body</font>
					<textcolor>kscape_text</textcolor>
				</control>'''
    return f'''				<control type="label" id="1901">
					<left>34</left>
					<top>{26 + L.frame}</top>
					<width>{panel_w - 68}</width>
					<height>56</height>
					<font>kscape_panel_title</font>
					<textcolor>FFFFFFFF</textcolor>
				</control>
				<control type="textbox" id="1902">
					<left>34</left>
					<top>{88 + L.frame}</top>
					<width>{panel_w - 68}</width>
					<height>{PANEL_TEXT_H}</height>
					<font>kscape_panel_body</font>
					<textcolor>kscape_text</textcolor>
				</control>'''


def build(L):
    panel_w, panel_h = G.panel_w(L), G.panel_h(L)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- GENERATED by tools/gen_wall_xml.py from resources/lib/geometry.py ({L.name} covers). Do not edit by hand. -->
<window>
	<defaultcontrol always="true">900</defaultcontrol>
	<controls>
		<control type="image">
			<width>{G.SCREEN_W}</width>
			<height>{G.SCREEN_H}</height>
			<texture colordiffuse="FF060607">kscape-white.png</texture>
		</control>
		<control type="button" id="900">
			<description>Focus sink: the window handles all navigation itself</description>
			<left>-200</left>
			<top>-200</top>
			<width>1</width>
			<height>1</height>
			<texturefocus/>
			<texturenofocus/>
		</control>
		<control type="group" id="1000">
			<description>Camera</description>
{slot(10000, L)}
{slot(20000, L)}
{focus_frame(L)}
			<control type="group" id="1900">
				<description>Info panel beside the focused cover</description>
				<width>{panel_w}</width>
				<height>{panel_h}</height>
				<animation effect="fade" start="0" end="100" time="220">Visible</animation>
				<animation effect="fade" start="100" end="0" time="120">Hidden</animation>
				<control type="image">
					<width>{panel_w}</width>
					<height>{panel_h}</height>
					<texture colordiffuse="{PANEL_BLUE}">kscape-white.png</texture>
				</control>
{panel_text(L, panel_w)}
			</control>
		</control>
		<control type="label" id="1950">
			<description>Status: loading, empty library, no favourites (two lines)</description>
			<left>260</left>
			<top>440</top>
			<width>1400</width>
			<height>200</height>
			<align>center</align>
			<aligny>center</aligny>
			<font>kscape_title</font>
			<textcolor>FFE6E6EA</textcolor>
			<wrapmultiline>true</wrapmultiline>
		</control>
{np_chip.chip()}	</controls>
</window>
'''


def main():
    folder = os.path.join(ROOT, 'resources', 'skins', 'Default', '1080i')
    for L, name in ((G.POSTER, 'script-kscape-wall.xml'), (G.SQUARE, 'script-kscape-wall-square.xml')):
        out = os.path.join(folder, name)
        with open(out, 'w') as f:
            f.write(build(L))
        print(f'wrote {out} ({L.pool_cols * L.pool_rows} slots per pool)')


if __name__ == '__main__':
    main()
