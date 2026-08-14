"""Dashboard en vivo: sirve el reporte en el navegador y se refresca solo.

Usa el servidor HTTP de la stdlib, asi que no hace falta instalar nada. Cada
peticion vuelve a leer las fuentes, con una cache corta para no machacar la API
del exchange si dejas la pestana abierta.

    jarvis dashboard --puerto 8000

Escucha solo en localhost por defecto. El reporte incluye tu historial de
operaciones: no lo expongas a internet sin poner algo delante que lo proteja.
"""

from __future__ import annotations

import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import Config
from .merge import fusionar
from .metrics import calcular, filtrar_periodo, rango_periodo
from .report import html as reporte_html
from .sources import crear_fuente

CACHE_SEG = 20


class _Cache:
    """Guarda el ultimo libro leido durante unos segundos.

    El navegador puede recargar cada 30 segundos y varias pestanas pueden pedir
    a la vez; sin esto cada recarga golpearia la API del exchange.
    """

    def __init__(self, segundos: float = CACHE_SEG):
        self.segundos = segundos
        self._candado = threading.Lock()
        self._datos: dict[str, tuple[float, object]] = {}

    def obtener(self, clave: str, calcular_valor):
        ahora = time.monotonic()
        with self._candado:
            guardado = self._datos.get(clave)
            if guardado and ahora - guardado[0] < self.segundos:
                return guardado[1]
        valor = calcular_valor()
        with self._candado:
            self._datos[clave] = (ahora, valor)
        return valor


def _construir_pagina(config: Config, periodo: str, refresco: int) -> str:
    fuentes = [crear_fuente(n, c) for n, c in config.fuentes.items()]
    desde, hasta = rango_periodo(periodo)
    libro = fusionar(fuentes, desde, hasta)
    trades = filtrar_periodo(libro.trades, desde, hasta)
    metricas = calcular(trades, config.capital_inicial)

    return reporte_html.render(
        metricas,
        trades=trades,
        moneda=config.moneda,
        titulo="Dashboard",
        periodo=periodo,
        abiertas=libro.abiertas,
        avisos=libro.errores,
        fuentes=libro.fuentes_ok,
        autorecarga=refresco,
    )


def crear_handler(config: Config, periodo: str, refresco: int, cache: _Cache):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Jarvis"

        def do_GET(self) -> None:  # noqa: N802 - nombre impuesto por la clase base
            partes = urlparse(self.path)
            if partes.path not in ("/", "/index.html"):
                self.send_error(404, "No encontrado")
                return

            consulta = parse_qs(partes.query)
            # El periodo se puede cambiar desde la propia URL: /?periodo=hoy
            elegido = consulta.get("periodo", [periodo])[0]

            try:
                cuerpo = cache.obtener(elegido, lambda: _construir_pagina(config, elegido, refresco))
            except Exception as e:  # noqa: BLE001 - el navegador debe ver el motivo
                cuerpo = _pagina_error(e)

            datos = cuerpo.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(datos)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(datos)

        def log_message(self, formato: str, *args) -> None:
            # Silencio por defecto: el log de acceso solo estorba en la terminal
            # donde estas mirando el reporte.
            pass

    return Handler


def _pagina_error(error: Exception) -> str:
    import html as _html

    return (
        "<!doctype html><meta charset='utf-8'>"
        "<title>Jarvis · error</title>"
        "<body style='font:15px system-ui;padding:40px;max-width:700px;margin:auto'>"
        "<h1 style='font-size:19px'>Jarvis no pudo generar el reporte</h1>"
        f"<pre style='background:#f4f4f5;padding:14px;border-radius:8px;"
        f"white-space:pre-wrap'>{_html.escape(str(error))}</pre>"
        "<p style='color:#666'>Revisa la configuracion y recarga la pagina.</p>"
        "</body>"
    )


def servir(
    config: Config,
    puerto: int = 8000,
    host: str = "127.0.0.1",
    periodo: str = "mes",
    refresco: int = 30,
    abrir: bool = True,
) -> None:
    """Arranca el dashboard y bloquea hasta que se corta con Ctrl+C."""
    cache = _Cache()
    handler = crear_handler(config, periodo, refresco, cache)
    servidor = ThreadingHTTPServer((host, puerto), handler)
    direccion = f"http://{host}:{puerto}"

    print(f"Jarvis sirviendo el dashboard en {direccion}")
    print(f"Periodo: {periodo}  ·  refresco cada {refresco}s  ·  Ctrl+C para parar")
    if host not in ("127.0.0.1", "localhost"):
        print("Aviso: escuchando fuera de localhost. El reporte contiene tu historial.")

    if abrir:
        threading.Timer(0.5, lambda: webbrowser.open(direccion)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard detenido.")
    finally:
        servidor.server_close()
