"""Filtro temático: decide si una nota habla de actividad legislativa nacional (ver config/keywords.yaml)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Pattern, Tuple
from urllib.parse import urlsplit

import yaml

from .modelos import Nota
from .texto import sin_tildes


def normalizar(texto: str) -> str:
    """Minúscula, sin tildes, solo letras/números separados por un espacio."""
    texto = sin_tildes(texto.lower())
    return re.sub(r"[^a-z0-9ñ]+", " ", texto).strip()


def patron(termino: str) -> Pattern:
    """'senador*' → \\bsenador\\w*\\b sobre texto normalizado."""
    t = normalizar(termino.rstrip("*"))
    comodin = r"\w*" if termino.endswith("*") else ""
    return re.compile(r"\b" + re.escape(t).replace(r"\ ", " ") + comodin + r"\b")


def texto_de(nota: Nota) -> Tuple[str, str]:
    """(título normalizado, resto normalizado = bajada + palabras del link)."""
    slug = urlsplit(nota.url).path.rsplit("/", 2)
    slug = " ".join(s for s in slug if s and not s.isdigit())
    slug = re.sub(r"\b[a-z]?\d{5,}\b|-n\d+$", " ", slug.lower())  # ids numéricos del CMS
    return normalizar(nota.titulo), normalizar(f"{nota.bajada} {slug}")


@dataclass
class Coincidencia:
    relevante: bool
    fuertes: List[str] = field(default_factory=list)
    debiles: List[str] = field(default_factory=list)
    personas: List[str] = field(default_factory=list)
    proyectos: List[str] = field(default_factory=list)

    @property
    def terminos(self) -> List[str]:
        return self.personas + self.proyectos + self.fuertes + self.debiles


class Filtro:
    def __init__(self, config: dict):
        from .clasificar import DetectorProyectos  # import diferido: clasificar usa normalizar()

        self.proyectos = DetectorProyectos(config.get("proyectos", {}))
        self.fuertes = [(t, patron(t)) for t in config.get("fuertes", [])]
        self.debiles = [(t, patron(t)) for t in config.get("debiles", [])]
        self.excluir = [re.compile(p) for p in config.get("excluir", [])]
        self.local = [patron(t) for t in config.get("contexto_local", [])]
        self.personas: List[Tuple[str, Pattern]] = []
        for _camara, lista in (config.get("personas") or {}).items():
            for p in lista or []:
                for variante in [p["nombre"], *p.get("alias", [])]:
                    self.personas.append((p["nombre"], patron(variante)))

    @classmethod
    def desde_yaml(cls, ruta: Path) -> "Filtro":
        return cls(yaml.safe_load(ruta.read_text(encoding="utf-8")))

    def limpiar_exclusiones(self, texto: str) -> str:
        for rx in self.excluir:
            texto = rx.sub(" ", texto)
        return texto

    def evaluar_texto(self, texto: str) -> Coincidencia:
        original = normalizar(texto)
        texto = self.limpiar_exclusiones(original)
        fuertes = [t for t, rx in self.fuertes if rx.search(texto)]
        debiles = [t for t, rx in self.debiles if rx.search(texto)]
        personas = sorted({n for n, rx in self.personas if rx.search(texto)})
        proyectos = self.proyectos.detectar(texto)
        relevante = bool(fuertes or personas or proyectos or len(debiles) >= 2)
        if relevante and not (fuertes or personas) and any(rx.search(original) for rx in self.local):
            # Sin términos fuertes y con contexto provincial/municipal: probablemente es una
            # legislatura local ("el proyecto de Presupuesto 2027" de la Ciudad, por ejemplo).
            relevante = False
        return Coincidencia(relevante, fuertes, debiles, personas, proyectos)

    def evaluar(self, nota: Nota) -> Coincidencia:
        titulo, resto = texto_de(nota)
        return self.evaluar_texto(f"{titulo} . {resto}")


def es_relevante(nota: Nota, filtro: Filtro) -> Tuple[bool, List[str]]:
    """Reglas por fuente + filtro de palabras. Devuelve (relevante, términos que coincidieron)."""
    if nota.categoria == "oficial":
        # Prensa de las cámaras, leyes y DNU entran siempre; los decretos comunes solo si
        # hablan de leyes (promulgación, veto).
        if nota.fuente_id != "boletin_oficial" or nota.seccion in ("Leyes", "DNU"):
            return True, ["fuente oficial"]
    c = filtro.evaluar(nota)
    return c.relevante, c.terminos

