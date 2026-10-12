"""Colectores por tipo de feed. Cada uno recibe (cliente, feed, fuente, ctx) y devuelve un Resultado."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict

from ..http import Cliente
from ..modelos import Resultado


@dataclass
class Contexto:
    ahora: datetime  # aware, UTC
    desde: datetime  # aware, UTC: notas anteriores se descartan


Colector = Callable[[Cliente, dict, dict, Contexto], Resultado]

PARSERS_HTML: Dict[str, Colector] = {}


def parser_html(nombre: str):
    def registrar(fn: Colector) -> Colector:
        PARSERS_HTML[nombre] = fn
        return fn
    return registrar


def colector_para(feed: dict) -> Colector:
    from . import medios_html, oficiales, rss, sitemap  # noqa: F401  (registran sus parsers)

    tipo = feed["tipo"]
    if tipo == "rss":
        return rss.recolectar
    if tipo == "sitemap":
        return sitemap.recolectar
    if tipo == "html":
        try:
            return PARSERS_HTML[feed["parser"]]
        except KeyError:
            raise ValueError(f"parser HTML desconocido: {feed.get('parser')}") from None
    raise ValueError(f"tipo de feed desconocido: {tipo}")
