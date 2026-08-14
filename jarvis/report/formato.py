"""Utilidades de formato compartidas por todos los reportes."""

from __future__ import annotations

import os
import re
import sys

ANCHO = 64
_CODIGOS_ANSI = re.compile(r"\033\[[0-9;]*m")


def sin_color(texto: str) -> str:
    """Quita los codigos ANSI para poder medir el ancho real del texto."""
    return _CODIGOS_ANSI.sub("", texto)


class Color:
    VERDE = "\033[32m"
    ROJO = "\033[31m"
    AMARILLO = "\033[33m"
    GRIS = "\033[90m"
    NEGRITA = "\033[1m"
    FIN = "\033[0m"


def color_activo(forzar: bool | None = None) -> bool:
    """Decide si pintar: solo en terminal y si NO_COLOR no lo prohibe."""
    if forzar is not None:
        return forzar
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


class Pintor:
    """Aplica color solo si la terminal lo admite."""

    def __init__(self, activo: bool):
        self.activo = activo

    def __call__(self, texto: str, color: str) -> str:
        return f"{color}{texto}{Color.FIN}" if self.activo else texto

    def segun_signo(self, texto: str, valor: float) -> str:
        if valor > 0:
            return self(texto, Color.VERDE)
        if valor < 0:
            return self(texto, Color.ROJO)
        return self(texto, Color.GRIS)


def linea(izq: str, der: str, ancho: int = ANCHO) -> str:
    """Une etiqueta y valor separados por puntos, ignorando codigos de color."""
    visible = len(sin_color(izq)) + len(sin_color(der))
    relleno = max(1, ancho - visible - 2)
    return f"{izq} {'.' * relleno} {der}"


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
