"""The "now playing" chip drawn top right of the generated views (cover walls, list views,
collections) while something plays, so you can see it while browsing the libraries.

A video shows live in Kodi's own videowindow control (the playing video, scaled, kept in its
aspect ratio, rendered by Kodi's player: no extra decoding); music shows its cover. Then the play
state, elapsed / total time, the title and a progress bar. Colours are literal so the chip also
draws under another skin.
"""

X, Y, W, H = 1272, 26, 620, 108
THUMB_W, THUMB_H = 160, 90          # 16:9 video
ART = 90                            # square cover
PAD = 9
AMBER = 'kscape_amber'
DIM = 'FF9AA3B5'


def chip(ind='\t\t', white='kscape-white.png', cid=None):
    """`cid`: an id for the chip's group, for windows that move it (the cover wall, into a
    CinemaScope band)."""
    tx = PAD + THUMB_W + 18
    tw = W - tx - 18
    gid = f' id="{cid}"' if cid else ''
    return f'''{ind}<control type="group"{gid}>
{ind}	<description>Now playing chip (tools/np_chip.py)</description>
{ind}	<left>{X}</left>
{ind}	<top>{Y}</top>
{ind}	<visible>Player.HasMedia</visible>
{ind}	<animation effect="fade" start="0" end="100" time="300">Visible</animation>
{ind}	<animation effect="fade" start="100" end="0" time="200">Hidden</animation>
{ind}	<control type="image">
{ind}		<width>{W}</width>
{ind}		<height>{H}</height>
{ind}		<texture colordiffuse="kscape_bg_chip">{white}</texture>
{ind}	</control>
{ind}	<control type="image">
{ind}		<width>{W}</width>
{ind}		<height>3</height>
{ind}		<texture colordiffuse="kscape_blue">{white}</texture>
{ind}	</control>
{ind}	<control type="image">
{ind}		<left>{PAD}</left>
{ind}		<top>{PAD}</top>
{ind}		<width>{THUMB_W}</width>
{ind}		<height>{THUMB_H}</height>
{ind}		<texture colordiffuse="FF000000">{white}</texture>
{ind}		<visible>Player.HasVideo</visible>
{ind}	</control>
{ind}	<control type="videowindow">
{ind}		<left>{PAD}</left>
{ind}		<top>{PAD}</top>
{ind}		<width>{THUMB_W}</width>
{ind}		<height>{THUMB_H}</height>
{ind}		<visible>Player.HasVideo</visible>
{ind}	</control>
{ind}	<control type="image">
{ind}		<left>{PAD + THUMB_W - ART}</left>
{ind}		<top>{PAD}</top>
{ind}		<width>{ART}</width>
{ind}		<height>{ART}</height>
{ind}		<aspectratio>scale</aspectratio>
{ind}		<texture background="true">$INFO[Player.Art(thumb)]</texture>
{ind}		<visible>Player.HasAudio</visible>
{ind}	</control>
{ind}	<control type="label">
{ind}		<left>{tx}</left>
{ind}		<top>10</top>
{ind}		<width>{tw}</width>
{ind}		<height>26</height>
{ind}		<font>kscape_badge</font>
{ind}		<textcolor>{AMBER}</textcolor>
{ind}		<label>$ADDON[script.kscape.wall 32133]</label>
{ind}		<visible>!Player.Paused</visible>
{ind}	</control>
{ind}	<control type="label">
{ind}		<left>{tx}</left>
{ind}		<top>10</top>
{ind}		<width>{tw}</width>
{ind}		<height>26</height>
{ind}		<font>kscape_badge</font>
{ind}		<textcolor>{AMBER}</textcolor>
{ind}		<label>$ADDON[script.kscape.wall 32134]</label>
{ind}		<visible>Player.Paused</visible>
{ind}	</control>
{ind}	<control type="label">
{ind}		<left>{tx}</left>
{ind}		<top>10</top>
{ind}		<width>{tw}</width>
{ind}		<height>26</height>
{ind}		<align>right</align>
{ind}		<font>kscape_badge</font>
{ind}		<textcolor>{DIM}</textcolor>
{ind}		<label>$INFO[Player.Time]$INFO[Player.Duration, / ]</label>
{ind}	</control>
{ind}	<control type="label">
{ind}		<left>{tx}</left>
{ind}		<top>38</top>
{ind}		<width>{tw}</width>
{ind}		<height>36</height>
{ind}		<font>kscape_small</font>
{ind}		<textcolor>FFFFFFFF</textcolor>
{ind}		<label>$INFO[Player.Title]</label>
{ind}	</control>
{ind}	<control type="progress">
{ind}		<left>{tx}</left>
{ind}		<top>{H - 22}</top>
{ind}		<width>{tw}</width>
{ind}		<height>5</height>
{ind}		<texturebg colordiffuse="kscape_track">{white}</texturebg>
{ind}		<midtexture colordiffuse="{AMBER}">{white}</midtexture>
{ind}		<info>Player.Progress</info>
{ind}	</control>
{ind}</control>
'''

