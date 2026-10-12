"""Deduplicación por URL y agrupación de la misma noticia en temas; clasificación del tema."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from monitor.clasificar import Clasificador, DetectorProyectos
from monitor.dedup import agrupar
from monitor.filtro import normalizar
from monitor.modelos import Nota
from monitor.procesamiento import armar_temas
from monitor.recoleccion import unificar

CONFIG = yaml.safe_load((Path(__file__).parent.parent / "config" / "keywords.yaml").read_text(encoding="utf-8"))
T0 = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def n(titulo, medio, bajada="", minutos=0, url=None, fuente="medio"):
    return Nota(url=url or f"https://{medio.lower().replace(' ', '')}.com/{abs(hash(titulo))}",
                titulo=titulo, medio=medio, fuente_id=fuente, categoria="diario", bajada=bajada,
                fecha=T0 + timedelta(minutes=minutos))


# Notas reales de la primera corrida (10/10/2026): tres medios, misma noticia, distinta redacción.
MENEM = [
    n("Martín Menem condicionó las alianzas electorales con los gobernadores para 2027 a un acuerdo",
      "Infobae", "El presidente de la Cámara de Diputados admitió tensiones respecto al armado político de cara a la elección"),
    n("Martín Menem mandó un mensaje a la interna del Gobierno por el armado electoral", "TN", minutos=5),
    n('Tensión interna: Martín Menem calificó como "muy complejo" el armado político del Gobierno', "C5N", minutos=9),
]
OTRAS = [
    n("Presupuesto 2027: el Gobierno busca los votos de sus aliados, que reclaman más fondos",
      "TN", "La comisión de Presupuesto y Hacienda recibe al secretario de Hacienda el martes", minutos=20),
    n("Myriam Bregman convocó a una movilización al Congreso para rechazar un megadecreto", "Clarín",
      "La diputada de izquierda pidió quórum para tratar el DNU", minutos=30),
    n("Lorenzetti defendió el fallo sobre la Ley de Tierras", "Perfil", minutos=40),
]


def test_misma_noticia_en_varios_medios_es_un_tema():
    grupos = agrupar(MENEM + OTRAS)
    por_nota = {i: g for g in grupos for i in g}
    assert por_nota[0] == por_nota[1] == por_nota[2]
    assert len(grupos) == 4  # Menem + 3 temas sueltos


def test_noticias_distintas_no_se_mezclan():
    grupos = agrupar(OTRAS)
    assert len(grupos) == 3


def test_titulos_casi_identicos_se_unen_sin_bajada():
    a = n("Diputados aprobó la ley de financiamiento universitario", "Medio A")
    b = n("Diputados aprobó la Ley de Financiamiento Universitario", "Medio B", minutos=3)
    assert len(agrupar([a, b] + OTRAS)) == 4


def test_unificar_por_url_normalizada():
    a = n("Título", "Medio", url="https://medio.com/politica/nota?utm_source=twitter")
    b = n("Título", "Medio", url="https://medio.com/politica/nota/", bajada="Bajada")
    unicas = unificar([a, b])
    assert len(unicas) == 1 and unicas[0].bajada == "Bajada"


def test_temas_ordenados_por_cantidad_de_medios():
    temas = armar_temas(OTRAS + MENEM, Clasificador(CONFIG))
    assert temas[0].n_medios == 3
    assert "Menem" in temas[0].titulo
    assert [t.n_medios for t in temas] == sorted((t.n_medios for t in temas), reverse=True)


def test_mismo_medio_dos_veces_cuenta_una():
    a = n("Martín Menem condicionó las alianzas electorales con los gobernadores", "TN")
    b = n("Martín Menem condicionó las alianzas electorales con los gobernadores para 2027", "TN", minutos=60)
    tema, = armar_temas([a, b], Clasificador(CONFIG))
    assert tema.n_medios == 1 and len(tema.notas) == 2


# ---------------------------------------------------------------- clasificación
CLASIF = Clasificador(CONFIG)


def test_camara():
    assert CLASIF.camara(["El Senado aprobó el pliego"]) == "Senado"
    assert CLASIF.camara(["Diputados sesiona el jueves", "La Cámara baja define"]) == "Diputados"
    assert CLASIF.camara(["Diputados dio media sanción y pasa al Senado", "El Senado lo trata en noviembre"]) == "Ambas"
    assert CLASIF.camara(["La Bicameral de Trámite Legislativo revisa el DNU"]) == "Ambas"
    assert CLASIF.camara(["El Gobierno negocia con los gobernadores"]) == "Sin determinar"
    assert CLASIF.camara(["Grupo de amistad"], fuentes=["hcdn_prensa"]) == "Diputados"


def test_tipo():
    assert CLASIF.tipo(["Milei vetó la ley de financiamiento universitario"], []) == "Veto / DNU"
    assert CLASIF.tipo(["Sin quórum, se cayó la sesión especial"], []) == "Sesión"
    assert CLASIF.tipo(["Plenario de comisiones: dictamen para el Presupuesto"], []) == "Comisión"
    assert CLASIF.tipo(["El Gobierno negocia con los gobernadores los votos de sus bloques"], []) == "Negociación política"
    assert CLASIF.tipo(["Un diputado presentó un proyecto para regular las apps"], []) == "Proyecto"
    assert CLASIF.tipo(["El Congreso se iluminó de azul"], []) == "Otro"


def test_proyecto_asociado():
    d = DetectorProyectos(CONFIG["proyectos"])
    assert d.detectar(normalizar("Expediente 0032-S-2026. Proyecto de Ley de Inviolabilidad de la Propiedad Privada")) == \
        ["Inviolabilidad de la propiedad privada", "Expte. 0032-S-2026"]
    assert d.detectar(normalizar("Decreto 1160/2026 - Promúlgase la Ley N° 27.826")) == ["Ley 27.826"]
    assert d.detectar(normalizar("Orden del Día 433. Ley sobre Endeudamiento Familiar")) == ["Endeudamiento familiar", "OD 433"]
    assert "DNU 70/23" in d.detectar(normalizar("el DNU 70/23 sobre Bases"))
    assert CLASIF.proyecto(["Presupuesto 2027: los gobernadores", "El Presupuesto 2027 llega al recinto", "Ley 27.826"]) == "Presupuesto 2027"
