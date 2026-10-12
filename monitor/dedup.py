"""Agrupa notas que cuentan la misma noticia en "temas".

Las URLs ya llegan deduplicadas (recoleccion.unificar y la clave única de la base). Acá se
agrupa por similitud de contenido: TF-IDF sobre título (peso doble) y bajada, comparando cada
nota contra el centroide de cada tema ya formado. Comparar contra el centroide, y no contra
la nota más parecida, evita que se encadenen temas distintos a través de notas intermedias.
Además, dos títulos casi idénticos (fuzzy >= 85) se unen siempre, aunque no haya bajada.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Dict, List, Optional, Sequence

from rapidfuzz import fuzz

from .filtro import normalizar
from .modelos import Nota

UMBRAL = 0.16  # se puede cambiar en keywords.yaml → agrupamiento.umbral
UMBRAL_TITULO = 85

STOPWORDS = set("""
de la el los las un una unos unas y o u e en a al del por para con sin que se su sus lo le les
es son fue ser era como mas pero ya tras sobre entre hasta desde ante segun contra durante este
esta estos estas ese esa eso esos esas aquel hay no si muy tambien cual cuales cuando donde quien
quienes porque nos mi tu ha han habia tiene tienen todo todos toda todas otro otra otros otras
asi ahora hoy ayer manana dia semana cada uno dos tres qué cómo dijo afirmo aseguro
""".split())


def tokens(texto: str) -> List[str]:
    salida = []
    for t in normalizar(texto).split():
        if t in STOPWORDS or (len(t) < 3 and not t.isdigit()):
            continue
        if len(t) > 4 and t.endswith("s"):  # plural simple: diputados ~ diputado
            t = t[:-1]
        salida.append(t)
    return salida


def _tf(nota: Nota) -> Counter:
    c = Counter()
    for t in tokens(nota.titulo):
        c[t] += 2
    for t in tokens(nota.bajada):
        c[t] += 1
    return c


def _norma(v: Dict[str, float]) -> float:
    return math.sqrt(sum(x * x for x in v.values())) or 1.0


def _coseno(a: Dict[str, float], b: Dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items()) / (_norma(a) * _norma(b))


def calcular_idf(corpus: Sequence[Nota]) -> Dict[str, float]:
    """IDF sobre un corpus amplio (idealmente todo lo recolectado, no solo lo relevante):
    así "diputados" o "gobierno" pesan poco y los nombres propios y temas concretos pesan más."""
    df = Counter(t for n in corpus for t in set(_tf(n)))
    total = len(corpus)
    return {t: math.log((1 + total) / (1 + d)) + 1 for t, d in df.items()}


def agrupar(notas: Sequence[Nota], umbral: float = UMBRAL, umbral_titulo: int = UMBRAL_TITULO,
            idf: Optional[Dict[str, float]] = None) -> List[List[int]]:
    """Devuelve grupos de índices de `notas`. Procesa en orden cronológico para que sea estable."""
    tfs = [_tf(n) for n in notas]
    idf = idf or calcular_idf(notas)
    maximo = max(idf.values(), default=1.0)  # término nunca visto en el corpus: peso máximo
    total = len(notas)
    vectores = [{t: f * idf.get(t, maximo) for t, f in tf.items()} for tf in tfs]
    titulos = [" ".join(tokens(n.titulo)) for n in notas]

    orden = sorted(range(total), key=lambda i: (notas[i].fecha is None, notas[i].fecha or 0, i))
    grupos: List[List[int]] = []
    centroides: List[Dict[str, float]] = []
    for i in orden:
        mejor, mejor_sim = -1, 0.0
        for g, centro in enumerate(centroides):
            sim = _coseno(vectores[i], centro)
            if sim < umbral and any(fuzz.token_set_ratio(titulos[i], titulos[j]) >= umbral_titulo
                                    for j in grupos[g]):
                sim = 1.0
            if sim > mejor_sim:
                mejor, mejor_sim = g, sim
        if mejor >= 0 and mejor_sim >= umbral:
            grupos[mejor].append(i)
            for t, x in vectores[i].items():
                centroides[mejor][t] = centroides[mejor].get(t, 0.0) + x
        else:
            grupos.append([i])
            centroides.append(dict(vectores[i]))
    return grupos


def representante(notas: Sequence[Nota], grupo: Sequence[int]) -> int:
    """La nota del grupo más cercana al centro: su título se usa como título del tema."""
    if len(grupo) == 1:
        return grupo[0]
    vect = {i: {t: float(f) for t, f in _tf(notas[i]).items()} for i in grupo}
    centro: Dict[str, float] = {}
    for v in vect.values():
        for t, x in v.items():
            centro[t] = centro.get(t, 0.0) + x
    return max(grupo, key=lambda i: (_coseno(vect[i], centro), notas[i].categoria != "oficial"))
