"""El cliente respeta robots.txt y el ritmo mínimo por dominio, sin tocar la red."""
import time

import httpx
import pytest

from monitor.http import BloqueadoPorRobots, Cliente

ROBOTS = "User-agent: *\nDisallow: /privado/\n"


def cliente_falso(delay=0.3, robots=ROBOTS, robots_status=200):
    pedidos = []

    def responder(request: httpx.Request):
        pedidos.append((time.monotonic(), str(request.url)))
        if request.url.path == "/robots.txt":
            return httpx.Response(robots_status, text=robots)
        return httpx.Response(200, text="ok")

    c = Cliente(delay=delay)
    c._http = httpx.Client(transport=httpx.MockTransport(responder))
    return c, pedidos


def test_respeta_robots():
    c, _ = cliente_falso()
    assert c.get("https://medio.com/politica/nota").text == "ok"
    with pytest.raises(BloqueadoPorRobots):
        c.get("https://medio.com/privado/nota")


def test_robots_inaccesible_no_pide_nada():
    c, pedidos = cliente_falso(robots_status=503)
    c.reintentos = 0
    with pytest.raises(ConnectionError):
        c.get("https://medio.com/nota")
    assert [u for _, u in pedidos] == ["https://medio.com/robots.txt"]


def test_ritmo_por_dominio():
    c, pedidos = cliente_falso(delay=0.3)
    for i in range(3):
        c.get(f"https://medio.com/nota{i}")
    c.get("https://otro.com/nota")  # otro dominio: no espera al anterior
    tiempos = [t for t, u in pedidos if "medio.com" in u]  # robots + 3 notas
    assert all(b - a >= 0.29 for a, b in zip(tiempos, tiempos[1:]))
