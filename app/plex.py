"""Cliente mínimo para Plex Media Server + proveedor de metadatos de Plex (metadata.provider.plex.tv).

El proveedor de metadatos es lo que permite saber el TOTAL real de episodios de una temporada
(y sus fechas de emisión), no solo los que hay en disco -> así se distingue "1 capítulo" de
"temporada completa" sin necesitar API keys de TMDB/TVDB.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

PROVIDER = "https://metadata.provider.plex.tv"


class PlexClient:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self.headers = {"X-Plex-Token": token, "Accept": "application/json",
                        "X-Plex-Client-Identifier": "plex-notify", "X-Plex-Product": "plex-notify"}
        self.client = httpx.AsyncClient(timeout=30, headers=self.headers)
        self._machine_id: str | None = None
        self._provider_cache: dict[str, tuple[float, Any]] = {}

    async def _get(self, path: str, params: dict | None = None, base: str | None = None) -> dict:
        r = await self.client.get((base or self.url) + path, params=params)
        r.raise_for_status()
        return r.json().get("MediaContainer", {})

    async def machine_id(self) -> str:
        if not self._machine_id:
            self._machine_id = (await self._get("/identity")).get("machineIdentifier", "")
        return self._machine_id

    async def server_info(self) -> dict:
        return await self._get("/")

    async def sections(self) -> list[dict]:
        return (await self._get("/library/sections")).get("Directory", [])

    async def items_added_since(self, section: str, plex_type: int, since: int) -> list[dict]:
        """type 1 = película, 4 = episodio. Devuelve los ítems con addedAt >= since."""
        out, start, size = [], 0, 200
        while True:
            # Plex usa la sintaxis `addedAt>>=VALOR` (operador ">>" + "="): la clave es "addedAt>>".
            d = await self._get(f"/library/sections/{section}/all", {
                "type": plex_type, "sort": "addedAt:desc", "addedAt>>": int(since),
                "X-Plex-Container-Start": start, "X-Plex-Container-Size": size})
            batch = d.get("Metadata", [])
            fresh = [m for m in batch if (m.get("addedAt") or 0) >= since]
            out.extend(fresh)
            # orden descendente: si aparece algo más viejo que `since`, no hay más páginas útiles
            if len(batch) < size or len(fresh) < len(batch):
                return out
            start += size

    async def recent(self, section: str, plex_type: int, limit: int = 60) -> list[dict]:
        d = await self._get(f"/library/sections/{section}/all", {
            "type": plex_type, "sort": "addedAt:desc",
            "X-Plex-Container-Start": 0, "X-Plex-Container-Size": limit})
        return d.get("Metadata", [])

    async def metadata(self, rating_key: str | int) -> dict | None:
        try:
            md = (await self._get(f"/library/metadata/{rating_key}")).get("Metadata", [])
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        return md[0] if md else None

    async def children(self, rating_key: str | int) -> list[dict]:
        return (await self._get(f"/library/metadata/{rating_key}/children")).get("Metadata", [])

    async def image(self, thumb: str | None, width: int = 600, height: int = 900) -> bytes | None:
        if not thumb:
            return None
        try:
            r = await self.client.get(self.url + "/photo/:/transcode", params={
                "width": width, "height": height, "minSize": 1, "upscale": 1, "url": thumb})
            r.raise_for_status()
            return r.content
        except httpx.HTTPError:
            return None

    # ---------------- proveedor de metadatos (totales reales) ----------------
    async def _provider(self, path: str) -> dict | None:
        hit = self._provider_cache.get(path)
        if hit and time.time() - hit[0] < 6 * 3600:
            return hit[1]
        # El proveedor pagina de a 20 por defecto y rechaza (400/403) tamaños > ~200: paginar por headers.
        d, start, size = None, 0, 200
        try:
            while True:
                r = await self.client.get(PROVIDER + path, headers={
                    "X-Plex-Container-Start": str(start), "X-Plex-Container-Size": str(size)})
                r.raise_for_status()
                page = r.json().get("MediaContainer", {})
                if d is None:
                    d = page
                else:
                    d.setdefault("Metadata", []).extend(page.get("Metadata", []))
                got = len(page.get("Metadata", []))
                start += got
                if got == 0 or start >= int(page.get("totalSize") or 0):
                    break
        except (httpx.HTTPError, ValueError):
            d = None
        self._provider_cache[path] = (time.time(), d)
        return d

    async def provider_seasons(self, show_guid: str | None) -> dict[int, dict] | None:
        """{season_index: {'ratingKey', 'leafCount'}} desde el proveedor, o None si la serie no está identificada."""
        if not show_guid or not show_guid.startswith("plex://show/"):
            return None
        d = await self._provider(f"/library/metadata/{show_guid.rsplit('/', 1)[1]}/children")
        if not d:
            return None
        return {s["index"]: s for s in d.get("Metadata", []) if "index" in s}

    async def provider_episodes(self, season_rating_key: str) -> list[dict] | None:
        d = await self._provider(f"/library/metadata/{season_rating_key}/children")
        return None if d is None else d.get("Metadata", [])

    async def shared_users(self) -> list[dict]:
        """Usuarios con quienes compartes el servidor (plex.tv), con su correo y las bibliotecas a las que tienen acceso."""
        machine = await self.machine_id()
        hdr = {"X-Plex-Token": self.token, "X-Plex-Client-Identifier": "plex-notify", "Accept": "application/xml"}
        async with httpx.AsyncClient(timeout=30, headers=hdr) as c:
            users = ET.fromstring((await c.get("https://plex.tv/api/users")).raise_for_status().text)
            shared = ET.fromstring((await c.get(f"https://plex.tv/api/servers/{machine}/shared_servers"))
                                   .raise_for_status().text)
        access = {}
        for ss in shared.findall("SharedServer"):
            access[ss.get("userID")] = {
                "all": ss.get("allLibraries") == "1",
                "sections": [x.get("key") for x in ss.findall("Section") if x.get("shared") == "1"],
                "accepted": ss.get("accepted") != "0"}
        out = []
        for u in users.findall("User"):
            srv = next((x for x in u.findall("Server") if x.get("machineIdentifier") == machine), None)
            if srv is None:
                continue  # no comparte este servidor
            a = access.get(u.get("id"), {"all": srv.get("allLibraries") == "1", "sections": [], "accepted": True})
            out.append({"id": u.get("id"), "username": u.get("username") or u.get("title"),
                        "title": u.get("title"), "email": u.get("email") or "", "thumb": u.get("thumb"),
                        "all_libraries": a["all"], "sections": a["sections"],
                        "pending": srv.get("pending") == "1"})
        return sorted(out, key=lambda x: x["username"].lower())

    def web_link(self, machine_id: str, rating_key: str | int) -> str:
        return (f"https://app.plex.tv/desktop/#!/server/{machine_id}/details?"
                f"key=%2Flibrary%2Fmetadata%2F{rating_key}")
