"""Contrato comun de las fuentes de datos.

Una fuente sabe leer operaciones de un sitio concreto (un CSV, una base de
datos, la API de un exchange) y devolverlas normalizadas. Nada mas. Fusionar,
deduplicar y calcular ocurre despues, sobre el resultado combinado.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from ..models import Fill, Trade


@dataclass
class Lote:
    """Lo que devuelve una fuente: ejecuciones sueltas y/o cierres ya hechos."""

    fills: list[Fill] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.fills) + len(self.trades)


class ErrorDeFuente(RuntimeError):
    """La fuente no pudo leerse. Lleva el nombre para poder reportarlo."""

    def __init__(self, fuente: str, mensaje: str):
        self.fuente = fuente
        super().__init__(f"[{fuente}] {mensaje}")


class Fuente(ABC):
    """Base de todas las fuentes."""

    tipo: str = "base"

    def __init__(self, nombre: str, **opciones):
        self.nombre = nombre
        self.opciones = opciones

    @abstractmethod
    def leer(self, desde: datetime | None = None, hasta: datetime | None = None) -> Lote:
        """Devuelve las operaciones de la fuente en el rango pedido.

        El filtro por fecha es una optimizacion: las fuentes remotas deberian
        respetarlo para no bajar de mas, pero el filtrado definitivo lo hace
        Jarvis igualmente, asi que una fuente puede ignorarlo sin romper nada.
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.nombre}>"
