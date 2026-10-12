"""Parsers HTML de fuentes oficiales: agendas y prensa de ambas cámaras, y Boletín Oficial.

Son el último recurso (ninguna de estas fuentes tiene RSS) y dependen del HTML actual:
si un rediseño los rompe, el colector devuelve 0 ítems y el informe marca la fuente como "vacía".
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..modelos import EventoAgenda, Nota, Resultado
from ..texto import TZ_AR, a_utc, fecha_es, limpiar, recortar
from . import Contexto, parser_html

MAX_TEMARIO = 800  # temarios oficiales de sesión pueden ser largos


def _hoy_ar(ctx: Contexto) -> date:
    return ctx.ahora.astimezone(TZ_AR).date()


def _vigente_por_dia(fecha: Optional[datetime], ctx: Contexto) -> bool:
    """Para fuentes que solo publican la fecha (sin hora): vale el día calendario argentino."""
    return fecha is not None and fecha.astimezone(TZ_AR).date() >= ctx.desde.astimezone(TZ_AR).date()


def _tipo_evento(texto: str) -> str:
    t = texto.lower()
    if re.search(r"\bsesi[oó]n\b", t):
        return "sesion"
    if re.search(r"grupo parlamentario de amistad", t):
        return "otro"
    if re.search(r"comisi[oó]n|plenario|bicameral|audiencia p[uú]blica|reuni[oó]n informativa", t):
        return "comision"
    return "otro"


def _soup(cliente, url: str) -> BeautifulSoup:
    soup = BeautifulSoup(cliente.get(url).content, "html.parser")
    # El Senado responde 200 con una página de "Sitio Web en Mantenimiento" cuando está caído.
    if re.search(r"sitio web en mantenimiento", soup.get_text(" ")[:3000], re.I):
        raise ConnectionError("el sitio está en mantenimiento")
    return soup


# ---------------------------------------------------------------------------- Diputados
def parsear_hcdn_agenda(soup: BeautifulSoup, url_base: str) -> List[EventoAgenda]:
    tabla = soup.select_one("table#agendaComisiones")
    if tabla is None:
        return []
    eventos, dia = [], None
    for tr in tabla.find_all("tr"):
        th = tr.find("th")
        if th is not None:
            f = fecha_es(th.get_text(" ", strip=True))
            dia = f.date() if f else None
            continue
        celdas = tr.find_all("td", recursive=False)
        if dia is None or len(celdas) != 2:
            continue
        izq, der = celdas
        hora_el = izq.find("strong")
        hora = hora_el.get_text(strip=True) if hora_el else ""
        lugar = limpiar(izq.get_text(" ", strip=True).replace(hora, "", 1))
        suspendida = "suspendida" in lugar.lower()
        # Un plenario lista varias comisiones, cada una en su <a><strong>; si no hay, el órgano va en <h5>.
        comisiones = [limpiar(s.get_text(" ")).rstrip(", ") for s in der.select("a strong")]
        comisiones = [c for c in comisiones if c]
        textos_h5 = [limpiar(h.get_text(" ")) for h in der.find_all("h5") if h.get_text(strip=True)]
        if len(comisiones) > 1:
            organo = "Plenario: " + ", ".join(comisiones)
        else:
            organo = (comisiones or textos_h5 or ["Reunión"])[0]
        citacion = der.find("a", string=re.compile("citaci", re.I))
        temario = limpiar(der.get_text(" ", strip=True))
        for quitar in comisiones + textos_h5[:1] + ["ver citación"]:
            temario = temario.replace(quitar, "", 1)
        temario = temario.strip(" ,")
        if re.search(r"\bsesi[oó]n\b", organo, re.I):
            tipo = "sesion"
        elif "AMISTAD" in organo.upper():
            tipo = "otro"
        else:
            tipo = "comision"  # agenda de comisiones: el nombre ("PRESUPUESTO Y HACIENDA") no dice "comisión"
        eventos.append(EventoAgenda(
            camara="Diputados", fecha=dia, hora=hora, titulo=organo, tipo=tipo,
            fuente_id="hcdn_agenda", lugar=re.sub(r"(?i)\bsuspendida\b", "", lugar).strip(" -"),
            temario=recortar(temario, MAX_TEMARIO),
            url=urljoin(url_base, citacion["href"]) if citacion else url_base,
            suspendida=suspendida,
        ))
    return eventos


@parser_html("hcdn_agenda")
def hcdn_agenda(cliente, feed, fuente, ctx) -> Resultado:
    eventos = parsear_hcdn_agenda(_soup(cliente, feed["url"]), feed["url"])
    hoy = _hoy_ar(ctx)
    return Resultado(agenda=[e for e in eventos if e.fecha >= hoy], leidos=len(eventos))


def parsear_hcdn_prensa(soup: BeautifulSoup, url_base: str, fuente: dict) -> List[Nota]:
    notas = []
    for div in soup.select("div.noticia"):
        a = div.find("a", href=True)
        titulo = div.find("h3")
        if not a or not titulo:
            continue
        fecha_el = div.select_one("p.fecha")
        bajada_el = [p for p in div.find_all("p") if "fecha" not in (p.get("class") or [])]
        notas.append(Nota(
            url=urljoin(url_base, a["href"]), titulo=limpiar(titulo.get_text(" ")),
            medio=fuente["medio"], fuente_id=fuente["id"], categoria=fuente["categoria"],
            fecha=fecha_es(fecha_el.get_text()) if fecha_el else None,
            bajada=recortar(bajada_el[0].get_text(" ")) if bajada_el else "",
            seccion="Prensa Diputados",
        ))
    return notas


@parser_html("hcdn_prensa")
def hcdn_prensa(cliente, feed, fuente, ctx) -> Resultado:
    notas = parsear_hcdn_prensa(_soup(cliente, feed["url"]), feed["url"], fuente)
    return Resultado(notas=[n for n in notas if _vigente_por_dia(n.fecha, ctx)], leidos=len(notas))


# ---------------------------------------------------------------------------- Senado
_DIA_SENADO = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóú]+)", re.I)


def parsear_senado_agenda(soup: BeautifulSoup, url_base: str, referencia: date) -> List[EventoAgenda]:
    from ..texto import MESES

    eventos, dia = [], None
    for div in soup.select("div.mods"):
        tit = div.select_one(".textReg16_blueTit2")
        if tit is None:
            continue
        texto = limpiar(tit.get_text(" "))
        if div.get("data-type") == "cam":  # encabezado de día: "Lunes 05 de octubre" (sin año)
            m = _DIA_SENADO.search(texto.lower())
            dia = None
            if m and m.group(2) in MESES:
                mes = MESES[m.group(2)]
                anio = referencia.year + (1 if mes < referencia.month - 6 else 0) - (1 if mes > referencia.month + 6 else 0)
                dia = date(anio, mes, int(m.group(1)))
            continue
        if dia is None:
            continue
        hora, _, titulo = texto.partition(" h - ")
        if not titulo:
            hora, titulo = "", texto
        suspendida = bool(re.match(r"(?i)suspendid[oa]\s*-\s*", titulo))
        titulo = re.sub(r"(?i)^suspendid[oa]\s*-\s*", "", titulo)
        lugar = ""
        for strong in div.find_all("strong"):
            if strong.get_text(strip=True).startswith("Lugar"):
                lugar = limpiar(strong.parent.get_text(" ")).replace("Lugar:", "").strip()
                break
        cnt = div.select_one("div.cnt p.textReg11_grey")
        temario = recortar(cnt.get_text(" "), MAX_TEMARIO) if cnt else ""
        eventos.append(EventoAgenda(
            camara="Senado", fecha=dia, hora=hora.strip(), titulo=titulo, tipo=_tipo_evento(titulo),
            fuente_id="senado_agenda", lugar=lugar, temario=temario, url=url_base,
            suspendida=suspendida,
        ))
    return eventos


@parser_html("senado_agenda")
def senado_agenda(cliente, feed, fuente, ctx) -> Resultado:
    hoy = _hoy_ar(ctx)
    eventos, leidos = [], 0
    for semana in (hoy, hoy + timedelta(days=7)):
        url = feed["url"].format(dd=f"{semana.day:02d}", mm=f"{semana.month:02d}", aaaa=semana.year)
        parseados = parsear_senado_agenda(_soup(cliente, url), url, semana)
        leidos += len(parseados)
        eventos += [e for e in parseados if e.fecha >= hoy]
    return Resultado(agenda=eventos, leidos=leidos)


def parsear_senado_prensa(soup: BeautifulSoup, url_base: str, fuente: dict) -> List[Nota]:
    notas, vistos = [], set()
    for a in soup.select("h1.portada a[href]"):
        url = urljoin(url_base, a["href"])
        if url in vistos:
            continue
        vistos.add(url)
        bloque = a.find_parent("div", class_="caption") or a.parent
        fecha_el = bloque.select_one("span.meta-data")
        m = re.search(r"/prensa/(\d+)/", url)
        texto_el = bloque.select_one(f"#noticiaTexto{m.group(1)}") if m else None
        notas.append(Nota(
            url=url, titulo=limpiar(a.get_text(" ")), medio=fuente["medio"], fuente_id=fuente["id"],
            categoria=fuente["categoria"],
            fecha=fecha_es(limpiar(fecha_el.get_text(" "))) if fecha_el else None,
            bajada=recortar(texto_el.get_text(" ")) if texto_el else "",
            seccion="Prensa Senado",
        ))
    return notas


@parser_html("senado_prensa")
def senado_prensa(cliente, feed, fuente, ctx) -> Resultado:
    notas = parsear_senado_prensa(_soup(cliente, feed["url"]), feed["url"], fuente)
    return Resultado(notas=[n for n in notas if _vigente_por_dia(n.fecha, ctx)], leidos=len(notas))


# ---------------------------------------------------------------------------- Boletín Oficial
RUBROS_BO = {"LEYES", "DECRETOS"}  # el resto de la 1ª sección (resoluciones, avisos) no es legislativo


def parsear_boletin(soup: BeautifulSoup, url_base: str, fuente: dict) -> List[Nota]:
    cont = soup.select_one("#avisosSeccionDiv")
    if cont is None:
        return []
    notas, rubro, vistos = [], "", set()
    for el in cont.find_all(["h5", "a"]):
        if el.name == "h5" and "seccion-rubro" in (el.get("class") or []):
            rubro = limpiar(el.get_text()).upper()
            continue
        href = el.get("href", "")
        if el.name != "a" or not href.startswith("/detalleAviso/primera/") or "?" in href:
            continue
        if rubro not in RUBROS_BO or href in vistos:
            continue
        vistos.add(href)
        tema = limpiar(el.select_one("p.item").get_text(" ")) if el.select_one("p.item") else ""
        detalles = [limpiar(s.get_text(" ")) for s in el.select("p.item-detalle")]
        norma = detalles[0] if detalles else ""
        sumario = detalles[1] if len(detalles) > 1 else ""
        es_dnu = sumario.upper().startswith("DNU-")
        sumario = re.sub(r"^[A-Z]+-\d{4}-\d+-[A-Z-]+\s*-\s*", "", sumario)  # saca "DECTO-2026-1160-APN-PTE - "
        m = re.search(r"/(\d{8})$", href)
        fecha = a_utc(datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=TZ_AR)) if m else None
        notas.append(Nota(
            url=urljoin(url_base, href),
            titulo=f"{'DNU ' + norma.split()[-1] if es_dnu else norma}: {sumario}".strip(": "),
            medio=fuente["medio"], fuente_id=fuente["id"], categoria=fuente["categoria"],
            fecha=fecha, bajada=tema.title() if tema.isupper() else tema,
            seccion="DNU" if es_dnu else rubro.capitalize(),
        ))
    return notas


@parser_html("boletin_oficial")
def boletin_oficial(cliente, feed, fuente, ctx) -> Resultado:
    soup = _soup(cliente, feed["url"])
    if soup.select_one("#avisosSeccionDiv") is None:
        raise ValueError("no se encontró el sumario de la 1ª sección (¿cambió el HTML?)")
    notas = parsear_boletin(soup, feed["url"], fuente)
    return Resultado(notas=[n for n in notas if _vigente_por_dia(n.fecha, ctx)], leidos=len(notas))
