"""Lectura de archivos y bases de datos, tal y como los escriben los bots."""

from __future__ import annotations

import json
import sqlite3

import pytest

from jarvis.sources import crear_fuente
from jarvis.sources.archivo import FuenteArchivo
from jarvis.sources.base import ErrorDeFuente
from jarvis.sources.basedatos import FuenteBaseDatos

CSV_EJECUCIONES = """\
fecha,simbolo,lado,cantidad,precio,comision
2026-03-02 09:00:00,BTCUSDT,buy,1,100,0.1
2026-03-02 10:00:00,BTCUSDT,sell,1,110,0.11
"""

CSV_CERRADAS = """\
open_time,close_time,symbol,direction,qty,entry_price,exit_price,pnl,fee
2026-03-02 09:00:00,2026-03-02 10:00:00,ETHUSDT,long,2,50,55,10,0.2
"""


def escribir(tmp_path, nombre, contenido):
    ruta = tmp_path / nombre
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def test_lee_ejecuciones_sueltas_de_un_csv(tmp_path):
    ruta = escribir(tmp_path, "ops.csv", CSV_EJECUCIONES)
    lote = FuenteArchivo("bot", ruta=str(ruta)).leer()

    assert len(lote.fills) == 2
    assert not lote.trades
    assert lote.fills[0].side == "buy"
    assert lote.fills[0].symbol == "BTCUSDT"
    assert lote.fills[0].fee == pytest.approx(0.1)


def test_lee_operaciones_ya_cerradas(tmp_path):
    ruta = escribir(tmp_path, "cerradas.csv", CSV_CERRADAS)
    lote = FuenteArchivo("bot", ruta=str(ruta)).leer()

    assert not lote.fills
    assert len(lote.trades) == 1
    op = lote.trades[0]
    assert op.symbol == "ETHUSDT"
    assert op.pnl == pytest.approx(10)
    assert op.pnl_neto == pytest.approx(9.8)


def test_calcula_el_pnl_si_el_archivo_no_lo_trae(tmp_path):
    contenido = (
        "open_time,close_time,symbol,direction,qty,entry_price,exit_price\n"
        "2026-03-02 09:00:00,2026-03-02 10:00:00,BTCUSDT,long,2,100,110\n"
    )
    ruta = escribir(tmp_path, "sin_pnl.csv", contenido)
    lote = FuenteArchivo("bot", ruta=str(ruta)).leer()

    assert lote.trades[0].pnl == pytest.approx(20)


def test_el_pnl_de_un_corto_se_invierte(tmp_path):
    contenido = (
        "open_time,close_time,symbol,direction,qty,entry_price,exit_price\n"
        "2026-03-02 09:00:00,2026-03-02 10:00:00,BTCUSDT,short,1,110,100\n"
    )
    ruta = escribir(tmp_path, "corto.csv", contenido)
    lote = FuenteArchivo("bot", ruta=str(ruta)).leer()

    assert lote.trades[0].direction == "short"
    assert lote.trades[0].pnl == pytest.approx(10)


def test_reconoce_el_punto_y_coma_como_separador(tmp_path):
    ruta = escribir(tmp_path, "euro.csv", CSV_EJECUCIONES.replace(",", ";"))
    lote = FuenteArchivo("bot", ruta=str(ruta)).leer()
    assert len(lote.fills) == 2


def test_lee_json_con_lista_de_operaciones(tmp_path):
    datos = [
        {"ts": "2026-03-02T09:00:00Z", "symbol": "BTCUSDT", "side": "buy",
         "qty": 1, "price": 100},
    ]
    ruta = escribir(tmp_path, "ops.json", json.dumps(datos))
    lote = FuenteArchivo("bot", ruta=str(ruta)).leer()

    assert len(lote.fills) == 1


def test_lee_json_envuelto_en_una_clave(tmp_path):
    datos = {"trades": [
        {"ts": "2026-03-02T09:00:00Z", "symbol": "BTCUSDT", "side": "sell",
         "qty": 1, "price": 100},
    ]}
    ruta = escribir(tmp_path, "ops.json", json.dumps(datos))
    assert len(FuenteArchivo("bot", ruta=str(ruta)).leer().fills) == 1


def test_lee_jsonl_una_operacion_por_linea(tmp_path):
    lineas = "\n".join(
        json.dumps({"ts": f"2026-03-02T0{i}:00:00Z", "symbol": "BTCUSDT",
                    "side": "buy", "qty": 1, "price": 100})
        for i in range(3)
    )
    ruta = escribir(tmp_path, "ops.jsonl", lineas)
    assert len(FuenteArchivo("bot", ruta=str(ruta)).leer().fills) == 3


def test_los_comodines_leen_varios_archivos(tmp_path):
    escribir(tmp_path, "enero.csv", CSV_EJECUCIONES)
    escribir(tmp_path, "febrero.csv", CSV_EJECUCIONES)
    lote = FuenteArchivo("bot", ruta=str(tmp_path / "*.csv")).leer()

    assert len(lote.fills) == 4


def test_una_fila_corrupta_no_tumba_el_reporte(tmp_path):
    contenido = CSV_EJECUCIONES + "fecha_invalida,BTCUSDT,buy,1,100,0\n"
    ruta = escribir(tmp_path, "sucio.csv", contenido)
    lote = FuenteArchivo("bot", ruta=str(ruta)).leer()

    assert len(lote.fills) == 2  # las dos buenas se conservan


def test_en_modo_estricto_una_fila_corrupta_si_falla(tmp_path):
    contenido = CSV_EJECUCIONES + "fecha_invalida,BTCUSDT,buy,1,100,0\n"
    ruta = escribir(tmp_path, "sucio.csv", contenido)

    with pytest.raises(ErrorDeFuente):
        FuenteArchivo("bot", ruta=str(ruta), estricto=True).leer()


def test_archivo_inexistente_avisa_con_la_ruta(tmp_path):
    with pytest.raises(ErrorDeFuente, match="no existe"):
        FuenteArchivo("bot", ruta=str(tmp_path / "fantasma.csv")).leer()


def test_falta_la_opcion_ruta():
    with pytest.raises(ErrorDeFuente, match="ruta"):
        FuenteArchivo("bot").leer()


def test_las_lineas_en_blanco_se_ignoran(tmp_path):
    ruta = escribir(tmp_path, "huecos.csv", CSV_EJECUCIONES + "\n\n")
    assert len(FuenteArchivo("bot", ruta=str(ruta)).leer().fills) == 2


# -- base de datos --------------------------------------------------------

def crear_sqlite(tmp_path):
    ruta = tmp_path / "bot.db"
    con = sqlite3.connect(ruta)
    con.execute(
        "CREATE TABLE trades (fecha TEXT, simbolo TEXT, lado TEXT, "
        "cantidad REAL, precio REAL, comision REAL)"
    )
    con.executemany(
        "INSERT INTO trades VALUES (?,?,?,?,?,?)",
        [
            ("2026-03-02 09:00:00", "BTCUSDT", "buy", 1.0, 100.0, 0.1),
            ("2026-03-02 10:00:00", "BTCUSDT", "sell", 1.0, 110.0, 0.11),
        ],
    )
    con.commit()
    con.close()
    return ruta


def test_lee_una_tabla_de_sqlite(tmp_path):
    ruta = crear_sqlite(tmp_path)
    lote = FuenteBaseDatos("db", ruta=str(ruta), tabla="trades").leer()

    assert len(lote.fills) == 2
    assert lote.fills[0].symbol == "BTCUSDT"


def test_acepta_una_consulta_propia(tmp_path):
    ruta = crear_sqlite(tmp_path)
    fuente = FuenteBaseDatos(
        "db", ruta=str(ruta), consulta="SELECT * FROM trades WHERE lado = 'buy'"
    )
    assert len(fuente.leer().fills) == 1


def test_rechaza_nombres_de_tabla_sospechosos(tmp_path):
    ruta = crear_sqlite(tmp_path)
    fuente = FuenteBaseDatos("db", ruta=str(ruta), tabla="trades; DROP TABLE trades")

    with pytest.raises(ErrorDeFuente, match="nombre de tabla invalido"):
        fuente.leer()


def test_la_base_se_abre_en_solo_lectura(tmp_path):
    """Jarvis nunca debe poder modificar la base de datos del bot."""
    ruta = crear_sqlite(tmp_path)
    fuente = FuenteBaseDatos("db", ruta=str(ruta), consulta="DELETE FROM trades")

    with pytest.raises(ErrorDeFuente, match="solo lectura|readonly|read-only"):
        fuente.leer()


def test_base_inexistente_avisa(tmp_path):
    with pytest.raises(ErrorDeFuente, match="no existe"):
        FuenteBaseDatos("db", ruta=str(tmp_path / "no.db"), tabla="t").leer()


# -- registro -------------------------------------------------------------

def test_crear_fuente_por_tipo(tmp_path):
    ruta = escribir(tmp_path, "ops.csv", CSV_EJECUCIONES)
    fuente = crear_fuente("mi_bot", {"tipo": "csv", "ruta": str(ruta)})

    assert isinstance(fuente, FuenteArchivo)
    assert fuente.nombre == "mi_bot"


def test_el_alias_del_exchange_se_rellena_solo():
    fuente = crear_fuente("bn", {"tipo": "binance", "api_key": "x", "api_secret": "y"})
    assert fuente.opciones["exchange"] == "binance"


def test_tipo_desconocido_lista_los_disponibles():
    with pytest.raises(ErrorDeFuente, match="Disponibles"):
        crear_fuente("x", {"tipo": "telepatia"})
