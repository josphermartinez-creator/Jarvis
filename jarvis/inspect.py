"""Diagnostico de un archivo de operaciones.

Responde a la pregunta practica: "tengo este archivo, ¿le sirve a Jarvis?".
Lee las primeras filas, dice que columna reconocio para cada campo, cuales
faltan y si el resultado sera util o no. Sin adivinar nada.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from .sources.iqoption import RESULTADOS_VALIDOS, es_historial_binarias
from .sources.parsing import a_fecha, a_lado, a_numero, mapear_columnas

# Lo minimo para poder reconstruir operaciones a partir de ejecuciones.
IMPRESCINDIBLES_FILL = ("ts", "symbol", "side", "qty", "price")
# Lo minimo si el archivo ya trae operaciones cerradas.
IMPRESCINDIBLES_TRADE = ("symbol", "close_ts")

DESCRIPCIONES = {
    "ts": "fecha y hora de la ejecucion",
    "open_ts": "fecha de apertura",
    "close_ts": "fecha de cierre",
    "symbol": "par o simbolo operado",
    "side": "compra o venta",
    "direction": "largo o corto",
    "qty": "cantidad",
    "price": "precio de ejecucion",
    "entry_price": "precio de entrada",
    "exit_price": "precio de salida",
    "pnl": "resultado de la operacion",
    "fee": "comision",
    "fee_currency": "moneda de la comision",
    "ext_id": "identificador de la operacion",
    # Campos del historial de opciones binarias.
    "timestamp": "fecha y hora de la operacion",
    "par": "par operado",
    "resultado": "win / loss / empate",
    "monto": "importe apostado",
    "ganancia": "resultado en dinero",
    "estrategia": "estrategia que abrio la operacion",
    "balance": "saldo tras la operacion",
    "franja_horaria": "franja de una hora",
    "dia_semana": "dia de la semana",
    "racha_perdidas_momento": "perdidas seguidas tras la operacion",
}


@dataclass
class Diagnostico:
    ruta: Path
    formato: str = ""
    filas: int = 0
    columnas: list[str] = field(default_factory=list)
    detectado: dict[str, str] = field(default_factory=dict)
    faltan: list[str] = field(default_factory=list)
    modo: str = ""
    problemas: list[str] = field(default_factory=list)
    muestra: dict = field(default_factory=dict)

    @property
    def sirve(self) -> bool:
        return self.modo != "" and not self.faltan


def _leer_filas(ruta: Path, limite: int = 200) -> tuple[str, list[dict]]:
    texto = ruta.read_text(encoding="utf-8-sig", errors="replace")
    sufijo = ruta.suffix.lower()

    if sufijo == ".json":
        datos = json.loads(texto)
        if isinstance(datos, dict):
            for clave in ("trades", "operaciones", "data", "result", "list"):
                if isinstance(datos.get(clave), list):
                    datos = datos[clave]
                    break
            else:
                datos = [datos]
        return "json", [d for d in datos[:limite] if isinstance(d, dict)]

    if sufijo in (".jsonl", ".ndjson"):
        filas = []
        for linea in texto.splitlines()[:limite]:
            if linea.strip():
                dato = json.loads(linea)
                if isinstance(dato, dict):
                    filas.append(dato)
        return "jsonl", filas

    muestra = "\n".join(texto.splitlines()[:5])
    try:
        delim = csv.Sniffer().sniff(muestra, delimiters=",;\t|").delimiter
    except csv.Error:
        delim = ","
    lector = csv.DictReader(texto.splitlines(), delimiter=delim)
    nombre = {",": "csv", ";": "csv (;)", "\t": "tsv", "|": "csv (|)"}.get(delim, "csv")
    return nombre, [f for _, f in zip(range(limite), lector)]


def inspeccionar(ruta: Path | str) -> Diagnostico:
    """Analiza un archivo y devuelve que encontro y que le falta."""
    archivo = Path(ruta).expanduser()
    diag = Diagnostico(ruta=archivo)

    if not archivo.exists():
        diag.problemas.append(f"no existe el archivo {archivo}")
        return diag

    try:
        diag.formato, filas = _leer_filas(archivo)
    except (json.JSONDecodeError, UnicodeDecodeError, csv.Error) as e:
        diag.problemas.append(f"no se pudo leer el archivo: {e}")
        return diag

    if not filas:
        diag.problemas.append("el archivo esta vacio o solo tiene la cabecera")
        return diag

    diag.filas = len(filas)
    diag.columnas = list(filas[0].keys())
    diag.muestra = filas[0]

    if es_historial_binarias(diag.columnas):
        return _diagnostico_binarias(diag, filas)

    try:
        diag.detectado = mapear_columnas(diag.columnas)
    except KeyError as e:
        diag.problemas.append(str(e))
        return diag

    tiene = set(diag.detectado)
    cerradas = ({"entry_price", "exit_price"} <= tiene) or (
        "pnl" in tiene and ("close_ts" in tiene or "ts" in tiene)
    )

    if cerradas:
        diag.modo = "operaciones cerradas"
        requeridos = IMPRESCINDIBLES_TRADE
        # Con 'ts' sola nos basta: sirve de apertura y cierre.
        if "ts" in tiene:
            requeridos = tuple(c for c in requeridos if c != "close_ts")
    else:
        diag.modo = "ejecuciones sueltas (se emparejaran por FIFO)"
        requeridos = IMPRESCINDIBLES_FILL

    diag.faltan = [c for c in requeridos if c not in tiene]
    if diag.faltan:
        diag.modo = ""

    diag.problemas.extend(_validar_valores(filas, diag.detectado))
    return diag


def _diagnostico_binarias(diag: Diagnostico, filas: list[dict]) -> Diagnostico:
    """Diagnostico del historial de opciones binarias del bot.

    Este formato no se mide con los campos del spot: aqui lo que hace falta es
    la fecha, el par, el monto apostado, el resultado y la ganancia.
    """
    diag.modo = "opciones binarias (historial del bot)"
    esperadas = {
        "timestamp": "fecha y hora",
        "par": "par operado",
        "resultado": "win / loss / empate",
        "monto": "importe apostado",
        "ganancia": "resultado en dinero",
    }

    presentes = {c.strip().lower() for c in diag.columnas}
    for columna, descripcion in esperadas.items():
        if columna in presentes:
            diag.detectado[columna] = columna
        elif columna == "timestamp" and "fecha" in presentes:
            diag.detectado["timestamp"] = "fecha"
        else:
            diag.faltan.append(columna)

    for opcional in ("estrategia", "balance", "franja_horaria", "dia_semana",
                     "direccion", "racha_perdidas_momento"):
        if opcional in presentes:
            diag.detectado[opcional] = opcional

    if diag.faltan:
        diag.modo = ""
        return diag

    # Los resultados raros no rompen el reporte, pero conviene avisar.
    raros = {
        (f.get("resultado") or "").strip().lower()
        for f in filas
    } - set(RESULTADOS_VALIDOS) - {""}
    if raros:
        diag.problemas.append(
            f"valores de 'resultado' que no reconozco: {', '.join(sorted(raros))}"
        )

    sin_confirmar = sum(
        1 for f in filas if (f.get("resultado") or "").strip().lower() == "desconocido"
    )
    if sin_confirmar:
        diag.problemas.append(
            f"{sin_confirmar} de {len(filas)} operaciones estan como "
            f"'desconocido' (la API no confirmo el resultado): se excluyen del "
            f"calculo para no falsear la efectividad"
        )

    if "estrategia" not in presentes:
        diag.problemas.append(
            "sin columna 'estrategia': no podre desglosar por estrategia"
        )
    if "balance" not in presentes:
        diag.problemas.append(
            "sin columna 'balance': la curva y la maxima caida se calcularan "
            "acumulando las ganancias, sin reflejar depositos ni retiros"
        )

    return diag


def _validar_valores(filas: list[dict], mapa: dict[str, str]) -> list[str]:
    """Comprueba que los valores se puedan interpretar, no solo las cabeceras."""
    problemas: list[str] = []
    revisar = filas[:50]

    for campo in ("ts", "open_ts", "close_ts"):
        if campo not in mapa:
            continue
        for fila in revisar:
            valor = fila.get(mapa[campo])
            if valor in (None, ""):
                continue
            try:
                a_fecha(valor)
            except ValueError:
                problemas.append(
                    f"la columna '{mapa[campo]}' no parece una fecha valida "
                    f"(ejemplo: {valor!r})"
                )
            break

    if "side" in mapa:
        for fila in revisar:
            valor = fila.get(mapa["side"])
            if valor in (None, ""):
                continue
            try:
                a_lado(valor)
            except ValueError:
                problemas.append(
                    f"la columna '{mapa['side']}' no se entiende como compra/venta "
                    f"(ejemplo: {valor!r}); se esperan valores tipo buy/sell, "
                    f"compra/venta, long/short"
                )
            break

    for campo in ("qty", "price", "entry_price", "exit_price", "pnl"):
        if campo not in mapa:
            continue
        columna = mapa[campo]
        valores = [f.get(columna) for f in revisar if f.get(columna) not in (None, "")]
        if valores and all(a_numero(v, float("nan")) != a_numero(v, float("nan")) for v in valores[:5]):
            problemas.append(
                f"la columna '{columna}' no contiene numeros reconocibles "
                f"(ejemplo: {valores[0]!r})"
            )

    if "fee" not in mapa:
        problemas.append(
            "no hay columna de comisiones: el PnL neto sera algo optimista"
        )

    return problemas


def formatear(diag: Diagnostico) -> str:
    """Presenta el diagnostico como texto legible en la terminal."""
    out: list[str] = []
    out.append(f"Archivo:  {diag.ruta}")

    if diag.formato:
        out.append(f"Formato:  {diag.formato}  ·  {diag.filas} filas leidas")
    out.append("")

    if not diag.columnas:
        for p in diag.problemas:
            out.append(f"  ERROR: {p}")
        return "\n".join(out)

    out.append(f"Columnas encontradas ({len(diag.columnas)}):")
    out.append(f"  {', '.join(diag.columnas)}")
    out.append("")

    out.append("Lo que Jarvis reconocio:")
    for campo, columna in sorted(diag.detectado.items()):
        ejemplo = str(diag.muestra.get(columna, ""))[:24]
        descripcion = DESCRIPCIONES.get(campo, campo)
        out.append(f"  OK   {columna:<20} -> {descripcion:<28} ej: {ejemplo}")

    sin_usar = [c for c in diag.columnas if c not in diag.detectado.values()]
    if sin_usar:
        out.append("")
        out.append("Columnas que Jarvis ignora (no pasa nada):")
        out.append(f"  {', '.join(sin_usar)}")

    out.append("")
    if diag.faltan:
        out.append("FALTA lo siguiente para poder generar el reporte:")
        for campo in diag.faltan:
            out.append(f"  --   {campo:<16} {DESCRIPCIONES.get(campo, '')}")
        out.append("")
        out.append("Si la columna existe pero con otro nombre, dilo en jarvis.yaml:")
        out.append("  fuentes:")
        out.append("    mi_bot:")
        out.append("      tipo: archivo")
        out.append(f"      ruta: {diag.ruta}")
        out.append("      columnas:")
        for campo in diag.faltan:
            out.append(f"        {campo}: NOMBRE_DE_TU_COLUMNA")
    else:
        out.append(f"LISTO. El archivo sirve: {diag.modo}.")
        out.append(f"Prueba:  jarvis reporte --fuente {diag.ruta}")

    if diag.problemas:
        out.append("")
        out.append("Avisos:")
        for p in diag.problemas:
            out.append(f"  !    {p}")

    return "\n".join(out)
