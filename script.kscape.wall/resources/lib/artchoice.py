"""Artwork a scraper offered for an item, from the XML Kodi keeps beside it (pure parsing).

Kodi stores the choices as <thumb aspect="poster" preview="...">url</thumb> elements and
<fanart><thumb preview="...">file</thumb></fanart>; the art actually in use is a separate record
reached through JSON-RPC. Each candidate is (art type, url, preview url).
"""
import re
import xml.etree.ElementTree as ET

# Aspects a scraper names, as the art type Kodi stores them under.
ASPECTS = {'poster': 'poster', 'banner': 'banner', 'landscape': 'landscape', 'clearlogo': 'clearlogo',
           'logo': 'clearlogo', 'clearart': 'clearart', 'discart': 'discart', 'disc': 'discart',
           'keyart': 'keyart', 'thumb': 'thumb', 'cover': 'thumb', 'fanart': 'fanart',
           'back': 'back', 'spine': 'spine'}


def _root(text):
    text = re.sub(r'<\?xml[^>]*\?>', '', text or '').strip()
    if not text:
        return None
    try:
        return ET.fromstring(f'<r>{text}</r>')
    except ET.ParseError:
        return None


def parse_thumbs(text, season=None):
    """[(art type, url, preview)] from a <thumb> list. A thumb without an aspect is a poster.
    Season thumbs (type="season") are only returned for that `season`, and only then."""
    root = _root(text)
    out = []
    for t in root.iter('thumb') if root is not None else ():
        url = (t.text or '').strip()
        if not url:
            continue
        if (t.get('type') == 'season') != (season is not None):
            continue
        if season is not None and str(t.get('season')) != str(season):
            continue
        aspect = (t.get('aspect') or 'poster').lower()
        out.append((ASPECTS.get(aspect, aspect), url, t.get('preview') or url))
    return out


def parse_fanart(text):
    """[(fanart, url, preview)]: a <fanart url="base"><thumb preview="p">file</thumb></fanart> list."""
    root = _root(text)
    out = []
    for fan in root.iter('fanart') if root is not None else ():
        base = fan.get('url') or ''
        for t in fan.iter('thumb'):
            name = (t.text or '').strip()
            if not name:
                continue
            url = name if '://' in name else base + name
            preview = t.get('preview') or ''
            out.append(('fanart', url, (base + preview) if preview and '://' not in preview else (preview or url)))
    return out


def candidates(arttype, thumbs_xml='', fanart_xml='', season=None):
    """The urls on offer for `arttype`, first seen first, without repeats: [(url, preview)]."""
    pool = parse_thumbs(thumbs_xml, season) + parse_fanart(fanart_xml)
    seen, out = set(), []
    for kind, url, preview in pool:
        if kind == arttype and url not in seen:
            seen.add(url)
            out.append((url, preview))
    return out
