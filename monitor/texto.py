"""Utilidades de texto, URLs y fechas usadas por colectores, filtro y deduplicación."""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dateutil import parser as dateparser
from zoneinfo import ZoneInfo

TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")

MAX_BAJADA = 300  # caracteres: alcanza para una bajada y evita guardar cuerpos de nota

_PARAMS_TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|mc_\w+|ref|outputType|cid|at_\w+)$", re.I)

MESES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"], start=1)}
MESES["setiembre"] = 9


def limpiar(texto: Optional[str]) -> str:
    """Saca HTML, decodifica entidades y colapsa espacios."""
    if not texto:
        return ""
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = html.unescape(texto)
    return re.sub(r"\s+", " ", texto).strip()


def recortar(texto: str, maximo: int = MAX_BAJADA) -> str:
    texto = limpiar(texto)
    if len(texto) <= maximo:
        return texto
    corte = texto.rfind(" ", 0, maximo)
    return texto[: corte if corte > maximo // 2 else maximo].rstrip(" ,.;:") + "…"


def normalizar_url(url: str) -> str:
    """Clave canónica de una URL: sin tracking, sin fragmento, host en minúscula, sin barra final."""
    p = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _PARAMS_TRACKING.match(k)]
    path = p.path.rstrip("/") or "/"
    host = p.netloc.lower()
    return urlunsplit(("https", host, path, urlencode(query), ""))


def seccion_desde_url(url: str) -> str:
    """Primer segmento del path si parece una sección (no un año ni un slug largo)."""
    segs = [s for s in urlsplit(url).path.split("/") if s]
    if len(segs) < 2:
        return ""
    s = segs[0]
    if s.isdigit() or len(s) > 30 or s in ("ta_article", "noticias", "nota", "notas", "amp"):
        return ""
    return s.replace("-", " ")


def a_utc(valor) -> Optional[datetime]:
    """Convierte string / struct_time / datetime a datetime aware en UTC. Sin tz se asume hora argentina."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        dt = valor
    elif hasattr(valor, "tm_year"):  # time.struct_time de feedparser, ya en UTC
        return datetime(*valor[:6], tzinfo=timezone.utc)
    else:
        try:
            dt = dateparser.parse(str(valor))
        except (ValueError, OverflowError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ_AR)
    return dt.astimezone(timezone.utc)


def fecha_es(texto: str) -> Optional[datetime]:
    """'06 de octubre de 2026' → datetime 00:00 hora argentina."""
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de|del)\s+(\d{4})", texto.lower())
    if not m or m.group(2) not in MESES:
        return None
    return datetime(int(m.group(3)), MESES[m.group(2)], int(m.group(1)), tzinfo=TZ_AR)


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
