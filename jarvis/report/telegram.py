"""Envio del reporte por Telegram.

Manda un resumen corto de texto y, opcionalmente, el dashboard HTML como
archivo adjunto para verlo completo desde el movil.

Para configurarlo: habla con @BotFather, crea un bot y quedate con el token;
escribele algo a tu bot y saca tu chat_id de
https://api.telegram.org/bot<TOKEN>/getUpdates
"""

from __future__ import annotations

import json
import math
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from ..metrics import Metricas
from .formato import dinero, duracion, pct

API = "https://api.telegram.org"
TIMEOUT = 30


class ErrorTelegram(RuntimeError):
    pass


def _escapar(texto: str) -> str:
    """Escapa los caracteres reservados de MarkdownV2 de Telegram."""
    for c in r"_*[]()~`>#+-=|{}.!":
        texto = texto.replace(c, f"\\{c}")
    return texto


def resumen(m: Metricas, moneda: str = "USDT", periodo: str = "") -> str:
    """Resumen compacto pensado para leerse en la pantalla del movil."""
    if not m.hay_datos:
        titulo = f"*Jarvis* · {_escapar(periodo)}" if periodo else "*Jarvis*"
        return f"{titulo}\n\nSin operaciones cerradas en este periodo\\."

    icono = "🟢" if m.pnl_neto > 0 else "🔴" if m.pnl_neto < 0 else "⚪"
    signo = "+" if m.pnl_neto >= 0 else ""
    pf = "∞" if math.isinf(m.profit_factor) else f"{m.profit_factor:.2f}"

    lineas = [
        f"{icono} *Jarvis* · {_escapar(periodo or 'reporte')}",
        "",
        f"*{_escapar(signo + dinero(m.pnl_neto))} {_escapar(moneda)}*",
        "",
        f"Operaciones: *{m.operaciones}*  \\({m.ganadoras}✅ {m.perdedoras}❌\\)",
        f"Aciertos: *{_escapar(pct(m.winrate))}*",
        f"Profit factor: *{_escapar(pf)}*",
        f"Expectativa: *{_escapar(dinero(m.expectativa))}* por operacion",
        f"Maxima caida: *{_escapar('-' + dinero(m.max_drawdown))}* "
        f"\\({_escapar(pct(m.max_drawdown_pct))}\\)",
        f"Comisiones: {_escapar('-' + dinero(m.comisiones))}",
        f"Duracion media: {_escapar(duracion(m.duracion_media_seg))}",
    ]

    if m.por_simbolo:
        lineas.append("")
        lineas.append("*Por simbolo*")
        for b in m.por_simbolo[:5]:
            marca = "🟢" if b.pnl >= 0 else "🔴"
            s = "+" if b.pnl >= 0 else ""
            lineas.append(
                f"{marca} `{_escapar(b.clave)}`  {_escapar(s + dinero(b.pnl))}  "
                f"\\({b.operaciones} ops\\)"
            )

    if m.mejor and m.peor:
        lineas.append("")
        lineas.append(
            f"Mejor: `{_escapar(m.mejor.symbol)}` "
            f"{_escapar('+' + dinero(m.mejor.pnl_neto))}"
        )
        lineas.append(
            f"Peor: `{_escapar(m.peor.symbol)}` {_escapar(dinero(m.peor.pnl_neto))}"
        )

    return "\n".join(lineas)


def _peticion(token: str, metodo: str, campos: dict, archivo: Path | None = None) -> dict:
    url = f"{API}/bot{token}/{metodo}"

    if archivo is None:
        datos = urllib.parse.urlencode(campos).encode()
        cabeceras = {"Content-Type": "application/x-www-form-urlencoded"}
    else:
        # multipart/form-data a mano: es la unica forma de adjuntar sin librerias.
        frontera = uuid.uuid4().hex
        trozos: list[bytes] = []
        for clave, valor in campos.items():
            trozos.append(
                f"--{frontera}\r\n"
                f'Content-Disposition: form-data; name="{clave}"\r\n\r\n'
                f"{valor}\r\n".encode()
            )
        tipo = mimetypes.guess_type(archivo.name)[0] or "application/octet-stream"
        trozos.append(
            f"--{frontera}\r\n"
            f'Content-Disposition: form-data; name="document"; '
            f'filename="{archivo.name}"\r\n'
            f"Content-Type: {tipo}\r\n\r\n".encode()
        )
        trozos.append(archivo.read_bytes())
        trozos.append(f"\r\n--{frontera}--\r\n".encode())

        datos = b"".join(trozos)
        cabeceras = {"Content-Type": f"multipart/form-data; boundary={frontera}"}

    peticion = urllib.request.Request(url, data=datos, headers=cabeceras, method="POST")
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT) as respuesta:
            return json.loads(respuesta.read().decode())
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode(errors="replace")[:300]
        raise ErrorTelegram(f"Telegram respondio HTTP {e.code}: {cuerpo}") from e
    except urllib.error.URLError as e:
        raise ErrorTelegram(f"no se pudo contactar con Telegram: {e.reason}") from e


def enviar(
    token: str,
    chat_id: str,
    texto: str,
    adjunto: Path | str | None = None,
) -> None:
    """Manda el resumen y, si se indica, adjunta el dashboard HTML."""
    if not token or not chat_id:
        raise ErrorTelegram(
            "faltan el token o el chat_id (ponlos en jarvis.yaml como "
            "${TELEGRAM_BOT_TOKEN} y ${TELEGRAM_CHAT_ID})"
        )

    respuesta = _peticion(
        token,
        "sendMessage",
        {"chat_id": chat_id, "text": texto, "parse_mode": "MarkdownV2"},
    )
    if not respuesta.get("ok"):
        raise ErrorTelegram(f"Telegram rechazo el mensaje: {respuesta.get('description')}")

    if adjunto:
        ruta = Path(adjunto)
        if not ruta.exists():
            raise ErrorTelegram(f"no existe el archivo adjunto {ruta}")
        respuesta = _peticion(
            token,
            "sendDocument",
            {"chat_id": chat_id, "caption": "Dashboard completo"},
            archivo=ruta,
        )
        if not respuesta.get("ok"):
            raise ErrorTelegram(
                f"Telegram rechazo el adjunto: {respuesta.get('description')}"
            )
