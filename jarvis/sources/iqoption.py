"""Fuente para el historial de BOT JPH TRADING (opciones binarias, IQ Option).

El bot escribe ``datos/historial_operaciones.csv`` con una fila por operacion
cerrada. Las opciones binarias no son como el spot: no hay precio de entrada y
salida, hay un monto apostado y un resultado. Esta fuente traduce ese formato al
modelo de Jarvis sin perder lo que es propio de las binarias (resultado,
estrategia, nivel de martingala, balance), que se conserva en ``meta`` para las
metricas especificas de :mod:`jarvis.binarias`.

Columnas del historial:
    timestamp, fecha, hora, dia_semana, franja_horaria, par, estrategia,
    direccion, resultado, monto, ganancia, balance, racha_perdidas_momento
"""

from __future__ import annotations

import csv
from datetime import datetime
from glob import glob
from pathlib import Path

from ..models import Trade
from .base import ErrorDeFuente, Fuente, Lote
from .parsing import a_fecha, a_numero

# Ubicaciones donde el bot deja el historial, en orden de preferencia.
RUTAS_HABITUALES = (
    "datos/historial_operaciones.csv",
    "historial_operaciones.csv",
    "~/BotIFCAuto/datos/historial_operaciones.csv",
    "C:/BotIFCAuto/datos/historial_operaciones.csv",
)

# Columnas que identifican inequivocamente este formato.
FIRMA = {"resultado", "monto", "ganancia"}

RESULTADOS_VALIDOS = ("win", "loss", "empate", "desconocido")


def es_historial_binarias(cabeceras) -> bool:
    """True si las cabeceras corresponden al historial de opciones binarias.

    Se usa para que apuntar Jarvis al CSV del bot funcione sin declarar el tipo.
    """
    normalizadas = {str(c).strip().lower() for c in cabeceras}
    return FIRMA <= normalizadas and ("par" in normalizadas or "symbol" in normalizadas)


def buscar_historial(base: Path | None = None) -> Path | None:
    """Busca el historial del bot en las rutas donde suele estar."""
    for patron in RUTAS_HABITUALES:
        ruta = Path(patron).expanduser()
        if not ruta.is_absolute() and base:
            ruta = base / patron
        if ruta.exists():
            return ruta
    return None


class FuenteIQOption(Fuente):
    """Lee el historial de operaciones binarias del bot.

    Opciones de configuracion:
        ruta   : ruta del CSV. Si se omite, se busca en las rutas habituales.
        incluir: resultados a incluir. Por defecto se excluye ``desconocido``,
                 que son operaciones ejecutadas cuya suerte la API nunca
                 confirmo: contarlas como empate falsearia la efectividad.
    """

    tipo = "iqoption"

    def leer(self, desde: datetime | None = None, hasta: datetime | None = None) -> Lote:
        rutas = self._rutas()
        incluir = self._incluir()
        lote = Lote()

        for ruta in rutas:
            for numero, fila in enumerate(self._filas(ruta), start=2):
                try:
                    operacion = self._a_trade(fila, ruta)
                except (ValueError, KeyError) as e:
                    if self.opciones.get("estricto"):
                        raise ErrorDeFuente(
                            self.nombre, f"{ruta.name} linea {numero}: {e}"
                        ) from e
                    continue
                if operacion is None:
                    continue
                if operacion.meta["resultado"] in incluir:
                    lote.trades.append(operacion)

        return lote

    def _incluir(self) -> set[str]:
        pedido = self.opciones.get("incluir")
        if not pedido:
            return {"win", "loss", "empate"}
        if isinstance(pedido, str):
            pedido = [p.strip() for p in pedido.split(",") if p.strip()]
        desconocidos = set(pedido) - set(RESULTADOS_VALIDOS)
        if desconocidos:
            raise ErrorDeFuente(
                self.nombre,
                f"resultado no valido en 'incluir': {', '.join(sorted(desconocidos))}. "
                f"Validos: {', '.join(RESULTADOS_VALIDOS)}",
            )
        return set(pedido)

    def _rutas(self) -> list[Path]:
        patron = self.opciones.get("ruta")
        if not patron:
            encontrada = buscar_historial()
            if not encontrada:
                raise ErrorDeFuente(
                    self.nombre,
                    "no encuentro historial_operaciones.csv. Indica la ruta con "
                    "'ruta:' en la configuracion; suele estar en la carpeta "
                    "'datos' junto al bot",
                )
            return [encontrada]

        ruta = Path(str(patron)).expanduser()
        if any(c in str(ruta) for c in "*?["):
            encontradas = sorted(Path(p) for p in glob(str(ruta), recursive=True))
        else:
            encontradas = [ruta] if ruta.exists() else []

        if not encontradas:
            raise ErrorDeFuente(self.nombre, f"no existe el historial en {patron}")
        return encontradas

    @staticmethod
    def _filas(ruta: Path):
        texto = ruta.read_text(encoding="utf-8-sig", errors="replace")
        yield from csv.DictReader(texto.splitlines())

    def _a_trade(self, fila: dict, ruta: Path) -> Trade | None:
        par = (fila.get("par") or fila.get("symbol") or "").strip()
        if not par:
            return None  # fila en blanco o cabecera repetida

        resultado = (fila.get("resultado") or "").strip().lower()
        if resultado not in RESULTADOS_VALIDOS:
            raise ValueError(f"resultado desconocido: {resultado!r}")

        momento = fila.get("timestamp") or fila.get("fecha")
        if not momento:
            raise KeyError("la fila no tiene fecha")
        cuando = a_fecha(momento)

        monto = a_numero(fila.get("monto"))
        ganancia = a_numero(fila.get("ganancia"))
        if monto <= 0:
            raise ValueError(f"monto invalido: {fila.get('monto')!r}")

        # BUY apuesta a que sube, SELL a que baja: equivalen a largo y corto.
        crudo = (fila.get("direccion") or "").strip().upper()
        direccion = "short" if crudo in ("SELL", "PUT", "LOWER", "BAJA") else "long"

        # Las binarias se modelan como una unidad comprada al precio del monto
        # y vendida a monto + ganancia. Asi 'retorno_pct' sale exactamente el
        # retorno sobre lo apostado, que es la cifra que importa aqui.
        return Trade(
            symbol=par,
            direction=direccion,
            open_ts=cuando,
            close_ts=cuando,
            qty=1.0,
            entry_price=monto,
            exit_price=monto + ganancia,
            pnl=ganancia,
            fees=0.0,  # en binarias la comision ya esta descontada del payout
            source=self.nombre,
            meta={
                "binarias": True,
                "resultado": resultado,
                "monto": monto,
                "estrategia": (fila.get("estrategia") or "").strip() or "(sin nombre)",
                "balance": a_numero(fila.get("balance")),
                "racha_perdidas": int(a_numero(fila.get("racha_perdidas_momento"))),
                "franja": (fila.get("franja_horaria") or "").strip(),
                "dia_semana": (fila.get("dia_semana") or "").strip(),
                "archivo": ruta.name,
            },
        )
