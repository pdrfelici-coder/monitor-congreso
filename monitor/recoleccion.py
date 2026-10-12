"""Corre todas las fuentes en paralelo (el ritmo por dominio lo controla el Cliente) y junta resultados."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

from .colectores import Contexto, colector_para
from .http import Cliente
from .modelos import EstadoFuente, EventoAgenda, Nota
from .texto import normalizar_url

log = logging.getLogger(__name__)


def cargar_fuentes(ruta: Path) -> List[dict]:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    return [f for f in datos["fuentes"] if f.get("activa", True)]


def correr_fuente(cliente: Cliente, fuente: dict, ctx: Contexto) -> Tuple[List[Nota], List[EventoAgenda], EstadoFuente]:
    inicio = time.monotonic()
    estado = EstadoFuente(fuente["id"], fuente["medio"], "ok")
    notas: List[Nota] = []
    agenda: List[EventoAgenda] = []
    fallidos, leidos = 0, 0
    for feed in fuente["feeds"]:
        try:
            res = colector_para(feed)(cliente, feed, fuente, ctx)
        except Exception as e:  # noqa: BLE001 — una fuente rota no debe frenar al resto
            fallidos += 1
            estado.errores.append(f"{feed.get('url')}: {type(e).__name__}: {e}"[:300])
            log.warning("[%s] falló %s: %s", fuente["id"], feed.get("url"), e)
            continue
        notas += res.notas
        agenda += res.agenda
        leidos += res.leidos
    if fallidos == len(fuente["feeds"]):
        estado.estado = "error"
    elif fallidos:
        estado.estado = "parcial"
    elif leidos == 0:
        estado.estado = "vacia"
        estado.errores.append("no se leyó ningún ítem (¿cambió el formato?)")
    estado.items = len(notas) + len(agenda)
    estado.segundos = time.monotonic() - inicio
    return notas, agenda, estado


def unificar(notas: List[Nota]) -> List[Nota]:
    """Una nota por URL; si llegó por RSS y por sitemap, completa los campos vacíos."""
    por_url: Dict[str, Nota] = {}
    for n in notas:
        clave = normalizar_url(n.url)
        previa = por_url.get(clave)
        if previa is None:
            por_url[clave] = n
            continue
        for campo in ("bajada", "autor", "seccion", "fecha"):
            if not getattr(previa, campo) and getattr(n, campo):
                setattr(previa, campo, getattr(n, campo))
    return list(por_url.values())


def recolectar(fuentes: List[dict], ctx: Contexto, cliente: Cliente, hilos: int = 8):
    notas: List[Nota] = []
    agenda: List[EventoAgenda] = []
    estados: List[EstadoFuente] = []
    with ThreadPoolExecutor(max_workers=hilos) as ex:
        for n, a, e in ex.map(lambda f: correr_fuente(cliente, f, ctx), fuentes):
            notas += n
            agenda += a
            estados.append(e)
    return unificar(notas), agenda, estados
