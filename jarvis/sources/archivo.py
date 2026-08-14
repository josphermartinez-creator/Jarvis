"""Fuente de archivo: CSV, TSV, JSON y JSONL.

Es la fuente que funciona con cualquier bot sin tocarle una linea de codigo:
la mayoria ya escribe un log de operaciones. Jarvis detecta solo las columnas y
si el archivo trae ejecuciones sueltas o operaciones ya cerradas.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from functools import lru_cache
from glob import glob
from pathlib import Path
from typing import Any, Iterable

from ..models import Fill, Trade
from .base import ErrorDeFuente, Fuente, Lote
from .parsing import a_direccion, a_fecha, a_lado, a_numero, mapear_columnas


class FuenteArchivo(Fuente):
    """Lee operaciones de un archivo local.

    Opciones de configuracion:
        ruta       : ruta al archivo, admite comodines (``logs/*.csv``).
        columnas   : mapeo manual campo -> columna, si la deteccion falla.
        formato    : ``auto`` (por extension), ``csv``, ``tsv``, ``json``, ``jsonl``.
        delimitador: separador para csv, si no es el habitual.
    """

    tipo = "archivo"

    def leer(self, desde: datetime | None = None, hasta: datetime | None = None) -> Lote:
        rutas = self._resolver_rutas()
        lote = Lote()

        for ruta in rutas:
            for fila in self._filas(ruta):
                try:
                    registro = self._convertir(fila, ruta)
                except (ValueError, KeyError) as e:
                    if self.opciones.get("estricto"):
                        raise ErrorDeFuente(self.nombre, f"{ruta.name}: {e}") from e
                    continue  # una fila corrupta no debe tumbar el reporte entero
                if registro is None:
                    continue
                if isinstance(registro, Fill):
                    lote.fills.append(registro)
                else:
                    lote.trades.append(registro)

        return lote

    # -- lectura ---------------------------------------------------------

    def _resolver_rutas(self) -> list[Path]:
        patron = self.opciones.get("ruta")
        if not patron:
            raise ErrorDeFuente(self.nombre, "falta la opcion 'ruta'")

        ruta = Path(patron).expanduser()
        if any(c in str(ruta) for c in "*?["):
            encontradas = sorted(Path(p) for p in glob(str(ruta), recursive=True))
        else:
            encontradas = [ruta] if ruta.exists() else []

        if not encontradas:
            raise ErrorDeFuente(self.nombre, f"no existe ningun archivo en {patron}")
        return encontradas

    def _formato(self, ruta: Path) -> str:
        formato = self.opciones.get("formato", "auto")
        if formato != "auto":
            return formato
        sufijo = ruta.suffix.lower()
        return {".json": "json", ".jsonl": "jsonl", ".ndjson": "jsonl",
                ".tsv": "tsv"}.get(sufijo, "csv")

    def _filas(self, ruta: Path) -> Iterable[dict[str, Any]]:
        formato = self._formato(ruta)
        texto = ruta.read_text(encoding="utf-8-sig")

        if formato == "json":
            datos = json.loads(texto)
            # Acepta tanto una lista como {"trades": [...]} o {"data": [...]}.
            if isinstance(datos, dict):
                for clave in ("trades", "operaciones", "data", "result", "list"):
                    if isinstance(datos.get(clave), list):
                        datos = datos[clave]
                        break
                else:
                    datos = [datos]
            yield from (d for d in datos if isinstance(d, dict))
            return

        if formato == "jsonl":
            for linea in texto.splitlines():
                linea = linea.strip()
                if linea:
                    dato = json.loads(linea)
                    if isinstance(dato, dict):
                        yield dato
            return

        delimitador = self.opciones.get("delimitador") or ("\t" if formato == "tsv" else None)
        if delimitador is None:
            muestra = "\n".join(texto.splitlines()[:5])
            try:
                delimitador = csv.Sniffer().sniff(muestra, delimiters=",;\t|").delimiter
            except csv.Error:
                delimitador = ","
        yield from csv.DictReader(texto.splitlines(), delimiter=delimitador)

    # -- conversion ------------------------------------------------------

    @lru_cache(maxsize=8)
    def _mapa(self, cabeceras: tuple[str, ...]) -> dict[str, str]:
        """Deteccion de columnas cacheada: se resuelve una vez por archivo."""
        return mapear_columnas(list(cabeceras), self.opciones.get("columnas"))

    def _convertir(self, fila: dict[str, Any], ruta: Path) -> Fill | Trade | None:
        if not any(str(v).strip() for v in fila.values() if v is not None):
            return None  # linea en blanco

        mapa = self._mapa(tuple(fila.keys()))

        def get(campo: str):
            return fila.get(mapa[campo]) if campo in mapa else None

        symbol = get("symbol")
        if not symbol:
            raise KeyError(
                "no encuentro la columna del simbolo; configura "
                "'columnas: {symbol: <tu_columna>}'"
            )

        # Una operacion cerrada se reconoce porque trae precio de entrada y de
        # salida, o bien un PnL junto a las dos fechas.
        tiene_precios = get("entry_price") is not None and get("exit_price") is not None
        tiene_pnl = get("pnl") is not None
        if tiene_precios or (tiene_pnl and get("close_ts") is not None):
            return self._a_trade(get, symbol, ruta)
        return self._a_fill(get, symbol, ruta)

    def _a_trade(self, get, symbol: str, ruta: Path) -> Trade:
        apertura = get("open_ts") or get("ts")
        cierre = get("close_ts") or get("ts")
        if apertura is None or cierre is None:
            raise KeyError("faltan las fechas de apertura y cierre")

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
            open_ts=a_fecha(apertura),
            close_ts=a_fecha(cierre),
            qty=qty,
            entry_price=entrada,
            exit_price=salida,
            pnl=pnl,
            fees=abs(a_numero(get("fee"))),
            source=self.nombre,
            ext_id=str(get("ext_id") or ""),
            meta={"archivo": ruta.name},
        )

    def _a_fill(self, get, symbol: str, ruta: Path) -> Fill:
        ts = get("ts") or get("close_ts") or get("open_ts")
        if ts is None:
            raise KeyError("no encuentro ninguna columna de fecha")
        if get("side") is None:
            raise KeyError("no encuentro la columna de compra/venta")

        return Fill(
            ts=a_fecha(ts),
            symbol=str(symbol),
            side=a_lado(get("side")),
            qty=a_numero(get("qty")),
            price=a_numero(get("price")),
            fee=abs(a_numero(get("fee"))),
            fee_currency=str(get("fee_currency") or ""),
            source=self.nombre,
            ext_id=str(get("ext_id") or ""),
            meta={"archivo": ruta.name},
        )
