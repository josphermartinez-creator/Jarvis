"""La fusion es la razon de ser de Jarvis: varias fuentes, un solo libro.

Si la deduplicacion falla, el usuario ve el doble de beneficio del que tiene.
Eso es peor que no tener reporte.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from jarvis.merge import fusionar
from jarvis.models import Fill, Trade
from jarvis.sources.base import ErrorDeFuente, Fuente, Lote

from .conftest import t


class FuenteFalsa(Fuente):
    """Fuente de mentira que devuelve lo que se le da, para poder probar."""

    def __init__(self, nombre, fills=None, trades=None, error=None):
        super().__init__(nombre)
        self._fills = fills or []
        self._trades = trades or []
        self._error = error

    def leer(self, desde=None, hasta=None):
        if self._error:
            raise ErrorDeFuente(self.nombre, self._error)
        return Lote(fills=list(self._fills), trades=list(self._trades))


def fill(minutos, side, source, qty=1.0, price=100.0, ext_id="", symbol="BTCUSDT"):
    return Fill(
        ts=t(minutos), symbol=symbol, side=side, qty=qty, price=price,
        source=source, ext_id=ext_id,
    )


def trade(minutos=60, source="", pnl=10.0, ext_id="", symbol="BTCUSDT"):
    return Trade(
        symbol=symbol, direction="long", open_ts=t(0), close_ts=t(minutos),
        qty=1.0, entry_price=100.0, exit_price=110.0, pnl=pnl,
        source=source, ext_id=ext_id,
    )


def test_una_sola_fuente_pasa_tal_cual():
    libro = fusionar([FuenteFalsa("bot", fills=[
        fill(0, "buy", "bot"), fill(60, "sell", "bot"),
    ])])

    assert len(libro.trades) == 1
    assert libro.duplicados == 0
    assert libro.fuentes_ok == ["bot (2)"]


def test_dos_fuentes_distintas_se_suman():
    libro = fusionar([
        FuenteFalsa("bot", fills=[
            fill(0, "buy", "bot", symbol="BTCUSDT"),
            fill(60, "sell", "bot", symbol="BTCUSDT"),
        ]),
        FuenteFalsa("exchange", fills=[
            fill(10, "buy", "exchange", symbol="ETHUSDT"),
            fill(70, "sell", "exchange", symbol="ETHUSDT"),
        ]),
    ])

    assert len(libro.trades) == 2
    assert libro.duplicados == 0


def test_el_mismo_id_de_exchange_en_dos_fuentes_se_deduplica():
    """El caso real: el CSV del bot y la API cuentan la misma ejecucion."""
    libro = fusionar([
        FuenteFalsa("bot", fills=[
            fill(0, "buy", "bot", ext_id="A1"),
            fill(60, "sell", "bot", ext_id="A2"),
        ]),
        FuenteFalsa("exchange", fills=[
            fill(0, "buy", "exchange", ext_id="A1"),
            fill(60, "sell", "exchange", ext_id="A2"),
        ]),
    ])

    assert len(libro.trades) == 1
    assert libro.duplicados == 2


def test_sin_id_se_deduplica_por_huella():
    libro = fusionar([
        FuenteFalsa("bot", fills=[fill(0, "buy", "bot"), fill(60, "sell", "bot")]),
        FuenteFalsa("copia", fills=[fill(0, "buy", "copia"), fill(60, "sell", "copia")]),
    ])

    assert len(libro.trades) == 1
    assert libro.duplicados == 2


def test_deduplica_pese_a_un_desfase_de_reloj_pequeno():
    """Dos fuentes pueden registrar la misma ejecucion con segundos de diferencia."""
    a = Fill(ts=t(0), symbol="BTCUSDT", side="buy", qty=1, price=100, source="bot")
    b = Fill(
        ts=t(0) + timedelta(seconds=1), symbol="BTCUSDT", side="buy",
        qty=1, price=100, source="exchange",
    )

    libro = fusionar([FuenteFalsa("bot", fills=[a]), FuenteFalsa("exchange", fills=[b])])

    assert libro.duplicados == 1
    assert len(libro.abiertas) == 1  # una sola compra abierta, no dos


def test_no_deduplica_operaciones_legitimamente_parecidas():
    """Un bot de rejilla repite la misma orden a proposito. No son duplicados."""
    a = Fill(ts=t(0), symbol="BTCUSDT", side="buy", qty=1, price=100, source="bot")
    b = Fill(ts=t(30), symbol="BTCUSDT", side="buy", qty=1, price=100, source="bot")

    libro = fusionar([FuenteFalsa("bot", fills=[a, b])])

    assert libro.duplicados == 0
    assert libro.abiertas[0].qty == pytest.approx(2)


def test_operaciones_cerradas_duplicadas_tambien_se_detectan():
    libro = fusionar([
        FuenteFalsa("bot", trades=[trade(source="bot", ext_id="T1")]),
        FuenteFalsa("api", trades=[trade(source="api", ext_id="T1")]),
    ])

    assert len(libro.trades) == 1
    assert libro.duplicados == 1


def test_se_pueden_mezclar_ejecuciones_y_operaciones_cerradas():
    libro = fusionar([
        FuenteFalsa("bot", fills=[
            fill(0, "buy", "bot", symbol="BTCUSDT"),
            fill(60, "sell", "bot", symbol="BTCUSDT"),
        ]),
        FuenteFalsa("mt5", trades=[trade(source="mt5", symbol="EURUSD")]),
    ])

    assert len(libro.trades) == 2
    assert {op.symbol for op in libro.trades} == {"BTCUSDT", "EURUSD"}


def test_una_fuente_caida_no_impide_el_reporte():
    libro = fusionar([
        FuenteFalsa("bot", fills=[fill(0, "buy", "bot"), fill(60, "sell", "bot")]),
        FuenteFalsa("exchange", error="la API no responde"),
    ])

    assert len(libro.trades) == 1
    assert len(libro.errores) == 1
    assert "la API no responde" in libro.errores[0]
    assert libro.fuentes_ok == ["bot (2)"]


def test_si_fallan_todas_las_fuentes_se_reportan_todos_los_errores():
    libro = fusionar([
        FuenteFalsa("a", error="sin permisos"),
        FuenteFalsa("b", error="archivo corrupto"),
    ])

    assert not libro.hay_datos
    assert len(libro.errores) == 2


def test_las_posiciones_abiertas_se_reportan_aparte():
    libro = fusionar([FuenteFalsa("bot", fills=[fill(0, "buy", "bot", qty=3)])])

    assert not libro.trades
    assert len(libro.abiertas) == 1
    assert libro.abiertas[0].qty == pytest.approx(3)
