"""Fuente MetaTrader 5 (forex, indices, CFDs).

Dos caminos, segun donde corras Jarvis:

- ``directo``: usa la libreria oficial ``MetaTrader5``, que solo existe en
  Windows y necesita el terminal abierto. Trae el historial completo.
- ``informe``: lee un informe exportado desde el terminal (HTML o CSV). Sirve
  desde cualquier sistema operativo y no necesita nada instalado.

Si no se indica modo, Jarvis intenta el directo y cae al informe si la libreria
no esta disponible.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path

from ..models import Trade
from .base import ErrorDeFuente, Fuente, Lote
from .parsing import a_fecha, a_numero

# Tipos de operacion de MT5: 0 = compra, 1 = venta. El resto (depositos,
# balance, credito) no son operaciones y se descartan.
_COMPRA, _VENTA = 0, 1


class FuenteMT5(Fuente):
    """Lee el historial de MetaTrader 5.

    Opciones de configuracion:
        modo    : ``auto`` (por defecto), ``directo`` o ``informe``.
        ruta    : ruta del informe exportado, para el modo ``informe``.
        login   : numero de cuenta, para el modo directo.
        password: contrasena de la cuenta.
        servidor: nombre del servidor del broker.
    """

    tipo = "mt5"

    def leer(self, desde: datetime | None = None, hasta: datetime | None = None) -> Lote:
        modo = self.opciones.get("modo", "auto")

        if modo in ("auto", "directo"):
            try:
                return self._directo(desde, hasta)
            except ErrorDeFuente:
                if modo == "directo":
                    raise
                # En modo auto seguimos probando con el informe exportado.

        if self.opciones.get("ruta"):
            return self._informe()

        raise ErrorDeFuente(
            self.nombre,
            "sin la libreria MetaTrader5 hace falta la opcion 'ruta' con un "
            "informe exportado desde el terminal (Historial > Informe)",
        )

    # -- modo directo ----------------------------------------------------

    def _directo(self, desde: datetime | None, hasta: datetime | None) -> Lote:
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError as e:
            raise ErrorDeFuente(
                self.nombre, "la libreria MetaTrader5 no esta instalada (solo Windows)"
            ) from e

        credenciales = {}
        if self.opciones.get("login"):
            credenciales = {
                "login": int(self.opciones["login"]),
                "password": self.opciones.get("password", ""),
                "server": self.opciones.get("servidor", ""),
            }

        if not mt5.initialize(**credenciales):
            raise ErrorDeFuente(self.nombre, f"no se pudo conectar al terminal: {mt5.last_error()}")

        try:
            inicio = desde or datetime(2000, 1, 1, tzinfo=timezone.utc)
            fin = hasta or datetime.now(timezone.utc)
            operaciones = mt5.history_deals_get(inicio, fin) or []

            # MT5 entrega 'deals' sueltos: una entrada y una salida por posicion.
            # Se agrupan por ticket de posicion para reconstruir la operacion.
            posiciones: dict[int, list] = {}
            for d in operaciones:
                if d.type not in (_COMPRA, _VENTA):
                    continue
                posiciones.setdefault(d.position_id, []).append(d)

            lote = Lote()
            for ticket, deals in posiciones.items():
                deals.sort(key=lambda d: d.time)
                if len(deals) < 2:
                    continue  # posicion aun abierta
                entrada, salida = deals[0], deals[-1]
                lote.trades.append(
                    Trade(
                        symbol=entrada.symbol,
                        direction="long" if entrada.type == _COMPRA else "short",
                        open_ts=datetime.fromtimestamp(entrada.time, tz=timezone.utc),
                        close_ts=datetime.fromtimestamp(salida.time, tz=timezone.utc),
                        qty=float(entrada.volume),
                        entry_price=float(entrada.price),
                        exit_price=float(salida.price),
                        pnl=sum(float(d.profit) for d in deals),
                        fees=sum(
                            abs(float(d.commission)) + abs(float(d.swap)) for d in deals
                        ),
                        source=self.nombre,
                        ext_id=str(ticket),
                    )
                )
            return lote
        finally:
            mt5.shutdown()

    # -- modo informe ----------------------------------------------------

    def _informe(self) -> Lote:
        ruta = Path(str(self.opciones["ruta"])).expanduser()
        if not ruta.exists():
            raise ErrorDeFuente(self.nombre, f"no existe el informe {ruta}")

        texto = ruta.read_text(encoding="utf-8", errors="replace")
        if ruta.suffix.lower() in (".htm", ".html"):
            filas = self._filas_html(texto)
        else:
            filas = [linea.split("\t") for linea in texto.splitlines() if "\t" in linea]

        lote = Lote()
        for celdas in filas:
            operacion = self._fila_a_trade(celdas)
            if operacion:
                lote.trades.append(operacion)

        if not lote.trades:
            raise ErrorDeFuente(
                self.nombre,
                f"no se reconocio ninguna operacion en {ruta.name}; exporta el "
                f"informe desde la pestana Historial del terminal",
            )
        return lote

    @staticmethod
    def _filas_html(texto: str) -> list[list[str]]:
        filas = []
        for bloque in re.findall(r"<tr[^>]*>(.*?)</tr>", texto, re.S | re.I):
            celdas = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", bloque, re.S | re.I)
            limpias = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in celdas]
            if limpias:
                filas.append(limpias)
        return filas

    def _fila_a_trade(self, celdas: list[str]) -> Trade | None:
        """Interpreta una fila del informe estandar de MT5.

        Formato: hora apertura, ticket, simbolo, tipo, volumen, precio entrada,
        S/L, T/P, hora cierre, precio cierre, comision, swap, beneficio.
        """
        if len(celdas) < 13:
            return None
        try:
            tipo = celdas[3].strip().lower()
            if tipo not in ("buy", "sell"):
                return None
            return Trade(
                symbol=celdas[2],
                direction="long" if tipo == "buy" else "short",
                open_ts=a_fecha(celdas[0]),
                close_ts=a_fecha(celdas[8]),
                qty=a_numero(celdas[4]),
                entry_price=a_numero(celdas[5]),
                exit_price=a_numero(celdas[9]),
                pnl=a_numero(celdas[12]),
                fees=abs(a_numero(celdas[10])) + abs(a_numero(celdas[11])),
                source=self.nombre,
                ext_id=celdas[1].strip(),
            )
        except (ValueError, IndexError):
            return None  # fila de cabecera o de resumen
