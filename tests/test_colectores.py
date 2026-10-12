"""Parsers de recolección contra fixtures mínimos con la misma estructura que los sitios reales."""
from datetime import date, datetime, timedelta, timezone

from bs4 import BeautifulSoup

from monitor.colectores import Contexto, oficiales, rss, sitemap
from monitor.colectores.medios_html import parsear_tiempoar
from monitor.colectores.x_api import _lotes
from monitor.recoleccion import unificar
from monitor.modelos import Nota
from monitor.texto import MAX_BAJADA, normalizar_url, seccion_desde_url

FUENTE = {"id": "prueba", "medio": "Medio de Prueba", "categoria": "diario"}


def soup(html):
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------- RSS y sitemap
RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>X</title>
<item><title>Diputados aprob&#243; el Presupuesto</title><link>https://medio.com/politica/presupuesto-1/?utm_source=rss</link>
<dc:creator>Ana P&#233;rez</dc:creator><category>Pol&#237;tica</category>
<pubDate>Sat, 10 Oct 2026 22:00:00 +0000</pubDate>
<description><![CDATA[<p>""" + b"palabra " * 200 + b"""</p>]]></description>
<content:encoded><![CDATA[CUERPO COMPLETO QUE NO SE DEBE GUARDAR]]></content:encoded></item>
<item><title>Nota vieja</title><link>https://medio.com/politica/vieja</link>
<pubDate>Mon, 05 Oct 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""


def test_rss_toma_metadatos_y_recorta_bajada():
    notas = rss.parsear(RSS, FUENTE)
    n = notas[0]
    assert n.titulo == "Diputados aprobó el Presupuesto"
    assert n.autor == "Ana Pérez"
    assert n.seccion == "Política"
    assert n.fecha == datetime(2026, 10, 10, 22, tzinfo=timezone.utc)
    assert len(n.bajada) <= MAX_BAJADA + 1 and n.bajada.endswith("…")
    assert "CUERPO COMPLETO" not in n.bajada


class ClienteFalso:
    def __init__(self, contenido):
        self.contenido = contenido

    def get(self, url):
        return type("R", (), {"content": self.contenido})()


def test_rss_descarta_fuera_de_ventana():
    ahora = datetime(2026, 10, 11, 10, tzinfo=timezone.utc)
    ctx = Contexto(ahora=ahora, desde=ahora - timedelta(hours=24))
    res = rss.recolectar(ClienteFalso(RSS), {"url": "x"}, FUENTE, ctx)
    assert [n.titulo for n in res.notas] == ["Diputados aprobó el Presupuesto"]
    assert res.leidos == 2


SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
 <url><loc>https://www.c5n.com/politica/sesion-senado-n1</loc>
  <news:news><news:publication><news:name>C5N</news:name><news:language>es</news:language></news:publication>
  <news:publication_date>2026-10-11T00:30:00Z</news:publication_date>
  <news:title>El Senado sesiona el jueves</news:title></news:news></url>
 <url><loc>https://www.c5n.com/politica/sin-titulo</loc></url>
</urlset>"""


def test_sitemap_de_noticias():
    notas = sitemap.parsear(SITEMAP, FUENTE)
    assert len(notas) == 1
    assert notas[0].titulo == "El Senado sesiona el jueves"
    assert notas[0].seccion == "politica"
    assert notas[0].fecha == datetime(2026, 10, 11, 0, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------- Diputados
HCDN_AGENDA = """
<table id="agendaComisiones">
<thead><tr><th colspan=2> martes 13 de octubre del 2026</th></tr></thead>
<tr><td><strong>12:00</strong><br/>Anexo "C" - 2° piso<br></td>
<td><!-- <a href="/x"><h5></h5></a> --><a href="/comisiones/permanentes/cpyhacienda"><strong>PRESUPUESTO Y HACIENDA</strong></a>
<h5></h5><strong>INVITADO.</strong><br>Presupuesto 2027.<br/>
<a href="https://parlamentaria.hcdn.gob.ar/citacion.pdf">ver citación</a></td></tr>
<tr><td><strong>14:00</strong><br/> SUSPENDIDA<br></td>
<td><a href="/c"><strong>COMERCIO</strong></a><h5></h5><strong>INVITADOS.</strong><br>Remises.</td></tr>
<tr><td><strong>16:00</strong><br/>Sala 1</td>
<td><a href="/a"><strong>ASUNTOS CONSTITUCIONALES, </strong></a><a href="/b"><strong>LEGISLACION GENERAL</strong></a>
<h5></h5>Propiedad privada.</td></tr>
<thead><tr><th colspan=2> jueves 15 de octubre del 2026</th></tr></thead>
<tr><td><strong>14:00</strong><br/>RECINTO</td><td><h5>SESIÓN ESPECIAL</h5><strong>A SOLICITUD DE X</strong><br>Temario.</td></tr>
<tr><td><strong>14:00</strong><br/>Salón Blanco</td><td><h5>GRUPO PARLAMENTARIO DE AMISTAD CON PANAMÁ</h5>Embajador.</td></tr>
</table>"""


def test_hcdn_agenda():
    ev = oficiales.parsear_hcdn_agenda(soup(HCDN_AGENDA), "https://www.hcdn.gob.ar/comisiones/agenda/")
    assert [(e.fecha, e.hora, e.tipo) for e in ev] == [
        (date(2026, 10, 13), "12:00", "comision"),
        (date(2026, 10, 13), "14:00", "comision"),
        (date(2026, 10, 13), "16:00", "comision"),
        (date(2026, 10, 15), "14:00", "sesion"),
        (date(2026, 10, 15), "14:00", "otro"),
    ]
    presupuesto, comercio, plenario, sesion, _ = ev
    assert presupuesto.titulo == "PRESUPUESTO Y HACIENDA"
    assert presupuesto.url == "https://parlamentaria.hcdn.gob.ar/citacion.pdf"
    assert "Presupuesto 2027" in presupuesto.temario and "ver citación" not in presupuesto.temario
    assert comercio.suspendida and not presupuesto.suspendida
    assert plenario.titulo == "Plenario: ASUNTOS CONSTITUCIONALES, LEGISLACION GENERAL"
    assert sesion.titulo == "SESIÓN ESPECIAL" and "A SOLICITUD" in sesion.temario


def test_hcdn_prensa():
    html = """<div class="noticia"><a href="/prensa/noticia/DICTAMEN-X/"><div class="box-texto">
      <p class="fecha">06 de octubre de 2026</p><h3>DICTAMEN FAVORABLE</h3><p>Fue en el marco...</p></div></a></div>"""
    n, = oficiales.parsear_hcdn_prensa(soup(html), "https://www.hcdn.gob.ar/prensa/", FUENTE)
    assert n.url == "https://www.hcdn.gob.ar/prensa/noticia/DICTAMEN-X/"
    assert n.fecha.date() == date(2026, 10, 6)
    assert n.bajada == "Fue en el marco..."


# ---------------------------------------------------------------- Senado
SENADO_AGENDA = """
<div class="mods agendaOtras off cam" data-type="cam"><p><span class="textReg16_blueTit2">Martes 29 de
  diciembre</span></p></div>
<div class="mods agendaCulturales off cul" data-type="cul"><p><span class="textReg16_blueTit2"> 11:00 h - Reunión de la Comisión de Presupuesto</span></p>
  <div class="cnt"><p class="textReg11_grey">Temario: Presupuesto 2027</p>
  <p class="textReg11_grey"><span><strong>Lugar:</strong> Salón Illia </span></p></div></div>
<div class="mods agendaOtras off cam" data-type="cam"><p><span class="textReg16_blueTit2">Viernes 01 de enero</span></p></div>
<div class="mods agendaCulturales off cul" data-type="cul"><p><span class="textReg16_blueTit2"> 16:00 h - SUSPENDIDA - Sesión especial</span></p></div>
<div class="mods agendaCulturales off cul" data-type="cul"><p><span class="textReg16_blueTit2"> 11:00 a 17:00 h - Visitas guiadas</span></p></div>
"""


def test_senado_agenda_infiere_anio_y_tipo():
    ev = oficiales.parsear_senado_agenda(soup(SENADO_AGENDA), "u", referencia=date(2026, 12, 28))
    assert [(e.fecha, e.hora, e.tipo, e.suspendida) for e in ev] == [
        (date(2026, 12, 29), "11:00", "comision", False),
        (date(2027, 1, 1), "16:00", "sesion", True),
        (date(2027, 1, 1), "11:00 a 17:00", "otro", False),
    ]
    assert ev[0].lugar == "Salón Illia"
    assert ev[1].titulo == "Sesión especial"


def test_senado_prensa():
    html = """<div class="caption"><div class="out"><span class="meta-data">10 de
      octubre    de 2026</span><h1 class="portada"><a href="/prensa/24483/noticias">TÍTULO</a></h1></div>
      <div id="noticiaTexto24483"><p>Bajada.</p></div></div>"""
    n, = oficiales.parsear_senado_prensa(soup(html), "https://www.senado.gob.ar/", FUENTE)
    assert n.url == "https://www.senado.gob.ar/prensa/24483/noticias"
    assert n.fecha.date() == date(2026, 10, 10)
    assert n.bajada == "Bajada."


# ---------------------------------------------------------------- Boletín Oficial
BO = """<div id="avisosSeccionDiv">
<h5 class="seccion-rubro">LEYES </h5>
<a href="/detalleAviso/primera/1/20261009"><div class="linea-aviso"><p class="item">RÉGIMEN PENAL TRIBUTARIO </p>
 <p class="item-detalle"><small>Ley 27826</small></p><p class="item-detalle"><small>Modificación.</small></p></div></a>
<h5 class="seccion-rubro">DECRETOS </h5>
<a href="/detalleAviso/primera/2/20261009?anexos=1">anexos</a>
<a href="/detalleAviso/primera/2/20261009"><div class="linea-aviso"><p class="item">PODER EJECUTIVO </p>
 <p class="item-detalle"><small>Decreto 1157/2026</small></p><p class="item-detalle"><small>DNU-2026-1157-APN-PTE - Ejercicio Combinado.</small></p></div></a>
<h5 class="seccion-rubro">RESOLUCIONES </h5>
<a href="/detalleAviso/primera/3/20261009"><div class="linea-aviso"><p class="item">ENTE</p></div></a>
</div>"""


def test_boletin_oficial_leyes_y_dnu():
    notas = oficiales.parsear_boletin(soup(BO), "https://www.boletinoficial.gob.ar/seccion/primera", FUENTE)
    assert [(n.titulo, n.seccion) for n in notas] == [
        ("Ley 27826: Modificación.", "Leyes"),
        ("DNU 1157/2026: Ejercicio Combinado.", "DNU"),
    ]
    assert notas[0].bajada == "Régimen Penal Tributario"
    assert notas[1].url == "https://www.boletinoficial.gob.ar/detalleAviso/primera/2/20261009"


# ---------------------------------------------------------------- Tiempo Argentino
def test_tiempoar():
    html = """<div class="article-preview"><a href="https://www.tiempoar.com.ar/ta_article/a/">img</a>
      <div class="category-title"><a href="#"><h4>La rosca parlamentaria</h4></a></div>
      <div class="title"><a href="https://www.tiempoar.com.ar/ta_article/a/"><p>Menem y el DNU 70</p></a></div>
      <div class="author"><p>Por <a href="/autor/x/">Verónica Benaim</a></p></div></div>"""
    n, = parsear_tiempoar(soup(html), "https://www.tiempoar.com.ar/", FUENTE)
    assert (n.titulo, n.autor, n.seccion, n.fecha) == ("Menem y el DNU 70", "Verónica Benaim", "La rosca parlamentaria", None)


# ---------------------------------------------------------------- utilidades
def test_normalizar_url():
    assert normalizar_url("http://WWW.Medio.com/politica/nota/?utm_source=tw&id=3#arriba") == \
        "https://www.medio.com/politica/nota?id=3"


def test_seccion_desde_url():
    assert seccion_desde_url("https://tn.com.ar/politica/2026/10/10/nota/") == "politica"
    assert seccion_desde_url("https://www.pagina12.com.ar/2026/10/10/nota/") == ""


def test_unificar_completa_campos():
    a = Nota(url="https://m.com/n?utm_source=x", titulo="T", medio="M", fuente_id="m", categoria="diario")
    b = Nota(url="https://m.com/n", titulo="T", medio="M", fuente_id="m", categoria="diario", bajada="B")
    assert [n.bajada for n in unificar([a, b])] == ["B"]


def test_lotes_x_respeta_largo():
    cuentas = [f"cuenta_numero_{i}" for i in range(60)]
    lotes = _lotes(cuentas)
    assert all(len(q) <= 512 for q in lotes)
    assert sum(q.count("from:") for q in lotes) == 60
