"""Modelos de datos normalizados de Jarvis.

Todo lo que entra desde cualquier fuente (CSV, base de datos, exchange, MT5)
termina convertido en uno de estos dos objetos:

- ``Fill``  : una ejecucion suelta (compra o venta parcial). Es lo que devuelven
              los exchanges. No tiene PnL propio.
- ``Trade`` : una operacion cerrada de ida y vuelta, con PnL calculado.

Las fuentes que ya entregan operaciones cerradas (muchos bots escriben su CSV
asi) producen ``Trade`` directamente. Las que entregan ejecuciones producen
``Fill`` y el emparejador FIFO de ``jarvis.matching`` las convierte en ``Trade``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

Side = Literal["buy", "sell"]
Direction = Literal["long", "short"]


def utc(ts: datetime) -> datetime:
    """Devuelve el datetime en UTC, asumiendo UTC si viene sin zona horaria."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


@dataclass(frozen=True)
class Fill:
    """Una ejecucion individual reportada por el exchange o el bot."""

    ts: datetime
    symbol: str
    side: Side
    qty: float
    price: float
    fee: float = 0.0
    fee_currency: str = ""
    source: str = ""
    ext_id: str = ""
    meta: dict = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ts", utc(self.ts))
        object.__setattr__(self, "symbol", self.symbol.upper().strip())
        if self.qty <= 0:
            raise ValueError(f"cantidad invalida en fill {self.symbol}: {self.qty}")
        if self.price < 0:
            raise ValueError(f"precio invalido en fill {self.symbol}: {self.price}")

    @property
    def notional(self) -> float:
        return self.qty * self.price

    @property
    def fingerprint(self) -> str:
        """Huella estable usada para deduplicar al fusionar fuentes.

        No incluye ``source``: el objetivo es justamente detectar la misma
        ejecucion llegando por dos caminos distintos (por ejemplo el CSV del bot
        y la API del exchange).
        """
        if self.ext_id:
            return f"{self.symbol}|{self.ext_id}"
        crudo = (
            f"{self.symbol}|{int(self.ts.timestamp())}|{self.side}"
            f"|{self.qty:.10g}|{self.price:.10g}"
        )
        return hashlib.sha1(crudo.encode()).hexdigest()


@dataclass(frozen=True)
class Trade:
    """Una operacion cerrada, con su resultado ya calculado."""

    symbol: str
    direction: Direction
    open_ts: datetime
    close_ts: datetime
    qty: float
    entry_price: float
    exit_price: float
    pnl: float
    fees: float = 0.0
    source: str = ""
    ext_id: str = ""
    meta: dict = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_ts", utc(self.open_ts))
        object.__setattr__(self, "close_ts", utc(self.close_ts))
        object.__setattr__(self, "symbol", self.symbol.upper().strip())
        if self.close_ts < self.open_ts:
            raise ValueError(
                f"operacion {self.symbol} cierra antes de abrir: "
                f"{self.open_ts} -> {self.close_ts}"
            )

    @property
    def pnl_neto(self) -> float:
        """PnL despues de comisiones."""
        return self.pnl - self.fees

    @property
    def es_ganadora(self) -> bool:
        return self.pnl_neto > 0

    @property
    def capital_empleado(self) -> float:
        return self.qty * self.entry_price

    @property
    def retorno_pct(self) -> float:
        """Retorno sobre el capital empleado, en porcentaje."""
        base = self.capital_empleado
        if base == 0:
            return 0.0
        return self.pnl_neto / base * 100.0

    @property
    def duracion_seg(self) -> float:
        return (self.close_ts - self.open_ts).total_seconds()

    @property
    def fingerprint(self) -> str:
        if self.ext_id:
            return f"{self.symbol}|{self.ext_id}"
        crudo = (
            f"{self.symbol}|{int(self.open_ts.timestamp())}"
            f"|{int(self.close_ts.timestamp())}|{self.direction}"
            f"|{self.qty:.10g}|{self.entry_price:.10g}|{self.exit_price:.10g}"
        )
        return hashlib.sha1(crudo.encode()).hexdigest()
