"""El emparejador FIFO es donde se decide si el PnL reportado es correcto."""

from __future__ import annotations

import pytest

from jarvis.matching import emparejar_fills

from .conftest import t


def test_largo_simple_calcula_ganancia(fill):
    cerradas, abiertas = emparejar_fills([
        fill(0, "buy", qty=2, price=100),
        fill(60, "sell", qty=2, price=110),
    ])

    assert len(cerradas) == 1
    assert not abiertas
    op = cerradas[0]
    assert op.direction == "long"
    assert op.pnl == pytest.approx(20.0)
    assert op.entry_price == 100
    assert op.exit_price == 110
    assert op.duracion_seg == 3600


def test_corto_gana_cuando_el_precio_baja(fill):
    cerradas, abiertas = emparejar_fills([
        fill(0, "sell", qty=1, price=100),
        fill(30, "buy", qty=1, price=90),
    ])

    assert not abiertas
    assert cerradas[0].direction == "short"
    assert cerradas[0].pnl == pytest.approx(10.0)


def test_cierre_parcial_deja_el_resto_abierto(fill):
    cerradas, abiertas = emparejar_fills([
        fill(0, "buy", qty=5, price=100),
        fill(10, "sell", qty=2, price=105),
    ])

    assert len(cerradas) == 1
    assert cerradas[0].qty == pytest.approx(2)
    assert cerradas[0].pnl == pytest.approx(10.0)
    assert len(abiertas) == 1
    assert abiertas[0].qty == pytest.approx(3)
    assert abiertas[0].direction == "long"


def test_fifo_consume_los_lotes_mas_antiguos_primero(fill):
    # Dos compras a distinto precio; la venta debe cerrar la primera.
    cerradas, abiertas = emparejar_fills([
        fill(0, "buy", qty=1, price=100),
        fill(10, "buy", qty=1, price=120),
        fill(20, "sell", qty=1, price=130),
    ])

    assert len(cerradas) == 1
    assert cerradas[0].entry_price == 100  # no 120
    assert cerradas[0].pnl == pytest.approx(30.0)
    assert abiertas[0].precio_medio == pytest.approx(120)


def test_una_venta_grande_cierra_varios_lotes(fill):
    cerradas, _ = emparejar_fills([
        fill(0, "buy", qty=1, price=100),
        fill(10, "buy", qty=1, price=200),
        fill(20, "sell", qty=2, price=250),
    ])

    assert len(cerradas) == 2
    assert sum(op.pnl for op in cerradas) == pytest.approx(150 + 50)


def test_reversion_de_posicion_cierra_y_abre_en_sentido_contrario(fill):
    # Compro 1, luego vendo 3: cierra el largo y abre un corto de 2.
    cerradas, abiertas = emparejar_fills([
        fill(0, "buy", qty=1, price=100),
        fill(10, "sell", qty=3, price=110),
    ])

    assert len(cerradas) == 1
    assert cerradas[0].pnl == pytest.approx(10.0)
    assert len(abiertas) == 1
    assert abiertas[0].direction == "short"
    assert abiertas[0].qty == pytest.approx(2)


def test_las_comisiones_se_reparten_entre_apertura_y_cierre(fill):
    cerradas, _ = emparejar_fills([
        fill(0, "buy", qty=2, price=100, fee=1.0),
        fill(10, "sell", qty=1, price=110, fee=0.5),
    ])

    # Media comision de entrada (1.0 * 1/2) mas la de salida completa.
    assert cerradas[0].fees == pytest.approx(1.0)
    assert cerradas[0].pnl_neto == pytest.approx(10.0 - 1.0)


def test_cada_simbolo_lleva_su_propio_libro(fill):
    cerradas, abiertas = emparejar_fills([
        fill(0, "buy", qty=1, price=100, symbol="BTCUSDT"),
        fill(5, "buy", qty=1, price=50, symbol="ETHUSDT"),
        fill(10, "sell", qty=1, price=110, symbol="BTCUSDT"),
    ])

    assert len(cerradas) == 1
    assert cerradas[0].symbol == "BTCUSDT"
    assert [p.symbol for p in abiertas] == ["ETHUSDT"]


def test_los_fills_desordenados_se_ordenan_por_fecha(fill):
    cerradas, _ = emparejar_fills([
        fill(60, "sell", qty=1, price=110),
        fill(0, "buy", qty=1, price=100),
    ])

    assert cerradas[0].open_ts == t(0)
    assert cerradas[0].close_ts == t(60)
    assert cerradas[0].pnl == pytest.approx(10.0)


def test_sin_fills_no_hay_nada_que_reportar():
    cerradas, abiertas = emparejar_fills([])
    assert cerradas == []
    assert abiertas == []
