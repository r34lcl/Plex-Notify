"""Traducciones. El texto base está en español y sirve de clave; EN lo traduce al inglés.
Si falta una traducción se usa el español (nunca falla).

El idioma activo es por contexto (asyncio/hilos): la web usa el de la configuración y los avisos también.
"""
from __future__ import annotations

from contextvars import ContextVar

from .i18n_en import EN

LANGS = ("es", "en")
_lang: ContextVar[str] = ContextVar("lang", default="es")


def set_lang(lang: str | None) -> None:
    _lang.set(lang if lang in LANGS else "es")


def get_lang() -> str:
    return _lang.get()


def _(text: str, **kw) -> str:
    out = EN.get(text, text) if _lang.get() == "en" else text
    if kw:
        try:
            out = out.format(**kw)
        except (KeyError, IndexError, ValueError):
            out = text.format(**kw)
    return out
