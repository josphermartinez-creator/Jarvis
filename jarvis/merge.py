"""Fusion de fuentes en un unico libro de operaciones.

Este es el corazon de "se pueden fusionar": puedes tener el CSV del bot, la API
del exchange y una base de datos apuntando a las mismas operaciones. Jarvis lee
todo, quita los duplicados y deja un libro unico.

La deduplicacion se apoya en la huella de cada operacion (``fingerprint``): si
la fuente da un identificador del exchange se usa ese; si no, se compara
simbolo, fechas, cantidad y precios. Ademas hay una segunda pasada por
proximidad temporal, porque dos fuentes pueden registrar la misma ejecucion con
unos segundos de diferencia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from .matching import PosicionAbierta, construir_libro
from .models import Fill, Trade
from .sources.base import ErrorDeFuente, Fuente

# Margen para considerar que dos registros de fuentes distintas son la misma
# operacion pese a no coincidir al milisegundo.
TOLERANCIA_SEG = 2.0
TOLERANCIA_PRECIO = 1e-6


@dataclass
class Libro:
    """Resultado de fusionar todas las fuentes."""

    trades: list[Trade] = field(default_factory=list)
    abiertas: list[PosicionAbierta] = field(default_factory=list)
    fuentes_ok: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    duplicados: int = 0
    # Metricas de opciones binarias, si el libro las trae. Lo rellena quien
    # analiza, no la fusion: aqui solo se reserva el hueco.
    binarias: object = None

    @property
    def hay_datos(self) -> bool:
        return bool(self.trades)


def _casi_igual(a: float, b: float, tol: float = TOLERANCIA_PRECIO) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def _dedup_fills(fills: Sequence[Fill]) -> tuple[list[Fill], int]:
    vistos: set[str] = set()
    salida: list[Fill] = []
    duplicados = 0

    for f in sorted(fills, key=lambda f: f.ts):
        if f.fingerprint in vistos:
            duplicados += 1
            continue

        # Segunda pasada: misma ejecucion registrada con desfase de reloj.
        gemelo = any(
            g.symbol == f.symbol
            and g.side == f.side
            and g.source != f.source
            and abs((g.ts - f.ts).total_seconds()) <= TOLERANCIA_SEG
            and _casi_igual(g.qty, f.qty)
            and _casi_igual(g.price, f.price)
            for g in reversed(salida[-50:])
        )
        if gemelo:
            duplicados += 1
            continue

        vistos.add(f.fingerprint)
        salida.append(f)

    return salida, duplicados


def _dedup_trades(trades: Sequence[Trade]) -> tuple[list[Trade], int]:
    vistos: set[str] = set()
    salida: list[Trade] = []
    duplicados = 0

    for t in sorted(trades, key=lambda t: t.close_ts):
        if t.fingerprint in vistos:
            duplicados += 1
            continue

        gemelo = any(
            g.symbol == t.symbol
            and g.direction == t.direction
            and g.source != t.source
            and abs((g.close_ts - t.close_ts).total_seconds()) <= TOLERANCIA_SEG
            and _casi_igual(g.qty, t.qty)
            and _casi_igual(g.entry_price, t.entry_price)
            for g in reversed(salida[-50:])
        )
        if gemelo:
            duplicados += 1
            continue

        vistos.add(t.fingerprint)
        salida.append(t)

    return salida, duplicados


def fusionar(
    fuentes: Sequence[Fuente],
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> Libro:
    """Lee todas las fuentes y devuelve un libro unico y deduplicado.

    Una fuente que falla no tumba el reporte: se anota el error y se sigue con
    las demas, porque casi siempre es mejor un reporte parcial y avisado que
    ninguno.
    """
    libro = Libro()
    fills: list[Fill] = []
    trades: list[Trade] = []

    for fuente in fuentes:
        try:
            lote = fuente.leer(desde, hasta)
        except ErrorDeFuente as e:
            libro.errores.append(str(e))
            continue
        except Exception as e:  # noqa: BLE001 - un fallo raro no debe cortar el resto
            libro.errores.append(f"[{fuente.nombre}] error inesperado: {e}")
            continue

        fills.extend(lote.fills)
        trades.extend(lote.trades)
        libro.fuentes_ok.append(f"{fuente.nombre} ({len(lote)})")

    fills, dup_fills = _dedup_fills(fills)
    trades, dup_trades = _dedup_trades(trades)
    libro.duplicados = dup_fills + dup_trades

    todas, abiertas = construir_libro(fills, trades)
    # Ultima pasada: el emparejador puede generar cierres que ya venian dados
    # por otra fuente como operacion cerrada.
    libro.trades, extra = _dedup_trades(todas)
    libro.duplicados += extra
    libro.abiertas = abiertas

    return libro
