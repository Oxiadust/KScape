"""Build a small local music and TV library for the isolated test Kodi (never point this at a real
profile).

Usage: python3 tools/make_test_media.py [out-dir]        default: /tmp/kscape-media

Writes:
  music/<Artist>/<Album> (<Year>)/NN - <Title>.flac   2 s tone, Vorbis tags (artist, album,
                                                     albumartist, genre x n, date, track)
                                 cover.jpg           most albums; some are left without art
  tv/<Show> (<Year>)/tvshow.nfo, poster.jpg, fanart.jpg, seasonNN-poster.jpg
                    Season NN/<Show> SxxEyy.mp4 + .nfo   3 s H.264 clip per episode

Register it with the test profile: tools/kodi_smoke_test.sh adds the sources and scans them
when MEDIA=1.
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
import math
import colorsys

from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else '/tmp/kscape-media'

ALBUMS = [  # artist, album, year, genres, tracks, has_art
    ('The Beatles', 'Abbey Road', 1969, ['Rock', 'Pop'], ['Come Together', 'Something', 'Here Comes the Sun'], True),
    ('The Beatles', 'Revolver', 1966, ['Rock', 'Psychedelic'], ['Taxman', 'Eleanor Rigby', 'Tomorrow Never Knows'], True),
    ('The Beatles', 'Rubber Soul', 1965, ['Rock', 'Pop'], ['Drive My Car', 'Norwegian Wood', 'Michelle'], True),
    ('ABBA', 'The Definitive Collection', 2001, ['Pop', 'Disco'], ['Waterloo', 'Mamma Mia', 'Dancing Queen'], True),
    ('Miles Davis', 'Kind of Blue', 1959, ['Jazz', 'Modal'], ['So What', 'Freddie Freeloader', 'Blue in Green'], True),
    ('Miles Davis', 'Bitches Brew', 1970, ['Jazz', 'Fusion'], ['Pharaoh\'s Dance', 'Spanish Key', 'Sanctuary'], False),
    ('John Coltrane', 'A Love Supreme', 1965, ['Jazz'], ['Acknowledgement', 'Resolution', 'Pursuance'], True),
    ('Stan Getz', 'Getz/Gilberto', 1964, ['Jazz', 'Bossa Nova'], ['The Girl from Ipanema', 'Doralice', 'Corcovado'], True),
    ('Dave Brubeck Quartet', 'Time Out', 1959, ['Jazz', 'Cool Jazz'], ['Blue Rondo a la Turk', 'Take Five', 'Kathy\'s Waltz'], True),
    ('Pink Floyd', 'The Dark Side of the Moon', 1973, ['Rock', 'Progressive Rock'], ['Speak to Me', 'Time', 'Money'], True),
    ('Pink Floyd', 'Wish You Were Here', 1975, ['Rock', 'Progressive Rock'], ['Shine On', 'Welcome to the Machine', 'Have a Cigar'], True),
    ('Prince', 'Purple Rain', 1984, ['Pop', 'Funk', 'Rock'], ['Let\'s Go Crazy', 'When Doves Cry', 'Purple Rain'], True),
    ('Michael Jackson', 'Thriller', 1982, ['Pop', 'R&B'], ['Wanna Be Startin\' Somethin\'', 'Thriller', 'Billie Jean'], True),
    ('Madonna', 'The Immaculate Collection', 1990, ['Pop', 'Dance'], ['Holiday', 'Like a Virgin', 'Vogue'], True),
    ('Dusty Springfield', 'Dusty in Memphis', 1969, ['Soul', 'Pop'], ['Just a Little Lovin\'', 'Son of a Preacher Man', 'Breakfast in Bed'], True),
    ('U2', 'The Joshua Tree', 1987, ['Rock'], ['Where the Streets Have No Name', 'With or Without You', 'Bullet the Blue Sky'], True),
    ('The Who', 'My Generation', 1965, ['Rock', 'Mod'], ['Out in the Street', 'The Kids Are Alright', 'My Generation'], False),
    ('Elton John', 'Goodbye Yellow Brick Road', 1973, ['Pop', 'Rock'], ['Funeral for a Friend', 'Candle in the Wind', 'Bennie and the Jets'], True),
    ('Bruce Springsteen', 'Born to Run', 1975, ['Rock'], ['Thunder Road', 'Born to Run', 'Jungleland'], True),
    ('Simon & Garfunkel', 'Bridge over Troubled Water', 1970, ['Folk', 'Pop'], ['Bridge over Troubled Water', 'El Condor Pasa', 'Cecilia'], True),
    ('Dire Straits', 'Brothers in Arms', 1985, ['Rock'], ['So Far Away', 'Money for Nothing', 'Walk of Life'], True),
    ('Eva Cassidy', 'Songbird', 1998, ['Folk', 'Jazz'], ['Fields of Gold', 'Wade in the Water', 'Songbird'], True),
    ('James Taylor', 'Sweet Baby James', 1970, ['Folk', 'Rock'], ['Sweet Baby James', 'Fire and Rain', 'Country Road'], True),
    ('Santana', 'Supernatural', 1999, ['Rock', 'Latin'], ['Yaleo', 'Smooth', 'Maria Maria'], True),
    ('Joni Mitchell', 'Blue', 1971, ['Folk'], ['All I Want', 'My Old Man', 'A Case of You'], False),
    ('Leonard Bernstein', 'Mahler: Symphony No. 5', 1986, ['Classical'], ['Trauermarsch', 'Sturmisch bewegt', 'Adagietto'], True),
    ('Tony Bennett', 'At Carnegie Hall', 1962, ['Vocal', 'Jazz'], ['Lullaby of Broadway', 'Just in Time', 'Ol\' Man River'], True),
    ('Frank Sinatra', 'In the Wee Small Hours', 1955, ['Vocal', 'Jazz'], ['In the Wee Small Hours', 'Mood Indigo', 'Glad to Be Unhappy'], True),
    ('Sting', 'Ten Summoner\'s Tales', 1993, ['Pop', 'Rock'], ['If I Ever Lose My Faith', 'Fields of Gold', 'Shape of My Heart'], True),
    ('The Beach Boys', 'Pet Sounds', 1966, ['Pop', 'Rock'], ['Wouldn\'t It Be Nice', 'God Only Knows', 'Caroline, No'], True),
]

SHOWS = [  # title, year, genres, studio, plot, seasons, episodes per season, cast
    ('Harbor Lights', 2019, ['Drama', 'Mystery'], 'North Coast', 'A harbor town keeps its secrets until a lighthouse keeper starts asking questions.', 3, 3, ['Ava Lane', 'Tom Reyes', 'June Park']),
    ('The Night Shift Kitchen', 2021, ['Comedy'], 'Bright Lane', 'Line cooks in an all-night diner deal with impossible orders and each other.', 2, 3, ['Sam Ortiz', 'Mia Grant']),
    ('Orbital', 2016, ['Science Fiction', 'Drama'], 'Starfield', 'The crew of a research station discovers the station is older than anyone was told.', 2, 4, ['Kai Novak', 'Ava Lane', 'Raj Mehta']),
    ('Atlas of Small Things', 2023, ['Documentary'], 'Field Notes', 'Each episode follows one tiny creature through a single day.', 1, 3, ['Nora Hale']),
    ('Cold Case Coast', 2012, ['Crime', 'Drama', 'Mystery'], 'North Coast', 'Two detectives reopen the files nobody else wants.', 3, 2, ['Tom Reyes', 'Lena Fox']),
]

COLORS = 37


def color(i, s=0.55, v=0.75):
    r, g, b = colorsys.hsv_to_rgb((i * 0.618) % 1, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def font(size):
    for path in ('/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/System/Library/Fonts/Helvetica.ttc'):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def art(path, size, lines, i):
    """Simple gradient artwork with the title on it, so tests can tell covers apart."""
    w, h = size
    img = Image.new('RGB', size, color(i))
    d = ImageDraw.Draw(img)
    top, bottom = color(i, 0.6, 0.85), color(i + 3, 0.7, 0.35)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(top[k] * (1 - t) + bottom[k] * t) for k in range(3)))
    f = font(max(18, w // 12))
    y = h // 6
    for text in lines:
        d.text((w // 14, y), text, font=f, fill=(255, 255, 255))
        y += int(f.size * 1.3)
    img.save(path, quality=88)


def tone_flac(path):
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, 't.wav')
        with wave.open(wav, 'w') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            frames = b''.join(struct.pack('<h', int(3000 * math.sin(2 * math.pi * 440 * n / 22050)))
                              for n in range(22050 * 2))
            w.writeframes(frames)
        subprocess.run(['afconvert', '-f', 'flac', '-d', 'flac', wav, path], check=True)


def with_tags(src, dst, tags):
    """Copy a FLAC file, replacing its metadata with STREAMINFO + a VORBIS_COMMENT block."""
    data = open(src, 'rb').read()
    assert data[:4] == b'fLaC'
    pos, streaminfo = 4, None
    while True:
        header = data[pos]
        last, btype = header & 0x80, header & 0x7F
        length = int.from_bytes(data[pos + 1:pos + 4], 'big')
        if btype == 0:
            streaminfo = data[pos + 4:pos + 4 + length]
        pos += 4 + length
        if last:
            break
    vendor = b'kscape-test'
    body = struct.pack('<I', len(vendor)) + vendor + struct.pack('<I', len(tags))
    for k, v in tags:
        entry = f'{k}={v}'.encode()
        body += struct.pack('<I', len(entry)) + entry
    out = b'fLaC' + bytes([0]) + len(streaminfo).to_bytes(3, 'big') + streaminfo
    out += bytes([0x80 | 4]) + len(body).to_bytes(3, 'big') + body + data[pos:]
    with open(dst, 'wb') as f:
        f.write(out)


SWIFT_CLIP = r'''
import AVFoundation
import CoreVideo
let url = URL(fileURLWithPath: CommandLine.arguments[1])
try? FileManager.default.removeItem(at: url)
let w = 320, h = 180, fps: Int32 = 10, frames = 30
let writer = try! AVAssetWriter(outputURL: url, fileType: .mp4)
let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: w, AVVideoHeightKey: h])
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA, kCVPixelBufferWidthKey as String: w,
    kCVPixelBufferHeightKey as String: h])
writer.add(input)
writer.startWriting()
writer.startSession(atSourceTime: .zero)
for i in 0..<frames {
    while !input.isReadyForMoreMediaData { usleep(1000) }
    var pb: CVPixelBuffer?
    CVPixelBufferPoolCreatePixelBuffer(nil, adaptor.pixelBufferPool!, &pb)
    CVPixelBufferLockBaseAddress(pb!, [])
    let base = CVPixelBufferGetBaseAddress(pb!)!.assumingMemoryBound(to: UInt8.self)
    let stride = CVPixelBufferGetBytesPerRow(pb!)
    for y in 0..<h { for x in 0..<w {
        let p = base + y * stride + x * 4
        p[0] = UInt8((x + i * 8) % 256); p[1] = UInt8(y % 256); p[2] = 120; p[3] = 255
    } }
    CVPixelBufferUnlockBaseAddress(pb!, [])
    adaptor.append(pb!, withPresentationTime: CMTime(value: CMTimeValue(i), timescale: fps))
}
input.markAsFinished()
let done = DispatchSemaphore(value: 0)
writer.finishWriting { done.signal() }
done.wait()
'''


def clip(path):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'clip.swift')
        open(src, 'w').write(SWIFT_CLIP)
        subprocess.run(['swift', src, path], check=True, stderr=subprocess.DEVNULL)


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def make_music(root):
    os.makedirs(root, exist_ok=True)
    master = os.path.join(root, '.tone.flac')
    tone_flac(master)
    for i, (artist, album, year, genres, tracks, has_art) in enumerate(ALBUMS):
        folder = os.path.join(root, artist.replace('/', '-'), f'{album.replace("/", "-")} ({year})')
        os.makedirs(folder, exist_ok=True)
        for n, title in enumerate(tracks, 1):
            tags = [('ARTIST', artist), ('ALBUMARTIST', artist), ('ALBUM', album), ('TITLE', title),
                    ('DATE', str(year)), ('TRACKNUMBER', str(n))] + [('GENRE', g) for g in genres]
            with_tags(master, os.path.join(folder, f'{n:02d} - {title.replace("/", "-")}.flac'), tags)
        if has_art:
            art(os.path.join(folder, 'cover.jpg'), (500, 500), [album, artist], i)
    os.remove(master)


def make_tv(root):
    os.makedirs(root, exist_ok=True)
    master = os.path.join(root, '.clip.mp4')
    clip(master)
    for i, (title, year, genres, studio, plot, seasons, per, cast) in enumerate(SHOWS):
        folder = os.path.join(root, f'{title} ({year})')
        os.makedirs(folder, exist_ok=True)
        actors = ''.join(f'<actor><name>{esc(a)}</name><order>{k}</order></actor>' for k, a in enumerate(cast))
        with open(os.path.join(folder, 'tvshow.nfo'), 'w') as f:
            f.write(f'<?xml version="1.0" encoding="UTF-8"?><tvshow><title>{esc(title)}</title>'
                    f'<year>{year}</year><premiered>{year}-01-15</premiered><plot>{esc(plot)}</plot>'
                    + ''.join(f'<genre>{esc(g)}</genre>' for g in genres)
                    + f'<studio>{esc(studio)}</studio><mpaa>TV-14</mpaa>{actors}</tvshow>')
        art(os.path.join(folder, 'poster.jpg'), (400, 600), [title, str(year)], i + 7)
        art(os.path.join(folder, 'fanart.jpg'), (960, 540), [title], i + 7)
        for s in range(1, seasons + 1):
            art(os.path.join(folder, f'season{s:02d}-poster.jpg'), (400, 600), [title, f'Season {s}'], i * 3 + s)
            sfolder = os.path.join(folder, f'Season {s:02d}')
            os.makedirs(sfolder, exist_ok=True)
            for e in range(1, per + 1):
                base = os.path.join(sfolder, f'{title} S{s:02d}E{e:02d}')
                shutil.copy(master, base + '.mp4')
                with open(base + '.nfo', 'w') as f:
                    f.write(f'<?xml version="1.0" encoding="UTF-8"?><episodedetails>'
                            f'<title>Episode {e} of season {s}</title><season>{s}</season><episode>{e}</episode>'
                            f'<plot>{esc(title)}: chapter {e} of season {s}.</plot>'
                            f'<aired>{year + s - 1}-0{e}-10</aired><runtime>42</runtime></episodedetails>')
    os.remove(master)


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    make_music(os.path.join(OUT, 'music'))
    make_tv(os.path.join(OUT, 'tv'))
    print(f'wrote {OUT}: {len(ALBUMS)} albums, {len(SHOWS)} TV shows')


if __name__ == '__main__':
    main()
