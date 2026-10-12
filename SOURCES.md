# Relevamiento de fuentes

Relevado el 10/10/2026 con `tools/relevar_fuentes.py` más chequeos manuales con curl.
Todas las URLs de esta tabla se pidieron y respondieron 200 con contenido actual,
salvo donde se indica lo contrario. En todos los casos `robots.txt` permite el acceso
a las URLs elegidas. User-Agent usado: `MonitorCongresoAR/0.1 (...)`.

Leyenda de método: **RSS** > **Sitemap de noticias** (Google News sitemap, trae título y
fecha) > **HTML** (último recurso, solo listados, nunca el cuerpo de la nota).

## 1. Oficiales

| Fuente | Método | URL principal | Respaldo / notas |
|---|---|---|---|
| Diputados – agenda (comisiones y sesiones) | HTML | `https://www.hcdn.gob.ar/comisiones/agenda/` | Sin RSS (`/rss` → 404). Lista los próximos días con hora, sala, comisión (o plenario), temario y link a la citación. **También incluye las sesiones especiales convocadas** con su temario. `diputados.gob.ar` redirige a `hcdn.gob.ar`. |
| Diputados – prensa | HTML | `https://www.hcdn.gob.ar/prensa/` | El `sitemap_noticias_prensa.xml` existe pero está desactualizado y sin fechas: no sirve. El listado HTML trae fecha, título y bajada. |
| Diputados – proyectos, dictámenes, legisladores | API CKAN (datos abiertos) | `https://datos.hcdn.gob.ar/api/3/action/package_list` | Se actualizan **semanalmente** (último: 07/10/2026), así que no sirven para "lo de hoy". Se van a usar como tabla de referencia: título de un expediente, nómina de diputados y bloques para `keywords.yaml`. |
| Senado – agenda | HTML | `https://www.senado.gob.ar/parlamentario/Agenda/AgendaWeb/DD,MM,AAAA?agendaCompleta` | Sin RSS (`/rss`, `/prensa/rss` → 404). Cada página muestra la semana (lun-dom) de esa fecha: se piden esta semana y la próxima (2 requests). Mezcla comisiones y sesiones con visitas guiadas, conciertos e iluminaciones; se clasifican por título y el informe muestra solo comisiones y sesiones. |
| Senado – prensa | HTML | `https://www.senado.gob.ar/` (bloque de noticias del home) | No encontré un listado paginado de noticias (`/prensa/noticias` → 404). Cada nota está en `/prensa/{id}/noticias`. Se toman título + fecha + bajada desde el home. |
| Senado – órdenes del día, asuntos entrados | HTML | `/parlamentario/parlamentaria/ordenDelDia`, `/parlamentario/sesiones/asuntosEnt` | Links verificados desde el home; falta ver estructura en detalle. |
| Boletín Oficial – 1ª sección | HTML | `https://www.boletinoficial.gob.ar/seccion/primera` | Sin RSS (`/rss` → página de error). El sumario trae Leyes, Decretos y DNU con número y título. Sirve para promulgaciones, vetos y DNU. robots.txt solo bloquea la 2ª sección (no la usamos). |

## 2. Especializados

| Fuente | Método | URL | Notas |
|---|---|---|---|
| Parlamentario.com | RSS | `https://www.parlamentario.com/feed/` | WordPress, actualiza cada hora. ⚠️ Pide TLS 1.2+: con el Python 3.9/LibreSSL de esta Mac falla; con curl y con Python 3.11 (OpenSSL) anda bien. |
| La Política Online | RSS | `https://www.lapoliticaonline.com/files/rss/politica.xml` | 50 ítems. También `.../files/rss/ultimasnoticias-es.xml`. `/feed/` → 404. |
| Letra P | Sitemap de noticias | `https://www.letrap.com.ar/sitemap-news.xml` | Sin RSS (`/rss`, `/feed/` → 404). El sitemap trae unas 54 notas recientes con título y fecha. |

## 3. Diarios nacionales

| Fuente | Método | URL principal | Respaldo |
|---|---|---|---|
| La Nación | RSS | `https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/politica/?outputType=xml` | `.../sitemap-news.xml` (1000 ítems) |
| Clarín | RSS + sitemap | `https://www.clarin.com/rss/politica/` | El RSS trae solo 10 ítems: con eso no se cubren 24 hs. Se suma `https://www.clarin.com/sitemaps/sitemap_google_news.xml`. |
| Infobae | RSS | `https://www.infobae.com/arc/outboundfeeds/rss/category/politica/` | `.../news-sitemap2/`. El RSS general mezcla toda Latinoamérica: mejor la categoría. |
| Página/12 | RSS + sitemap | `https://www.pagina12.com.ar/arc/outboundfeeds/rss/?outputType=xml` | RSS general (no existe el de categoría: 404) + `.../breakingnews-short.xml`. ⚠️ El `breakingnews-sitemap.xml` que declara su robots.txt está **abandonado** (última nota: 22/08/2026); se detectó en la primera corrida. Los RSS viejos (`/rss/...`) dan 404. |
| Ámbito | RSS | `https://www.ambito.com/rss/pages/politica.xml` | `https://www.ambito.com/sitemap-news.xml` (20 ítems en el RSS; el sitemap amplía la cobertura). |
| El Cronista | RSS | `https://www.cronista.com/arc/outboundfeeds/rss/?outputType=xml` | No hay feed de categoría Política verificado. Feed general (100 ítems) + filtro temático. |
| Perfil | RSS | `https://www.perfil.com/feed/politica` | `https://www.perfil.com/sitemap/google-news-lastposts` |
| elDiarioAR | RSS | `https://www.eldiarioar.com/rss/politica/` | `https://www.eldiarioar.com/sitemap_google_news_a59a1.xml` |
| Tiempo Argentino | **HTML** | `https://www.tiempoar.com.ar/ta_section/politica/` | ⚠️ El feed `/feed/` está **comprometido**: devuelve spam en ruso de 2025. El feed de categoría viene vacío, `news-sitemap.xml` devuelve HTML y los sitemaps de artículos están desordenados (2016/2024). Solo queda leer títulos y links del listado de sección. |

## 4. Noticieros

| Fuente | Método | URL | Notas |
|---|---|---|---|
| TN | RSS + sitemap | `https://tn.com.ar/arc/outboundfeeds/rss/category/politica/?outputType=xml` | El RSS de Política trae ~29 ítems y abarca varios días; se suma `.../news-sitemap/?outputType=xml` (585). |
| C5N | Sitemap de noticias | `https://www.c5n.com/sitemap-news.xml` | Sin RSS (`/rss`, `/feed` → 404). |
| A24 | Sitemap de noticias | `https://www.a24.com/sitemap-news.xml` | Sin RSS (todo → 404). |
| LN+ | RSS | `https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/lnmas/?outputType=xml` | LN+ no tiene sitio propio: vive dentro de lanacion.com.ar. Mucho contenido no político; queda a cargo del filtro. Se registra como medio "LN+" aparte de La Nación. |

## 5. X / Twitter
Módulo aparte, **desactivado por defecto**. Usa solo la API oficial v2 (búsqueda reciente: `GET /2/tweets/search/recent` con `from:cuenta`, en lotes)
con `X_BEARER_TOKEN`. No se relevó: depende de que tengan credencial y del plan de API.

## Limitaciones y lo que no se pudo cubrir del todo

- **Sitemaps de noticias**: traen título y fecha, pero **no bajada, autor ni sección**.
  Para no pedir cada nota (y no tocar el cuerpo), en esas fuentes esos campos quedan
  vacíos. La sección se infiere de la URL cuando se puede (`/politica/...`).
- **Tiempo Argentino**: cobertura solo vía HTML del listado de sección, sin fecha confiable
  en el listado. La fecha se toma como "visto por primera vez" en la corrida.
- **Senado prensa**: solo las ~6 notas destacadas del home; si publican más en un día, se pierden.
- **Diputados agenda / Senado agenda / BO**: es scraping HTML. Es frágil ante rediseños.
  Si falla, el informe lo marca como fuente caída.
- **Paywalls** (La Nación, Clarín): no afectan, porque solo usamos título, bajada y link de feeds/sitemaps.

## Pendientes
- **Proyectos ingresados en el día y órdenes del día del Senado**: no se implementaron en la
  etapa 1. Los datos abiertos son semanales y las páginas del Senado (`ordenDelDia`,
  `asuntosEnt`) requieren otro parser. Por ahora, los proyectos llegan a través de la prensa
  y las agendas.
- **Parlamentario.com con Python < 3.11 en macOS**: el Python del sistema (LibreSSL) no
  negocia TLS con ese sitio. Con Python 3.11+ (OpenSSL) funciona. El informe la va a marcar
  como caída si se corre con el Python viejo.
