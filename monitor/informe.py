"""Arma el contexto del informe diario y lo renderiza a un HTML autocontenido."""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import db
from .modelos import EstadoFuente, Nota, Tema
from .texto import TZ_AR

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
TOP = 5
TEMAS_GRAFICO = 10
DIAS_AGENDA = 7

# Clase CSS por cámara: el color identifica la cámara (punto de color + texto en tinta).
CLASE_CAMARA = {"Diputados": "c1", "Senado": "c2", "Ambas": "c3"}


def fecha_larga(d: date) -> str:
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def hora_ar(n: Nota) -> str:
    return n.fecha.astimezone(TZ_AR).strftime("%H:%M") if n.fecha else ""


def _dedup_bicamerales(eventos: List[dict]) -> List[dict]:
    """Una comisión bicameral aparece en las dos agendas: se deja una sola (la de Diputados)."""
    vistos = {(e["fecha"], e["hora"]) for e in eventos if e["camara"] == "Diputados" and "bicameral" in e["titulo"].lower()}
    return [e for e in eventos
            if not (e["camara"] == "Senado" and "bicameral" in e["titulo"].lower() and (e["fecha"], e["hora"]) in vistos)]


def _titulo_agenda(t: str) -> str:
    """Los títulos de Diputados vienen en mayúsculas ("Plenario: DEFENSA NACIONAL, LEGISLACION PENAL"):
    se pasan a minúscula con mayúscula inicial en cada órgano, respetando "Ley"."""
    letras = [c for c in t if c.isalpha()]
    if not letras or sum(c.isupper() for c in letras) / len(letras) < 0.6:
        return t
    partes = re.split(r"(: |, | y (?=[A-ZÁÉÍÓÚÑ]{3,}))", t)
    salida = "".join(p if re.fullmatch(r": |, | y ", p) else p[:1].upper() + p[1:].lower() for p in partes)
    return re.sub(r"\b(ley|leyes)\b", lambda m: m.group(1).capitalize(), salida)


def _resumen_temario(texto: str, maximo: int = 220) -> str:
    if len(texto) <= maximo:
        return texto
    corte = texto.rfind(" ", 0, maximo)
    return texto[: corte if corte > 0 else maximo].rstrip(" ,.;:-") + "…"


def armar_agenda(con, hoy: date, ahora_iso: str, estados: List[EstadoFuente]) -> List[dict]:
    fuentes_ok = {e.fuente_id for e in estados if e.estado == "ok"}
    filas = db.agenda_proxima(con, hoy.isoformat(), (hoy + timedelta(days=DIAS_AGENDA - 1)).isoformat())
    eventos = []
    for f in filas:
        # Si la fuente respondió hoy, solo vale lo que publicó hoy (lo demás fue levantado o cambió).
        if f["fuente_id"] in fuentes_ok and f["actualizado"] != ahora_iso:
            continue
        temario = f["temario"] or ""  # texto oficial tal cual (pasarlo a minúscula rompe nombres propios)
        eventos.append({**dict(f), "titulo_mostrar": _titulo_agenda(f["titulo"]), "temario": temario,
                        "temario_corto": _resumen_temario(temario),
                        "de_corrida_anterior": f["actualizado"] != ahora_iso})
    eventos = _dedup_bicamerales(eventos)
    dias: Dict[str, List[dict]] = {}
    for e in eventos:
        dias.setdefault(e["fecha"], []).append(e)
    return [{"fecha": d, "etiqueta": fecha_larga(date.fromisoformat(d)), "es_hoy": d == hoy.isoformat(),
             "sesiones": [e for e in evs if e["tipo"] == "sesion"],
             "comisiones": [e for e in evs if e["tipo"] == "comision"]}
            for d, evs in dias.items()]


def _barras(items, maximo: Optional[float] = None) -> List[dict]:
    """[(etiqueta, valor, extra)] → filas con ancho en % para barras horizontales."""
    maximo = maximo or max((v for _, v, _ in items), default=1) or 1
    return [{"etiqueta": e, "valor": v, "pct": round(100 * v / maximo, 1), **extra} for e, v, extra in items]


def contexto(con, fecha: str, ahora: datetime, temas: List[Tema], estados: List[EstadoFuente],
             notas_x: List[Nota], ahora_iso: str) -> dict:
    hoy = date.fromisoformat(fecha)
    notas = [n for t in temas for n in t.notas]
    por_medio = Counter(n.medio for n in notas)
    previos = db.historico_diario(con, fecha)
    prom_notas = sum(r["notas"] for r in previos) / len(previos) if previos else None
    prom_medio = db.promedio_por_medio(con, fecha)

    # Volumen diario: 7 días previos + hoy (los días sin corrida quedan como "sin datos").
    por_dia = {r["fecha"]: r["notas"] for r in previos}
    por_dia[fecha] = len(notas)
    serie = []
    for i in range(7, -1, -1):
        d = hoy - timedelta(days=i)
        serie.append({"fecha": d.isoformat(), "etiqueta": f"{DIAS[d.weekday()][:2].capitalize()} {d.day}",
                      "valor": por_dia.get(d.isoformat()), "es_hoy": i == 0})
    max_serie = max((s["valor"] or 0 for s in serie), default=1) or 1
    for s in serie:
        s["pct"] = round(100 * (s["valor"] or 0) / max_serie, 1)

    max_medio = max(list(por_medio.values()) + list(prom_medio.values()) + [1])
    graf_medios = _barras(
        [(m, v, {"prom": prom_medio.get(m), "prom_pct": round(100 * prom_medio[m] / max_medio, 1) if m in prom_medio else None})
         for m, v in por_medio.most_common()],
        maximo=max_medio,
    )
    graf_temas = _barras([(t.titulo, len(t.notas), {"medios": t.n_medios, "puesto": i})
                          for i, t in enumerate(temas[:TEMAS_GRAFICO], start=1)])

    caidas = [e for e in estados if e.estado in ("error", "vacia")]
    parciales = [e for e in estados if e.estado == "parcial"]
    return {
        "fecha": fecha,
        "fecha_larga": fecha_larga(hoy).capitalize() + f" de {hoy.year}",
        "hora_corrida": ahora.astimezone(TZ_AR).strftime("%H:%M"),
        "kpi": {
            "notas": len(notas), "temas": len(temas), "medios": len(por_medio),
            "prom_notas": prom_notas, "dias_hist": len(previos),
            "delta": (len(notas) - prom_notas) / prom_notas * 100 if prom_notas else None,
            "caidas": len(caidas),
        },
        "top": temas[:TOP],
        "temas": temas,
        "agenda": armar_agenda(con, hoy, ahora_iso, estados),
        "serie": serie,
        "graf_medios": graf_medios,
        "graf_temas": graf_temas,
        "hay_promedio": bool(prom_medio),
        "notas_x": notas_x,
        "caidas": caidas,
        "parciales": parciales,
        "fuentes_ok": sum(1 for e in estados if e.estado == "ok"),
        "fuentes_total": sum(1 for e in estados if e.estado != "salteada"),
        "salteadas": [e for e in estados if e.estado == "salteada"],
        "medios_tabla": sorted(por_medio),
        "tipos_tabla": sorted({t.tipo for t in temas}),
        "camaras_tabla": [c for c in ("Diputados", "Senado", "Ambas", "Sin determinar") if any(t.camara == c for t in temas)],
        "clase_camara": CLASE_CAMARA,
        "hora_ar": hora_ar,
    }


def renderizar(ctx: dict, plantillas: Path, salida: Path) -> Path:
    env = Environment(loader=FileSystemLoader(plantillas), autoescape=select_autoescape(["html", "j2"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["miles"] = lambda v: f"{v:,.0f}".replace(",", ".")
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(env.get_template("informe.html.j2").render(**ctx), encoding="utf-8")
    return salida


def actualizar_indice(directorio: Path) -> Path:
    """index.html = el informe más reciente (así el link fijo siempre muestra el del día);
    archivo.html = lista de todos los días, del más nuevo al más viejo."""
    dias = sorted((p.stem for p in directorio.glob("????-??-??.html")), reverse=True)
    items = "\n".join(
        f'<li><a href="{d}.html">{fecha_larga(date.fromisoformat(d)).capitalize()} de {d[:4]}</a></li>' for d in dias)
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow">
<title>Monitor del Congreso · archivo</title>
<style>:root{{color-scheme:light dark}}body{{font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
max-width:640px;margin:40px auto;padding:0 16px;background:#f9f9f7;color:#0b0b0b}}
a{{color:#1c5cab}}li{{margin:6px 0}}
@media (prefers-color-scheme:dark){{body{{background:#0d0d0d;color:#fff}}a{{color:#86b6ef}}}}</style></head>
<body><p><a href="index.html">← Informe de hoy</a></p><h1>Informes anteriores</h1><ul>{items}</ul></body></html>"""
    (directorio / "archivo.html").write_text(html, encoding="utf-8")
    if dias:
        (directorio / "index.html").write_text((directorio / f"{dias[0]}.html").read_text(encoding="utf-8"), encoding="utf-8")
    return directorio / "index.html"
