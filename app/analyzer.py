"""Convierte un grupo de ítems recién agregados en un "evento" con significado:
1 episodio / varios / temporada completa agregada / temporada completada con este episodio /
varias temporadas / serie nueva / serie completa / película.
"""
from __future__ import annotations

import datetime as dt

from . import db
from .plex import PlexClient


def _res_label(media: list[dict] | None) -> list[str]:
    out = []
    for m in media or []:
        r = str(m.get("videoResolution") or "").lower()
        if not r:
            continue
        label = {"4k": "4K", "sd": "SD"}.get(r, f"{r}p" if r.isdigit() else r.upper())
        if label not in out:
            out.append(label)
    return out


def _size(media: list[dict] | None) -> int:
    return sum(p.get("size", 0) for m in media or [] for p in m.get("Part", []))


def _today() -> str:
    return dt.date.today().isoformat()


async def build_show_event(plex: PlexClient, show_key: str, items: list[dict], settings: dict) -> dict | None:
    show = await plex.metadata(show_key)
    if not show:
        return None
    machine = await plex.machine_id()
    local_seasons = {s.get("index"): s for s in await plex.children(show_key)}
    provider_seasons = await plex.provider_seasons(show.get("guid"))

    batch_keys = {i["rating_key"] for i in items}
    by_season: dict[int, list[dict]] = {}
    for i in items:
        by_season.setdefault(i["season_index"] if i["season_index"] is not None else -1, []).append(i)

    seasons_out = []
    total_eps = 0
    all_res: list[str] = []
    size = 0
    for s_idx in sorted(by_season):
        lseason = local_seasons.get(s_idx)
        if not lseason:
            continue
        local_eps = await plex.children(lseason["ratingKey"])
        local_by_key = {e["ratingKey"]: e for e in local_eps}
        local_indexes = {e.get("index") for e in local_eps if e.get("index") is not None}

        batch_eps = []
        for i in by_season[s_idx]:
            e = local_by_key.get(i["rating_key"])
            if not e:
                continue  # se borró antes de notificar
            replacement = db.previously_notified(show_key, s_idx, e.get("index"), list(batch_keys))
            res = _res_label(e.get("Media"))
            for r in res:
                if r not in all_res:
                    all_res.append(r)
            size += _size(e.get("Media"))
            batch_eps.append({
                "rating_key": e["ratingKey"], "index": e.get("index"), "title": e.get("title"),
                "aired": e.get("originallyAvailableAt"), "duration": e.get("duration"),
                "summary": e.get("summary"), "resolutions": res, "replacement": replacement,
                "thumb": e.get("thumb"),
            })
        if not settings.get("notify_replacements"):
            batch_eps = [e for e in batch_eps if not e["replacement"]]
        if not batch_eps:
            continue
        batch_eps.sort(key=lambda e: (e["index"] is None, e["index"] or 0))

        total = aired_total = None
        missing: list[int] = []
        pseason = (provider_seasons or {}).get(s_idx)
        if pseason and s_idx != 0:
            total = pseason.get("leafCount")
            peps = await plex.provider_episodes(pseason["ratingKey"]) or []
            if peps:
                total = len(peps)
                aired_idx = [e["index"] for e in peps
                             if e.get("originallyAvailableAt") and e["originallyAvailableAt"] <= _today()]
                aired_total = len(aired_idx)
                missing = sorted(set(aired_idx) - local_indexes)
                expected = {e["index"] for e in peps}
            else:
                expected = set(range(1, (total or 0) + 1))
        else:
            expected = set()

        complete = bool(expected) and expected <= local_indexes
        batch_idx = {e["index"] for e in batch_eps}
        full_in_batch = complete and expected <= batch_idx
        caught_up = (not complete and aired_total is not None and aired_total > 0 and not missing)

        if full_in_batch:
            kind = "season_full"
        elif complete:
            kind = "season_completed"
        elif len(batch_eps) == 1:
            kind = "episode"
        else:
            kind = "episodes"

        total_eps += len(batch_eps)
        seasons_out.append({
            "index": s_idx, "title": lseason.get("title"), "thumb": lseason.get("thumb"),
            "rating_key": lseason["ratingKey"], "summary": lseason.get("summary"),
            "episodes": batch_eps, "in_plex": len(local_indexes), "total": total,
            "aired_total": aired_total, "missing": missing, "complete": complete,
            "caught_up": caught_up, "kind": kind,
            "link": plex.web_link(machine, lseason["ratingKey"]),
        })

    if not seasons_out:
        return None

    show_leaf = show.get("leafCount") or 0
    is_new_show = show_leaf <= len(batch_keys)
    real_seasons = [s for s in seasons_out if s["index"] != 0]
    all_local_seasons = [i for i in local_seasons if i not in (0, None)]
    series_full = (is_new_show and len(real_seasons) >= 1
                   and all(s["kind"] == "season_full" for s in real_seasons)
                   and len(real_seasons) == len(all_local_seasons)
                   and provider_seasons is not None
                   and len([i for i in provider_seasons if i != 0]) == len(real_seasons))

    if series_full and len(real_seasons) > 1:
        kind = "series_full"
    elif len(seasons_out) > 1:
        kind = "multi_season"
    else:
        kind = seasons_out[0]["kind"]

    genres = [g["tag"] for g in show.get("Genre", [])][:3]
    return {
        "type": "show", "kind": kind, "section": str(show.get("librarySectionID") or ""), "is_new_show": is_new_show, "series_full": series_full,
        "identified": provider_seasons is not None,
        "show": {
            "rating_key": show["ratingKey"], "title": show.get("title"), "year": show.get("year"),
            "summary": show.get("summary"), "thumb": show.get("thumb"), "studio": show.get("studio"),
            "genres": genres, "library": show.get("librarySectionTitle"),
            "content_rating": show.get("contentRating"), "seasons_in_plex": len(all_local_seasons),
            "link": plex.web_link(machine, show["ratingKey"]),
        },
        "seasons": seasons_out, "episode_count": total_eps,
        "resolutions": all_res, "size": size,
        "rating_keys": [e["rating_key"] for s in seasons_out for e in s["episodes"]],
    }


async def build_movie_event(plex: PlexClient, rating_key: str) -> dict | None:
    m = await plex.metadata(rating_key)
    if not m:
        return None
    machine = await plex.machine_id()
    return {
        "type": "movie", "kind": "movie", "section": str(m.get("librarySectionID") or ""),
        "movie": {
            "rating_key": m["ratingKey"], "title": m.get("title"), "year": m.get("year"),
            "original_title": m.get("originalTitle"), "tagline": m.get("tagline"),
            "summary": m.get("summary"), "thumb": m.get("thumb"), "duration": m.get("duration"),
            "genres": [g["tag"] for g in m.get("Genre", [])][:3],
            "directors": [d["tag"] for d in m.get("Director", [])][:2],
            "rating": m.get("audienceRating") or m.get("rating"),
            "content_rating": m.get("contentRating"), "studio": m.get("studio"),
            "library": m.get("librarySectionTitle"), "resolutions": _res_label(m.get("Media")),
            "size": _size(m.get("Media")), "link": plex.web_link(machine, m["ratingKey"]),
        },
        "rating_keys": [m["ratingKey"]],
    }
