from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from jarvis.models import Fill, Trade

BASE = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)  # un lunes


def t(minutos: int) -> datetime:
    """Instante desplazado desde la base, para escribir casos legibles."""
    return BASE + timedelta(minutes=minutos)


@pytest.fixture
def fill():
    def crear(minutos, side, qty=1.0, price=100.0, symbol="BTCUSDT", fee=0.0, **extra):
        return Fill(
            ts=t(minutos), symbol=symbol, side=side, qty=qty, price=price, fee=fee, **extra
        )

    return crear


@pytest.fixture
def trade():
    def crear(
        minutos_apertura=0, minutos_cierre=60, pnl=10.0, symbol="BTCUSDT",
        direction="long", qty=1.0, entrada=100.0, salida=110.0, fees=0.0, **extra
    ):
        return Trade(
            symbol=symbol,
            direction=direction,
            open_ts=t(minutos_apertura),
            close_ts=t(minutos_cierre),
            qty=qty,
            entry_price=entrada,
            exit_price=salida,
            pnl=pnl,
            fees=fees,
            **extra,
        )

    return crear
