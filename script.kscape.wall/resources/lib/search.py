"""Library search scoped to one media kind (pure Python).

Matching ignores case, accents and punctuation. Results are ranked: titles that start with the
query, then titles with a word starting with it, then titles containing it anywhere, then items
matched only through a secondary field (cast, director, artist). Ties keep library order.
"""
import re
import unicodedata

from .media import Album, Show

_PUNCT = re.compile(r"[^\w\s]")


def fold(text):
    """'Amélie: Le Fabuleux' -> 'amelie le fabuleux'."""
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(_PUNCT.sub(' ', text.casefold()).split())


def fields(item):
    """(primary texts, secondary texts) searched for `item`."""
    if isinstance(item, Album):
        return [item.title, item.artist], list(item.artists) + sorted(item.genres)
    if isinstance(item, Show):
        return [item.title], list(item.cast)
    return [item.title], list(item.cast) + sorted(item.directors)


def _rank(query, texts):
    best = None
    for t in texts:
        f = fold(t)
        if not f:
            continue
        if f.startswith(query):
            r = 0
        elif (' ' + query) in (' ' + f):
            r = 1
        elif query in f:
            r = 2
        else:
            continue
        best = r if best is None else min(best, r)
    return best


def search(items, query):
    """Items matching `query`, best first. An empty query matches nothing."""
    q = fold(query)
    if not q:
        return []
    scored = []
    for i, item in enumerate(items):
        primary, secondary = fields(item)
        r = _rank(q, primary)
        if r is None:
            r = 3 if _rank(q, secondary) is not None else None
        if r is not None:
            scored.append((r, i, item))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [item for _, _, item in scored]
