"""Bucle de detección: consulta Plex, guarda ítems nuevos, espera a que la "subida" termine
(quiet_seconds sin nuevos ítems de esa serie) y recién ahí arma y envía UNA notificación por serie."""
from __future__ import annotations

import asyncio
import logging
import time

from . import analyzer, db, notifiers, render
from .i18n import set_lang
from .plex import PlexClient

log = logging.getLogger("plex-notify")
OVERLAP = 120  # s de solapamiento al consultar por addedAt


class Worker:
    def __init__(self, plex: PlexClient):
        self.plex = plex
        self.last_poll: float | None = None
        self.last_error: str | None = None
        self._wake = asyncio.Event()

    def wake(self):
        self._wake.set()

    async def sections(self, settings: dict) -> list[dict]:
        secs = [s for s in await self.plex.sections() if s["type"] in ("movie", "show")]
        if settings["sections"]:
            secs = [s for s in secs if s["key"] in settings["sections"]]
        return secs

    async def poll(self) -> int:
        settings = db.get_settings()
        new = 0
        for sec in await self.sections(settings):
            key = sec["key"]
            wm = db.get_state(f"wm.{key}")
            if wm is None:
                # primer arranque: no notificar el historial, partir desde "ahora"
                db.set_state(f"wm.{key}", int(time.time()))
                log.info("biblioteca %s (%s): marca inicial creada", sec["title"], key)
                continue
            ptype = 1 if sec["type"] == "movie" else 4
            items = await self.plex.items_added_since(key, ptype, wm - OVERLAP)
            rows = []
            for it in items:
                if ptype == 1:
                    rows.append({"rating_key": it["ratingKey"], "section": key, "kind": "movie",
                                 "group_key": f"movie:{it['ratingKey']}", "show_guid": None,
                                 "season_index": None, "episode_index": None, "added_at": it.get("addedAt")})
                else:
                    rows.append({"rating_key": it["ratingKey"], "section": key, "kind": "episode",
                                 "group_key": f"show:{it['grandparentRatingKey']}",
                                 "show_guid": it["grandparentRatingKey"],
                                 "season_index": it.get("parentIndex"), "episode_index": it.get("index"),
                                 "added_at": it.get("addedAt")})
            n = db.mark_seen(rows)
            if n:
                log.info("%s: %d ítems nuevos", sec["title"], n)
            new += n
            if items:
                db.set_state(f"wm.{key}", max(wm, max(i.get("addedAt", 0) for i in items)))
        return new

    async def flush(self, force: bool = False) -> list[int]:
        settings = db.get_settings()
        sent = []
        for g in db.pending_groups():
            if not force and time.time() - g["last_seen"] < settings["quiet_seconds"]:
                continue
            items = db.pending_items(g["group_key"])
            keys = [i["rating_key"] for i in items]
            if g["kind"] == "movie":
                ev = await analyzer.build_movie_event(self.plex, keys[0])
            else:
                ev = await analyzer.build_show_event(self.plex, g["group_key"].split(":", 1)[1], items, settings)
            if not ev:
                db.drop_seen(keys) if g["kind"] == "movie" else db.assign(keys, 0)
                continue
            nid = await self.send_event(ev, settings)
            db.assign(keys, nid)
            sent.append(nid)
        return sent

    async def deliver(self, ev: dict, settings: dict, only: str | None = None) -> tuple[dict, list[dict]]:
        msg = render.build(ev, settings["max_episode_list"])
        poster = await self.plex.image(msg["thumb"])
        results = await notifiers.dispatch(settings, msg, poster, only=only, section=ev.get("section"))
        for r in results:
            (log.info if r["ok"] else log.warning)("envío %s %s: %s", r["channel"], r.get("target", ""),
                                                  "ok" if r["ok"] else r["error"])
        return msg, results

    async def send_event(self, ev: dict, settings: dict, only: str | None = None, store: bool = True) -> int:
        msg, results = await self.deliver(ev, settings, only)
        if not store:
            return 0
        return db.add_notification(ev["kind"], msg["headline"], msg["title"], render.plain_text(msg), ev, results)

    async def refresh_users(self) -> list[dict]:
        users = await self.plex.shared_users()
        db.set_state("plex_users", users)
        db.set_state("plex_users_at", time.time())
        return users

    async def run(self):
        while True:
            settings = db.get_settings()
            set_lang(settings.get("language"))
            try:
                if time.time() - (db.get_state("plex_users_at", 0) or 0) > 6 * 3600:
                    await self.refresh_users()
            except Exception as e:  # noqa: BLE001
                log.warning("no se pudo leer usuarios de plex.tv: %s", e)
            try:
                await self.poll()
                await self.flush()
                self.last_error = None
            except Exception as e:  # noqa: BLE001
                self.last_error = f"{type(e).__name__}: {e}"
                log.exception("error en el ciclo")
            self.last_poll = time.time()
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=settings["poll_seconds"])
            except asyncio.TimeoutError:
                pass
