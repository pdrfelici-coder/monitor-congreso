"""Relevamiento de fuentes: comprueba RSS, sitemaps y robots.txt de cada medio.

Solo stdlib, para poder correrlo antes de instalar dependencias.
Uso: python tools/relevar_fuentes.py > relevamiento.json
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

UA = "MonitorCongresoAR/0.1 (monitor de prensa legislativa; respeta robots.txt)"
DELAY = 2.0

# Candidatos a comprobar. Se suman los <link rel=alternate> del home y los Sitemap: del robots.txt.
FUENTES = {
    "diputados": ("https://www.diputados.gob.ar/", [
        "https://www.diputados.gob.ar/rss", "https://www.diputados.gob.ar/rss.xml",
        "https://www.diputados.gob.ar/prensa/", "https://www.diputados.gob.ar/comisiones/agenda/",
        "https://www.hcdn.gob.ar/", "https://datos.hcdn.gob.ar/",
    ]),
    "senado": ("https://www.senado.gob.ar/", [
        "https://www.senado.gob.ar/rss", "https://www.senado.gob.ar/prensa/rss",
        "https://www.senado.gob.ar/parlamentario/comisiones/agenda",
        "https://www.senado.gob.ar/prensa", "https://www.senado.gob.ar/micrositios/DatosAbiertos/",
    ]),
    "boletin_oficial": ("https://www.boletinoficial.gob.ar/", [
        "https://www.boletinoficial.gob.ar/rss", "https://www.boletinoficial.gob.ar/seccion/primera",
    ]),
    "parlamentario": ("https://www.parlamentario.com/", [
        "https://www.parlamentario.com/feed/", "https://www.parlamentario.com/rss",
    ]),
    "lpo": ("https://www.lapoliticaonline.com/", [
        "https://www.lapoliticaonline.com/rss", "https://www.lapoliticaonline.com/feed/",
        "https://www.lapoliticaonline.com/files/rss/politica.xml",
    ]),
    "letrap": ("https://www.letrap.com.ar/", [
        "https://www.letrap.com.ar/rss", "https://www.letrap.com.ar/feed/",
        "https://www.letrap.com.ar/rss/home.xml",
    ]),
    "lanacion": ("https://www.lanacion.com.ar/", [
        "https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml",
        "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/politica/?outputType=xml",
    ]),
    "clarin": ("https://www.clarin.com/", [
        "https://www.clarin.com/rss/politica/", "https://www.clarin.com/rss/lo-ultimo/",
    ]),
    "infobae": ("https://www.infobae.com/", [
        "https://www.infobae.com/arc/outboundfeeds/rss/",
        "https://www.infobae.com/arc/outboundfeeds/rss/category/politica/",
    ]),
    "pagina12": ("https://www.pagina12.com.ar/", [
        "https://www.pagina12.com.ar/rss/secciones/el-pais/notas",
        "https://www.pagina12.com.ar/rss/portada",
    ]),
    "ambito": ("https://www.ambito.com/", [
        "https://www.ambito.com/rss/pages/politica.xml", "https://www.ambito.com/rss/pages/home.xml",
    ]),
    "cronista": ("https://www.cronista.com/", [
        "https://www.cronista.com/arc/outboundfeeds/rss/?outputType=xml",
        "https://www.cronista.com/files/rss/politica.xml", "https://www.cronista.com/rss/",
    ]),
    "perfil": ("https://www.perfil.com/", [
        "https://www.perfil.com/feed/politica", "https://www.perfil.com/feed",
    ]),
    "eldiarioar": ("https://www.eldiarioar.com/", [
        "https://www.eldiarioar.com/rss/politica/", "https://www.eldiarioar.com/rss/",
    ]),
    "tiempoar": ("https://www.tiempoar.com.ar/", [
        "https://www.tiempoar.com.ar/feed/", "https://www.tiempoar.com.ar/ta_article/politica/feed/",
        "https://www.tiempoar.com.ar/rss",
    ]),
    "tn": ("https://tn.com.ar/", [
        "https://tn.com.ar/arc/outboundfeeds/rss/?outputType=xml",
        "https://tn.com.ar/arc/outboundfeeds/rss/category/politica/?outputType=xml",
    ]),
    "c5n": ("https://www.c5n.com/", [
        "https://www.c5n.com/rss/politica", "https://www.c5n.com/rss", "https://www.c5n.com/feed",
    ]),
    "a24": ("https://www.a24.com/", [
        "https://www.a24.com/rss/politica", "https://www.a24.com/rss", "https://www.a24.com/feed",
    ]),
    "lnmas": ("https://www.lanacion.com.ar/lnmas/", [
        "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/lnmas/?outputType=xml",
    ]),
}


def fetch(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(3_000_000)
            return {"status": r.status, "final_url": r.geturl(),
                    "ctype": r.headers.get("Content-Type", ""), "body": body}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "final_url": url, "ctype": "", "body": b"", "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"status": None, "final_url": url, "ctype": "", "body": b"", "error": repr(e)[:200]}


def analizar_xml(body: bytes) -> dict:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return {"kind": "no-xml"}
    tag = root.tag.split("}")[-1]
    ns = root.tag.split("}")[0].strip("{") if "}" in root.tag else ""
    if tag == "rss" or tag == "RDF":
        items = root.findall(".//item")
        fechas = [i.findtext("pubDate") or "" for i in items[:3]]
        return {"kind": "rss", "items": len(items), "muestra": [(i.findtext("title") or "")[:90] for i in items[:2]], "fechas": fechas}
    if tag == "feed":
        entries = [e for e in root if e.tag.endswith("entry")]
        return {"kind": "atom", "items": len(entries)}
    if tag == "urlset":
        txt = body[:5000].decode("utf-8", "ignore")
        return {"kind": "sitemap-news" if "sitemap-news" in txt else "sitemap", "items": len(list(root))}
    if tag == "sitemapindex":
        locs = [e.findtext("{*}loc") or "" for e in root][:400]
        return {"kind": "sitemapindex", "items": len(locs), "news_like": [l for l in locs if re.search(r"news|noticias|google", l, re.I)][:5]}
    return {"kind": f"xml:{tag}", "ns": ns}


class Dominio:
    def __init__(self):
        self.locks: dict[str, threading.Lock] = {}
        self.last: dict[str, float] = {}

    def wait(self, url: str):
        host = urlparse(url).netloc
        lock = self.locks.setdefault(host, threading.Lock())
        with lock:
            delta = time.monotonic() - self.last.get(host, 0)
            if delta < DELAY:
                time.sleep(DELAY - delta)
            self.last[host] = time.monotonic()


RATE = Dominio()


def get(url):
    RATE.wait(url)
    return fetch(url)


def relevar(nombre: str, home: str, candidatos: list[str]) -> dict:
    out = {"fuente": nombre, "home": home, "checks": []}
    robots_url = urljoin(home, "/robots.txt")
    r = get(robots_url)
    rp = urllib.robotparser.RobotFileParser()
    txt = r["body"].decode("utf-8", "ignore") if r["status"] == 200 else ""
    rp.parse(txt.splitlines())
    sitemaps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", txt)
    out["robots"] = {"status": r["status"], "sitemaps": sitemaps, "error": r.get("error")}

    h = get(home)
    out["home_status"] = h["status"]
    alt = []
    if h["body"]:
        html = h["body"].decode("utf-8", "ignore")
        for m in re.finditer(r"<link[^>]+>", html, re.I):
            tag = m.group(0)
            if re.search(r"application/(rss|atom)\+xml", tag, re.I):
                hm = re.search(r'href=["\']([^"\']+)', tag)
                if hm:
                    alt.append(urljoin(home, hm.group(1)))
        out["home_rss_links"] = alt

    vistos = set()
    news_sitemaps = [s for s in sitemaps if re.search(r"news|noticias|google", s, re.I)]
    for url in candidatos + alt + news_sitemaps[:3]:
        if url in vistos:
            continue
        vistos.add(url)
        res = get(url)
        info = {"url": url, "status": res["status"], "final_url": res["final_url"],
                "ctype": res["ctype"][:60], "robots_ok": rp.can_fetch(UA, url) if txt else None}
        if res.get("error"):
            info["error"] = res["error"][:150]
        if res["status"] == 200 and res["body"]:
            if b"<?xml" in res["body"][:200] or b"<rss" in res["body"][:500] or "xml" in res["ctype"]:
                info.update(analizar_xml(res["body"]))
            else:
                info["kind"] = "html"
                info["title"] = (re.search(rb"<title[^>]*>(.*?)</title>", res["body"], re.S | re.I) or [None, b""])[1][:100].decode("utf-8", "ignore").strip()
        out["checks"].append(info)
    return out


def main():
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(relevar, n, h, c) for n, (h, c) in FUENTES.items()]
        res = [f.result() for f in futs]
    json.dump(res, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
