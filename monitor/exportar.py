"""Export diario a CSV (UTF-8 con BOM para que Excel respete las tildes)."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from .modelos import Tema
from .texto import TZ_AR


def exportar_csv(directorio: Path, fecha: str, temas: List[Tema]) -> List[Path]:
    directorio.mkdir(parents=True, exist_ok=True)
    ruta_temas = directorio / f"{fecha}_temas.csv"
    ruta_notas = directorio / f"{fecha}_notas.csv"
    with ruta_temas.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["puesto", "titulo", "camara", "tipo", "proyecto", "n_medios", "n_notas", "medios"])
        for i, t in enumerate(temas, start=1):
            w.writerow([i, t.titulo, t.camara, t.tipo, t.proyecto, t.n_medios, len(t.notas), " | ".join(t.medios)])
    with ruta_notas.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["puesto_tema", "camara", "tipo", "medio", "titulo", "bajada", "autor", "seccion",
                    "fecha_hora_ar", "url"])
        for i, t in enumerate(temas, start=1):
            for n in t.notas:
                fecha_ar = n.fecha.astimezone(TZ_AR).strftime("%Y-%m-%d %H:%M") if n.fecha else ""
                w.writerow([i, t.camara, t.tipo, n.medio, n.titulo, n.bajada, n.autor, n.seccion, fecha_ar, n.url])
    return [ruta_temas, ruta_notas]
