"""Jarvis: reportes de tu bot de trading.

Lee las operaciones desde donde las tengas (CSV, base de datos, exchange, MT5),
las fusiona en un unico libro sin duplicados y calcula las metricas que
importan: PnL, aciertos, profit factor, drawdown, rachas y desglose por
simbolo, dia y hora.

Uso rapido:

    from jarvis import reporte
    print(reporte("operaciones.csv"))
"""

from __future__ import annotations

from .config import Config, cargar
from .merge import Libro, fusionar
from .metrics import Metricas, calcular, filtrar_periodo, rango_periodo
from .models import Fill, Trade
from .sources import crear_fuente

__version__ = "0.1.0"

__all__ = [
    "Config",
    "Fill",
    "Libro",
    "Metricas",
    "Trade",
    "__version__",
    "analizar",
    "calcular",
    "cargar",
    "crear_fuente",
    "filtrar_periodo",
    "fusionar",
    "rango_periodo",
    "reporte",
]


def analizar(
    origen: str | Config,
    periodo: str = "todo",
    capital_inicial: float = 0.0,
) -> tuple[Metricas, Libro]:
    """Lee, fusiona y calcula en un paso.

    ``origen`` puede ser la ruta de un archivo de operaciones o una ``Config``
    ya cargada con varias fuentes.
    """
    if isinstance(origen, Config):
        config = origen
        fuentes = [crear_fuente(n, c) for n, c in config.fuentes.items()]
    else:
        config = Config(capital_inicial=capital_inicial)
        fuentes = [crear_fuente("archivo", {"tipo": "archivo", "ruta": str(origen)})]

    desde, hasta = rango_periodo(periodo)
    libro = fusionar(fuentes, desde, hasta)
    trades = filtrar_periodo(libro.trades, desde, hasta)
    capital = capital_inicial or config.capital_inicial
    return calcular(trades, capital), libro


def reporte(origen: str | Config, periodo: str = "todo", **opciones) -> str:
    """Devuelve el reporte de terminal listo para imprimir."""
    from .report.console import render

    metricas, libro = analizar(origen, periodo, opciones.pop("capital_inicial", 0.0))
    return render(
        metricas,
        moneda=opciones.pop("moneda", "USDT"),
        periodo=periodo,
        abiertas=libro.abiertas,
        avisos=libro.errores,
        **opciones,
    )
