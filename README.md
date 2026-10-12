# Monitor del Congreso

Monitor diario de medios argentinos sobre la actividad del Congreso Nacional (Diputados y Senado).

Todos los días, a primera hora, recolecta lo publicado en las últimas 24 horas por las fuentes
oficiales, los medios especializados, los diarios nacionales y los sitios de noticieros. Se queda
con lo que habla del Congreso, agrupa la misma noticia contada por varios medios en un solo
**tema**, lo clasifica y arma un informe HTML pensado para leerse en dos minutos:

- **Lo más cubierto:** los 5 temas con más medios, con un link a cada nota.
- **Agenda legislativa:** sesiones y reuniones de comisión de hoy y de los próximos días.
- **Volumen:** notas por día (contra los 7 días anteriores), por medio y por tema.
- **Tabla completa:** filtrable por cámara, tipo y medio, con buscador.
- **Pie:** qué fuentes no respondieron y la hora de la corrida.

## Dónde se ve

Una vez configurado en GitHub (ver abajo), el informe del día está siempre en
`https://<tu-usuario>.github.io/<nombre-del-repo>/`. Desde ahí, "Días anteriores" lleva al
archivo con todos los informes.

## Cómo funciona

```
run.py                       un solo comando que hace todo
config/fuentes.yaml          qué fuentes se consultan y cómo (RSS, sitemap o HTML)
config/keywords.yaml         filtro temático, personas, clasificación y proyectos — EDITABLE
config/cuentas_x.yaml        cuentas de X (módulo apagado por defecto)
monitor/http.py              cliente HTTP: User-Agent propio, robots.txt, 1 request cada 2 s por dominio
monitor/colectores/          un colector por tipo de fuente
monitor/filtro.py            decide si una nota es sobre el Congreso
monitor/dedup.py             agrupa la misma noticia en un tema
monitor/clasificar.py        cámara, tipo y proyecto de ley de cada tema
monitor/db.py                SQLite con el histórico
monitor/informe.py           arma el HTML (plantilla en templates/)
datos/monitor.db             base histórica (notas, temas, agenda, corridas)
datos/csv/                   export diario: AAAA-MM-DD_temas.csv y AAAA-MM-DD_notas.csv
informes/                    un HTML por día + index.html (el último) + archivo.html
SOURCES.md                   relevamiento de fuentes: qué método usa cada una y qué no se pudo cubrir
```

Reglas que respeta: solo guarda título, bajada (recortada), medio, autor, fecha, URL y sección;
nunca el cuerpo de las notas; no saltea paywalls; respeta `robots.txt`; se identifica con un
User-Agent propio y hace como máximo 1 request cada 2 segundos por dominio. Si una fuente
falla, se registra y el informe lo muestra en el pie.

## Puesta en marcha en GitHub (una sola vez)

Corre en los servidores de GitHub, así que **la computadora puede estar apagada**.

1. **Subir el proyecto a un repositorio de GitHub.** Con una cuenta gratuita, el repositorio tiene
   que ser **público** para poder usar GitHub Pages (con GitHub Pro puede ser privado).
2. **Activar GitHub Pages:** en el repositorio, *Settings → Pages → Build and deployment →
   Source: **GitHub Actions***.
3. **Probarlo:** *Actions → Monitor diario → Run workflow*. En unos minutos el informe queda
   publicado en el link de Pages (también aparece en el resumen de la corrida).

A partir de ahí corre solo todos los días a las **06:30 hora argentina**. GitHub a veces demora las
corridas programadas entre 5 y 30 minutos; por eso se programa antes de las 7:00. Para cambiar el
horario, editá la línea `cron` en `.github/workflows/diario.yml` (está en hora UTC: Argentina es UTC−3).

Cada corrida guarda en el repositorio la base, los CSV y el informe del día, así que el histórico
queda versionado.

**Si una corrida falla,** GitHub te avisa por mail. En *Actions* se ve el detalle.

## Editar el filtro y la clasificación

Todo está en `config/keywords.yaml`, con comentarios:

- `fuertes`: alcanza con uno para que la nota entre (quórum, dictamen, Senado…).
- `debiles`: hacen falta dos (ley + veto, presupuesto + votos…).
- `excluir`: frases que se borran antes de buscar (Congresos de otros países, legislaturas provinciales…).
- `personas`: autoridades y jefes de bloque. Cuentan como término fuerte.
- `proyectos`: proyectos conocidos para asociar a cada tema (Presupuesto 2027, etc.).
- `tipos` y `camaras`: palabras que definen la clasificación.
- `agrupamiento.umbral`: qué tan parecidas tienen que ser dos notas para ir al mismo tema.

Al subir un cambio, GitHub corre los tests automáticamente (*Actions → Tests*) y avisa si algo se rompió.

## Módulo de X (opcional, apagado)

Usa solo la API oficial de X; nunca scraping. Para activarlo:

1. Poné `activo: true` en `config/cuentas_x.yaml` y completá las cuentas.
2. En el repositorio: *Settings → Secrets and variables → Actions → New repository secret*,
   con nombre `X_BEARER_TOKEN` y el token de la API.

Sin el token o con `activo: false`, el módulo se saltea sin afectar al resto.

## Correrlo en una computadora (opcional)

Hace falta Python 3.11 o superior (en Mac, el instalador de [python.org](https://www.python.org/downloads/)).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python run.py            # recolecta, procesa y genera informes/AAAA-MM-DD.html
python -m pytest -q      # tests
```

Opciones de `run.py`: `--horas 48` (ventana más amplia), `--solo clarin,tn` (probar algunas
fuentes), `--db` e `--informes` (otras rutas), `-v` (más detalle).

## Limitaciones conocidas

- Las fuentes oficiales (agendas de las cámaras, Boletín Oficial) y Tiempo Argentino se leen
  desde el HTML de sus páginas porque no tienen RSS: si rediseñan el sitio, esa fuente aparece
  como "vacía" o "caída" en el pie hasta que se ajuste el parser.
- En los medios que solo ofrecen sitemap (Letra P, C5N, A24 y parte de otros) no hay bajada ni autor.
- La clasificación es por reglas: es predecible, pero a veces se equivoca. La agrupación en temas
  puede juntar dos historias parecidas o separar una que se cuenta con palabras muy distintas.
- Las listas de autoridades del Senado están pendientes (ver `config/keywords.yaml`).
- Más detalles por fuente en `SOURCES.md`.
