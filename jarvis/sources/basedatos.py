"""Fuente de base de datos: SQLite de serie, PostgreSQL/MySQL si hay driver.

Muchos bots guardan sus operaciones en una tabla en vez de un CSV. Esta fuente
lanza una consulta y normaliza las filas igual que la fuente de archivo, asi
que tambien detecta sola los nombres de las columnas.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import Fill, Trade
from .base import ErrorDeFuente, Fuente, Lote
from .parsing import a_direccion, a_fecha, a_lado, a_numero, mapear_columnas


class FuenteBaseDatos(Fuente):
    """Lee operaciones de una base de datos.

    Opciones de configuracion:
        ruta / dsn : archivo SQLite, o cadena de conexion para otros motores.
        motor      : ``sqlite`` (por defecto), ``postgres`` o ``mysql``.
        tabla      : nombre de la tabla, si no se da ``consulta``.
        consulta   : SQL propio. Manda sobre ``tabla``.
        columnas   : mapeo manual campo -> columna.
    """

    tipo = "basedatos"

    def leer(self, desde: datetime | None = None, hasta: datetime | None = None) -> Lote:
        filas = self._consultar()
        lote = Lote()

        if not filas:
            return lote

        mapa = mapear_columnas(list(filas[0].keys()), self.opciones.get("columnas"))
        for fila in filas:
            try:
                registro = self._convertir(fila, mapa)
            except (ValueError, KeyError) as e:
                if self.opciones.get("estricto"):
                    raise ErrorDeFuente(self.nombre, str(e)) from e
                continue
            if isinstance(registro, Fill):
                lote.fills.append(registro)
            else:
                lote.trades.append(registro)

        return lote

    # -- acceso ----------------------------------------------------------

    def _sql(self) -> str:
        consulta = self.opciones.get("consulta")
        if consulta:
            return consulta
        tabla = self.opciones.get("tabla")
        if not tabla:
            raise ErrorDeFuente(self.nombre, "hace falta 'tabla' o 'consulta'")
        # El nombre de tabla viene del archivo de configuracion del propio
        # usuario, pero se valida igual para que un valor raro falle claro en
        # lugar de acabar concatenado en el SQL.
        if not all(c.isalnum() or c in "_." for c in tabla):
            raise ErrorDeFuente(self.nombre, f"nombre de tabla invalido: {tabla!r}")
        return f"SELECT * FROM {tabla}"

    def _consultar(self) -> list[dict[str, Any]]:
        motor = self.opciones.get("motor", "sqlite").lower()
        sql = self._sql()

        if motor == "sqlite":
            ruta = self.opciones.get("ruta") or self.opciones.get("dsn")
            if not ruta:
                raise ErrorDeFuente(self.nombre, "falta la opcion 'ruta' del archivo SQLite")
            archivo = Path(str(ruta)).expanduser()
            if not archivo.exists():
                raise ErrorDeFuente(self.nombre, f"no existe la base de datos {archivo}")
            # Solo lectura: Jarvis nunca debe poder escribir en la base del bot.
            conexion = sqlite3.connect(f"file:{archivo}?mode=ro", uri=True)
            try:
                conexion.row_factory = sqlite3.Row
                return [dict(f) for f in conexion.execute(sql).fetchall()]
            except sqlite3.Error as e:
                raise ErrorDeFuente(self.nombre, f"error de SQLite: {e}") from e
            finally:
                conexion.close()

        if motor in ("postgres", "postgresql"):
            return self._consultar_dbapi("psycopg2", sql, "pip install psycopg2-binary")
        if motor == "mysql":
            return self._consultar_dbapi("pymysql", sql, "pip install pymysql")

        raise ErrorDeFuente(self.nombre, f"motor no soportado: {motor}")

    def _consultar_dbapi(self, modulo: str, sql: str, ayuda: str) -> list[dict[str, Any]]:
        import importlib

        try:
            driver = importlib.import_module(modulo)
        except ImportError as e:
            raise ErrorDeFuente(self.nombre, f"falta el driver {modulo} ({ayuda})") from e

        dsn = self.opciones.get("dsn")
        if not dsn:
            raise ErrorDeFuente(self.nombre, "falta la opcion 'dsn' de conexion")

        conexion = driver.connect(dsn) if modulo == "psycopg2" else driver.connect(**_dsn_a_dict(dsn))
        try:
            cursor = conexion.cursor()
            cursor.execute(sql)
            nombres = [d[0] for d in cursor.description]
            return [dict(zip(nombres, fila)) for fila in cursor.fetchall()]
        finally:
            conexion.close()

    # -- conversion ------------------------------------------------------

    def _convertir(self, fila: dict[str, Any], mapa: dict[str, str]) -> Fill | Trade:
        def get(campo: str):
            return fila.get(mapa[campo]) if campo in mapa else None

        symbol = get("symbol")
        if not symbol:
            raise KeyError("no encuentro la columna del simbolo")

        tiene_precios = get("entry_price") is not None and get("exit_price") is not None
        if tiene_precios or (get("pnl") is not None and get("close_ts") is not None):
            entrada = a_numero(get("entry_price"))
            salida = a_numero(get("exit_price"))
            qty = a_numero(get("qty"), 1.0) or 1.0
            crudo_dir = get("direction") or get("side")
            direccion = a_direccion(crudo_dir) if crudo_dir else "long"

            if get("pnl") is not None:
                pnl = a_numero(get("pnl"))
            elif direccion == "long":
                pnl = (salida - entrada) * qty
            else:
                pnl = (entrada - salida) * qty

            return Trade(
                symbol=str(symbol),
                direction=direccion,
                open_ts=a_fecha(get("open_ts") or get("ts")),
                close_ts=a_fecha(get("close_ts") or get("ts")),
                qty=qty,
                entry_price=entrada,
                exit_price=salida,
                pnl=pnl,
                fees=abs(a_numero(get("fee"))),
                source=self.nombre,
                ext_id=str(get("ext_id") or ""),
            )

        return Fill(
            ts=a_fecha(get("ts") or get("close_ts")),
            symbol=str(symbol),
            side=a_lado(get("side")),
            qty=a_numero(get("qty")),
            price=a_numero(get("price")),
            fee=abs(a_numero(get("fee"))),
            fee_currency=str(get("fee_currency") or ""),
            source=self.nombre,
            ext_id=str(get("ext_id") or ""),
        )


def _dsn_a_dict(dsn: str) -> dict[str, Any]:
    """Convierte ``mysql://usuario:clave@host:puerto/base`` a kwargs de pymysql."""
    from urllib.parse import urlparse

    partes = urlparse(dsn)
    conf: dict[str, Any] = {}
    if partes.hostname:
        conf["host"] = partes.hostname
    if partes.port:
        conf["port"] = partes.port
    if partes.username:
        conf["user"] = partes.username
    if partes.password:
        conf["password"] = partes.password
    if partes.path.lstrip("/"):
        conf["database"] = partes.path.lstrip("/")
    return conf
