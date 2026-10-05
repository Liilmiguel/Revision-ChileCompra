"""Cliente de la API de licitaciones de Mercado Público.

- Una petición a la vez con pausa mínima entre llamadas (la API rechaza concurrencia).
- Reintentos con backoff exponencial ante 5xx, errores de red y JSON inválido.
- La API señala errores en el cuerpo (`{"Codigo": 203, "Mensaje": ...}`) aun con
  status 2xx: se convierten en ApiError.
- El ticket nunca aparece en mensajes de error ni logs.
"""

from __future__ import annotations

import logging
import time
from datetime import date

import httpx

API_BASE = "https://api.mercadopublico.cl/servicios/v1/publico/"

log = logging.getLogger(__name__)


class ApiError(RuntimeError):
    """Error informado por la API (ticket inválido, cuota agotada, etc.)."""


class MercadoPublicoClient:
    def __init__(
        self,
        ticket: str,
        *,
        min_interval: float = 1.5,
        max_retries: int = 4,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ) -> None:
        self._ticket = ticket
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._sleep = sleep
        self._last_call = 0.0
        self._http = httpx.Client(base_url=API_BASE, timeout=60, transport=transport)

    def __enter__(self) -> MercadoPublicoClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self._http.close()

    def mask(self, text: str) -> str:
        return text.replace(self._ticket, "***")

    def _throttle(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = time.monotonic()

    def _get(self, params: dict) -> dict:
        last_error = ""
        for attempt in range(self._max_retries):
            self._throttle()
            try:
                resp = self._http.get("licitaciones.json", params={**params, "ticket": self._ticket})
                if resp.status_code < 500:
                    body = resp.json()
                    if "Listado" in body:
                        return body
                    # Error de negocio: no se reintenta salvo que sea transitorio.
                    msg = f"API Codigo {body.get('Codigo')}: {body.get('Mensaje')} (HTTP {resp.status_code})"
                    if resp.status_code == 429:
                        last_error = msg
                    else:
                        raise ApiError(msg)
                else:
                    last_error = f"HTTP {resp.status_code}"
            except (httpx.HTTPError, ValueError) as exc:
                last_error = self.mask(str(exc))
            log.warning("reintento %d tras %s", attempt + 1, last_error)
            self._sleep(2 ** (attempt + 1))
        raise ApiError(f"sin respuesta válida tras {self._max_retries} intentos: {last_error}")

    def listing(self, day: date) -> list[dict]:
        """Licitaciones cuyo evento (adjudicación, cierre…) ocurrió ese día. Solo 4 campos."""
        return self._get({"fecha": day.strftime("%d%m%Y")})["Listado"]

    def detail(self, codigo_externo: str) -> dict | None:
        listado = self._get({"codigo": codigo_externo})["Listado"]
        return listado[0] if listado else None
