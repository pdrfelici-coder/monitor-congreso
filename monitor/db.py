"""Persistencia en SQLite. Histórico de notas, agenda y estado de cada corrida."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .modelos import EstadoFuente, EventoAgenda, Nota, Tema
from .texto import normalizar_url

ESQUEMA = """
CREATE TABLE IF NOT EXISTS corridas (
    id          INTEGER PRIMARY KEY,
    inicio      TEXT NOT NULL,   -- ISO UTC
    fin         TEXT,
    desde       TEXT NOT NULL    -- inicio de la ventana de recolección
);

CREATE TABLE IF NOT EXISTS corrida_fuentes (
    corrida_id  INTEGER NOT NULL REFERENCES corridas(id),
    fuente_id   TEXT NOT NULL,
    medio       TEXT NOT NULL,
    estado      TEXT NOT NULL,   -- ok | parcial | vacia | error | salteada
    items       INTEGER NOT NULL,
    errores     TEXT,
    segundos    REAL,
    PRIMARY KEY (corrida_id, fuente_id)
);

CREATE TABLE IF NOT EXISTS notas (
    id           INTEGER PRIMARY KEY,
    url_norm     TEXT NOT NULL UNIQUE,
    url          TEXT NOT NULL,
    titulo       TEXT NOT NULL,
    bajada       TEXT,
    medio        TEXT NOT NULL,
    autor        TEXT,
    seccion      TEXT,
    fecha        TEXT,            -- ISO UTC; NULL si la fuente no la publica
    fuente_id    TEXT NOT NULL,
    categoria    TEXT NOT NULL,
    terminos     TEXT,            -- palabras clave que la hicieron entrar al filtro
    primera_vez  TEXT NOT NULL,   -- ISO UTC de la corrida que la vio primero
    corrida_id   INTEGER NOT NULL REFERENCES corridas(id)
);
CREATE INDEX IF NOT EXISTS ix_notas_corrida ON notas(corrida_id);
CREATE INDEX IF NOT EXISTS ix_notas_fecha ON notas(fecha);

CREATE TABLE IF NOT EXISTS temas (
    id           INTEGER PRIMARY KEY,
    fecha        TEXT NOT NULL,   -- AAAA-MM-DD del informe (hora argentina)
    corrida_id   INTEGER NOT NULL REFERENCES corridas(id),
    puesto       INTEGER NOT NULL,
    titulo       TEXT NOT NULL,
    camara       TEXT NOT NULL,
    tipo         TEXT NOT NULL,
    proyecto     TEXT,
    n_medios     INTEGER NOT NULL,
    n_notas      INTEGER NOT NULL,
    medios       TEXT NOT NULL    -- lista separada por " | "
);
CREATE INDEX IF NOT EXISTS ix_temas_fecha ON temas(fecha);

CREATE TABLE IF NOT EXISTS nota_tema (
    nota_id      INTEGER NOT NULL REFERENCES notas(id),
    tema_id      INTEGER NOT NULL REFERENCES temas(id) ON DELETE CASCADE,
    PRIMARY KEY (nota_id, tema_id)
);

CREATE TABLE IF NOT EXISTS agenda (
    id           INTEGER PRIMARY KEY,
    camara       TEXT NOT NULL,
    fecha        TEXT NOT NULL,   -- AAAA-MM-DD
    hora         TEXT NOT NULL,
    titulo       TEXT NOT NULL,
    tipo         TEXT NOT NULL,
    lugar        TEXT,
    temario      TEXT,
    url          TEXT,
    suspendida   INTEGER NOT NULL DEFAULT 0,
    fuente_id    TEXT NOT NULL,
    actualizado  TEXT NOT NULL,
    UNIQUE (camara, fecha, hora, titulo)
);
"""


def conectar(ruta: Path) -> sqlite3.Connection:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    return con


def iniciar_corrida(con, inicio: datetime, desde: datetime) -> int:
    cur = con.execute("INSERT INTO corridas (inicio, desde) VALUES (?, ?)",
                      (inicio.isoformat(), desde.isoformat()))
    con.commit()
    return cur.lastrowid


def cerrar_corrida(con, corrida_id: int, fin: datetime, estados: Iterable[EstadoFuente]):
    con.executemany(
        "INSERT OR REPLACE INTO corrida_fuentes VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(corrida_id, e.fuente_id, e.medio, e.estado, e.items, " | ".join(e.errores), round(e.segundos, 1))
         for e in estados],
    )
    con.execute("UPDATE corridas SET fin = ? WHERE id = ?", (fin.isoformat(), corrida_id))
    con.commit()


def guardar_notas(con, notas: List[Nota], corrida_id: int, ahora: datetime,
                  terminos: Optional[Dict[str, List[str]]] = None) -> Dict[str, Tuple[int, bool, str]]:
    """Inserta las notas que no existían (por URL normalizada).

    Devuelve {url: (id, es_nueva, primera_vez ISO UTC)} para todas las notas recibidas.
    """
    terminos = terminos or {}
    salida = {}
    for n in notas:
        clave = normalizar_url(n.url)
        cur = con.execute(
            """INSERT OR IGNORE INTO notas
               (url_norm, url, titulo, bajada, medio, autor, seccion, fecha, fuente_id, categoria,
                terminos, primera_vez, corrida_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (clave, n.url, n.titulo, n.bajada, n.medio, n.autor, n.seccion,
             n.fecha.isoformat() if n.fecha else None, n.fuente_id, n.categoria,
             ", ".join(terminos.get(n.url, [])), ahora.isoformat(), corrida_id),
        )
        if cur.rowcount:
            salida[n.url] = (cur.lastrowid, True, ahora.isoformat())
        else:
            fila = con.execute("SELECT id, primera_vez FROM notas WHERE url_norm = ?", (clave,)).fetchone()
            salida[n.url] = (fila["id"], False, fila["primera_vez"])
    con.commit()
    return salida


def guardar_temas(con, fecha: str, corrida_id: int, temas: List[Tema], ids: Dict[str, Tuple[int, bool, str]]):
    """Reemplaza los temas del día (correr dos veces el mismo día no duplica)."""
    con.execute("DELETE FROM nota_tema WHERE tema_id IN (SELECT id FROM temas WHERE fecha = ?)", (fecha,))
    con.execute("DELETE FROM temas WHERE fecha = ?", (fecha,))
    for puesto, t in enumerate(temas, start=1):
        cur = con.execute(
            """INSERT INTO temas (fecha, corrida_id, puesto, titulo, camara, tipo, proyecto,
                                  n_medios, n_notas, medios)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fecha, corrida_id, puesto, t.titulo, t.camara, t.tipo, t.proyecto,
             t.n_medios, len(t.notas), " | ".join(t.medios)),
        )
        con.executemany("INSERT OR IGNORE INTO nota_tema VALUES (?, ?)",
                        [(ids[n.url][0], cur.lastrowid) for n in t.notas])
    con.commit()


def guardar_agenda(con, eventos: List[EventoAgenda], ahora: datetime) -> int:
    for e in eventos:
        con.execute(
            """INSERT INTO agenda (camara, fecha, hora, titulo, tipo, lugar, temario, url, suspendida,
                                   fuente_id, actualizado)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (camara, fecha, hora, titulo) DO UPDATE SET
                   tipo = excluded.tipo, lugar = excluded.lugar, temario = excluded.temario,
                   url = excluded.url, suspendida = excluded.suspendida, actualizado = excluded.actualizado""",
            (e.camara, e.fecha.isoformat(), e.hora, e.titulo, e.tipo, e.lugar, e.temario, e.url,
             int(e.suspendida), e.fuente_id, ahora.isoformat()),
        )
    con.commit()
    return len(eventos)


# ---------------------------------------------------------------------------- consultas para el informe
def historico_diario(con, fecha: str, dias: int = 7) -> List[sqlite3.Row]:
    """Notas y temas por día en los `dias` anteriores a `fecha` (solo días con corrida)."""
    return con.execute(
        """SELECT t.fecha, COUNT(DISTINCT nt.nota_id) AS notas, COUNT(DISTINCT t.id) AS temas
           FROM temas t JOIN nota_tema nt ON nt.tema_id = t.id
           WHERE t.fecha < ? AND t.fecha >= date(?, ?)
           GROUP BY t.fecha ORDER BY t.fecha""",
        (fecha, fecha, f"-{dias} day"),
    ).fetchall()


def promedio_por_medio(con, fecha: str, dias: int = 7) -> Dict[str, float]:
    """Promedio diario de notas por medio en los días previos con corrida (0 si no publicó ese día)."""
    filas = con.execute(
        """SELECT n.medio, COUNT(DISTINCT n.id) AS notas
           FROM temas t JOIN nota_tema nt ON nt.tema_id = t.id JOIN notas n ON n.id = nt.nota_id
           WHERE t.fecha < ? AND t.fecha >= date(?, ?)
           GROUP BY n.medio""",
        (fecha, fecha, f"-{dias} day"),
    ).fetchall()
    n_dias = len(historico_diario(con, fecha, dias))
    return {f["medio"]: f["notas"] / n_dias for f in filas} if n_dias else {}


def agenda_proxima(con, desde: str, hasta: str) -> List[sqlite3.Row]:
    return con.execute(
        """SELECT * FROM agenda WHERE fecha >= ? AND fecha <= ? AND tipo IN ('sesion', 'comision')
           ORDER BY fecha, hora, camara""",
        (desde, hasta),
    ).fetchall()
