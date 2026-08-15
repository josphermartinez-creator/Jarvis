"""Lectura del estado en vivo desde el panel del bot."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jarvis import vivo
from jarvis.report import vivo_consola, vivo_html
from jarvis.report.formato import Pintor, sin_color

ESTADO_BASE = {
    "corriendo": True,
    "conectado": True,
    "modo": "PRACTICE",
    "balance": 248.37,
    "wins": 7,
    "losses": 4,
    "neto": 12.85,
    "perdidas_seguidas": 2,
    "martingala_nivel": 2,
    "martingala_monto": 9.68,
    "exposicion_en_vuelo": 9.68,
    "error": "",
    "pares_operando": ["EURUSD-OTC", "AUDCAD-OTC"],
    "pares_estado": {"EURUSD-OTC": {"senal": "esperando"}},
    "pares_bloqueados": {},
    "watchdog_atascados": [],
    "operaciones": [{"par": "EURUSD-OTC", "resultado": "win"}],
    "log": ["[WIN] EURUSD-OTC +$1.70"],
    "csrf_token": "no-deberia-usarse",
}


@pytest.fixture
def panel():
    """Levanta un panel falso que responde como el del bot."""
    servidores = []

    def arrancar(payload=None, codigo=200, cuerpo_crudo=None):
        datos = ESTADO_BASE if payload is None else payload

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/api/estado":
                    self.send_error(404)
                    return
                if codigo != 200:
                    self.send_error(codigo)
                    return
                cuerpo = (
                    cuerpo_crudo.encode() if cuerpo_crudo is not None
                    else json.dumps(datos).encode()
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def log_message(self, *a):
                pass

        servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        servidores.append(servidor)
        return f"http://127.0.0.1:{servidor.server_address[1]}"

    yield arrancar

    for s in servidores:
        s.shutdown()
        s.server_close()


# -- consulta -------------------------------------------------------------

def test_lee_el_estado_del_panel(panel):
    estado = vivo.consultar(panel())

    assert estado.corriendo
    assert estado.conectado
    assert estado.balance == pytest.approx(248.37)
    assert estado.wins == 7
    assert estado.losses == 4


def test_el_bot_apagado_no_es_un_fallo_de_jarvis():
    """Puerto cerrado: se marca como apagado, no como error de configuracion."""
    with pytest.raises(vivo.BotNoDisponible) as e:
        vivo.consultar("http://127.0.0.1:1", timeout=1)

    assert e.value.apagado


def test_una_respuesta_que_no_es_json_avisa_claro(panel):
    url = panel(cuerpo_crudo="<html>hola</html>")

    with pytest.raises(vivo.BotNoDisponible, match="no es JSON"):
        vivo.consultar(url)


def test_un_401_pide_la_contrasena(panel):
    with pytest.raises(vivo.BotNoDisponible, match="contrasena"):
        vivo.consultar(panel(codigo=401))


def test_falta_de_claves_no_revienta(panel):
    estado = vivo.consultar(panel({"corriendo": True}))

    assert estado.corriendo
    assert estado.balance == 0
    assert estado.pares == []


def test_valores_corruptos_caen_a_su_defecto(panel):
    estado = vivo.consultar(panel({**ESTADO_BASE, "balance": "no-es-un-numero"}))

    assert estado.balance == 0


# -- interpretacion -------------------------------------------------------

def test_distingue_la_cuenta_real_de_la_de_practica():
    assert not vivo.interpretar({"modo": "PRACTICE"}).es_cuenta_real
    assert vivo.interpretar({"modo": "REAL"}).es_cuenta_real


def test_sin_modo_no_se_asume_cuenta_real():
    """Ante la duda, no alarmar diciendo que opera con dinero real."""
    assert not vivo.interpretar({}).es_cuenta_real


def test_los_pares_bloqueados_llevan_su_vencimiento():
    datos = {
        "pares_estado": {"EURUSD-OTC": {"senal": "esperando"}},
        "pares_bloqueados": {"AUDCAD-OTC": time.time() + 600},
    }
    estado = vivo.interpretar(datos)
    bloqueados = [p.par for p in estado.pares_bloqueados]

    assert bloqueados == ["AUDCAD-OTC"]


def test_un_bloqueo_ya_vencido_no_cuenta():
    datos = {"pares_bloqueados": {"AUDCAD-OTC": time.time() - 60}}
    assert vivo.interpretar(datos).pares_bloqueados == []


def test_los_atascados_del_watchdog_llegan_como_pares_y_segundos():
    estado = vivo.interpretar({"watchdog_atascados": [["EURUSD-OTC", 90]]})
    assert estado.atascados == ["EURUSD-OTC"]


def test_la_efectividad_de_la_sesion_ignora_las_no_decididas():
    estado = vivo.interpretar({"wins": 6, "losses": 4})
    assert estado.efectividad_sesion == pytest.approx(60.0)


def test_sin_operaciones_la_efectividad_es_cero():
    assert vivo.interpretar({}).efectividad_sesion == 0


def test_el_resumen_describe_el_estado():
    assert vivo.interpretar({"corriendo": False}).resumen == "detenido"
    assert "sin conexion" in vivo.interpretar({"corriendo": True}).resumen
    assert "practica" in vivo.interpretar(
        {"corriendo": True, "conectado": True, "modo": "PRACTICE"}
    ).resumen


# -- avisos ---------------------------------------------------------------

def test_avisa_si_corre_sin_conexion():
    avisos = vivo.avisos(vivo.interpretar({"corriendo": True, "conectado": False}))
    assert any("sin conexion" in a for a in avisos)


def test_avisa_de_la_cuenta_real():
    avisos = vivo.avisos(
        vivo.interpretar({"corriendo": True, "conectado": True, "modo": "REAL"})
    )
    assert any("dinero real" in a for a in avisos)


def test_avisa_de_la_martingala_alta():
    avisos = vivo.avisos(
        vivo.interpretar({"martingala_nivel": 3, "martingala_monto": 21.3})
    )
    assert any("nivel 3" in a for a in avisos)


def test_avisa_si_hay_mucho_en_juego():
    avisos = vivo.avisos(
        vivo.interpretar({"exposicion_en_vuelo": 60.0, "balance": 100.0})
    )
    assert any("en juego" in a for a in avisos)


def test_una_exposicion_pequena_no_alarma():
    avisos = vivo.avisos(
        vivo.interpretar({"exposicion_en_vuelo": 2.0, "balance": 250.0})
    )
    assert not any("en juego" in a for a in avisos)


def test_un_bot_tranquilo_no_genera_avisos():
    estado = vivo.interpretar(
        {"corriendo": True, "conectado": True, "modo": "PRACTICE", "balance": 250.0}
    )
    assert vivo.avisos(estado) == []


# -- presentacion ---------------------------------------------------------

def test_la_vista_de_terminal_muestra_lo_esencial():
    estado = vivo.interpretar(ESTADO_BASE)
    salida = vivo_consola.render(estado, "USD", Pintor(False))

    assert "BOT OPERANDO" in salida
    assert "Balance" in salida
    assert "Martingala" in salida


def test_la_vista_de_terminal_marca_el_bot_detenido():
    salida = vivo_consola.render(
        vivo.interpretar({"corriendo": False}), "USD", Pintor(False)
    )
    assert "BOT DETENIDO" in salida


def test_las_lineas_de_la_vista_caben_en_la_terminal():
    estado = vivo.interpretar(ESTADO_BASE)
    salida = vivo_consola.render(estado, "USD", Pintor(True))

    for linea in salida.splitlines():
        assert len(sin_color(linea)) <= 80


def test_el_panel_html_marca_la_cuenta_real():
    estado = vivo.interpretar({**ESTADO_BASE, "modo": "REAL"})
    assert "dinero real" in vivo_html.panel(estado, "USD")


def test_el_panel_html_escapa_lo_que_viene_del_bot():
    estado = vivo.interpretar({**ESTADO_BASE, "error": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in vivo_html.panel(estado, "USD")


def test_el_panel_html_escapa_el_log():
    estado = vivo.interpretar({**ESTADO_BASE, "log": ["<img onerror=x>"]})
    assert "<img onerror=x>" not in vivo_html.panel(estado, "USD")


def test_el_panel_apagado_aclara_que_el_historial_sigue_valiendo():
    salida = vivo_html.panel_apagado("no responde", "http://127.0.0.1:5000")
    assert "historial" in salida


# -- integracion en el dashboard ------------------------------------------

def test_el_dashboard_pone_el_estado_arriba(trade):
    from jarvis.metrics import calcular
    from jarvis.report import html

    trades = [trade(pnl=5)]
    doc = html.render(calcular(trades), trades=trades, vivo=vivo.interpretar(ESTADO_BASE))

    assert 'class="vivo' in doc
    assert ".vivo {" in doc  # los estilos del panel viajan con el
    # El estado actual va antes del analisis del historial.
    assert doc.index("vivo-cabecera") < doc.index('class="resultado"')


def test_sin_estado_en_vivo_no_se_incluyen_sus_estilos(trade):
    from jarvis.metrics import calcular
    from jarvis.report import html

    trades = [trade(pnl=5)]
    doc = html.render(calcular(trades), trades=trades)

    assert ".vivo {" not in doc


def test_el_dashboard_muestra_el_aviso_si_el_bot_esta_apagado(trade):
    from jarvis.metrics import calcular
    from jarvis.report import html

    trades = [trade(pnl=5)]
    doc = html.render(calcular(trades), trades=trades, vivo_error="no responde en localhost")

    assert "Bot sin conexion" in doc
    assert "no responde en localhost" in doc
