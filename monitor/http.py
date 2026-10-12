"""Cliente HTTP educado: User-Agent identificable, robots.txt y 1 request cada 2 s por dominio."""
from __future__ import annotations

import logging
import threading
import time
import urllib.robotparser
from typing import Dict, Optional
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

USER_AGENT = "MonitorCongresoAR/0.1 (monitor personal de prensa legislativa; respeta robots.txt)"


class BloqueadoPorRobots(Exception):
    pass


class Cliente:
    def __init__(self, user_agent: str = USER_AGENT, delay: float = 2.0,
                 timeout: float = 25.0, reintentos: int = 2):
        self.user_agent = user_agent
        self.delay = delay
        self.reintentos = reintentos
        self._http = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Language": "es-AR,es;q=0.9"},
            timeout=timeout, follow_redirects=True,
        )
        self._lock = threading.Lock()
        self._proximo: Dict[str, float] = {}  # host -> momento (monotonic) del próximo request permitido
        self._robots: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        self._robots_locks: Dict[str, threading.Lock] = {}
        self._robots_error: Dict[str, str] = {}  # host -> motivo por el que no se pudo leer robots.txt

    def close(self):
        self._http.close()

    # ------------------------------------------------------------------ throttling
    def _esperar_turno(self, host: str):
        """Reserva el próximo hueco para el host: los requests arrancan separados por >= delay."""
        with self._lock:
            ahora = time.monotonic()
            turno = max(ahora, self._proximo.get(host, 0.0))
            self._proximo[host] = turno + self._delay_host(host)
        espera = turno - ahora
        if espera > 0:
            time.sleep(espera)

    def _delay_host(self, host: str) -> float:
        rp = self._robots.get(host)
        crawl = rp.crawl_delay(self.user_agent) if rp else None
        return max(self.delay, float(crawl or 0))

    # ------------------------------------------------------------------ robots.txt
    def _robots_para(self, esquema: str, host: str) -> Optional[urllib.robotparser.RobotFileParser]:
        """Devuelve el parser de robots del host; None significa 'no se pudo leer → no pedir nada'."""
        with self._lock:
            lock = self._robots_locks.setdefault(host, threading.Lock())
        with lock:
            if host in self._robots:
                return self._robots[host]
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self._pedir(f"{esquema}://{host}/robots.txt", host)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                elif r.status_code in (401, 403):
                    rp.disallow_all = True
                elif 400 <= r.status_code < 500:
                    rp.allow_all = True  # no hay robots.txt: todo permitido (RFC 9309)
                else:
                    rp = None  # 5xx: inaccesible, se asume prohibido
                    self._robots_error[host] = f"robots.txt respondió HTTP {r.status_code}"
            except httpx.HTTPError as e:
                log.warning("robots.txt de %s inaccesible: %s", host, e)
                rp = None
                self._robots_error[host] = f"no se pudo leer robots.txt ({type(e).__name__}: {e})"
            self._robots[host] = rp
            return rp

    def permitido(self, url: str) -> bool:
        partes = urlsplit(url)
        rp = self._robots_para(partes.scheme, partes.netloc)
        return rp is not None and rp.can_fetch(self.user_agent, url)

    # ------------------------------------------------------------------ requests
    def _pedir(self, url: str, host: str) -> httpx.Response:
        ultimo_error: Optional[Exception] = None
        for intento in range(self.reintentos + 1):
            self._esperar_turno(host)
            try:
                r = self._http.get(url)
            except httpx.TransportError as e:
                ultimo_error = e
            else:
                if r.status_code != 429 and r.status_code < 500:
                    return r
                ultimo_error = httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            if intento < self.reintentos:
                time.sleep(3 * (intento + 1))
        assert ultimo_error is not None
        raise ultimo_error

    def get(self, url: str) -> httpx.Response:
        """GET respetando robots.txt y el ritmo por dominio. Lanza excepción si no es 2xx."""
        partes = urlsplit(url)
        if not self.permitido(url):
            motivo = self._robots_error.get(partes.netloc)
            if motivo:
                raise ConnectionError(motivo)
            raise BloqueadoPorRobots(f"robots.txt no permite {url}")
        r = self._pedir(url, partes.netloc)
        r.raise_for_status()
        return r
