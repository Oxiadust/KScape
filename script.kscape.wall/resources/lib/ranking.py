"""Deterministic, explainable relatedness ranking between movies, albums or TV shows (pure Python)."""

WEIGHTS = {
    'set': 100.0,        # same movie set / franchise
    'director': 40.0,    # per shared director, capped at one
    'actor': 20.0,       # per shared actor, scaled by billing position in both films
    'genre': 8.0,        # per shared genre
    'tag': 6.0,          # per shared tag
    'decade': 4.0,       # same release decade
    'year': 3.0,         # extra for close release years, fading over 6 years
}


def _billing(i):
    """Top-billed counts fully; later billing counts progressively less."""
    return 1.0 / (1.0 + 0.35 * i)


def score(a, b, weights=WEIGHTS):
    """Relatedness of b to anchor a. Higher is more related; 0 means unrelated."""
    s = 0.0
    if a.setid and a.setid == b.setid:
        s += weights['set']
    if a.directors & b.directors:
        s += weights['director']
    if a.cast and b.cast:
        index_b = {name: i for i, name in enumerate(b.cast)}
        for i, name in enumerate(a.cast):
            j = index_b.get(name)
            if j is not None:
                s += weights['actor'] * _billing(i) * _billing(j)
    s += weights['genre'] * len(a.genres & b.genres)
    s += weights['tag'] * len(a.tags & b.tags)
    if a.year and b.year:
        if a.year // 10 == b.year // 10:
            s += weights['decade']
        s += weights['year'] * max(0.0, 1.0 - abs(a.year - b.year) / 6.0)
    return s


def _era(a, b, weights):
    s = 0.0
    if a.year and b.year:
        if a.year // 10 == b.year // 10:
            s += weights['decade']
        s += weights['year'] * max(0.0, 1.0 - abs(a.year - b.year) / 6.0)
    return s


ALBUM_WEIGHTS = {
    'artist': 100.0,     # same album artist
    'shared': 40.0,      # an artist in common (collaborations, compilations)
    'genre': 10.0,       # per shared genre
    'style': 6.0,        # per shared style
    'decade': 4.0,
    'year': 3.0,
}


def album_score(a, b, weights=ALBUM_WEIGHTS):
    s = 0.0
    if a.artistsort and a.artistsort == b.artistsort:
        s += weights['artist']
    elif set(a.artists) & set(b.artists):
        s += weights['shared']
    s += weights['genre'] * len(a.genres & b.genres)
    s += weights['style'] * len(a.styles & b.styles)
    return s + _era(a, b, weights)


SHOW_WEIGHTS = {
    'studio': 20.0,      # same network or studio
    'actor': 20.0,       # per shared actor, scaled by billing
    'genre': 8.0,
    'decade': 4.0,
    'year': 3.0,
}


def show_score(a, b, weights=SHOW_WEIGHTS):
    s = 0.0
    if a.studios & b.studios:
        s += weights['studio']
    if a.cast and b.cast:
        index_b = {name: i for i, name in enumerate(b.cast)}
        for i, name in enumerate(a.cast):
            j = index_b.get(name)
            if j is not None:
                s += weights['actor'] * _billing(i) * _billing(j)
    s += weights['genre'] * len(a.genres & b.genres)
    return s + _era(a, b, weights)


def rank_related(anchor, movies, weights=None, score_fn=score):
    """All items except the anchor, most related first (`score_fn`: score, album_score or
    show_score; `weights` defaults to that function's own).

    Ties break on year distance, then sort title, then key, so the order is stable.
    """
    others = [m for m in movies if m.key != anchor.key]
    rate = (lambda m: score_fn(anchor, m)) if weights is None else (lambda m: score_fn(anchor, m, weights))
    return sorted(others, key=lambda m: (
        -round(rate(m), 6),
        abs((m.year or 0) - (anchor.year or 0)),
        m.sorttitle,
        m.key,
    ))
