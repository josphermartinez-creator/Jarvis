"""Secciones del reporte de terminal propias de opciones binarias."""

from __future__ import annotations

from ..binarias import BloqueBinario, MetricasBinarias
from .formato import ANCHO, Color, Pintor, dinero, linea as _linea, pct


def _titulo(texto: str, c: Pintor) -> list[str]:
    return [c(f"  {texto}", Color.NEGRITA), c("  " + "─" * (ANCHO - 2), Color.GRIS)]


def _tabla(bloques: list[BloqueBinario], c: Pintor, etiqueta_ancho: int = 16) -> list[str]:
    """Tabla comun: operaciones, efectividad, umbral y margen."""
    out = [
        c(
            f"  {'':<{etiqueta_ancho}} {'ops':>5} {'efect':>7} {'umbral':>7} "
            f"{'margen':>8} {'neto':>10}",
            Color.GRIS,
        )
    ]
    for b in bloques:
        if b.pagos:
            margen = f"{b.margen:+.1f}"
            umbral = pct(b.punto_equilibrio)
        else:
            margen = umbral = "—"
        marca = "✓" if b.rentable else "✗"
        out.append(
            f"  {b.clave[:etiqueta_ancho]:<{etiqueta_ancho}} {b.total:>5} "
            f"{pct(b.efectividad):>7} {umbral:>7} "
            + c.segun_signo(f"{margen:>8}", b.margen)
            + c.segun_signo(f"{dinero(b.neto):>10}", b.neto)
            + " "
            + c.segun_signo(marca, b.margen)
        )
    return out


def render(m: MetricasBinarias, moneda: str, c: Pintor) -> list[str]:
    """Bloque completo de binarias, para insertar en el reporte de terminal."""
    if not m.hay_datos:
        return []

    out: list[str] = []

    # -- veredicto: lo primero, porque es la conclusion
    out.extend(_titulo("OPCIONES BINARIAS", c))
    out.append(_linea("  Operaciones", str(m.total)))
    out.append(_linea(
        "  Ganadas / perdidas",
        f"{c(str(m.ganadas), Color.VERDE)} / {c(str(m.perdidas), Color.ROJO)}",
    ))
    if m.empates or m.desconocidas:
        detalle = []
        if m.empates:
            detalle.append(f"{m.empates} empate(s)")
        if m.desconocidas:
            detalle.append(f"{m.desconocidas} sin confirmar")
        out.append(_linea("  Fuera del calculo", ", ".join(detalle)))

    out.append(_linea("  Efectividad", c(pct(m.efectividad), Color.NEGRITA)))
    out.append(_linea("  Pago medio al acertar", pct(m.payout_medio * 100)))
    out.append(_linea(
        "  Punto de equilibrio",
        c(pct(m.punto_equilibrio), Color.AMARILLO),
    ))
    out.append(_linea(
        "  Margen sobre el equilibrio",
        c.segun_signo(f"{m.margen:+.1f} puntos", m.margen),
    ))
    out.append("")
    color_veredicto = Color.VERDE if m.rentable else Color.ROJO
    out.append("  " + c(m.veredicto.upper(), color_veredicto))
    out.append("")

    # -- dinero
    out.extend(_titulo("DINERO", c))
    out.append(_linea("  Invertido en total", f"{dinero(m.invertido)} {moneda}"))
    out.append(_linea("  Monto medio", f"{dinero(m.monto_medio)} {moneda}"))
    out.append(_linea(
        "  Resultado neto",
        c.segun_signo(f"{'+' if m.neto >= 0 else ''}{dinero(m.neto)} {moneda}", m.neto),
    ))
    out.append(_linea("  Retorno sobre lo invertido", c.segun_signo(pct(m.roi), m.roi)))
    out.append(_linea(
        "  Esperanza por operacion",
        c.segun_signo(f"{dinero(m.esperanza_por_operacion)} {moneda}",
                      m.esperanza_por_operacion),
    ))
    out.append(_linea(
        "  Balance",
        f"{dinero(m.balance_inicial)} → {dinero(m.balance_final)} {moneda}",
    ))
    out.append(_linea(
        "  Maxima caida del balance",
        c(f"-{dinero(m.max_caida)} ({pct(m.max_caida_pct)})", Color.ROJO),
    ))
    out.append(_linea("  Racha ganadora", c(f"{m.racha_ganadas} seguidas", Color.VERDE)))
    out.append(_linea("  Racha perdedora", c(f"{m.racha_perdidas} seguidas", Color.ROJO)))
    out.append(_linea("  Dias operados", str(m.dias_operados)))
    out.append("")

    if len(m.por_par) > 1:
        out.extend(_titulo("POR PAR", c))
        out.extend(_tabla(m.por_par[:12], c))
        out.append("")

    if len(m.por_estrategia) > 1:
        out.extend(_titulo("POR ESTRATEGIA", c))
        out.extend(_tabla(m.por_estrategia, c))
        out.append("")

    if len(m.profundidad) > 1:
        out.extend(_titulo("SEGUN PERDIDAS SEGUIDAS PREVIAS", c))
        out.append(c(
            f"  {'previas':<9} {'ops':>5} {'efect':>7} {'monto medio':>13} {'neto':>10}",
            Color.GRIS,
        ))
        for p in m.profundidad:
            out.append(
                f"  {p.perdidas_previas:<9} {p.operaciones:>5} "
                f"{pct(p.efectividad):>7} {dinero(p.monto_medio):>13} "
                + c.segun_signo(f"{dinero(p.neto):>10}", p.neto)
            )
        out.append(c(
            "  Si la efectividad no sube al bajar por la cadena, doblar el monto",
            Color.GRIS,
        ))
        out.append(c("  no mejora las probabilidades: solo agranda la apuesta.", Color.GRIS))
        out.append("")

    if len(m.por_franja) > 2:
        out.extend(_titulo("POR FRANJA HORARIA", c))
        out.extend(_tabla([b for b in m.por_franja if b.total >= 5], c, etiqueta_ancho=12))
        out.append("")

    if len(m.por_dia_semana) > 1:
        out.extend(_titulo("POR DIA DE LA SEMANA", c))
        out.extend(_tabla(m.por_dia_semana, c, etiqueta_ancho=12))
        out.append("")

    return out
