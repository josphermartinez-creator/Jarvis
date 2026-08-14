"""Reporte de terminal: el resumen que se lee de un vistazo.

Sin librerias de formato: cajas con caracteres Unicode y color ANSI, que se
desactiva solo cuando la salida no es una terminal (por ejemplo al redirigir a
un archivo o mandarlo por correo).
"""

from __future__ import annotations

import math
from datetime import datetime

from ..matching import PosicionAbierta
from ..metrics import Metricas
from .formato import (
    ANCHO,
    Color,
    Pintor,
    barra,
    color_activo,
    dinero,
    duracion,
    esparkline,
    pct,
)
from .formato import linea as _linea

DIAS = ("Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo")


def _envolver(texto: str, c: Pintor, color: str, sangria: str = "  ") -> list[str]:
    """Parte un aviso largo en varias lineas para que quepa en la terminal."""
    import textwrap

    lineas = textwrap.wrap(texto, width=ANCHO - len(sangria)) or [texto]
    continuacion = sangria + "  "
    return [
        c(f"{sangria if i == 0 else continuacion}{linea}", color)
        for i, linea in enumerate(lineas)
    ]


def render(
    m: Metricas,
    moneda: str = "USDT",
    titulo: str = "REPORTE DE TRADING",
    periodo: str = "",
    abiertas: list[PosicionAbierta] | None = None,
    avisos: list[str] | None = None,
    color: bool | None = None,
    detalle: bool = True,
    binarias: "MetricasBinarias | None" = None,
) -> str:
    """Genera el reporte completo como texto listo para imprimir.

    Si ``binarias`` trae metricas de opciones binarias, se muestran esas en vez
    del bloque de spot: en binarias no hay precio de entrada y salida, asi que
    profit factor o duracion media no significan nada.
    """
    c = Pintor(color_activo(color))
    out: list[str] = []
    sep = "─" * ANCHO

    # -- cabecera
    out.append(c("╭" + "─" * ANCHO + "╮", Color.GRIS))
    encabezado = f"  JARVIS · {titulo}"
    if periodo:
        encabezado += f"  ({periodo})"
    out.append(c("│", Color.GRIS) + c(encabezado.ljust(ANCHO), Color.NEGRITA) + c("│", Color.GRIS))
    out.append(c("╰" + "─" * ANCHO + "╯", Color.GRIS))

    if not m.hay_datos:
        out.append("")
        out.append("  No hay operaciones cerradas en este periodo.")
        if abiertas:
            out.append(f"  Hay {len(abiertas)} posicion(es) abierta(s) sin cerrar todavia.")
        out.append("")
        return "\n".join(out)

    if m.desde and m.hasta:
        rango = f"{m.desde:%d/%m/%Y %H:%M} → {m.hasta:%d/%m/%Y %H:%M} UTC"
        out.append(c(f"  {rango}", Color.GRIS))
    out.append("")

    # -- resultado
    signo = "+" if m.pnl_neto >= 0 else ""
    grande = c(f"{signo}{dinero(m.pnl_neto)} {moneda}", Color.NEGRITA)
    out.append("  " + c(grande, Color.VERDE if m.pnl_neto >= 0 else Color.ROJO))
    if m.equity:
        out.append("  " + c(esparkline([p.equity for p in m.equity]), Color.GRIS))
    out.append("")

    if binarias is not None and binarias.hay_datos:
        from .binarias_consola import render as render_binarias

        out.extend(render_binarias(binarias, moneda, c))
        if avisos:
            out.append(c("  AVISOS", Color.NEGRITA))
            out.append(c("  " + sep[:ANCHO - 2], Color.GRIS))
            for aviso in avisos:
                out.extend(_envolver(f"! {aviso}", c, Color.AMARILLO))
            out.append("")
        out.append(c(f"  Generado {datetime.now():%d/%m/%Y %H:%M}", Color.GRIS))
        return "\n".join(out)

    out.append(_linea("  Operaciones", str(m.operaciones)))
    out.append(_linea(
        "  Aciertos",
        f"{c(str(m.ganadoras), Color.VERDE)} / {c(str(m.perdedoras), Color.ROJO)}"
        f"   {pct(m.winrate)}",
    ))
    out.append(_linea("  PnL bruto", f"{dinero(m.pnl_bruto)} {moneda}"))
    out.append(_linea("  Comisiones", c(f"-{dinero(m.comisiones)} {moneda}", Color.AMARILLO)))
    out.append(_linea("  PnL neto", c.segun_signo(f"{signo}{dinero(m.pnl_neto)} {moneda}", m.pnl_neto)))
    out.append("")

    # -- calidad de la estrategia
    out.append(c("  RENDIMIENTO", Color.NEGRITA))
    out.append(c("  " + sep[:ANCHO - 2], Color.GRIS))
    pf = "sin perdidas" if math.isinf(m.profit_factor) else f"{m.profit_factor:.2f}"
    out.append(_linea("  Profit factor", c.segun_signo(pf, m.profit_factor - 1)))
    out.append(_linea("  Expectativa/op", c.segun_signo(f"{dinero(m.expectativa)} {moneda}", m.expectativa)))
    payoff = "—" if math.isinf(m.payoff) else f"{m.payoff:.2f}"
    out.append(_linea("  Ratio ganancia/perdida", payoff))
    out.append(_linea("  Ganancia media", c(f"{dinero(m.ganancia_media)} {moneda}", Color.VERDE)))
    out.append(_linea("  Perdida media", c(f"{dinero(m.perdida_media)} {moneda}", Color.ROJO)))
    out.append(_linea("  Sharpe (anual.)", f"{m.sharpe:.2f}"))
    out.append(_linea("  Sortino (anual.)", f"{m.sortino:.2f}"))
    out.append("")

    # -- riesgo
    out.append(c("  RIESGO", Color.NEGRITA))
    out.append(c("  " + sep[:ANCHO - 2], Color.GRIS))
    out.append(_linea(
        "  Maxima caida (drawdown)",
        c(f"-{dinero(m.max_drawdown)} {moneda}  ({pct(m.max_drawdown_pct)})", Color.ROJO),
    ))
    out.append(_linea("  Racha ganadora", c(f"{m.racha_ganadora} seguidas", Color.VERDE)))
    out.append(_linea("  Racha perdedora", c(f"{m.racha_perdedora} seguidas", Color.ROJO)))
    out.append(_linea("  Duracion media", duracion(m.duracion_media_seg)))
    if m.mejor:
        out.append(_linea(
            "  Mejor operacion",
            c(f"{m.mejor.symbol} +{dinero(m.mejor.pnl_neto)}", Color.VERDE),
        ))
    if m.peor:
        out.append(_linea(
            "  Peor operacion",
            c(f"{m.peor.symbol} {dinero(m.peor.pnl_neto)}", Color.ROJO),
        ))
    out.append("")

    if detalle:
        out.extend(_seccion_simbolos(m, moneda, c, sep))
        out.extend(_seccion_dias(m, moneda, c, sep))
        out.extend(_seccion_horas(m, c, sep))

    if abiertas:
        out.append(c("  POSICIONES ABIERTAS", Color.NEGRITA))
        out.append(c("  " + sep[:ANCHO - 2], Color.GRIS))
        for p in abiertas:
            etiqueta = "LARGO" if p.direction == "long" else "CORTO"
            out.append(_linea(
                f"  {p.symbol} {etiqueta}",
                f"{p.qty:g} @ {dinero(p.precio_medio)}  desde {p.desde:%d/%m %H:%M}",
            ))
        out.append("")

    if avisos:
        out.append(c("  AVISOS", Color.NEGRITA))
        out.append(c("  " + sep[:ANCHO - 2], Color.GRIS))
        for aviso in avisos:
            out.extend(_envolver(f"! {aviso}", c, Color.AMARILLO))
        out.append("")

    out.append(c(f"  Generado {datetime.now():%d/%m/%Y %H:%M}", Color.GRIS))
    return "\n".join(out)


def _seccion_simbolos(m: Metricas, moneda: str, c: Pintor, sep: str) -> list[str]:
    if len(m.por_simbolo) <= 1:
        return []
    out = [c("  POR SIMBOLO", Color.NEGRITA), c("  " + sep[:ANCHO - 2], Color.GRIS)]
    tope = max((abs(b.pnl) for b in m.por_simbolo), default=1) or 1

    for b in m.por_simbolo[:12]:
        grafico = barra(b.pnl, tope, 18)
        out.append(
            f"  {b.clave:<12} {c.segun_signo(grafico, b.pnl)} "
            f"{c.segun_signo(f'{dinero(b.pnl):>12}', b.pnl)} {moneda:<5} "
            + c(f"{b.operaciones:>4} ops  {pct(b.winrate):>7}", Color.GRIS)
        )
    if len(m.por_simbolo) > 12:
        out.append(c(f"  ... y {len(m.por_simbolo) - 12} simbolos mas", Color.GRIS))
    out.append("")
    return out


def _seccion_dias(m: Metricas, moneda: str, c: Pintor, sep: str) -> list[str]:
    if len(m.por_dia) <= 1:
        return []
    ultimos = m.por_dia[-14:]
    out = [
        c(f"  ULTIMOS {len(ultimos)} DIAS CON OPERACIONES", Color.NEGRITA),
        c("  " + sep[:ANCHO - 2], Color.GRIS),
    ]
    tope = max((abs(b.pnl) for b in ultimos), default=1) or 1

    for b in ultimos:
        fecha = datetime.fromisoformat(b.clave)
        etiqueta = f"{fecha:%d/%m} {DIAS[fecha.weekday()][:3]}"
        out.append(
            f"  {etiqueta:<12} {c.segun_signo(barra(b.pnl, tope, 18), b.pnl)} "
            f"{c.segun_signo(f'{dinero(b.pnl):>12}', b.pnl)} {moneda:<5} "
            + c(f"{b.operaciones:>4} ops", Color.GRIS)
        )
    out.append("")
    return out


def _seccion_horas(m: Metricas, c: Pintor, sep: str) -> list[str]:
    """Reparto del resultado por hora del dia: donde gana y donde pierde el bot."""
    if len(m.por_hora) <= 2:
        return []

    por_hora = {int(b.clave): b for b in m.por_hora}
    tope = max((abs(b.pnl) for b in m.por_hora), default=1) or 1
    out = [c("  RESULTADO POR HORA (UTC)", Color.NEGRITA), c("  " + sep[:ANCHO - 2], Color.GRIS)]

    fila_etiquetas = "  " + "".join(f"{h:<3}" for h in range(0, 24, 2))
    fila_valores = "  "
    for h in range(24):
        b = por_hora.get(h)
        if not b:
            fila_valores += c("·", Color.GRIS)
        else:
            altura = "▁▂▃▄▅▆▇█"[min(7, int(abs(b.pnl) / tope * 7))]
            fila_valores += c.segun_signo(altura, b.pnl)
        fila_valores += " " if h % 2 else ""

    out.append(fila_valores)
    out.append(c(fila_etiquetas, Color.GRIS))
    out.append("")
    return out
