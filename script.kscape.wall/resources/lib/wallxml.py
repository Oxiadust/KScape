"""The cover wall's window XML, built from its layout (geometry.py).

tools/gen_wall_xml.py writes the two shipped files for a 16:9 screen: script-kscape-wall.xml
(2:3 posters: movies, TV shows) and script-kscape-wall-square.xml (album covers). On another
screen shape, or in a CinemaScope band (display.py), the wall builds the XML for its adapted
layout here (prepare()) and opens it from the add-on's profile folder: every size is in the
XML, so nothing has to be resized control by control at run time (each Python control call
waits for Kodi's GUI lock - resizing a few hundred slots that way took over a minute).

Control ids (k = 0..POOL-1, POOL = the layout's pool_cols x pool_rows):
  900          focus sink (keeps Kodi delivering actions to the window)
  998          viewport group: the camera's frame, placed at the wall's view (the screen, or a
               CinemaScope band); 1971-1974 black masks around a band
  1000         camera group: positioned at -camera, glides via runtime slide animations
  1001         amber focus frame: four bars around the focused cell, in front of the covers
  10000+k      pool A cover slot group: card, fallback title, poster, format badge (one box per
               width in BADGE_WIDTHS) and favourite heart, all drawn from Container(1990)'s item k
  1990 / 1991  the pools' data lists (slot(): poster art, properties on, text, badge, bw, fav)
  1002-1005    focus frame bars (top, bottom, left, right); 1903 panel background
  20000+k      pool B, same offsets
  1900         info panel group; 1901 title (a label; a two-line textbox for albums);
               1902 synopsis (posters) or artist (albums), placed below the title by Python
               1909 group of the 1910 grouplist under the synopsis (posters): 1911 resolution badge, 1912 TMDB
               icon + 1913 score, 1914 Rotten Tomatoes icon + 1915 Tomatometer - each shown by a
               window property (p.res, p.tmdb, p.rt), the images sized by Python
  1950         status label (loading / empty library), outside the camera group
  1960         filter caption along the bottom (Python shows it): 1962 the active filters
  1980         now-playing chip top right while something plays (npchip.py)

No <visible> tags on Python-driven controls: a visibility condition overrides setVisible().
"""
import hashlib
import os

from . import geometry as G
from . import npchip as np_chip

CARD = 'FF1A1A1F'
AMBER = 'kscape_amber'
PANEL_BLUE = 'kscape_blue'
PANEL_LINE = 38               # a line of kscape_panel_body (four make the 16:9 synopsis, 152 px)
BADGE_W, BADGE_H = 58, 28     # reference: small amber-outlined "HDR"/"UHD" tag, bottom right
HEART_BOX, HEART = 40, 26     # favourite marker, top right of the cover
FACT_ROW_H, BADGE_IMG_H = 34, 26   # badge and ratings row under the synopsis (badges.py widths)
CAPTION_H = 62
PANEL_IN_MS, PANEL_OUT_MS = 320, 180   # synopsis panel entrance and exit
PANEL_SLIDE, PANEL_ZOOM = 26, 96       # px it slides out from the cover; % it grows from


SX = 1.0                      # the screen's horizontal stretch while build() runs (display.stage)


def x(v):
    """A horizontal size that must look the same on any screen: Kodi stretches coordinates
    across the screen but draws text and artwork in their true proportions."""
    return max(1, int(round(v / SX)))


def plot_lines(L):
    """Synopsis lines between the title and the badge row (four on a 16:9 screen)."""
    return max(1, min(4, (G.panel_h(L) - (88 + L.frame) - FACT_ROW_H - 16) // PANEL_LINE))


# Badge boxes come in a few fixed widths (window.py picks one by the text's length): resizing a
# box per cover would cost Python control calls, which wait for Kodi's GUI lock.
BADGE_WIDTHS = ((2, 44), (5, 72), (10, 124), (99, 176))     # (most characters, width at 16:9)
SOURCES = {10000: 1990, 20000: 1991}                         # pool base -> its data list


def badge_width(n, L):
    return min(L.cover_w - 2 * x(8), x(dict(BADGE_WIDTHS)[n]))


def slot(base, L):
    """The pool's slots. Each draws its item from the pool's hidden data list (SOURCES): slot k
    shows ListItemAbsolute(k)'s poster art and its properties - on (shown), text (no artwork),
    badge and bw (badge box), fav. Python updates those offscreen list items, which takes no
    GUI lock; only moving a slot is a control call."""
    out = []
    W, H = L.cover_w, L.cover_h
    src = SOURCES[base]
    for k in range(L.pool_cols * L.pool_rows):
        item = lambda info: f'$INFO[Container({src}).ListItemAbsolute({k}).{info}]'
        prop = lambda name, value: f'String.IsEqual(Container({src}).ListItemAbsolute({k}).Property({name}),{value})'
        boxes = []
        for n, _ in BADGE_WIDTHS:
            bw = badge_width(n, L)
            boxes.append(f'''				<control type="group">
					<left>{W - bw - x(8)}</left>
					<top>{H - BADGE_H - 8}</top>
					<visible>{prop('bw', n)}</visible>
					<control type="image">
						<width>{bw}</width>
						<height>{BADGE_H}</height>
						<texture colordiffuse="{AMBER}">kscape-white.png</texture>
					</control>
					<control type="image">
						<left>{x(2)}</left>
						<top>2</top>
						<width>{bw - 2 * x(2)}</width>
						<height>{BADGE_H - 4}</height>
						<texture colordiffuse="F0141210">kscape-white.png</texture>
					</control>
					<control type="label">
						<width>{bw}</width>
						<height>{BADGE_H}</height>
						<align>center</align>
						<aligny>center</aligny>
						<font>kscape_badge</font>
						<textcolor>{AMBER}</textcolor>
						<label>{item('Property(badge)')}</label>
					</control>
				</control>''')
        out.append(f'''			<control type="group" id="{base + k}">
				<width>{W}</width>
				<height>{H}</height>
				<visible>{prop('on', 1)}</visible>
				<control type="image">
					<width>{W}</width>
					<height>{H}</height>
					<texture colordiffuse="{CARD}">kscape-white.png</texture>
				</control>
				<control type="textbox">
					<left>{x(12)}</left>
					<top>12</top>
					<width>{W - x(24)}</width>
					<height>{H - 24}</height>
					<align>center</align>
					<aligny>center</aligny>
					<font>kscape_small</font>
					<textcolor>FFC8C8D0</textcolor>
					<label>{item('Property(text)')}</label>
				</control>
				<control type="image">
					<width>{W}</width>
					<height>{H}</height>
					<aspectratio>scale</aspectratio>
					<fadetime>120</fadetime>
					<texture background="true">{item('Art(poster)')}</texture>
				</control>
{chr(10).join(boxes)}
				<control type="group">
					<left>{W - x(HEART_BOX) - x(8)}</left>
					<top>8</top>
					<visible>{prop('fav', 1)}</visible>
					<control type="image">
						<width>{x(HEART_BOX)}</width>
						<height>{HEART_BOX}</height>
						<texture colordiffuse="C8141210">kscape-white.png</texture>
					</control>
					<control type="image">
						<left>{(x(HEART_BOX) - x(HEART)) // 2}</left>
						<top>{(HEART_BOX - HEART) // 2 + 1}</top>
						<width>{x(HEART)}</width>
						<height>{HEART}</height>
						<texture colordiffuse="{AMBER}">kscape-heart.png</texture>
					</control>
				</control>
			</control>''')
    return '\n'.join(out)


def sources():
    """The pools' hidden data lists, off screen (they hold the items; nothing is drawn)."""
    return ''.join(f'''		<control type="list" id="{cid}">
			<description>Data for pool {"A" if base == 10000 else "B"}'s slots (window.Pool)</description>
			<left>-4000</left>
			<top>-4000</top>
			<width>10</width>
			<height>10</height>
			<itemlayout width="10" height="10"/>
			<focusedlayout width="10" height="10"/>
		</control>
''' for base, cid in SOURCES.items())


def focus_frame(L):
    """Hollow amber frame hugging the cover (no gap), drawn after the cover slots so it glides
    over them; the info panel follows it and sits flush against its outer edge."""
    t, tx = L.frame, G.fx(L)
    w, h = L.cover_w + 2 * tx, L.cover_h + 2 * t
    bars = [(0, 0, w, t), (0, h - t, w, t), (0, t, tx, h - 2 * t), (w - tx, t, tx, h - 2 * t)]
    out = [f'''			<control type="group" id="1001">
				<description>Focus frame</description>
				<width>{w}</width>
				<height>{h}</height>''']
    for n, (x, y, bw, bh) in enumerate(bars):
        out.append(f'''				<control type="image" id="{1002 + n}">
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
					<left>{x(34)}</left>
					<top>{26 + L.frame}</top>
					<width>{panel_w - 2 * x(34)}</width>
					<height>104</height>
					<font>kscape_panel_title</font>
					<textcolor>FFFFFFFF</textcolor>
				</control>
				<control type="textbox" id="1902">
					<left>{x(34)}</left>
					<top>{88 + L.frame}</top>
					<width>{panel_w - 2 * x(34)}</width>
					<height>76</height>
					<font>kscape_panel_body</font>
					<textcolor>kscape_text</textcolor>
				</control>'''
    return f'''				<control type="label" id="1901">
					<left>{x(34)}</left>
					<top>{26 + L.frame}</top>
					<width>{panel_w - 2 * x(34)}</width>
					<height>56</height>
					<font>kscape_panel_title</font>
					<textcolor>FFFFFFFF</textcolor>
				</control>
				<control type="textbox" id="1902">
					<left>{x(34)}</left>
					<top>{88 + L.frame}</top>
					<width>{panel_w - 2 * x(34)}</width>
					<height>{plot_lines(L) * PANEL_LINE}</height>
					<font>kscape_panel_body</font>
					<textcolor>kscape_text</textcolor>
				</control>
{facts_row(L, panel_w)}'''


def facts_row(L, panel_w):
    """Resolution badge and ratings under the synopsis, as in the reference (posters only)."""
    top = 88 + L.frame + plot_lines(L) * PANEL_LINE + 6
    def img(cid, prop, tex, w, tint=''):
        colour = f' colordiffuse="{tint}"' if tint else ''
        return f'''					<control type="image" id="{cid}">
						<top>{(FACT_ROW_H - BADGE_IMG_H) // 2}</top>
						<width>{x(w)}</width>
						<height>{BADGE_IMG_H}</height>
						<texture{colour}>{tex}</texture>
						<visible>!String.IsEmpty(Window.Property({prop}))</visible>
					</control>'''
    def label(cid, prop):
        return f'''					<control type="label" id="{cid}">
						<width>auto</width>
						<height>{FACT_ROW_H}</height>
						<aligny>center</aligny>
						<font>kscape_panel_body</font>
						<textcolor>kscape_text</textcolor>
						<label>$INFO[Window.Property({prop})]</label>
						<visible>!String.IsEmpty(Window.Property({prop}))</visible>
					</control>'''
    def gap(w, cond):
        return f'''					<control type="image">
						<width>{w}</width>
						<height>{FACT_ROW_H}</height>
						<texture/>
						<visible>{cond}</visible>
					</control>'''
    return f'''				<control type="group" id="1909">
					<description>Badge row (a group: Python cannot hold a grouplist)</description>
					<left>{x(34)}</left>
					<top>{top}</top>
					<width>{panel_w - 2 * x(34)}</width>
					<height>{FACT_ROW_H}</height>
				<control type="grouplist" id="1910">
					<width>{panel_w - 2 * x(34)}</width>
					<height>{FACT_ROW_H}</height>
					<orientation>horizontal</orientation>
					<itemgap>6</itemgap>
					<usecontrolcoords>true</usecontrolcoords>
{img(1911, 'p.res', '$INFO[Window.Property(p.res)]', 36, AMBER)}
{gap(14, '!String.IsEmpty(Window.Property(p.res))')}
{img(1912, 'p.tmdb', 'kscape-tmdb.png', 50)}
{label(1913, 'p.tmdb')}
{gap(14, '!String.IsEmpty(Window.Property(p.tmdb))')}
{img(1914, 'p.rt', '$INFO[Window.Property(p.rticon)]', BADGE_IMG_H)}
{label(1915, 'p.rt')}
				</control>
				</control>'''


def masks():
    """Black outside a CinemaScope band (window.py sizes them; hidden otherwise), over the covers
    and panel that reach past it."""
    out = []
    for n, name in enumerate(('above', 'below', 'left of', 'right of')):
        out.append(f'''		<control type="image" id="{1971 + n}">
			<description>Mask {name} the band</description>
			<width>1</width>
			<height>1</height>
			<texture colordiffuse="FF000000">kscape-white.png</texture>
		</control>''')
    return '\n'.join(out)


def caption():
    """The active filters, along the bottom of the wall (Explore and the Filter menu)."""
    return f'''		<control type="group" id="1960">
			<description>Filter caption: what the wall is filtered by and how many match</description>
			<top>{G.SCREEN_H - CAPTION_H}</top>
			<animation effect="fade" start="0" end="100" time="250">Visible</animation>
			<animation effect="fade" start="100" end="0" time="150">Hidden</animation>
			<control type="image" id="1961">
				<width>{G.SCREEN_W}</width>
				<height>{CAPTION_H}</height>
				<texture colordiffuse="kscape_bg_shade">kscape-white.png</texture>
			</control>
			<control type="image" id="1963">
				<width>{G.SCREEN_W}</width>
				<height>3</height>
				<texture colordiffuse="kscape_blue">kscape-white.png</texture>
			</control>
			<control type="label" id="1962">
				<left>48</left>
				<top>3</top>
				<width>{G.SCREEN_W - 96}</width>
				<height>{CAPTION_H - 3}</height>
				<aligny>center</aligny>
				<font>kscape_panel_body</font>
				<textcolor>kscape_text</textcolor>
			</control>
		</control>
'''


def panel_animations(L, panel_w, panel_h, ind='\t\t\t\t'):
    """The synopsis panel eases in beside the selected cover: a fade, a short slide out from the
    cover's side and a slight scale, then eases out the same way, faster. The side comes from the
    window property kscape.panel.side (window.py sets it before showing the panel). With reduced
    motion it only fades."""
    full = '!String.IsEqual(Window(Home).Property(kscape.reduced),1)'
    out = [f'{ind}<animation effect="fade" start="0" end="100" time="{PANEL_IN_MS}" tween="sine" easing="out">Visible</animation>',
           f'{ind}<animation effect="fade" start="100" end="0" time="{PANEL_OUT_MS}" tween="sine" easing="in">Hidden</animation>']
    for side, cx in (('right', 0), ('left', panel_w)):
        dx = -PANEL_SLIDE if side == 'right' else PANEL_SLIDE
        cond = f'{full} + String.IsEqual(Window.Property(kscape.panel.side),{side})'
        out += [
            f'{ind}<animation effect="slide" start="{dx},0" end="0,0" time="{PANEL_IN_MS}" tween="cubic" easing="out" condition="{cond}">Visible</animation>',
            f'{ind}<animation effect="zoom" start="{PANEL_ZOOM}" end="100" center="{cx},{panel_h // 2}" time="{PANEL_IN_MS}" tween="cubic" easing="out" condition="{cond}">Visible</animation>',
            f'{ind}<animation effect="slide" start="0,0" end="{dx // 2},0" time="{PANEL_OUT_MS}" tween="sine" easing="in" condition="{cond}">Hidden</animation>',
        ]
    return '\n'.join(out)


def build(L, sx=1.0):
    """The wall's XML for layout `L` on a screen stretched by `sx`."""
    global SX
    SX = sx
    try:
        return _build(L)
    finally:
        SX = 1.0


def _build(L):
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
{sources()}		<control type="group" id="998">
			<description>Viewport: the screen, or a CinemaScope band (window.py places it)</description>
		<control type="group" id="1000">
			<description>Camera</description>
{slot(10000, L)}
{slot(20000, L)}
{focus_frame(L)}
			<control type="group" id="1900">
				<description>Info panel beside the focused cover</description>
				<width>{panel_w}</width>
				<height>{panel_h}</height>
{panel_animations(L, panel_w, panel_h)}
				<control type="image" id="1903">
					<width>{panel_w}</width>
					<height>{panel_h}</height>
					<texture colordiffuse="{PANEL_BLUE}">kscape-white.png</texture>
				</control>
{panel_text(L, panel_w)}
			</control>
		</control>
		</control>
{masks()}
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
{caption()}{np_chip.chip(cid=1980)}	</controls>
</window>
'''


def prepare(L, sx, addon_path, profile_path):
    """The XML for an adapted layout, written to (and opened from) the add-on's profile folder,
    with a copy of the wall's images beside it (Kodi looks for them next to the XML). Returns
    (script path for WindowXML, file name). Files of earlier layouts are removed."""
    import shutil
    xml = build(L, sx)
    tag = hashlib.sha1(xml.encode('utf-8')).hexdigest()[:10]
    name = f'script-kscape-wall-{L.name}-{tag}.xml'
    skin = os.path.join(profile_path, 'display', 'resources', 'skins', 'Default')
    folder, media = os.path.join(skin, '1080i'), os.path.join(skin, 'media')
    os.makedirs(folder, exist_ok=True)
    os.makedirs(media, exist_ok=True)
    source = os.path.join(addon_path, 'resources', 'skins', 'Default', 'media')
    for f in os.listdir(source):
        src, dst = os.path.join(source, f), os.path.join(media, f)
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copyfile(src, dst)
    for f in os.listdir(folder):
        if f.startswith(f'script-kscape-wall-{L.name}-') and f != name:
            os.remove(os.path.join(folder, f))
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as out:
            out.write(xml)
    return os.path.join(profile_path, 'display'), name
