"""Clasificación por reglas: cámara, tipo y proyecto de ley asociado (ver config/keywords.yaml)."""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Pattern, Sequence, Tuple

from .filtro import normalizar, patron

# Sobre texto normalizado (sin puntos ni guiones): "0032-S-2026" llega como "0032 s 2026".
RX_EXPEDIENTE = re.compile(r"\b(\d{1,5}) (d|s|pe|jgm|ov|cd) (20\d\d|\d\d)\b")
RX_LEY = re.compile(r"\bley (?:n |nro |numero )?(2\d) ?(\d{3})\b")
RX_ORDEN_DIA = re.compile(r"\borden del dia (?:n |nro |numero )?(\d{1,4})\b")
# Solo DNU explícitos: "Decreto 1159/2026" a secas es un decreto común (designaciones, etc.).
RX_DNU = re.compile(r"\b(?:dnu|decreto de necesidad y urgencia) (?:n |nro )?(\d{1,4}) (20\d\d|\d\d)\b")

SIN_CAMARA = "Sin determinar"


class DetectorProyectos:
    def __init__(self, proyectos: Dict[str, Sequence[str]]):
        self.conocidos: List[Tuple[str, Pattern]] = [
            (nombre, re.compile(p)) for nombre, patrones in (proyectos or {}).items() for p in patrones
        ]

    def detectar(self, texto_norm: str) -> List[str]:
        """Proyectos mencionados, primero los conocidos por nombre."""
        hallados = []
        for nombre, rx in self.conocidos:
            if rx.search(texto_norm) and nombre not in hallados:
                hallados.append(nombre)
        for m in RX_EXPEDIENTE.finditer(texto_norm):
            hallados.append(f"Expte. {m.group(1)}-{m.group(2).upper()}-{m.group(3)}")
        for m in RX_LEY.finditer(texto_norm):
            hallados.append(f"Ley {m.group(1)}.{m.group(2)}")
        for m in RX_ORDEN_DIA.finditer(texto_norm):
            hallados.append(f"OD {m.group(1)}")
        for m in RX_DNU.finditer(texto_norm):
            hallados.append(f"DNU {m.group(1)}/{m.group(2)}")
        return list(dict.fromkeys(hallados))


class Clasificador:
    def __init__(self, config: dict):
        self.tipos = [
            (clave, d["etiqueta"], [patron(t) for t in d["terminos"]])
            for clave, d in config["tipos"].items()
        ]
        self.camaras = {c: [patron(t) for t in ts] for c, ts in config["camaras"].items()}
        self.proyectos = DetectorProyectos(config.get("proyectos", {}))

    def tipo(self, titulos: Sequence[str], resto: Sequence[str]) -> str:
        """Gana el tipo con más coincidencias (títulos x2); empate → orden de la config; nada → Otro."""
        puntajes = []
        for orden, (_clave, etiqueta, patrones) in enumerate(self.tipos):
            p = sum(2 * len(rx.findall(normalizar(t))) for t in titulos for rx in patrones)
            p += sum(len(rx.findall(normalizar(t))) for t in resto for rx in patrones)
            puntajes.append((p, -orden, etiqueta))
        mejor = max(puntajes)
        return mejor[2] if mejor[0] > 0 else "Otro"

    def camara(self, textos: Sequence[str], fuentes: Sequence[str] = ()) -> str:
        """Cuenta en cuántos textos aparece cada cámara. Si las dos pesan parecido → Ambas."""
        cuenta = Counter()
        for t in textos:
            n = normalizar(t)
            for camara, patrones in self.camaras.items():
                if any(rx.search(n) for rx in patrones):
                    cuenta[camara] += 1
        for f in fuentes:  # las fuentes oficiales dicen de qué cámara son
            if f.startswith("hcdn"):
                cuenta["Diputados"] += 1
            elif f.startswith("senado"):
                cuenta["Senado"] += 1
        d, s = cuenta["Diputados"], cuenta["Senado"]
        if d and s and min(d, s) / max(d, s) >= 0.34:
            return "Ambas"
        if d or s:
            return "Diputados" if d > s else "Senado"
        return "Ambas" if cuenta["Ambas"] else SIN_CAMARA

    def proyecto(self, textos: Sequence[str]) -> str:
        """El proyecto más mencionado entre los textos del tema ("" si ninguno)."""
        cuenta = Counter()
        for t in textos:
            for p in self.proyectos.detectar(normalizar(t)):
                cuenta[p] += 1
        return cuenta.most_common(1)[0][0] if cuenta else ""
