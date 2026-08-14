"""Las metricas son lo que el usuario lee y en lo que basa sus decisiones."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from jarvis.metrics import calcular, filtrar_periodo, periodo_anterior, rango_periodo


def test_libro_vacio_no_revienta():
    m = calcular([])
    assert not m.hay_datos
    assert m.operaciones == 0
    assert m.winrate == 0


def test_cuenta_y_reparte_ganadoras_y_perdedoras(trade):
    m = calcular([trade(pnl=10), trade(pnl=-5), trade(pnl=20)])

    assert m.operaciones == 3
    assert m.ganadoras == 2
    assert m.perdedoras == 1
    assert m.pnl_neto == pytest.approx(25)
    assert m.winrate == pytest.approx(2 / 3 * 100)


def test_las_comisiones_salen_del_resultado_neto(trade):
    m = calcular([trade(pnl=100, fees=10)])

    assert m.pnl_bruto == pytest.approx(100)
    assert m.comisiones == pytest.approx(10)
    assert m.pnl_neto == pytest.approx(90)


def test_una_operacion_gana_en_bruto_pero_pierde_por_comisiones(trade):
    """El caso que mas enganos produce en los bots de alta frecuencia."""
    m = calcular([trade(pnl=5, fees=8)])

    assert m.pnl_bruto == pytest.approx(5)
    assert m.pnl_neto == pytest.approx(-3)
    assert m.ganadoras == 0
    assert m.perdedoras == 1


def test_profit_factor_es_lo_ganado_entre_lo_perdido(trade):
    m = calcular([trade(pnl=30), trade(pnl=-10)])
    assert m.profit_factor == pytest.approx(3.0)


def test_profit_factor_infinito_si_no_hubo_perdidas(trade):
    m = calcular([trade(pnl=10), trade(pnl=20)])
    assert math.isinf(m.profit_factor)


def test_expectativa_es_el_resultado_medio_por_operacion(trade):
    m = calcular([trade(pnl=10), trade(pnl=-4), trade(pnl=3)])
    assert m.expectativa == pytest.approx(9 / 3)


def test_drawdown_mide_la_caida_desde_el_pico(trade):
    # 100 arriba, luego -60: la caida desde el pico es 60 sobre 1100.
    m = calcular([trade(pnl=100), trade(pnl=-60)], capital_inicial=1000)

    assert m.max_drawdown == pytest.approx(60)
    assert m.max_drawdown_pct == pytest.approx(60 / 1100 * 100)


def test_el_drawdown_no_se_reduce_al_recuperarse(trade):
    m = calcular([trade(pnl=100), trade(pnl=-60), trade(pnl=500)], capital_inicial=1000)
    assert m.max_drawdown == pytest.approx(60)


def test_rachas_cuentan_resultados_consecutivos(trade):
    m = calcular([
        trade(pnl=1), trade(pnl=1), trade(pnl=1),
        trade(pnl=-1), trade(pnl=-1),
        trade(pnl=1),
    ])

    assert m.racha_ganadora == 3
    assert m.racha_perdedora == 2


def test_mejor_y_peor_operacion_usan_el_neto(trade):
    m = calcular([
        trade(pnl=100, fees=99, symbol="CARA"),   # neto 1
        trade(pnl=50, fees=0, symbol="BUENA"),    # neto 50
        trade(pnl=-30, fees=0, symbol="MALA"),
    ])

    assert m.mejor.symbol == "BUENA"
    assert m.peor.symbol == "MALA"


def test_desglose_por_simbolo_ordenado_por_resultado(trade):
    m = calcular([
        trade(symbol="BTCUSDT", pnl=10),
        trade(symbol="ETHUSDT", pnl=-5),
        trade(symbol="BTCUSDT", pnl=15),
    ])

    assert [b.clave for b in m.por_simbolo] == ["BTCUSDT", "ETHUSDT"]
    assert m.por_simbolo[0].operaciones == 2
    assert m.por_simbolo[0].pnl == pytest.approx(25)


def test_desglose_por_dia_agrupa_por_fecha_de_cierre(trade):
    m = calcular([
        trade(minutos_cierre=60, pnl=10),
        trade(minutos_cierre=120, pnl=5),
        trade(minutos_cierre=60 * 30, pnl=-3),  # dia siguiente
    ])

    assert len(m.por_dia) == 2
    assert m.por_dia[0].operaciones == 2


def test_sharpe_es_cero_con_un_solo_dia(trade):
    m = calcular([trade(pnl=10), trade(pnl=20)], capital_inicial=1000)
    assert m.sharpe == 0.0


def test_sortino_ignora_la_volatilidad_al_alza(trade):
    """Con solo dias buenos no hay riesgo a la baja que penalizar."""
    operaciones = [trade(minutos_cierre=60 * 24 * d, pnl=10) for d in range(1, 6)]
    m = calcular(operaciones, capital_inicial=1000)
    assert m.sortino == 0.0


def test_retorno_pct_usa_el_capital_empleado(trade):
    op = trade(qty=2, entrada=50, pnl=10)  # capital 100
    assert op.retorno_pct == pytest.approx(10.0)


# -- periodos -------------------------------------------------------------

AHORA = datetime(2026, 3, 4, 15, 30, tzinfo=timezone.utc)  # miercoles


def test_periodo_hoy_empieza_a_medianoche():
    desde, hasta = rango_periodo("hoy", AHORA)
    assert desde == datetime(2026, 3, 4, 0, 0, tzinfo=timezone.utc)
    assert hasta == AHORA


def test_periodo_semana_empieza_el_lunes():
    desde, _ = rango_periodo("semana", AHORA)
    assert desde == datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)


def test_periodo_mes_empieza_el_dia_uno():
    desde, _ = rango_periodo("mes", AHORA)
    assert desde.day == 1
    assert desde.month == 3


def test_periodo_todo_no_pone_limites():
    assert rango_periodo("todo", AHORA) == (None, None)


def test_periodo_relativo_en_dias():
    desde, hasta = rango_periodo("7d", AHORA)
    assert (hasta - desde).days == 7


def test_rango_explicito_incluye_el_dia_final_completo():
    desde, hasta = rango_periodo("2026-01-01:2026-01-31", AHORA)
    assert desde.day == 1
    assert hasta.day == 31
    assert hasta.hour == 23  # no se corta a medianoche


def test_periodo_invalido_avisa_con_las_opciones():
    with pytest.raises(ValueError, match="periodo desconocido"):
        rango_periodo("la semana pasada mas o menos", AHORA)


def test_periodo_anterior_tiene_el_mismo_largo():
    desde, hasta = rango_periodo("7d", AHORA)
    p_desde, p_hasta = periodo_anterior(desde, hasta)

    # Acaba justo antes de que empiece el actual, para no contar dos veces el
    # limite: de ahi el microsegundo de diferencia.
    assert p_hasta < desde
    assert abs((hasta - desde) - (p_hasta - p_desde)).total_seconds() < 0.001


def test_filtrar_periodo_usa_la_fecha_de_cierre(trade):
    operaciones = [trade(minutos_cierre=0), trade(minutos_cierre=60 * 48)]
    from .conftest import t

    filtradas = filtrar_periodo(operaciones, t(-10), t(10))
    assert len(filtradas) == 1
