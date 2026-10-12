"""Listados HTML de medios sin RSS ni sitemap utilizable. Solo título, autor y link del listado."""
from __future__ import annotations

from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..modelos import Nota, Resultado
from ..texto import limpiar
from . import parser_html


def parsear_tiempoar(soup: BeautifulSoup, url_base: str, fuente: dict) -> List[Nota]:
    notas, vistos = [], set()
    for art in soup.select("div.article-preview"):
        a = art.select_one(".title a[href]")
        if a is None:
            continue
        url = urljoin(url_base, a["href"])
        if url in vistos:
            continue
        vistos.add(url)
        volanta = art.select_one(".category-title h4")
        autor = art.select_one(".author a")
        notas.append(Nota(
            url=url, titulo=limpiar(a.get_text(" ")), medio=fuente["medio"], fuente_id=fuente["id"],
            categoria=fuente["categoria"], fecha=None,  # el listado no trae fecha: vale "visto por primera vez"
            autor=limpiar(autor.get_text(" ")) if autor else "",
            seccion=limpiar(volanta.get_text(" ")) if volanta else "Política",
        ))
    return notas


@parser_html("tiempoar_seccion")
def tiempoar_seccion(cliente, feed, fuente, ctx) -> Resultado:
    soup = BeautifulSoup(cliente.get(feed["url"]).content, "html.parser")
    notas = parsear_tiempoar(soup, feed["url"], fuente)
    return Resultado(notas=notas, leidos=len(notas))
