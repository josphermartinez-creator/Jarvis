"""Los reportes deben generarse siempre, incluso sin datos o con casos raros."""

from __future__ import annotations

import re

import pytest

from jarvis.matching import PosicionAbierta
from jarvis.metrics import calcular
from jarvis.report import console, html
from jarvis.report.formato import barra, duracion, esparkline, sin_color
from jarvis.report.telegram import resumen

from .conftest import t


# -- formato --------------------------------------------------------------

@pytest.mark.parametrize("segundos,esperado", [
    (45, "45s"),
    (90, "1m 30s"),
    (3600, "1h 0m"),
    (86400 * 2 + 3600 * 4, "2d 4h"),
])
def test_duracion_legible(segundos, esperado):
    assert duracion(segundos) == esperado


def test_la_barra_de_los_positivos_va_a_la_derecha():
    positiva = barra(10, 10, 20)
    assert positiva[:10].strip() == ""
    assert "█" in positiva[10:]


def test_la_barra_de_los_negativos_va_a_la_izquierda():
    negativa = barra(-10, 10, 20)
    assert "█" in negativa[:10]
    assert negativa[10:].strip() == ""


def test_la_barra_mantiene_el_ancho_pedido():
    assert len(barra(3, 10, 20)) == 20
    assert len(barra(0, 10, 20)) == 20


def test_el_esparkline_se_remuestrea_si_hay_muchos_puntos():
    assert len(esparkline(list(range(500)), ancho=60)) == 60


def test_el_esparkline_aguanta_una_linea_plana():
    assert len(esparkline([5.0] * 10)) == 10


# -- consola --------------------------------------------------------------

def test_el_reporte_sin_datos_lo_dice_claro():
    salida = console.render(calcular([]), color=False)
    assert "No hay operaciones cerradas" in salida


def test_el_reporte_sin_datos_menciona_las_posiciones_abiertas():
    abierta = PosicionAbierta("BTCUSDT", "long", 1.0, 100.0, t(0))
    salida = console.render(calcular([]), abiertas=[abierta], color=False)
    assert "1 posicion(es) abierta(s)" in salida


def test_el_reporte_completo_incluye_las_cifras_clave(trade):
    m = calcular([trade(pnl=100), trade(pnl=-40)], capital_inicial=1000)
    salida = console.render(m, color=False)

    assert "PnL neto" in salida
    assert "Profit factor" in salida
    assert "Maxima caida" in salida
    assert "+60.00" in salida


def test_sin_color_no_quedan_codigos_ansi(trade):
    salida = console.render(calcular([trade(pnl=10)]), color=False)
    assert "\033[" not in salida


def test_con_color_si_hay_codigos_ansi(trade):
    salida = console.render(calcular([trade(pnl=10)]), color=True)
    assert "\033[" in salida
    assert sin_color(salida) != salida


def test_las_lineas_del_reporte_no_se_desbordan(trade):
    """Con color activo el relleno se calcula sobre el texto visible."""
    m = calcular([trade(pnl=1234.56), trade(pnl=-99.1)], capital_inicial=5000)
    for linea in console.render(m, color=True).splitlines():
        assert len(sin_color(linea)) <= 80


def test_el_profit_factor_infinito_no_imprime_un_numero_absurdo(trade):
    salida = console.render(calcular([trade(pnl=10)]), color=False)
    assert "sin perdidas" in salida
    assert "inf" not in salida.lower()


def test_los_avisos_de_fuentes_caidas_aparecen(trade):
    salida = console.render(
        calcular([trade(pnl=10)]), avisos=["[api] no responde"], color=False
    )
    assert "AVISOS" in salida
    assert "no responde" in salida


# -- html -----------------------------------------------------------------

def test_el_dashboard_es_un_documento_completo(trade):
    m = calcular([trade(pnl=10), trade(pnl=-5)], capital_inicial=1000)
    doc = html.render(m, moneda="USDT")

    assert doc.startswith("<!doctype html>")
    assert doc.rstrip().endswith("</html>")
    assert "<title>" in doc


def test_el_dashboard_no_depende_de_internet(trade):
    """Un CDN caido no puede romper un reporte que miras dentro de un ano."""
    doc = html.render(calcular([trade(pnl=10)]))

    assert "http://" not in doc.replace('xmlns="http://', "")
    assert "<script" not in doc
    assert "src=" not in doc


def test_el_dashboard_sin_datos_tambien_se_genera():
    doc = html.render(calcular([]))
    assert "No hay operaciones cerradas" in doc


def test_el_dashboard_incluye_las_graficas(trade):
    operaciones = [trade(minutos_cierre=60 * 24 * d, pnl=10 * (-1) ** d) for d in range(1, 8)]
    doc = html.render(calcular(operaciones, capital_inicial=1000), trades=operaciones)

    assert doc.count("<svg") >= 3
    assert "Curva de capital" in doc
    assert "Resultado por dia" in doc


def test_el_dashboard_escapa_los_simbolos_raros(trade):
    """Un simbolo con caracteres HTML no debe poder inyectar nada."""
    op = trade(symbol="<img src=x onerror=alert(1)>", pnl=10)
    doc = html.render(calcular([op]), trades=[op])

    # Los simbolos se normalizan a mayusculas, de ahi la comparacion sin caso.
    assert "<img src=x" not in doc.lower()
    assert "&lt;img" in doc.lower()


def test_el_dashboard_escapa_los_avisos(trade):
    doc = html.render(calcular([trade(pnl=1)]), avisos=["<script>alert(1)</script>"])
    assert "<script>alert(1)</script>" not in doc


def test_la_autorecarga_solo_aparece_si_se_pide(trade):
    m = calcular([trade(pnl=1)])
    assert "http-equiv" not in html.render(m)
    assert 'content="30"' in html.render(m, autorecarga=30)


def test_el_dashboard_define_los_colores_para_ambos_temas(trade):
    doc = html.render(calcular([trade(pnl=1)]))
    assert "prefers-color-scheme: dark" in doc
    assert re.search(r":root\s*\{", doc)


# -- telegram -------------------------------------------------------------

def test_el_resumen_de_telegram_escapa_markdown(trade):
    texto = resumen(calcular([trade(pnl=-12.5)]), periodo="hoy")

    # El punto es un caracter reservado en MarkdownV2 y debe ir escapado.
    assert "12\\.5" in texto
    assert "🔴" in texto


def test_el_resumen_sin_datos_es_valido():
    texto = resumen(calcular([]), periodo="hoy")
    assert "Sin operaciones" in texto


def test_el_resumen_marca_en_verde_las_ganancias(trade):
    assert "🟢" in resumen(calcular([trade(pnl=50)]))


def test_el_resumen_lista_los_simbolos(trade):
    m = calcular([trade(symbol="BTCUSDT", pnl=10), trade(symbol="ETHUSDT", pnl=-3)])
    texto = resumen(m)

    assert "BTCUSDT" in texto
    assert "ETHUSDT" in texto
