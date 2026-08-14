"""Reportes de opciones binarias: terminal, dashboard y Telegram."""

from __future__ import annotations

import pytest

from jarvis import binarias
from jarvis.metrics import calcular as calcular_spot
from jarvis.report import console, html
from jarvis.report.formato import Pintor, sin_color
from jarvis.report.telegram import resumen_binarias
from jarvis.sources.iqoption import FuenteIQOption

from .test_binarias import CABECERA, fila


@pytest.fixture
def metricas(tmp_path):
    def crear(filas):
        ruta = tmp_path / "historial_operaciones.csv"
        ruta.write_text("\n".join([CABECERA, *filas]) + "\n", encoding="utf-8")
        trades = FuenteIQOption("bot", ruta=str(ruta)).leer().trades
        return binarias.calcular(trades), trades

    return crear


@pytest.fixture
def muestra(metricas):
    filas = [
        fila(minutos=i * 30, par="EURUSD-OTC", monto=10.0, ganancia=8.5, balance=100 + i)
        for i in range(12)
    ]
    filas += [
        fila(minutos=1000 + i * 30, par="GBPUSD-OTC", resultado="loss",
             monto=10.0, ganancia=-10.0, balance=100 - i)
        for i in range(8)
    ]
    return metricas(filas)


# -- terminal -------------------------------------------------------------

def test_el_reporte_muestra_el_punto_de_equilibrio(muestra):
    m, trades = muestra
    salida = console.render(calcular_spot(trades), binarias=m, color=False)

    assert "OPCIONES BINARIAS" in salida
    assert "Punto de equilibrio" in salida
    assert "Efectividad" in salida


def test_el_reporte_de_binarias_omite_las_metricas_de_spot(muestra):
    """Profit factor o duracion media no significan nada en binarias."""
    m, trades = muestra
    salida = console.render(calcular_spot(trades), binarias=m, color=False)

    assert "Profit factor" not in salida
    assert "Duracion media" not in salida


def test_el_reporte_incluye_el_veredicto(muestra):
    m, trades = muestra
    salida = console.render(calcular_spot(trades), binarias=m, color=False)

    assert m.veredicto.upper() in salida


def test_el_reporte_desglosa_por_par_y_profundidad(muestra):
    m, trades = muestra
    salida = console.render(calcular_spot(trades), binarias=m, color=False)

    assert "POR PAR" in salida
    assert "EURUSD-OTC" in salida
    assert "SEGUN PERDIDAS SEGUIDAS PREVIAS" in salida


def test_las_lineas_no_se_desbordan_con_color(muestra):
    m, trades = muestra
    salida = console.render(calcular_spot(trades), binarias=m, color=True)

    for linea in salida.splitlines():
        assert len(sin_color(linea)) <= 80


def test_los_avisos_largos_se_parten_en_varias_lineas(muestra):
    m, trades = muestra
    largo = (
        "Este es un aviso deliberadamente muy largo que no cabe de ninguna "
        "manera en el ancho de una sola linea de la terminal y por tanto debe "
        "repartirse en varias."
    )
    salida = console.render(
        calcular_spot(trades), binarias=m, avisos=[largo], color=False
    )

    for linea in salida.splitlines():
        assert len(linea) <= 80


def test_sin_binarias_se_usa_el_reporte_normal(trade):
    salida = console.render(calcular_spot([trade(pnl=10)]), color=False)

    assert "OPCIONES BINARIAS" not in salida
    assert "Profit factor" in salida


# -- dashboard ------------------------------------------------------------

def test_el_dashboard_de_binarias_es_autocontenido(muestra):
    m, trades = muestra
    doc = html.render(calcular_spot(trades), trades=trades, binarias=m)

    assert doc.startswith("<!doctype html>")
    assert "<script" not in doc
    assert "src=" not in doc


def test_el_dashboard_incluye_el_medidor_de_equilibrio(muestra):
    m, trades = muestra
    doc = html.render(calcular_spot(trades), trades=trades, binarias=m)

    assert "punto de equilibrio" in doc.lower()
    assert "equilibrio" in doc
    assert 'class="equilibrio"' in doc


def test_el_dashboard_marca_los_pares_por_debajo_del_umbral(muestra):
    m, trades = muestra
    doc = html.render(calcular_spot(trades), trades=trades, binarias=m)

    assert "GBPUSD-OTC" in doc
    assert "Por par" in doc


def test_el_dashboard_incluye_los_estilos_de_binarias(muestra):
    m, trades = muestra
    doc = html.render(calcular_spot(trades), trades=trades, binarias=m)

    assert ".veredicto" in doc


def test_los_estilos_de_binarias_no_estorban_en_el_de_spot(trade):
    doc = html.render(calcular_spot([trade(pnl=5)]), trades=[trade(pnl=5)])
    assert ".veredicto" not in doc


def test_varios_avisos_se_agrupan_en_un_solo_bloque(muestra):
    m, trades = muestra
    doc = html.render(
        calcular_spot(trades), trades=trades, binarias=m,
        avisos=["primero", "segundo", "tercero"],
    )

    assert doc.count('class="aviso"') == 1
    assert "3 cosas que conviene mirar" in doc
    assert doc.count("<li>") == 3


def test_un_solo_aviso_va_sin_lista(muestra):
    m, trades = muestra
    doc = html.render(calcular_spot(trades), trades=trades, binarias=m, avisos=["uno"])

    assert "<li>" not in doc
    assert "uno" in doc


def test_el_dashboard_escapa_los_avisos(muestra):
    m, trades = muestra
    doc = html.render(
        calcular_spot(trades), trades=trades, binarias=m,
        avisos=["<script>alert(1)</script>", "otro"],
    )

    assert "<script>alert(1)</script>" not in doc


# -- telegram -------------------------------------------------------------

def test_el_resumen_de_telegram_lleva_el_equilibrio(muestra):
    m, _ = muestra
    texto = resumen_binarias(m, moneda="USD", periodo="hoy")

    assert "Efectividad" in texto
    assert "Equilibrio" in texto
    assert "Margen" in texto


def test_el_resumen_escapa_los_puntos_de_markdown(muestra):
    m, _ = muestra
    texto = resumen_binarias(m, periodo="hoy")

    # En MarkdownV2 el punto es reservado: cada decimal debe ir escapado.
    for fragmento in texto.split("*"):
        assert ". " not in fragmento or "\\." in texto


def test_el_resumen_marca_si_supera_el_equilibrio(muestra):
    m, _ = muestra
    texto = resumen_binarias(m)

    assert ("✅" in texto) == m.rentable
