"""Fuente de exchange: descarga el historial real desde la API (Binance, Bybit).

Solo usa endpoints de lectura. Jarvis nunca manda ordenes, y las claves deben
ser de solo lectura: si tu API key tiene permiso de trading, quitaselo antes de
usarla aqui.

Implementado con urllib de la stdlib para no arrastrar dependencias.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..models import Fill, Trade
from .base import ErrorDeFuente, Fuente, Lote

TIMEOUT = 20
REINTENTOS = 3


def _http(url: str, cabeceras: dict[str, str] | None = None, fuente: str = "") -> dict:
    """GET con reintentos y espera creciente ante fallos de red o limite de tasa."""
    ultimo_error: Exception | None = None

    for intento in range(REINTENTOS):
        peticion = urllib.request.Request(url, headers=cabeceras or {}, method="GET")
        try:
            with urllib.request.urlopen(peticion, timeout=TIMEOUT) as respuesta:
                return json.loads(respuesta.read().decode())
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode(errors="replace")[:300]
            # 429/418 = limite de peticiones; 5xx = problema del exchange.
            if e.code in (418, 429) or e.code >= 500:
                ultimo_error = ErrorDeFuente(fuente, f"HTTP {e.code}: {cuerpo}")
                time.sleep(2 ** intento)
                continue
            raise ErrorDeFuente(fuente, f"HTTP {e.code}: {cuerpo}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            ultimo_error = e
            time.sleep(2 ** intento)

    raise ErrorDeFuente(fuente, f"no se pudo contactar con la API: {ultimo_error}")


def _ms(momento: datetime | None) -> int | None:
    return int(momento.timestamp() * 1000) if momento else None


class FuenteExchange(Fuente):
    """Descarga el historial de operaciones desde un exchange.

    Opciones de configuracion:
        exchange  : ``binance``, ``binance_futuros`` o ``bybit``.
        api_key   : clave publica. Usa ``${VARIABLE}`` para leerla del entorno.
        api_secret: clave secreta. Igual, mejor por variable de entorno.
        simbolos  : lista de pares a consultar (obligatorio en Binance).
        categoria : solo Bybit: ``linear`` (por defecto), ``spot`` o ``inverse``.
    """

    tipo = "exchange"

    def leer(self, desde: datetime | None = None, hasta: datetime | None = None) -> Lote:
        exchange = str(self.opciones.get("exchange", "binance")).lower()
        clave = self.opciones.get("api_key")
        secreto = self.opciones.get("api_secret")

        if not clave or not secreto:
            raise ErrorDeFuente(
                self.nombre,
                "faltan api_key / api_secret (recomendado: ponlos como "
                "${BINANCE_API_KEY} y exportalos como variables de entorno)",
            )

        if exchange in ("binance", "binance_spot"):
            return self._binance(clave, secreto, desde, hasta, futuros=False)
        if exchange in ("binance_futuros", "binance_futures"):
            return self._binance(clave, secreto, desde, hasta, futuros=True)
        if exchange == "bybit":
            return self._bybit(clave, secreto, desde, hasta)

        raise ErrorDeFuente(self.nombre, f"exchange no soportado: {exchange}")

    # -- Binance ---------------------------------------------------------

    def _binance(
        self, clave: str, secreto: str,
        desde: datetime | None, hasta: datetime | None, futuros: bool,
    ) -> Lote:
        simbolos = self.opciones.get("simbolos") or []
        if isinstance(simbolos, str):
            simbolos = [s.strip() for s in simbolos.split(",") if s.strip()]
        if not simbolos:
            raise ErrorDeFuente(
                self.nombre,
                "Binance exige consultar simbolo a simbolo: indica "
                "'simbolos: [BTCUSDT, ETHUSDT]' en la configuracion",
            )

        base = "https://fapi.binance.com" if futuros else "https://api.binance.com"
        ruta = "/fapi/v1/userTrades" if futuros else "/api/v3/myTrades"
        lote = Lote()

        for symbol in simbolos:
            params: dict[str, object] = {"symbol": symbol.upper(), "limit": 1000}
            if _ms(desde):
                params["startTime"] = _ms(desde)
            if _ms(hasta):
                params["endTime"] = _ms(hasta)
            params["timestamp"] = int(time.time() * 1000)

            consulta = urllib.parse.urlencode(params)
            firma = hmac.new(secreto.encode(), consulta.encode(), hashlib.sha256).hexdigest()
            url = f"{base}{ruta}?{consulta}&signature={firma}"

            datos = _http(url, {"X-MBX-APIKEY": clave}, self.nombre)
            if isinstance(datos, dict):  # Binance devuelve un dict solo al fallar
                raise ErrorDeFuente(self.nombre, f"respuesta inesperada: {datos}")

            for t in datos:
                comision = abs(float(t.get("commission", 0)))
                lote.fills.append(
                    Fill(
                        ts=datetime.fromtimestamp(int(t["time"]) / 1000, tz=timezone.utc),
                        symbol=t["symbol"],
                        side="buy" if t.get("isBuyer") or t.get("side") == "BUY" else "sell",
                        qty=float(t["qty"]),
                        price=float(t["price"]),
                        fee=comision,
                        fee_currency=t.get("commissionAsset", ""),
                        source=self.nombre,
                        ext_id=str(t.get("id", "")),
                    )
                )

        return lote

    # -- Bybit -----------------------------------------------------------

    def _bybit(
        self, clave: str, secreto: str, desde: datetime | None, hasta: datetime | None
    ) -> Lote:
        base = "https://api.bybit.com"
        categoria = self.opciones.get("categoria", "linear")
        simbolos = self.opciones.get("simbolos") or [None]
        if isinstance(simbolos, str):
            simbolos = [s.strip() for s in simbolos.split(",") if s.strip()]

        lote = Lote()
        ventana = "5000"

        for symbol in simbolos:
            cursor = ""
            while True:
                params = {"category": categoria, "limit": "100"}
                if symbol:
                    params["symbol"] = str(symbol).upper()
                if _ms(desde):
                    params["startTime"] = str(_ms(desde))
                if _ms(hasta):
                    params["endTime"] = str(_ms(hasta))
                if cursor:
                    params["cursor"] = cursor

                consulta = urllib.parse.urlencode(params)
                marca = str(int(time.time() * 1000))
                # Bybit v5 firma: timestamp + apiKey + recvWindow + queryString
                crudo = f"{marca}{clave}{ventana}{consulta}"
                firma = hmac.new(secreto.encode(), crudo.encode(), hashlib.sha256).hexdigest()

                datos = _http(
                    f"{base}/v5/position/closed-pnl?{consulta}",
                    {
                        "X-BAPI-API-KEY": clave,
                        "X-BAPI-TIMESTAMP": marca,
                        "X-BAPI-RECV-WINDOW": ventana,
                        "X-BAPI-SIGN": firma,
                    },
                    self.nombre,
                )

                if datos.get("retCode") != 0:
                    raise ErrorDeFuente(
                        self.nombre, f"Bybit: {datos.get('retMsg', 'error desconocido')}"
                    )

                resultado = datos.get("result") or {}
                for p in resultado.get("list", []):
                    abierto = datetime.fromtimestamp(
                        int(p["createdTime"]) / 1000, tz=timezone.utc
                    )
                    cerrado = datetime.fromtimestamp(
                        int(p["updatedTime"]) / 1000, tz=timezone.utc
                    )
                    # En Bybit 'side' es el lado del cierre: si cerraste vendiendo,
                    # la posicion era larga.
                    direccion = "long" if p.get("side") == "Sell" else "short"
                    comisiones = abs(float(p.get("openFee", 0))) + abs(
                        float(p.get("closeFee", 0))
                    )
                    # closedPnl de Bybit ya viene neto de comisiones. Jarvis guarda
                    # el bruto por separado, asi que se las devolvemos al PnL para
                    # que 'pnl_neto' vuelva a coincidir con lo que dice el exchange.
                    lote.trades.append(
                        Trade(
                            symbol=p["symbol"],
                            direction=direccion,
                            open_ts=abierto,
                            close_ts=max(cerrado, abierto),
                            qty=float(p.get("qty", 0)),
                            entry_price=float(p.get("avgEntryPrice", 0)),
                            exit_price=float(p.get("avgExitPrice", 0)),
                            pnl=float(p.get("closedPnl", 0)) + comisiones,
                            fees=comisiones,
                            source=self.nombre,
                            ext_id=str(p.get("orderId", "")),
                        )
                    )

                cursor = resultado.get("nextPageCursor") or ""
                if not cursor:
                    break

        return lote
