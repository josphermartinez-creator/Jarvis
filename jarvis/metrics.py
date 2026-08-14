"""Calculo de metricas de rendimiento a partir del libro de operaciones.

Solo stdlib: nada de pandas ni numpy, para que Jarvis corra en cualquier lado
(un VPS pelado, una Raspberry, el mismo contenedor del bot).
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Sequence

from .models import Trade

# Operaciones por año usadas para anualizar el Sharpe cuando agrupamos por dia.
DIAS_HABILES_ANIO = 365


@dataclass
class PuntoEquity:
    ts: datetime
    equity: float
    drawdown: float
    drawdown_pct: float


@dataclass
class Bloque:
    """Resultado agregado de un subconjunto de operaciones (simbolo, dia, hora)."""

    clave: str
    operaciones: int
    pnl: float
    ganadoras: int
    perdedoras: int

    @property
    def winrate(self) -> float:
        return self.ganadoras / self.operaciones * 100 if self.operaciones else 0.0


@dataclass
class Metricas:
    """Todo lo que Jarvis sabe decir sobre un periodo."""

    desde: datetime | None = None
    hasta: datetime | None = None
    operaciones: int = 0
    ganadoras: int = 0
    perdedoras: int = 0
    neutras: int = 0

    pnl_bruto: float = 0.0
    comisiones: float = 0.0
    pnl_neto: float = 0.0

    ganancia_media: float = 0.0
    perdida_media: float = 0.0
    mejor: Trade | None = None
    peor: Trade | None = None

    profit_factor: float = 0.0
    expectativa: float = 0.0
    payoff: float = 0.0

    racha_ganadora: int = 0
    racha_perdedora: int = 0

    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0

    duracion_media_seg: float = 0.0
    volumen_operado: float = 0.0

    equity: list[PuntoEquity] = field(default_factory=list)
    por_simbolo: list[Bloque] = field(default_factory=list)
    por_dia: list[Bloque] = field(default_factory=list)
    por_hora: list[Bloque] = field(default_factory=list)
    por_dia_semana: list[Bloque] = field(default_factory=list)

    @property
    def winrate(self) -> float:
        decididas = self.ganadoras + self.perdedoras
        return self.ganadoras / decididas * 100 if decididas else 0.0

    @property
    def hay_datos(self) -> bool:
        return self.operaciones > 0


def _agrupar(trades: Sequence[Trade], clave) -> list[Bloque]:
    acumulado: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        acumulado[clave(t)].append(t.pnl_neto)
    bloques = [
        Bloque(
            clave=k,
            operaciones=len(v),
            pnl=sum(v),
            ganadoras=sum(1 for p in v if p > 0),
            perdedoras=sum(1 for p in v if p < 0),
        )
        for k, v in acumulado.items()
    ]
    return bloques


def _sharpe_y_sortino(por_dia: list[Bloque], capital_base: float) -> tuple[float, float]:
    """Sharpe y Sortino anualizados sobre retornos diarios.

    Se asume tasa libre de riesgo 0, que es lo habitual para reportar bots de
    cripto intradia. Con menos de dos dias de datos no hay desviacion que medir
    y se devuelve 0.
    """
    if len(por_dia) < 2 or capital_base <= 0:
        return 0.0, 0.0

    retornos = [b.pnl / capital_base for b in sorted(por_dia, key=lambda b: b.clave)]
    media = statistics.fmean(retornos)
    factor = math.sqrt(DIAS_HABILES_ANIO)

    desv = statistics.stdev(retornos)
    sharpe = (media / desv * factor) if desv > 0 else 0.0

    negativos = [r for r in retornos if r < 0]
    if negativos:
        desv_baja = math.sqrt(sum(r * r for r in negativos) / len(retornos))
        sortino = (media / desv_baja * factor) if desv_baja > 0 else 0.0
    else:
        sortino = 0.0

    return sharpe, sortino


def _rachas(trades: Sequence[Trade]) -> tuple[int, int]:
    mejor_g = mejor_p = actual_g = actual_p = 0
    for t in trades:
        if t.pnl_neto > 0:
            actual_g += 1
            actual_p = 0
        elif t.pnl_neto < 0:
            actual_p += 1
            actual_g = 0
        else:
            continue
        mejor_g = max(mejor_g, actual_g)
        mejor_p = max(mejor_p, actual_p)
    return mejor_g, mejor_p


def _curva_equity(
    trades: Sequence[Trade], capital_inicial: float
) -> tuple[list[PuntoEquity], float, float]:
    """Curva de capital acumulado y su maximo drawdown.

    El drawdown porcentual se mide contra el pico previo, que es la definicion
    que le importa a quien opera: cuanto se cayo desde el mejor momento.
    """
    equity = capital_inicial
    pico = capital_inicial
    max_dd = 0.0
    max_dd_pct = 0.0
    puntos: list[PuntoEquity] = []

    for t in trades:
        equity += t.pnl_neto
        pico = max(pico, equity)
        dd = pico - equity
        dd_pct = (dd / pico * 100) if pico > 0 else 0.0
        max_dd = max(max_dd, dd)
        max_dd_pct = max(max_dd_pct, dd_pct)
        puntos.append(PuntoEquity(ts=t.close_ts, equity=equity, drawdown=dd, drawdown_pct=dd_pct))

    return puntos, max_dd, max_dd_pct


def calcular(trades: Sequence[Trade], capital_inicial: float = 0.0) -> Metricas:
    """Calcula el paquete completo de metricas para las operaciones dadas.

    ``capital_inicial`` sirve para expresar el drawdown y el Sharpe en
    porcentaje. Si no se conoce, Jarvis usa el capital medio empleado por
    operacion como referencia, que da una escala razonable aunque aproximada.
    """
    m = Metricas()
    if not trades:
        return m

    ordenadas = sorted(trades, key=lambda t: t.close_ts)
    m.operaciones = len(ordenadas)
    m.desde = ordenadas[0].open_ts
    m.hasta = ordenadas[-1].close_ts

    resultados = [t.pnl_neto for t in ordenadas]
    ganancias = [r for r in resultados if r > 0]
    perdidas = [r for r in resultados if r < 0]

    m.ganadoras = len(ganancias)
    m.perdedoras = len(perdidas)
    m.neutras = m.operaciones - m.ganadoras - m.perdedoras

    m.pnl_bruto = sum(t.pnl for t in ordenadas)
    m.comisiones = sum(t.fees for t in ordenadas)
    m.pnl_neto = sum(resultados)

    m.ganancia_media = statistics.fmean(ganancias) if ganancias else 0.0
    m.perdida_media = statistics.fmean(perdidas) if perdidas else 0.0
    m.mejor = max(ordenadas, key=lambda t: t.pnl_neto)
    m.peor = min(ordenadas, key=lambda t: t.pnl_neto)

    total_ganado = sum(ganancias)
    total_perdido = abs(sum(perdidas))
    # Sin perdidas el profit factor es infinito; se marca con inf y el reporte
    # lo imprime como "sin perdidas" en lugar de un numero enorme sin sentido.
    m.profit_factor = (total_ganado / total_perdido) if total_perdido > 0 else (
        math.inf if total_ganado > 0 else 0.0
    )
    m.expectativa = m.pnl_neto / m.operaciones
    if m.perdida_media:
        m.payoff = m.ganancia_media / abs(m.perdida_media)
    else:
        m.payoff = math.inf if m.ganancia_media else 0.0

    m.racha_ganadora, m.racha_perdedora = _rachas(ordenadas)
    m.duracion_media_seg = statistics.fmean([t.duracion_seg for t in ordenadas])
    m.volumen_operado = sum(t.capital_empleado for t in ordenadas)

    base = capital_inicial if capital_inicial > 0 else m.volumen_operado / m.operaciones
    m.equity, m.max_drawdown, m.max_drawdown_pct = _curva_equity(ordenadas, base)

    m.por_simbolo = sorted(
        _agrupar(ordenadas, lambda t: t.symbol), key=lambda b: b.pnl, reverse=True
    )
    m.por_dia = sorted(
        _agrupar(ordenadas, lambda t: t.close_ts.date().isoformat()), key=lambda b: b.clave
    )
    m.por_hora = sorted(
        _agrupar(ordenadas, lambda t: f"{t.close_ts.hour:02d}"), key=lambda b: b.clave
    )
    m.por_dia_semana = sorted(
        _agrupar(ordenadas, lambda t: str(t.close_ts.weekday())), key=lambda b: b.clave
    )

    m.sharpe, m.sortino = _sharpe_y_sortino(m.por_dia, base)
    return m


def filtrar_periodo(
    trades: Sequence[Trade], desde: datetime | None, hasta: datetime | None
) -> list[Trade]:
    """Filtra por fecha de cierre. Los limites son inclusivos."""
    salida = []
    for t in trades:
        if desde and t.close_ts < desde:
            continue
        if hasta and t.close_ts > hasta:
            continue
        salida.append(t)
    return salida


def comparar(actual: Metricas, previo: Metricas) -> dict[str, float]:
    """Variacion de las metricas clave frente al periodo anterior.

    Devuelve diferencias absolutas; el reporte decide como pintarlas.
    """
    return {
        "pnl_neto": actual.pnl_neto - previo.pnl_neto,
        "operaciones": actual.operaciones - previo.operaciones,
        "winrate": actual.winrate - previo.winrate,
        "profit_factor": (
            actual.profit_factor - previo.profit_factor
            if math.isfinite(actual.profit_factor) and math.isfinite(previo.profit_factor)
            else 0.0
        ),
    }


def rango_periodo(nombre: str, ahora: datetime | None = None) -> tuple[datetime | None, datetime | None]:
    """Traduce un periodo hablado ('hoy', 'semana', 'mes') a fechas concretas.

    Acepta ademas ``NdM`` estilo ``7d`` / ``3m`` y un rango explicito
    ``AAAA-MM-DD:AAAA-MM-DD``.
    """
    ahora = ahora or datetime.now(timezone.utc)
    nombre = (nombre or "todo").strip().lower()
    inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)

    if nombre in ("todo", "all", "siempre"):
        return None, None
    if nombre == "hoy":
        return inicio_dia, ahora
    if nombre == "ayer":
        return inicio_dia - timedelta(days=1), inicio_dia - timedelta(microseconds=1)
    if nombre in ("semana", "week"):
        return inicio_dia - timedelta(days=inicio_dia.weekday()), ahora
    if nombre in ("mes", "month"):
        return inicio_dia.replace(day=1), ahora
    if nombre in ("anio", "año", "year"):
        return inicio_dia.replace(month=1, day=1), ahora

    if ":" in nombre:
        a, b = nombre.split(":", 1)
        desde = datetime.fromisoformat(a).replace(tzinfo=ahora.tzinfo) if a else None
        if b:
            hasta = datetime.fromisoformat(b).replace(tzinfo=ahora.tzinfo)
            if hasta.hour == hasta.minute == 0:
                hasta += timedelta(days=1, microseconds=-1)
        else:
            hasta = None
        return desde, hasta

    if len(nombre) > 1 and nombre[:-1].isdigit():
        cantidad, unidad = int(nombre[:-1]), nombre[-1]
        dias = {"d": 1, "s": 7, "w": 7, "m": 30, "a": 365, "y": 365}.get(unidad)
        if dias:
            return ahora - timedelta(days=cantidad * dias), ahora

    raise ValueError(
        f"periodo desconocido: {nombre!r}. Usa hoy, ayer, semana, mes, anio, "
        f"todo, 7d, 3m o AAAA-MM-DD:AAAA-MM-DD"
    )


def periodo_anterior(
    desde: datetime | None, hasta: datetime | None
) -> tuple[datetime | None, datetime | None]:
    """Ventana inmediatamente anterior, del mismo largo, para comparar."""
    if not desde or not hasta:
        return None, None
    largo = hasta - desde
    return desde - largo, desde - timedelta(microseconds=1)
