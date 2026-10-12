"""Estructuras de datos que comparten colectores, base e informe."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional


@dataclass
class Nota:
    """Metadatos de una nota. Nunca el cuerpo: solo lo que pide el informe."""

    url: str
    titulo: str
    medio: str
    fuente_id: str
    categoria: str
    fecha: Optional[datetime] = None  # aware, en UTC
    bajada: str = ""
    autor: str = ""
    seccion: str = ""


@dataclass
class EventoAgenda:
    camara: str  # "Diputados" | "Senado"
    fecha: date
    hora: str
    titulo: str  # comisión u órgano, o título del evento
    tipo: str  # "comision" | "sesion" | "otro"
    fuente_id: str
    lugar: str = ""
    temario: str = ""
    url: str = ""
    suspendida: bool = False


@dataclass
class Resultado:
    """Lo que devuelve un colector para un feed."""

    notas: List[Nota] = field(default_factory=list)
    agenda: List[EventoAgenda] = field(default_factory=list)
    leidos: int = 0  # ítems parseados antes del filtro por fecha (para detectar parsers rotos)


@dataclass
class EstadoFuente:
    fuente_id: str
    medio: str
    estado: str  # "ok" | "parcial" | "vacia" | "error" | "salteada"
    items: int = 0
    errores: List[str] = field(default_factory=list)
    segundos: float = 0.0


@dataclass
class Tema:
    """Una noticia cubierta por uno o más medios."""

    titulo: str
    camara: str  # "Diputados" | "Senado" | "Ambas" | "Sin determinar"
    tipo: str  # etiqueta de keywords.yaml (Sesión, Comisión, ...) u "Otro"
    proyecto: str
    notas: List[Nota] = field(default_factory=list)

    @property
    def medios(self) -> List[str]:
        return list(dict.fromkeys(n.medio for n in self.notas))

    @property
    def n_medios(self) -> int:
        return len(self.medios)
