"""Filtro temático con el keywords.yaml real: si alguien edita la config y rompe un caso, salta acá."""
from pathlib import Path

import pytest
import yaml

from monitor.filtro import Filtro, es_relevante, normalizar, patron
from monitor.modelos import Nota

CONFIG = yaml.safe_load((Path(__file__).parent.parent / "config" / "keywords.yaml").read_text(encoding="utf-8"))
FILTRO = Filtro(CONFIG)


def nota(titulo, bajada="", url="https://medio.com/politica/nota", categoria="diario", fuente="medio", seccion=""):
    return Nota(url=url, titulo=titulo, medio="Medio", fuente_id=fuente, categoria=categoria,
                bajada=bajada, seccion=seccion)


@pytest.mark.parametrize("titulo, bajada", [
    ("El oficialismo busca quórum para la sesión del jueves", ""),
    ("Diputados: dictamen favorable para la reforma", ""),
    ("El Senado aprobó la ley con 40 votos", ""),
    ("La oposición consiguió media sanción", ""),
    ("Cristian Ritondo cuestionó al Gobierno", ""),       # persona
    ("Ritondo y la mesa con el PRO", ""),                  # alias de persona
    ("Presupuesto 2027: los gobernadores piden más fondos", ""),  # proyecto conocido
    ("Se presentó el expediente 1234-D-2026", ""),         # número de expediente
    ("Milei vetó la ley de financiamiento", ""),           # 2 débiles: veta*, ley
    ("Una nota sin palabras clave en el título", "La interpelación al jefe de Gabinete quedó para la semana próxima."),
])
def test_entran(titulo, bajada):
    assert FILTRO.evaluar(nota(titulo, bajada)).relevante, FILTRO.evaluar(nota(titulo, bajada))


@pytest.mark.parametrize("titulo, bajada", [
    ("El Senado de Estados Unidos aprobó un paquete de ayuda", ""),
    ("El Congreso de Brasil debate la reforma tributaria", ""),
    ("Elecciones en España: qué pasa en el Congreso de los Diputados", ""),
    ("La Cámara de Diputados bonaerense aprobó el endeudamiento", ""),
    ("El Senado de la provincia de Córdoba sesionó", ""),
    ("La Libertad Avanza hizo un congreso de jóvenes en Morón", ""),
    ("Presupuesto porteño 2027", "El gobierno porteño presentó su proyecto de Presupuesto 2027 y la legislatura abrió la discusión en comisión."),
    ("Horror en el zoológico: un hombre entró al recinto de un tigre", ""),
    ("Se mantiene el bloqueo atmosférico: hasta cuándo llueve", ""),
    ("Torneo Clausura: Barracas aplicó la ley del ex", ""),  # 'ley' sola no alcanza
])
def test_quedan_afuera(titulo, bajada):
    assert not FILTRO.evaluar(nota(titulo, bajada)).relevante, FILTRO.evaluar(nota(titulo, bajada))


def test_ignora_tildes_y_mayusculas():
    assert FILTRO.evaluar(nota("SESION ESPECIAL EN LA CAMARA BAJA")).relevante
    assert FILTRO.evaluar(nota("sesión especial en la cámara baja")).relevante


def test_palabra_completa():
    rx = patron("dnu")
    assert rx.search(normalizar("El DNU 70/23"))
    assert not rx.search(normalizar("adnumero"))
    assert patron("senad*").search("senadoras")


def test_usa_palabras_del_link_cuando_no_hay_bajada():
    n = nota("Lo que viene esta semana", url="https://medio.com/politica/sesion-especial-en-diputados-n123456")
    assert FILTRO.evaluar(n).relevante


def test_fuentes_oficiales():
    assert es_relevante(nota("GRUPO DE AMISTAD", categoria="oficial", fuente="hcdn_prensa"), FILTRO)[0]
    assert es_relevante(nota("Ley 27826: Modificación.", categoria="oficial", fuente="boletin_oficial", seccion="Leyes"), FILTRO)[0]
    # Un decreto común del BO entra solo si habla de leyes (promulgación o veto)
    assert not es_relevante(nota("Decreto 1159/2026: Desígnase Embajador.", categoria="oficial",
                                 fuente="boletin_oficial", seccion="Decretos"), FILTRO)[0]
    assert es_relevante(nota("Decreto 1160/2026: Promúlgase la Ley N° 27.826.", categoria="oficial",
                             fuente="boletin_oficial", seccion="Decretos"), FILTRO)[0]


def test_devuelve_terminos():
    c = FILTRO.evaluar(nota("Martín Menem convocó a sesión especial"))
    assert "Martin Menem" in c.personas and "sesion especial" in c.fuertes
