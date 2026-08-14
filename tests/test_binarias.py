"""Opciones binarias: la fuente del bot y sus metricas propias.

El punto de equilibrio es la cifra que decide si una estrategia se sostiene, asi
que se prueba con numeros calculados a mano.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from jarvis import binarias
from jarvis.sources.iqoption import FuenteIQOption, es_historial_binarias
from jarvis.sources.base import ErrorDeFuente

from .conftest import t

CABECERA = (
    "timestamp,fecha,hora,dia_semana,franja_horaria,par,estrategia,"
    "direccion,resultado,monto,ganancia,balance,racha_perdidas_momento"
)


def fila(minutos=0, par="EURUSD-OTC", resultado="win", monto=2.0, ganancia=1.7,
         balance=100.0, estrategia="rsi", direccion="BUY", racha=0) -> str:
    momento = t(minutos)
    dias = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
    return (
        f"{momento:%Y-%m-%d %H:%M:%S},{momento:%Y-%m-%d},{momento:%H:%M:%S},"
        f"{dias[momento.weekday()]},{momento.hour:02d}:00-{momento.hour:02d}:59,"
        f"{par},{estrategia},{direccion},{resultado},{monto},{ganancia},"
        f"{balance},{racha}"
    )


@pytest.fixture
def historial(tmp_path):
    def crear(filas, nombre="historial_operaciones.csv"):
        ruta = tmp_path / nombre
        ruta.write_text("\n".join([CABECERA, *filas]) + "\n", encoding="utf-8")
        return ruta

    return crear


# -- deteccion y lectura --------------------------------------------------

def test_reconoce_el_formato_por_las_cabeceras():
    assert es_historial_binarias(CABECERA.split(","))
    assert not es_historial_binarias(["fecha", "simbolo", "lado", "precio"])


def test_lee_una_operacion_ganadora(historial):
    ruta = historial([fila(resultado="win", monto=2.0, ganancia=1.7)])
    lote = FuenteIQOption("bot", ruta=str(ruta)).leer()

    assert len(lote.trades) == 1
    op = lote.trades[0]
    assert op.symbol == "EURUSD-OTC"
    assert op.pnl == pytest.approx(1.7)
    assert op.meta["resultado"] == "win"
    assert op.meta["monto"] == pytest.approx(2.0)
    assert op.meta["binarias"] is True


def test_el_retorno_es_sobre_lo_apostado(historial):
    """Apostar 2 y ganar 1,70 es un 85% de retorno."""
    ruta = historial([fila(monto=2.0, ganancia=1.7)])
    op = FuenteIQOption("bot", ruta=str(ruta)).leer().trades[0]

    assert op.retorno_pct == pytest.approx(85.0)


def test_una_perdida_se_lee_en_negativo(historial):
    ruta = historial([fila(resultado="loss", monto=5.0, ganancia=-5.0)])
    op = FuenteIQOption("bot", ruta=str(ruta)).leer().trades[0]

    assert op.pnl == pytest.approx(-5.0)
    assert not op.es_ganadora


def test_buy_es_largo_y_sell_es_corto(historial):
    ruta = historial([
        fila(minutos=0, direccion="BUY"),
        fila(minutos=5, direccion="SELL"),
    ])
    ops = FuenteIQOption("bot", ruta=str(ruta)).leer().trades

    assert ops[0].direction == "long"
    assert ops[1].direction == "short"


def test_las_no_confirmadas_se_excluyen_por_defecto(historial):
    ruta = historial([
        fila(minutos=0, resultado="win"),
        fila(minutos=5, resultado="desconocido", ganancia=0),
    ])
    lote = FuenteIQOption("bot", ruta=str(ruta)).leer()

    assert len(lote.trades) == 1
    assert lote.trades[0].meta["resultado"] == "win"


def test_se_pueden_incluir_las_no_confirmadas(historial):
    ruta = historial([
        fila(minutos=0, resultado="win"),
        fila(minutos=5, resultado="desconocido", ganancia=0),
    ])
    fuente = FuenteIQOption("bot", ruta=str(ruta), incluir=["win", "desconocido"])

    assert len(fuente.leer().trades) == 2


def test_un_resultado_invalido_en_incluir_avisa(historial):
    ruta = historial([fila()])
    fuente = FuenteIQOption("bot", ruta=str(ruta), incluir=["ganada"])

    with pytest.raises(ErrorDeFuente, match="no valido"):
        fuente.leer()


def test_los_empates_se_conservan(historial):
    ruta = historial([fila(resultado="empate", ganancia=0)])
    op = FuenteIQOption("bot", ruta=str(ruta)).leer().trades[0]

    assert op.pnl == 0
    assert op.meta["resultado"] == "empate"


def test_una_fila_corrupta_no_tumba_el_reporte(historial):
    ruta = historial([fila(minutos=0), fila(minutos=5, monto=0, ganancia=0)])
    assert len(FuenteIQOption("bot", ruta=str(ruta)).leer().trades) == 1


def test_historial_inexistente_avisa(tmp_path):
    fuente = FuenteIQOption("bot", ruta=str(tmp_path / "no_existe.csv"))
    with pytest.raises(ErrorDeFuente, match="no existe"):
        fuente.leer()


def test_apuntar_la_fuente_generica_al_historial_tambien_funciona(historial):
    """El usuario no deberia tener que declarar el tipo."""
    from jarvis.sources import crear_fuente

    ruta = historial([fila()])
    lote = crear_fuente("bot", {"tipo": "archivo", "ruta": str(ruta)}).leer()

    assert len(lote.trades) == 1
    assert lote.trades[0].meta["binarias"] is True


# -- punto de equilibrio --------------------------------------------------

def leer(historial, filas):
    return FuenteIQOption("bot", ruta=str(historial(filas))).leer().trades


def test_el_punto_de_equilibrio_sale_del_pago(historial):
    """Con un pago del 85%, hace falta acertar 1/1,85 = 54,05%."""
    ops = leer(historial, [fila(monto=10.0, ganancia=8.5)])
    m = binarias.calcular(ops)

    assert m.payout_medio == pytest.approx(0.85)
    assert m.punto_equilibrio == pytest.approx(100 / 1.85)


def test_un_pago_del_100_por_cien_exige_acertar_la_mitad(historial):
    ops = leer(historial, [fila(monto=10.0, ganancia=10.0)])
    assert binarias.calcular(ops).punto_equilibrio == pytest.approx(50.0)


def test_el_margen_es_la_efectividad_menos_el_umbral(historial):
    # 6 ganadas y 4 perdidas = 60% de efectividad, con pago del 100% (umbral 50).
    filas = [fila(minutos=i, monto=10.0, ganancia=10.0) for i in range(6)]
    filas += [
        fila(minutos=10 + i, resultado="loss", monto=10.0, ganancia=-10.0)
        for i in range(4)
    ]
    m = binarias.calcular(leer(historial, filas))

    assert m.efectividad == pytest.approx(60.0)
    assert m.punto_equilibrio == pytest.approx(50.0)
    assert m.margen == pytest.approx(10.0)
    assert m.rentable


def test_por_debajo_del_umbral_no_es_rentable(historial):
    # 24 ganadas y 36 perdidas con pago del 100%: 40% frente a un umbral del
    # 50%. Hacen falta mas de 50 decididas o el veredicto se reserva el juicio.
    filas = [fila(minutos=i, monto=10.0, ganancia=10.0) for i in range(24)]
    filas += [
        fila(minutos=100 + i, resultado="loss", monto=10.0, ganancia=-10.0)
        for i in range(36)
    ]
    m = binarias.calcular(leer(historial, filas))

    assert not m.rentable
    assert m.margen == pytest.approx(-10.0)
    assert "pierde" in m.veredicto


def test_los_empates_no_cuentan_en_la_efectividad(historial):
    filas = [
        fila(minutos=0, resultado="win", monto=10.0, ganancia=10.0),
        fila(minutos=5, resultado="loss", monto=10.0, ganancia=-10.0),
        fila(minutos=10, resultado="empate", monto=10.0, ganancia=0.0),
    ]
    m = binarias.calcular(leer(historial, filas))

    assert m.total == 3
    assert m.decididas == 2
    assert m.efectividad == pytest.approx(50.0)
    assert m.empates == 1


def test_sin_ganadoras_no_se_puede_medir_el_pago(historial):
    filas = [fila(minutos=i, resultado="loss", monto=5.0, ganancia=-5.0) for i in range(3)]
    m = binarias.calcular(leer(historial, filas))

    assert m.payout_medio == 0
    assert m.punto_equilibrio == 0
    assert m.margen == 0
    assert "no se puede medir el pago" in m.veredicto


def test_una_muestra_corta_se_marca_como_no_concluyente(historial):
    filas = [fila(minutos=i, monto=10.0, ganancia=10.0) for i in range(5)]
    assert "muestra corta" in binarias.calcular(leer(historial, filas)).veredicto


# -- dinero y riesgo ------------------------------------------------------

def test_el_roi_es_sobre_el_total_invertido(historial):
    filas = [
        fila(minutos=0, monto=10.0, ganancia=8.0),
        fila(minutos=5, resultado="loss", monto=10.0, ganancia=-10.0),
    ]
    m = binarias.calcular(leer(historial, filas))

    assert m.invertido == pytest.approx(20.0)
    assert m.neto == pytest.approx(-2.0)
    assert m.roi == pytest.approx(-10.0)


def test_la_caida_maxima_usa_el_balance_del_broker(historial):
    filas = [
        fila(minutos=0, monto=10.0, ganancia=50.0, balance=150.0),
        fila(minutos=5, resultado="loss", monto=10.0, ganancia=-30.0, balance=120.0),
        fila(minutos=10, resultado="loss", monto=10.0, ganancia=-20.0, balance=100.0),
    ]
    m = binarias.calcular(leer(historial, filas))

    assert m.balance_inicial == pytest.approx(100.0)
    assert m.balance_final == pytest.approx(100.0)
    assert m.max_caida == pytest.approx(50.0)       # de 150 a 100
    assert m.max_caida_pct == pytest.approx(50 / 150 * 100)


def test_las_rachas_se_cuentan_en_orden(historial):
    filas = [
        fila(minutos=0, resultado="loss", ganancia=-2.0),
        fila(minutos=5, resultado="loss", ganancia=-2.0),
        fila(minutos=10, resultado="loss", ganancia=-2.0),
        fila(minutos=15, resultado="win", ganancia=1.7),
        fila(minutos=20, resultado="win", ganancia=1.7),
    ]
    m = binarias.calcular(leer(historial, filas))

    assert m.racha_perdidas == 3
    assert m.racha_ganadas == 2


# -- desgloses ------------------------------------------------------------

def test_cada_par_tiene_su_propio_umbral(historial):
    """Un par que paga menos exige acertar mas: por eso el umbral es por par."""
    filas = [
        fila(minutos=0, par="EURUSD-OTC", monto=10.0, ganancia=9.0),   # pago 90%
        fila(minutos=5, par="AUDCAD-OTC", monto=10.0, ganancia=7.0),   # pago 70%
    ]
    m = binarias.calcular(leer(historial, filas))
    por_par = {b.clave: b for b in m.por_par}

    assert por_par["EURUSD-OTC"].punto_equilibrio == pytest.approx(100 / 1.9)
    assert por_par["AUDCAD-OTC"].punto_equilibrio == pytest.approx(100 / 1.7)


def test_desglose_por_estrategia(historial):
    filas = [
        fila(minutos=0, estrategia="rsi", monto=10.0, ganancia=8.0),
        fila(minutos=5, estrategia="rsi", monto=10.0, ganancia=8.0),
        fila(minutos=10, estrategia="bandas", resultado="loss", monto=10.0, ganancia=-10.0),
    ]
    m = binarias.calcular(leer(historial, filas))
    por_estrategia = {b.clave: b for b in m.por_estrategia}

    assert por_estrategia["rsi"].total == 2
    assert por_estrategia["bandas"].neto == pytest.approx(-10.0)


def test_los_dias_de_la_semana_van_en_orden(historial):
    filas = [fila(minutos=60 * 24 * d) for d in range(7)]
    claves = [b.clave for b in binarias.calcular(leer(historial, filas)).por_dia_semana]

    assert claves[0] == "lunes"
    assert claves[-1] == "domingo"


# -- profundidad de la cadena ---------------------------------------------

def test_la_profundidad_se_deduce_del_historial_no_de_la_columna(historial):
    """La columna del bot guarda la racha DESPUES del resultado, no antes."""
    filas = [
        fila(minutos=0, resultado="loss", ganancia=-2.0, racha=1),
        fila(minutos=5, resultado="loss", ganancia=-4.0, racha=2),
        fila(minutos=10, resultado="win", ganancia=7.0, racha=0),
    ]
    niveles = {
        p.perdidas_previas: p for p in binarias.calcular(leer(historial, filas)).profundidad
    }

    # La ganadora entro tras dos perdidas seguidas, aunque su columna diga 0.
    assert niveles[0].operaciones == 1
    assert niveles[1].operaciones == 1
    assert niveles[2].operaciones == 1
    assert niveles[2].ganadas == 1


def test_cada_par_lleva_su_propia_cadena(historial):
    filas = [
        fila(minutos=0, par="EURUSD-OTC", resultado="loss", ganancia=-2.0),
        fila(minutos=5, par="GBPUSD-OTC", resultado="win", ganancia=1.7),
    ]
    niveles = {
        p.perdidas_previas: p for p in binarias.calcular(leer(historial, filas)).profundidad
    }

    # La ganadora de GBPUSD no hereda la perdida de EURUSD.
    assert niveles[0].operaciones == 2


def test_un_empate_corta_la_cadena(historial):
    filas = [
        fila(minutos=0, resultado="loss", ganancia=-2.0),
        fila(minutos=5, resultado="empate", ganancia=0.0),
        fila(minutos=10, resultado="loss", ganancia=-2.0),
    ]
    niveles = {
        p.perdidas_previas: p for p in binarias.calcular(leer(historial, filas)).profundidad
    }

    assert niveles[0].operaciones == 2  # la primera perdida y la de tras el empate
    assert niveles[1].operaciones == 1  # el empate, que llegaba tras una perdida


def test_el_monto_medio_delata_la_martingala(historial):
    filas = [
        fila(minutos=0, resultado="loss", monto=2.0, ganancia=-2.0),
        fila(minutos=5, resultado="loss", monto=4.0, ganancia=-4.0),
        fila(minutos=10, resultado="win", monto=8.0, ganancia=6.8),
    ]
    niveles = {
        p.perdidas_previas: p for p in binarias.calcular(leer(historial, filas)).profundidad
    }

    assert niveles[0].monto_medio == pytest.approx(2.0)
    assert niveles[1].monto_medio == pytest.approx(4.0)
    assert niveles[2].monto_medio == pytest.approx(8.0)


# -- avisos ---------------------------------------------------------------

def test_avisa_cuando_esta_por_debajo_del_equilibrio(historial):
    filas = [fila(minutos=i, monto=10.0, ganancia=10.0) for i in range(14)]
    filas += [
        fila(minutos=100 + i, resultado="loss", monto=10.0, ganancia=-10.0)
        for i in range(20)
    ]
    avisos = binarias.avisos(binarias.calcular(leer(historial, filas)))

    assert any("por debajo del punto de equilibrio" in a for a in avisos)


def test_avisa_de_una_muestra_corta(historial):
    filas = [fila(minutos=i, monto=10.0, ganancia=8.0) for i in range(3)]
    avisos = binarias.avisos(binarias.calcular(leer(historial, filas)))

    assert any("muestra es corta" in a for a in avisos)


def test_sin_datos_no_hay_avisos():
    assert binarias.avisos(binarias.calcular([])) == []


def test_las_metricas_vacias_no_revientan():
    m = binarias.calcular([])

    assert not m.hay_datos
    assert m.efectividad == 0
    assert m.punto_equilibrio == 0
    assert m.veredicto == "sin datos"


def test_las_operaciones_de_spot_se_ignoran(trade):
    """binarias.calcular solo mira las operaciones marcadas como binarias."""
    assert not binarias.calcular([trade(pnl=10)]).hay_datos
