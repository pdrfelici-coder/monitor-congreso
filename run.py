"""Monitor diario de medios sobre el Congreso. Uso: python run.py [--horas 24] [--solo id1,id2]"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from monitor import db, informe
from monitor.clasificar import Clasificador
from monitor.dedup import UMBRAL
from monitor.colectores import Contexto, x_api
from monitor.exportar import exportar_csv
from monitor.filtro import Filtro
from monitor.http import Cliente
from monitor.procesamiento import armar_temas, filtrar
from monitor.recoleccion import cargar_fuentes, recolectar
from monitor.texto import TZ_AR

RAIZ = Path(__file__).resolve().parent
CONFIG = RAIZ / "config"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--horas", type=int, default=24, help="ventana de recolección (default 24)")
    ap.add_argument("--db", type=Path, default=RAIZ / "datos" / "monitor.db")
    ap.add_argument("--informes", type=Path, default=RAIZ / "informes", help="carpeta de salida del HTML")
    ap.add_argument("--solo", help="ids de fuentes separados por coma (para probar)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    ahora = datetime.now(timezone.utc)
    ctx = Contexto(ahora=ahora, desde=ahora - timedelta(hours=args.horas))
    fuentes = cargar_fuentes(CONFIG / "fuentes.yaml")
    if args.solo:
        ids = set(args.solo.split(","))
        fuentes = [f for f in fuentes if f["id"] in ids]

    con = db.conectar(args.db)
    corrida = db.iniciar_corrida(con, ahora, ctx.desde)

    cliente = Cliente()
    try:
        notas, agenda, estados = recolectar(fuentes, ctx, cliente)
    finally:
        cliente.close()
    if not args.solo:
        notas_x, estado_x = x_api.recolectar(CONFIG / "cuentas_x.yaml", ctx)
        notas += notas_x
        estados.append(estado_x)

    # Filtro temático: solo se guardan las notas sobre actividad legislativa.
    config_kw = yaml.safe_load((CONFIG / "keywords.yaml").read_text(encoding="utf-8"))
    relevantes, terminos = filtrar(notas, Filtro(config_kw))
    ids = db.guardar_notas(con, relevantes, corrida, ahora, terminos)
    db.guardar_agenda(con, agenda, ahora)

    # Temas: las notas de X van aparte. Las que no tienen fecha (listados HTML) cuentan si se
    # vieron por primera vez dentro de la ventana, para no arrastrarlas día tras día.
    desde_iso = ctx.desde.isoformat()
    para_temas = [n for n in relevantes
                  if n.categoria != "x" and (n.fecha is not None or ids[n.url][2] >= desde_iso)]
    umbral = (config_kw.get("agrupamiento") or {}).get("umbral", UMBRAL)
    temas = armar_temas(para_temas, Clasificador(config_kw), corpus=notas, umbral=umbral)
    fecha = ahora.astimezone(TZ_AR).strftime("%Y-%m-%d")
    db.guardar_temas(con, fecha, corrida, temas, ids)
    csvs = exportar_csv(args.db.parent / "csv", fecha, temas)
    db.cerrar_corrida(con, corrida, datetime.now(timezone.utc), estados)

    notas_x = [n for n in relevantes if n.categoria == "x"]
    ctx_html = informe.contexto(con, fecha, ahora, temas, estados, notas_x, ahora_iso=ahora.isoformat())
    html = informe.renderizar(ctx_html, RAIZ / "templates", args.informes / f"{fecha}.html")
    informe.actualizar_indice(args.informes)

    print(f"\nCorrida #{corrida} · ventana desde {ctx.desde:%Y-%m-%d %H:%M} UTC")
    print(f"{'fuente':<22}{'estado':<10}{'ítems':>6}  {'seg':>5}  detalle")
    for e in sorted(estados, key=lambda e: (e.estado == "ok", e.fuente_id)):
        print(f"{e.fuente_id:<22}{e.estado:<10}{e.items:>6}  {e.segundos:>5.1f}  {' | '.join(e.errores)[:110]}")
    nuevas = sum(1 for _id, es_nueva, _pv in ids.values() if es_nueva)
    print(f"\nNotas: {len(notas)} en ventana → {len(relevantes)} sobre el Congreso ({nuevas} nuevas en la base)")
    print(f"Temas: {len(temas)} · Agenda: {len(agenda)} eventos")
    print(f"Informe: {html}\nCSV: {csvs[0].parent}")
    for i, tema in enumerate(temas[:10], start=1):
        print(f"  {i:>2}. [{tema.n_medios} medios · {tema.camara} · {tema.tipo}"
              f"{' · ' + tema.proyecto if tema.proyecto else ''}] {tema.titulo[:90]}")
    caidas = [e.fuente_id for e in estados if e.estado in ("error", "vacia")]
    if caidas:
        print(f"Fuentes caídas: {', '.join(caidas)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
