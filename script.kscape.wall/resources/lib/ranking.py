"""Deterministic, explainable relatedness ranking between movies (pure Python)."""

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


def rank_related(anchor, movies, weights=WEIGHTS):
    """All movies except the anchor, most related first.

    Ties break on year distance, then sort title, then movie id, so the order is stable.
    """
    others = [m for m in movies if m.movieid != anchor.movieid]
    return sorted(others, key=lambda m: (
        -round(score(anchor, m, weights), 6),
        abs((m.year or 0) - (anchor.year or 0)),
        m.sorttitle,
        m.movieid,
    ))
