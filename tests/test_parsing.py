"""La deteccion automatica es lo que evita que el usuario configure nada.

Si esto falla, la promesa de "apunta Jarvis a tu CSV y ya" deja de ser cierta.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from jarvis.sources.parsing import (
    a_direccion,
    a_fecha,
    a_lado,
    a_numero,
    mapear_columnas,
)


# -- fechas ---------------------------------------------------------------

@pytest.mark.parametrize("valor", [
    "2026-03-02 09:00:00",
    "2026-03-02T09:00:00",
    "2026-03-02T09:00:00Z",
    "2026-03-02T09:00:00+00:00",
    "02/03/2026 09:00:00",
    "02.03.2026 09:00:00",
    "2026/03/02 09:00:00",
])
def test_reconoce_los_formatos_de_fecha_habituales(valor):
    assert a_fecha(valor) == datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)


def test_reconoce_epoch_en_segundos_y_milisegundos():
    segundos = 1772442000
    assert a_fecha(segundos) == a_fecha(segundos * 1000)
    assert a_fecha(str(segundos)) == a_fecha(segundos)


def test_una_fecha_sin_zona_se_asume_utc():
    assert a_fecha("2026-03-02 09:00:00").tzinfo == timezone.utc


def test_fecha_ilegible_falla_con_mensaje_claro():
    with pytest.raises(ValueError, match="no se reconoce la fecha"):
        a_fecha("el martes por la manana")


# -- numeros --------------------------------------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("123.45", 123.45),
    ("1,234.56", 1234.56),      # miles anglosajon
    ("1.234,56", 1234.56),      # miles europeo
    ("12,34", 12.34),           # decimal europeo
    ("$1,500.00", 1500.0),
    ("-42.5", -42.5),
    ("(12.34)", -12.34),        # negativo contable
    ("2.5%", 2.5),
    ("", 0.0),
    ("  ", 0.0),
])
def test_convierte_numeros_en_los_formatos_que_escriben_los_bots(texto, esperado):
    assert a_numero(texto) == pytest.approx(esperado)


def test_numero_ilegible_devuelve_el_valor_por_defecto():
    assert a_numero("no soy un numero", -1.0) == -1.0


# -- lados ----------------------------------------------------------------

@pytest.mark.parametrize("valor", ["buy", "BUY", "b", "compra", "long", "LONG"])
def test_reconoce_las_compras(valor):
    assert a_lado(valor) == "buy"


@pytest.mark.parametrize("valor", ["sell", "SELL", "s", "venta", "short"])
def test_reconoce_las_ventas(valor):
    assert a_lado(valor) == "sell"


def test_reconoce_lados_dentro_de_cadenas_compuestas():
    assert a_lado("ORDER_SIDE_BUY") == "buy"
    assert a_lado("Cerrar venta") == "sell"


def test_direccion_traduce_a_largo_o_corto():
    assert a_direccion("buy") == "long"
    assert a_direccion("venta") == "short"


def test_lado_desconocido_falla():
    with pytest.raises(ValueError, match="no se reconoce el lado"):
        a_lado("quizas")


# -- mapeo de columnas ----------------------------------------------------

def test_detecta_cabeceras_en_espanol():
    mapa = mapear_columnas(["fecha", "simbolo", "lado", "cantidad", "precio", "comision"])

    assert mapa["ts"] == "fecha"
    assert mapa["symbol"] == "simbolo"
    assert mapa["side"] == "lado"
    assert mapa["qty"] == "cantidad"
    assert mapa["price"] == "precio"
    assert mapa["fee"] == "comision"


def test_detecta_cabeceras_en_ingles():
    mapa = mapear_columnas(["timestamp", "symbol", "side", "qty", "price", "fee"])

    assert mapa["ts"] == "timestamp"
    assert mapa["symbol"] == "symbol"
    assert mapa["qty"] == "qty"


def test_detecta_cabeceras_con_mayusculas_y_guiones():
    mapa = mapear_columnas(["Close_Time", "Symbol", "Entry Price", "Exit-Price"])

    assert mapa["close_ts"] == "Close_Time"
    assert mapa["entry_price"] == "Entry Price"
    assert mapa["exit_price"] == "Exit-Price"


def test_el_mapeo_manual_gana_sobre_la_deteccion():
    mapa = mapear_columnas(
        ["fecha", "simbolo", "precio", "mi_precio_raro"],
        manual={"price": "mi_precio_raro"},
    )
    assert mapa["price"] == "mi_precio_raro"


def test_mapeo_manual_a_columna_inexistente_avisa():
    with pytest.raises(KeyError, match="no existe"):
        mapear_columnas(["fecha"], manual={"price": "columna_fantasma"})
