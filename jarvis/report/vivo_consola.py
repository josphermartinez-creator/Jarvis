"""Vista en vivo del bot para la terminal."""

from __future__ import annotations

from ..vivo import EstadoVivo
from .formato import ANCHO, Color, Pintor, dinero, linea as _linea, pct


def render(estado: EstadoVivo, moneda: str, c: Pintor) -> str:
    """Estado actual del bot, en una pantalla."""
    out: list[str] = []

    if estado.error or (estado.corriendo and not estado.conectado):
        punto, color, titulo = "●", Color.ROJO, "BOT CON PROBLEMAS"
    elif estado.corriendo:
        punto, color, titulo = "●", Color.VERDE, "BOT OPERANDO"
    else:
        punto, color, titulo = "○", Color.GRIS, "BOT DETENIDO"

    out.append(c("╭" + "─" * ANCHO + "╮", Color.GRIS))
    cabecera = f"  {punto} {titulo}"
    if estado.modo:
        etiqueta = "DINERO REAL" if estado.es_cuenta_real else estado.modo
        cabecera += f"  ·  {etiqueta}"
    out.append(
        c("│", Color.GRIS) + c(cabecera.ljust(ANCHO), color) + c("│", Color.GRIS)
    )
    out.append(c("╰" + "─" * ANCHO + "╯", Color.GRIS))
    out.append(c(f"  {estado.momento:%d/%m/%Y %H:%M:%S} UTC", Color.GRIS))
    out.append("")

    if estado.error:
        out.append(c(f"  {estado.error}", Color.ROJO))
        out.append("")

    out.append(_linea("  Balance", f"{dinero(estado.balance)} {moneda}"))

    signo = "+" if estado.neto >= 0 else ""
    out.append(_linea(
        "  Sesion de hoy",
        c.segun_signo(f"{signo}{dinero(estado.neto)} {moneda}", estado.neto),
    ))
    out.append(_linea(
        "  Ganadas / perdidas",
        f"{c(str(estado.wins), Color.VERDE)} / {c(str(estado.losses), Color.ROJO)}"
        f"   {pct(estado.efectividad_sesion)}",
    ))

    if estado.exposicion > 0:
        nota = f"{dinero(estado.exposicion)} {moneda}"
        if estado.balance > 0:
            nota += f"  ({estado.exposicion / estado.balance * 100:.0f}% del balance)"
        out.append(_linea("  En juego ahora", c(nota, Color.AMARILLO)))

    if estado.martingala_nivel > 0:
        color_mart = Color.ROJO if estado.martingala_nivel >= 2 else Color.AMARILLO
        out.append(_linea(
            "  Martingala",
            c(f"nivel {estado.martingala_nivel} · "
              f"proxima {dinero(estado.martingala_monto)} {moneda}", color_mart),
        ))
    elif estado.perdidas_seguidas > 0:
        out.append(_linea(
            "  Perdidas seguidas", c(str(estado.perdidas_seguidas), Color.AMARILLO)
        ))

    bloqueados = estado.pares_bloqueados
    if estado.pares_operando:
        out.append("")
        out.append(c("  PARES", Color.NEGRITA))
        out.append(c("  " + "─" * (ANCHO - 2), Color.GRIS))
        nombres_bloqueados = {p.par for p in bloqueados}
        for par in estado.pares_operando:
            detalle = next((p.senal for p in estado.pares if p.par == par), "")
            if par in nombres_bloqueados:
                out.append(f"  {par:<16} " + c("bloqueado", Color.ROJO))
            else:
                out.append(f"  {par:<16} " + c(detalle or "-", Color.GRIS))

    if estado.atascados:
        out.append("")
        out.append(c(f"  Atascados: {', '.join(estado.atascados)}", Color.ROJO))

    if estado.log:
        out.append("")
        out.append(c("  ULTIMO LOG", Color.NEGRITA))
        out.append(c("  " + "─" * (ANCHO - 2), Color.GRIS))
        for entrada in estado.log[:8]:
            recortada = entrada if len(entrada) <= ANCHO - 4 else entrada[:ANCHO - 7] + "..."
            out.append(c(f"  {recortada}", Color.GRIS))

    return "\n".join(out)
