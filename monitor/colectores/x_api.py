"""Módulo X/Twitter: SOLO la API oficial v2, nunca scraping. Desactivado por defecto.

Se activa si cuentas_x.yaml tiene `activo: true` Y existe la variable de entorno X_BEARER_TOKEN.
Usa búsqueda reciente (`from:cuenta1 OR from:cuenta2 ...`) en lotes, para gastar pocos requests.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Tuple

import httpx
import yaml

from ..modelos import EstadoFuente, Nota
from ..texto import a_utc, limpiar
from . import Contexto

log = logging.getLogger(__name__)

API = "https://api.x.com/2/tweets/search/recent"
MAX_QUERY = 512  # límite de largo de query del plan Basic; con Pro es 1024
MAX_PAGINAS = 5


def _lotes(cuentas: List[str], max_len: int = MAX_QUERY) -> List[str]:
    sufijo = " -is:retweet"
    lotes, actual = [], []
    for c in cuentas:
        candidata = " OR ".join(f"from:{x}" for x in actual + [c])
        if actual and len(f"({candidata}){sufijo}") > max_len:
            lotes.append(f"({' OR '.join(f'from:{x}' for x in actual)}){sufijo}")
            actual = []
        actual.append(c)
    if actual:
        lotes.append(f"({' OR '.join(f'from:{x}' for x in actual)}){sufijo}")
    return lotes


def recolectar(config_path: Path, ctx: Contexto) -> Tuple[List[Nota], EstadoFuente]:
    estado = EstadoFuente("x", "X/Twitter", "salteada")
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        estado.errores.append(f"no existe {config_path.name}")
        return [], estado
    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    if not cfg.get("activo"):
        estado.errores.append("desactivado en cuentas_x.yaml")
        return [], estado
    if not token:
        estado.errores.append("falta la variable de entorno X_BEARER_TOKEN")
        return [], estado

    cuentas = sorted({c["usuario"].lstrip("@") for grupo in (cfg.get("cuentas") or {}).values()
                      for c in (grupo or []) if c.get("usuario")})
    notas: List[Nota] = []
    estado.estado = "ok"
    with httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=30) as http:
        for query in _lotes(cuentas):
            params = {
                "query": query, "max_results": 100,
                "start_time": ctx.desde.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tweet.fields": "created_at,author_id", "expansions": "author_id",
                "user.fields": "username,name",
            }
            for _ in range(MAX_PAGINAS):
                try:
                    r = http.get(API, params=params)
                    r.raise_for_status()
                except httpx.HTTPError as e:
                    estado.estado = "parcial"
                    estado.errores.append(f"API X: {e}")
                    break
                datos = r.json()
                usuarios = {u["id"]: u for u in datos.get("includes", {}).get("users", [])}
                for t in datos.get("data", []):
                    u = usuarios.get(t["author_id"], {})
                    usuario = u.get("username", t["author_id"])
                    notas.append(Nota(
                        url=f"https://x.com/{usuario}/status/{t['id']}", titulo=limpiar(t["text"]),
                        medio="X", fuente_id="x", categoria="x", fecha=a_utc(t.get("created_at")),
                        autor=f"@{usuario}", seccion=u.get("name", ""),
                    ))
                siguiente = datos.get("meta", {}).get("next_token")
                if not siguiente:
                    break
                params["next_token"] = siguiente
    if estado.errores and not notas:
        estado.estado = "error"
    estado.items = len(notas)
    return notas, estado
