import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest

from observatorio.api_client import ApiError, MercadoPublicoClient

TICKET = "SECRETO-1234"
DETAIL = json.loads((Path(__file__).parent / "fixtures" / "api_detail.json").read_text())


def client(handler) -> MercadoPublicoClient:
    return MercadoPublicoClient(TICKET, min_interval=0, transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_ticket_invalido_es_error_aunque_http_sea_2xx():
    def handler(request):
        return httpx.Response(203, json={"Codigo": 203, "Mensaje": "Ticket no válido."})

    with client(handler) as c, pytest.raises(ApiError) as exc:
        c.listing(date(2026, 8, 1))
    assert "203" in str(exc.value)
    assert TICKET not in str(exc.value)


def test_reintenta_5xx_y_luego_responde():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(500)
        return httpx.Response(200, json=DETAIL)

    with client(handler) as c:
        detail = c.detail("1079866-30-LE26")
    assert len(calls) == 3
    assert detail["CodigoExterno"] == "1079866-30-LE26"
    assert calls[0].url.params["codigo"] == "1079866-30-LE26"


def test_agota_reintentos_sin_filtrar_ticket():
    def handler(request):
        raise httpx.ConnectError(f"fallo en {request.url}")

    with client(handler) as c, pytest.raises(ApiError) as exc:
        c.detail("x")
    assert TICKET not in str(exc.value)


def test_listing_usa_formato_ddmmaaaa():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json={"Cantidad": 0, "Listado": []})

    with client(handler) as c:
        assert c.listing(date(2026, 8, 14)) == []
    assert seen["fecha"] == "14082026"


def test_detalle_inexistente_devuelve_none():
    with client(lambda r: httpx.Response(200, json={"Cantidad": 0, "Listado": []})) as c:
        assert c.detail("no-existe") is None


def test_ticket_no_aparece_en_logs(caplog):
    caplog.set_level(logging.DEBUG)
    with client(lambda r: httpx.Response(200, json={"Cantidad": 0, "Listado": []})) as c:
        c.listing(date(2026, 8, 14))
    assert TICKET not in caplog.text
