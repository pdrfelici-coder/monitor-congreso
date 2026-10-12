"""El informe se genera de punta a punta con datos sintéticos y trae las secciones pedidas."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from monitor import db, informe
from monitor.modelos import EstadoFuente, EventoAgenda, Nota, Tema

RAIZ = Path(__file__).parent.parent
AHORA = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)  # 07:00 en Argentina
FECHA = "2026-10-13"


def nota(titulo, medio, h=1):
    return Nota(url=f"https://{medio.lower()}.com/{abs(hash(titulo))}", titulo=titulo, medio=medio,
                fuente_id=medio.lower(), categoria="diario", fecha=AHORA - timedelta(hours=h),
                bajada=f"Bajada de {titulo}")


def preparar(tmp_path):
    con = db.conectar(tmp_path / "m.db")
    # Un día previo con historia para que haya comparación
    corrida0 = db.iniciar_corrida(con, AHORA - timedelta(days=1), AHORA - timedelta(days=2))
    previa = [nota("Nota de ayer", "TN", h=26)]
    ids0 = db.guardar_notas(con, previa, corrida0, AHORA - timedelta(days=1))
    db.guardar_temas(con, "2026-10-12", corrida0, [Tema("Ayer", "Senado", "Sesión", "", previa)], ids0)

    corrida = db.iniciar_corrida(con, AHORA, AHORA - timedelta(hours=24))
    temas = [
        Tema("Presupuesto 2027 en comisión", "Diputados", "Comisión", "Presupuesto 2027",
             [nota("Presupuesto 2027 en comisión", "TN"), nota("Hacienda defendió el Presupuesto", "Clarín", 2)]),
        Tema("El Senado <b>aprobó</b> pliegos", "Senado", "Sesión", "", [nota("El Senado aprobó pliegos", "Infobae")]),
    ]
    notas = [n for t in temas for n in t.notas]
    ids = db.guardar_notas(con, notas, corrida, AHORA)
    db.guardar_temas(con, FECHA, corrida, temas, ids)
    db.guardar_agenda(con, [
        EventoAgenda("Diputados", date(2026, 10, 13), "12:00", "PRESUPUESTO Y HACIENDA", "comision", "hcdn_agenda",
                     temario="Presupuesto 2027"),
        EventoAgenda("Diputados", date(2026, 10, 15), "14:00", "SESIÓN ESPECIAL", "sesion", "hcdn_agenda",
                     temario="Orden del Día 433"),
        EventoAgenda("Senado", date(2026, 10, 13), "19:00", "Iluminación de los balcones", "otro", "senado_agenda"),
    ], AHORA)
    estados = [EstadoFuente("tn", "TN", "ok"), EstadoFuente("hcdn_agenda", "Diputados (agenda)", "ok"),
               EstadoFuente("senado_agenda", "Senado (agenda)", "error", errores=["el sitio está en mantenimiento"])]
    return con, temas, estados


def test_informe_completo(tmp_path):
    con, temas, estados = preparar(tmp_path)
    ctx = informe.contexto(con, FECHA, AHORA, temas, estados, [], ahora_iso=AHORA.isoformat())
    html = informe.renderizar(ctx, RAIZ / "templates", tmp_path / "informes" / f"{FECHA}.html").read_text()

    assert "Martes 13 de octubre de 2026" in html
    assert "Lo más cubierto" in html and "Presupuesto 2027 en comisión" in html
    assert "Agenda legislativa" in html and "Presupuesto y hacienda" in html and "Sesión especial" in html
    assert "Iluminación" not in html  # actividades protocolares fuera de la agenda
    assert "Notas por medio" in html and "Notas por tema" in html
    assert 'id="f-camara"' in html and 'id="f-medio"' in html
    assert "Senado (agenda)" in html and "mantenimiento" in html  # pie con fuentes caídas
    assert "<b>aprobó</b>" not in html  # el contenido de los medios se escapa
    assert "<script src" not in html and "<link" not in html  # autocontenido
    assert ctx["kpi"]["notas"] == 3 and ctx["kpi"]["prom_notas"] == 1


def test_indice(tmp_path):
    (tmp_path / "2026-10-12.html").write_text("x")
    (tmp_path / "2026-10-13.html").write_text("informe del 13")
    informe.actualizar_indice(tmp_path)
    archivo = (tmp_path / "archivo.html").read_text()
    assert archivo.index("2026-10-13.html") < archivo.index("2026-10-12.html")
    assert (tmp_path / "index.html").read_text() == "informe del 13"  # el link fijo muestra el último


def test_titulos_de_agenda():
    assert informe._titulo_agenda("Plenario: DEFENSA NACIONAL, LEGISLACION PENAL") == "Plenario: Defensa nacional, Legislacion penal"
    assert informe._titulo_agenda("Reunión de la Comisión de Ciencia") == "Reunión de la Comisión de Ciencia"
