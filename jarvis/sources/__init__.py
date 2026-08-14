"""Registro de fuentes disponibles."""

from __future__ import annotations

from .archivo import FuenteArchivo
from .base import ErrorDeFuente, Fuente, Lote
from .basedatos import FuenteBaseDatos
from .exchange import FuenteExchange
from .mt5 import FuenteMT5

REGISTRO: dict[str, type[Fuente]] = {
    "archivo": FuenteArchivo,
    "csv": FuenteArchivo,
    "json": FuenteArchivo,
    "basedatos": FuenteBaseDatos,
    "sqlite": FuenteBaseDatos,
    "db": FuenteBaseDatos,
    "exchange": FuenteExchange,
    "binance": FuenteExchange,
    "bybit": FuenteExchange,
    "mt5": FuenteMT5,
    "metatrader": FuenteMT5,
}


def crear_fuente(nombre: str, config: dict) -> Fuente:
    """Instancia una fuente a partir de su bloque de configuracion."""
    config = dict(config)
    tipo = str(config.pop("tipo", "archivo")).lower()

    clase = REGISTRO.get(tipo)
    if clase is None:
        raise ErrorDeFuente(
            nombre, f"tipo de fuente desconocido: {tipo!r}. "
            f"Disponibles: {', '.join(sorted(set(REGISTRO)))}"
        )

    # Los alias que nombran un exchange concreto lo rellenan solos.
    if tipo in ("binance", "bybit"):
        config.setdefault("exchange", tipo)

    return clase(nombre, **config)


__all__ = [
    "ErrorDeFuente",
    "Fuente",
    "FuenteArchivo",
    "FuenteBaseDatos",
    "FuenteExchange",
    "FuenteMT5",
    "Lote",
    "REGISTRO",
    "crear_fuente",
]
