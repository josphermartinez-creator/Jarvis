"""Emparejador FIFO: convierte ejecuciones sueltas en operaciones cerradas.

Un exchange no te dice "ganaste 12 dolares en esta operacion": te da una lista
de compras y ventas. Para reportar hay que emparejarlas. Jarvis usa FIFO (la
primera unidad que entra es la primera que sale), que es el criterio estandar
y el que usan Binance, Bybit y la mayoria de bots.

Soporta posiciones largas y cortas, cierres parciales y reversiones de posicion
(una venta que cierra el largo y abre un corto en la misma ejecucion).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from .models import Fill, Trade


@dataclass
class _Lote:
    """Un trozo de posicion abierta pendiente de cerrar."""

    ts: datetime
    qty: float
    price: float
    fee_por_unidad: float
    source: str


@dataclass
class PosicionAbierta:
    """Posicion que quedo sin cerrar al final del periodo analizado."""

    symbol: str
    direction: str
    qty: float
    precio_medio: float
    desde: datetime
    source: str = ""

    @property
    def capital_empleado(self) -> float:
        return self.qty * self.precio_medio

    def pnl_flotante(self, precio_actual: float) -> float:
        if self.direction == "long":
            return (precio_actual - self.precio_medio) * self.qty
        return (self.precio_medio - precio_actual) * self.qty


def emparejar_fills(fills: Iterable[Fill]) -> tuple[list[Trade], list[PosicionAbierta]]:
    """Empareja ejecuciones en operaciones cerradas siguiendo FIFO.

    Devuelve ``(operaciones_cerradas, posiciones_abiertas)``. Lo que queda
    abierto no se descarta: se reporta aparte para que el resumen no mienta por
    omision.
    """
    ordenados = sorted(fills, key=lambda f: (f.ts, f.symbol))
    # Por simbolo: lotes abiertos y el signo de la posicion (+1 largo, -1 corto).
    libros: dict[str, deque[_Lote]] = defaultdict(deque)
    signos: dict[str, int] = defaultdict(int)
    cerradas: list[Trade] = []

    for fill in ordenados:
        signo_fill = 1 if fill.side == "buy" else -1
        restante = fill.qty
        fee_unit = fill.fee / fill.qty if fill.qty else 0.0
        libro = libros[fill.symbol]

        # Fase 1: si la ejecucion va contra la posicion abierta, cierra lotes.
        if signos[fill.symbol] != 0 and signos[fill.symbol] != signo_fill:
            while restante > 1e-12 and libro:
                lote = libro[0]
                usado = min(restante, lote.qty)

                if signos[fill.symbol] == 1:  # cerramos un largo vendiendo
                    direccion = "long"
                    bruto = (fill.price - lote.price) * usado
                else:  # cerramos un corto comprando
                    direccion = "short"
                    bruto = (lote.price - fill.price) * usado

                comisiones = lote.fee_por_unidad * usado + fee_unit * usado
                fuente = lote.source if lote.source == fill.source else (
                    f"{lote.source}+{fill.source}" if lote.source else fill.source
                )
                cerradas.append(
                    Trade(
                        symbol=fill.symbol,
                        direction=direccion,
                        open_ts=lote.ts,
                        close_ts=fill.ts,
                        qty=usado,
                        entry_price=lote.price,
                        exit_price=fill.price,
                        pnl=bruto,
                        fees=comisiones,
                        source=fuente,
                    )
                )

                lote.qty -= usado
                restante -= usado
                if lote.qty <= 1e-12:
                    libro.popleft()

            if not libro:
                signos[fill.symbol] = 0

        # Fase 2: lo que sobra abre posicion nueva (o amplia la existente).
        if restante > 1e-12:
            libro.append(
                _Lote(
                    ts=fill.ts,
                    qty=restante,
                    price=fill.price,
                    fee_por_unidad=fee_unit,
                    source=fill.source,
                )
            )
            signos[fill.symbol] = signo_fill

    abiertas = []
    for symbol, libro in libros.items():
        if not libro:
            continue
        qty_total = sum(l.qty for l in libro)
        if qty_total <= 1e-12:
            continue
        precio_medio = sum(l.qty * l.price for l in libro) / qty_total
        abiertas.append(
            PosicionAbierta(
                symbol=symbol,
                direction="long" if signos[symbol] == 1 else "short",
                qty=qty_total,
                precio_medio=precio_medio,
                desde=min(l.ts for l in libro),
                source=libro[0].source,
            )
        )

    cerradas.sort(key=lambda t: t.close_ts)
    abiertas.sort(key=lambda p: p.symbol)
    return cerradas, abiertas


def construir_libro(
    fills: Sequence[Fill], trades: Sequence[Trade]
) -> tuple[list[Trade], list[PosicionAbierta]]:
    """Combina fuentes de ejecuciones y de operaciones ya cerradas.

    Las operaciones que una fuente ya entrega cerradas se respetan tal cual; las
    ejecuciones sueltas se emparejan por FIFO y se suman al mismo libro.
    """
    derivadas, abiertas = emparejar_fills(fills)
    todas = list(trades) + derivadas
    todas.sort(key=lambda t: t.close_ts)
    return todas, abiertas
