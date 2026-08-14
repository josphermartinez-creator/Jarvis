"""Utilidades de formato compartidas por todos los reportes."""

from __future__ import annotations

import re

ANCHO = 64
_CODIGOS_ANSI = re.compile(r"\033\[[0-9;]*m")


def sin_color(texto: str) -> str:
    """Quita los codigos ANSI para poder medir el ancho real del texto."""
    return _CODIGOS_ANSI.sub("", texto)


def dinero(valor: float, decimales: int = 2) -> str:
    """Formatea un importe con separador de miles."""
    return f"{valor:,.{decimales}f}"


def pct(valor: float, decimales: int = 1) -> str:
    return f"{valor:.{decimales}f}%"


def duracion(segundos: float) -> str:
    """Convierte segundos a algo legible: 45s, 12m, 3h 20m, 2d 4h."""
    segundos = int(segundos)
    if segundos < 60:
        return f"{segundos}s"
    if segundos < 3600:
        return f"{segundos // 60}m {segundos % 60}s"
    if segundos < 86400:
        return f"{segundos // 3600}h {(segundos % 3600) // 60}m"
    return f"{segundos // 86400}d {(segundos % 86400) // 3600}h"


def barra(valor: float, tope: float, ancho: int = 20) -> str:
    """Barra horizontal centrada en cero: negativos a la izquierda."""
    if tope <= 0:
        return " " * ancho
    mitad = ancho // 2
    unidades = min(mitad, round(abs(valor) / tope * mitad))
    if valor >= 0:
        return " " * mitad + "█" * unidades + " " * (mitad - unidades)
    return " " * (mitad - unidades) + "█" * unidades + " " * mitad


def esparkline(valores: list[float], ancho: int = 60) -> str:
    """Mini grafico de una linea, para la curva de capital en la terminal."""
    if not valores:
        return ""
    niveles = "▁▂▃▄▅▆▇█"

    if len(valores) > ancho:
        # Se remuestrea tomando puntos equiespaciados: basta para la silueta.
        paso = len(valores) / ancho
        valores = [valores[min(len(valores) - 1, int(i * paso))] for i in range(ancho)]

    minimo, maximo = min(valores), max(valores)
    rango = maximo - minimo
    if rango <= 0:
        return niveles[3] * len(valores)
    return "".join(niveles[min(7, int((v - minimo) / rango * 7))] for v in valores)
