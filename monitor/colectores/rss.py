"""RSS/Atom vía feedparser. Se toma título, resumen recortado, autor, fecha y categoría; nunca content:encoded."""
from __future__ import annotations

import feedparser

from ..modelos import Nota, Resultado
from ..texto import a_utc, limpiar, recortar, seccion_desde_url


def parsear(contenido: bytes, fuente: dict) -> list:
    d = feedparser.parse(contenido)
    if d.bozo and not d.entries:
        raise ValueError(f"feed ilegible: {d.bozo_exception!r}")
    notas = []
    for e in d.entries:
        url = e.get("link")
        titulo = limpiar(e.get("title"))
        if not url or not titulo:
            continue
        fecha = a_utc(e.get("published_parsed") or e.get("updated_parsed"))
        tags = [t.get("term") for t in e.get("tags", []) if t.get("term")]
        notas.append(Nota(
            url=url, titulo=titulo, medio=fuente["medio"], fuente_id=fuente["id"],
            categoria=fuente["categoria"], fecha=fecha,
            bajada=recortar(e.get("summary", "")),
            autor=limpiar(e.get("author", "")),
            seccion=limpiar(tags[0]) if tags else seccion_desde_url(url),
        ))
    return notas


def recolectar(cliente, feed, fuente, ctx) -> Resultado:
    notas = parsear(cliente.get(feed["url"]).content, fuente)
    vigentes = [n for n in notas if n.fecha is None or n.fecha >= ctx.desde]
    return Resultado(notas=vigentes, leidos=len(notas))
