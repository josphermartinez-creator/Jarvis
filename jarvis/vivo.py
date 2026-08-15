"""Estado en vivo del bot, leido de su propio panel.

El historial en CSV solo cuenta el pasado: una fila aparece cuando la operacion
ya cerro. Para saber que esta pasando ahora mismo — si el bot corre, si sigue
conectado, cuanto hay apostado en este momento — hay que preguntarle a el.

BOT JPH TRADING levanta su panel en ``http://127.0.0.1:5000`` y expone
``/api/estado`` con todo su estado interno. Desde la misma PC no pide
contrasena; desde otro equipo de la red hace falta la del panel, que se manda
por HTTP Basic.

Jarvis solo lee. Nunca llama a ``/api/iniciar`` ni a ``/api/detener``: quien
decide si el bot opera eres tu, no el panel de reportes.
"""

from __future__ import annotations

import base64
import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

URL_POR_DEFECTO = "http://127.0.0.1:5000"
TIMEOUT = 4


class BotNoDisponible(RuntimeError):
    """No se pudo hablar con el panel del bot.

    Casi siempre significa que el bot esta cerrado, que es una situacion
    normal y no un error que deba romper el reporte.
    """

    def __init__(self, mensaje: str, url: str = "", apagado: bool = False):
        self.url = url
        self.apagado = apagado
        super().__init__(mensaje)


@dataclass
class ParEnVuelo:
    """Un par y lo que el bot esta haciendo con el ahora mismo."""

    par: str
    senal: str = ""
    bloqueado_hasta: datetime | None = None

    @property
    def bloqueado(self) -> bool:
        if not self.bloqueado_hasta:
            return False
        return self.bloqueado_hasta > datetime.now(timezone.utc)


@dataclass
class EstadoVivo:
    """Instantanea de lo que el bot esta haciendo en este momento."""

    momento: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    corriendo: bool = False
    conectado: bool = False
    modo: str = ""
    error: str = ""

    balance: float = 0.0
    wins: int = 0
    losses: int = 0
    neto: float = 0.0

    perdidas_seguidas: int = 0
    martingala_nivel: int = 0
    martingala_monto: float = 0.0
    exposicion: float = 0.0

    pares: list[ParEnVuelo] = field(default_factory=list)
    pares_operando: list[str] = field(default_factory=list)
    atascados: list[str] = field(default_factory=list)
    operaciones_sesion: list[dict] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    @property
    def es_cuenta_real(self) -> bool:
        return self.modo.upper() not in ("PRACTICE", "PRACTICA", "DEMO", "")

    @property
    def operaciones_sesion_total(self) -> int:
        return self.wins + self.losses

    @property
    def efectividad_sesion(self) -> float:
        decididas = self.wins + self.losses
        return self.wins / decididas * 100 if decididas else 0.0

    @property
    def pares_bloqueados(self) -> list[ParEnVuelo]:
        return [p for p in self.pares if p.bloqueado]

    @property
    def resumen(self) -> str:
        """Una linea que describe el estado, para cabeceras y avisos."""
        if not self.corriendo:
            return "detenido"
        if not self.conectado:
            return "corriendo pero sin conexion con el broker"
        modo = "cuenta REAL" if self.es_cuenta_real else "cuenta de practica"
        return f"operando en {modo}"


def _numero(valor: Any, defecto: float = 0.0) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def _entero(valor: Any, defecto: int = 0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


def _a_momento(marca: Any) -> datetime | None:
    """Los desbloqueos vienen como epoch en segundos."""
    numero = _numero(marca, 0)
    if numero <= 0:
        return None
    try:
        return datetime.fromtimestamp(numero, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def interpretar(datos: dict) -> EstadoVivo:
    """Convierte la respuesta de ``/api/estado`` en un ``EstadoVivo``.

    Tolera que falten claves: el bot evoluciona y un reporte no deberia
    romperse porque una version anadiera o quitara un campo.
    """
    bloqueados = datos.get("pares_bloqueados") or {}
    estados = datos.get("pares_estado") or {}

    pares = []
    for par in sorted(set(estados) | set(bloqueados)):
        detalle = estados.get(par) or {}
        pares.append(
            ParEnVuelo(
                par=par,
                senal=str(detalle.get("senal", "") if isinstance(detalle, dict) else detalle),
                bloqueado_hasta=_a_momento(bloqueados.get(par)),
            )
        )

    atascados = datos.get("watchdog_atascados") or []
    if atascados and isinstance(atascados[0], (list, tuple)):
        # El watchdog los guarda como (par, segundos).
        atascados = [str(p[0]) for p in atascados]

    return EstadoVivo(
        corriendo=bool(datos.get("corriendo")),
        conectado=bool(datos.get("conectado")),
        modo=str(datos.get("modo", "")),
        error=str(datos.get("error", "") or ""),
        balance=_numero(datos.get("balance")),
        wins=_entero(datos.get("wins")),
        losses=_entero(datos.get("losses")),
        neto=_numero(datos.get("neto")),
        perdidas_seguidas=_entero(datos.get("perdidas_seguidas")),
        martingala_nivel=_entero(datos.get("martingala_nivel")),
        martingala_monto=_numero(datos.get("martingala_monto")),
        exposicion=_numero(datos.get("exposicion_en_vuelo")),
        pares=pares,
        pares_operando=[str(p) for p in (datos.get("pares_operando") or [])],
        atascados=[str(p) for p in atascados],
        operaciones_sesion=[o for o in (datos.get("operaciones") or []) if isinstance(o, dict)],
        log=[str(l) for l in (datos.get("log") or [])],
    )


def consultar(url: str = URL_POR_DEFECTO, password: str = "", timeout: int = TIMEOUT) -> EstadoVivo:
    """Pide el estado al panel del bot.

    ``password`` solo hace falta si Jarvis corre en otro equipo de la red y el
    bot tiene el acceso por LAN activado.
    """
    destino = f"{url.rstrip('/')}/api/estado"
    cabeceras = {"Accept": "application/json"}
    if password:
        credenciales = base64.b64encode(f"jarvis:{password}".encode()).decode()
        cabeceras["Authorization"] = f"Basic {credenciales}"

    peticion = urllib.request.Request(destino, headers=cabeceras, method="GET")
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise BotNoDisponible(
                "el panel del bot pide contrasena. Si Jarvis corre en otra PC, "
                "pon la del panel en 'bot.password' de la configuracion",
                destino,
            ) from e
        raise BotNoDisponible(f"el panel respondio HTTP {e.code}", destino) from e
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        # Lo normal cuando el bot no esta abierto. No es un fallo de Jarvis.
        raise BotNoDisponible(
            f"no responde en {url}. Abre BOT JPH TRADING y vuelve a intentarlo",
            destino,
            apagado=True,
        ) from e
    except json.JSONDecodeError as e:
        raise BotNoDisponible(
            f"{url} respondio algo que no es JSON: no parece el panel del bot",
            destino,
        ) from e

    if not isinstance(datos, dict):
        raise BotNoDisponible("la respuesta del panel no tiene el formato esperado", destino)

    return interpretar(datos)


def avisos(estado: EstadoVivo) -> list[str]:
    """Lo que conviene que veas del estado actual, por orden de urgencia."""
    salida: list[str] = []

    if estado.error:
        salida.append(f"El bot reporta un error: {estado.error}")

    if estado.corriendo and not estado.conectado:
        salida.append(
            "El bot esta en marcha pero sin conexion con el broker: no puede operar."
        )

    if estado.atascados:
        salida.append(
            f"El watchdog marco como atascados: {', '.join(estado.atascados)}."
        )

    if estado.corriendo and estado.es_cuenta_real:
        salida.append(f"Operando con dinero real (modo {estado.modo}).")

    if estado.martingala_nivel >= 2:
        salida.append(
            f"Martingala en nivel {estado.martingala_nivel}: la proxima operacion "
            f"seria de {estado.martingala_monto:,.2f}."
        )

    bloqueados = estado.pares_bloqueados
    if bloqueados:
        salida.append(
            f"Pares bloqueados por perdidas seguidas: "
            f"{', '.join(p.par for p in bloqueados)}."
        )

    if estado.exposicion > 0 and estado.balance > 0:
        porcentaje = estado.exposicion / estado.balance * 100
        if porcentaje >= 20:
            salida.append(
                f"Hay {estado.exposicion:,.2f} en juego ahora mismo, "
                f"un {porcentaje:.0f}% del balance."
            )

    return salida
