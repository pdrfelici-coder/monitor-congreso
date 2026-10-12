"""Filtro → agrupación en temas → clasificación → orden por cobertura."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .clasificar import Clasificador
from .dedup import UMBRAL, agrupar, calcular_idf, representante
from .filtro import Filtro, es_relevante
from .modelos import Nota, Tema


def filtrar(notas: List[Nota], filtro: Filtro) -> Tuple[List[Nota], Dict[str, List[str]]]:
    """Devuelve las notas relevantes y {url: términos que coincidieron}."""
    relevantes, terminos = [], {}
    for n in notas:
        ok, t = es_relevante(n, filtro)
        if ok:
            relevantes.append(n)
            terminos[n.url] = t
    return relevantes, terminos


def armar_temas(notas: List[Nota], clasificador: Clasificador, corpus: Optional[List[Nota]] = None,
                umbral: float = UMBRAL) -> List[Tema]:
    """`corpus` (todo lo recolectado, relevante o no) se usa para pesar las palabras."""
    temas = []
    idf = calcular_idf(corpus) if corpus else None
    for grupo in agrupar(notas, umbral=umbral, idf=idf):
        miembros = [notas[i] for i in grupo]
        rep = notas[representante(notas, grupo)]
        titulos = [n.titulo for n in miembros]
        resto = [n.bajada for n in miembros if n.bajada]
        temas.append(Tema(
            titulo=rep.titulo,
            camara=clasificador.camara(titulos + resto, [n.fuente_id for n in miembros]),
            tipo=clasificador.tipo(titulos, resto),
            proyecto=clasificador.proyecto(titulos + resto),
            # La nota representativa primero; el resto, de la más nueva a la más vieja.
            notas=[rep] + sorted((n for n in miembros if n is not rep),
                                 key=lambda n: n.fecha.timestamp() if n.fecha else 0, reverse=True),
        ))
    return ordenar(temas)


def ordenar(temas: List[Tema]) -> List[Tema]:
    """Más medios primero; a igualdad, más notas; después, lo más reciente."""
    def clave(t: Tema):
        ultima = max((n.fecha.timestamp() for n in t.notas if n.fecha), default=0)
        return (-t.n_medios, -len(t.notas), -ultima)
    return sorted(temas, key=clave)
