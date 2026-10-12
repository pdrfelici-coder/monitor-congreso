"""Sitemaps de Google News: loc + news:title + news:publication_date. No traen bajada ni autor."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ..modelos import Nota, Resultado
from ..texto import a_utc, limpiar, seccion_desde_url

NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
}


def parsear(contenido: bytes, fuente: dict) -> list:
    raiz = ET.fromstring(contenido)
    if not raiz.tag.endswith("urlset"):
        raise ValueError(f"no es un urlset: {raiz.tag}")
    notas = []
    for u in raiz.findall("sm:url", NS):
        url = (u.findtext("sm:loc", "", NS) or "").strip()
        titulo = limpiar(u.findtext("news:news/news:title", "", NS))
        if not url or not titulo:
            continue
        fecha = a_utc(u.findtext("news:news/news:publication_date", "", NS)
                      or u.findtext("sm:lastmod", "", NS))
        notas.append(Nota(
            url=url, titulo=titulo, medio=fuente["medio"], fuente_id=fuente["id"],
            categoria=fuente["categoria"], fecha=fecha, seccion=seccion_desde_url(url),
        ))
    return notas


def recolectar(cliente, feed, fuente, ctx) -> Resultado:
    notas = parsear(cliente.get(feed["url"]).content, fuente)
    # En sitemaps una nota sin fecha no se puede ubicar en el tiempo: se descarta.
    vigentes = [n for n in notas if n.fecha is not None and n.fecha >= ctx.desde]
    return Resultado(notas=vigentes, leidos=len(notas))
