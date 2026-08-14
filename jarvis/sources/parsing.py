"""Ayudantes para leer datos de bots que escriben cada uno a su manera.

Cada bot nombra las columnas distinto y guarda las fechas en el formato que le
apetece. Esto normaliza ambas cosas para que el usuario no tenga que reescribir
su CSV ni configurar nada en el caso comun.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Nombres que hemos visto en la practica para cada campo. Se comparan en
# minusculas y sin espacios ni guiones bajos.
ALIAS: dict[str, tuple[str, ...]] = {
    "ts": ("ts", "time", "timestamp", "date", "datetime", "fecha", "hora", "closetime",
           "exittime", "closedat", "transacttime", "createdtime"),
    "open_ts": ("opents", "opentime", "entrytime", "fechaapertura", "horaapertura",
                "opened", "openedat", "entrydate", "aperturafecha"),
    "close_ts": ("closets", "closetime", "exittime", "fechacierre", "horacierre",
                 "closed", "closedat", "exitdate", "cierrefecha"),
    "symbol": ("symbol", "simbolo", "par", "pair", "ticker", "instrument", "market",
               "activo", "asset"),
    "side": ("side", "lado", "direction", "direccion", "type", "tipo", "action",
             "operacion", "orderside"),
    "qty": ("qty", "quantity", "cantidad", "amount", "size", "volumen", "volume",
            "lots", "lotes", "executedqty", "filledsize"),
    "price": ("price", "precio", "avgprice", "averageprice", "fillprice",
              "precioejecucion"),
    "entry_price": ("entryprice", "precioentrada", "openprice", "precioapertura",
                    "entry", "entrada", "priceopen"),
    "exit_price": ("exitprice", "preciosalida", "closeprice", "preciocierre",
                   "exit", "salida", "priceclose"),
    "pnl": ("pnl", "profit", "ganancia", "resultado", "realizedpnl", "netprofit",
            "grossprofit", "pl", "profitloss", "closedpnl"),
    "fee": ("fee", "fees", "comision", "comisiones", "commission", "cost", "costo",
            "feecost"),
    "fee_currency": ("feecurrency", "feeasset", "monedacomision", "commissionasset"),
    "ext_id": ("id", "tradeid", "orderid", "ticket", "dealid", "execid", "idorden"),
    "direction": ("direction", "direccion", "posicion", "position", "positionside",
                  "postype"),
}

_PALABRAS_COMPRA = {"buy", "b", "compra", "long", "l", "bid", "0", "in"}
_PALABRAS_VENTA = {"sell", "s", "venta", "short", "sh", "ask", "1", "out"}

_FORMATOS_FECHA = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%m/%d/%Y %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%d.%m.%Y %H:%M:%S",
)


def normalizar_clave(nombre: str) -> str:
    return "".join(c for c in nombre.lower() if c.isalnum())


def mapear_columnas(cabeceras: list[str], manual: dict | None = None) -> dict[str, str]:
    """Deduce que columna del archivo corresponde a cada campo de Jarvis.

    ``manual`` (campo -> nombre de columna) siempre gana sobre la deteccion
    automatica, para los casos raros.
    """
    mapa: dict[str, str] = {}
    normalizadas = {normalizar_clave(h): h for h in cabeceras}

    for campo, alias in ALIAS.items():
        for a in alias:
            if a in normalizadas:
                mapa[campo] = normalizadas[a]
                break

    for campo, columna in (manual or {}).items():
        if columna in cabeceras:
            mapa[campo] = columna
        else:
            raise KeyError(
                f"la columna {columna!r} configurada para {campo!r} no existe. "
                f"Columnas disponibles: {', '.join(cabeceras)}"
            )
    return mapa


def a_fecha(valor, tz: timezone = timezone.utc) -> datetime:
    """Convierte a datetime en UTC desde epoch (s/ms/us) o texto."""
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=tz)

    if isinstance(valor, (int, float)):
        return _desde_epoch(float(valor), tz)

    texto = str(valor).strip()
    if not texto:
        raise ValueError("fecha vacia")

    # Epoch en texto: 10 digitos = segundos, 13 = milisegundos, 16 = microsegundos.
    if texto.replace(".", "", 1).replace("-", "", 1).isdigit():
        return _desde_epoch(float(texto), tz)

    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        parseada = datetime.fromisoformat(texto)
        return parseada if parseada.tzinfo else parseada.replace(tzinfo=tz)
    except ValueError:
        pass

    for fmt in _FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, fmt).replace(tzinfo=tz)
        except ValueError:
            continue

    raise ValueError(f"no se reconoce la fecha {valor!r}")


def _desde_epoch(numero: float, tz: timezone) -> datetime:
    magnitud = abs(numero)
    if magnitud >= 1e16:       # microsegundos
        numero /= 1_000_000
    elif magnitud >= 1e12:     # milisegundos
        numero /= 1000
    return datetime.fromtimestamp(numero, tz=tz)


def a_numero(valor, defecto: float = 0.0) -> float:
    """Convierte a float tolerando separadores de miles, simbolos y vacios."""
    if valor is None or valor == "":
        return defecto
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip().replace("$", "").replace("%", "").replace(" ", "")
    if not texto:
        return defecto

    negativo = texto.startswith("(") and texto.endswith(")")  # contabilidad: (12.34)
    if negativo:
        texto = texto[1:-1]

    # "1.234,56" (europeo) vs "1,234.56" (anglosajon).
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        entero, _, decimal = texto.rpartition(",")
        if len(decimal) == 3 and entero:
            texto = texto.replace(",", "")          # 1,234 -> separador de miles
        else:
            texto = f"{entero.replace(',', '')}.{decimal}"  # 12,34 -> decimal

    try:
        numero = float(texto)
    except ValueError:
        return defecto
    return -numero if negativo else numero


def a_lado(valor) -> str:
    """Normaliza el lado de la operacion a 'buy' o 'sell'."""
    texto = str(valor).strip().lower()
    if texto in _PALABRAS_COMPRA:
        return "buy"
    if texto in _PALABRAS_VENTA:
        return "sell"
    # Cadenas compuestas del estilo "ORDER_SIDE_BUY" o "Cerrar compra".
    if any(p in texto for p in ("buy", "compra", "long")):
        return "buy"
    if any(p in texto for p in ("sell", "venta", "short")):
        return "sell"
    raise ValueError(f"no se reconoce el lado {valor!r}")


def a_direccion(valor) -> str:
    """Normaliza la direccion de una operacion cerrada a 'long' o 'short'."""
    return "long" if a_lado(valor) == "buy" else "short"
