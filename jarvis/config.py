"""Carga de la configuracion de Jarvis (``jarvis.yaml``).

Si no hay PyYAML instalado se usa un lector minimo incluido aqui, suficiente
para el formato del archivo de ejemplo. Asi Jarvis sigue sin dependencias
obligatorias.

Los valores admiten ``${VARIABLE}`` para leer del entorno, que es como deben
manejarse las claves de API: nunca escritas en el archivo.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NOMBRES_POR_DEFECTO = ("jarvis.yaml", "jarvis.yml", ".jarvis.yaml")

PLANTILLA = """\
# Configuracion de Jarvis. Cada bloque de 'fuentes' es un origen de datos;
# se leen todos y se fusionan en un unico libro de operaciones.

capital_inicial: 1000        # para calcular drawdown y rentabilidad en %
moneda: USDT
zona_horaria: UTC

fuentes:

  # 1) El log que escribe tu bot. Jarvis detecta las columnas solo.
  mi_bot:
    tipo: archivo
    ruta: ~/mi-bot/operaciones.csv

  # 2) Varios archivos a la vez (admite comodines).
  # historico:
  #   tipo: archivo
  #   ruta: ~/mi-bot/logs/*.csv

  # 3) La base de datos del bot.
  # base:
  #   tipo: sqlite
  #   ruta: ~/mi-bot/bot.db
  #   tabla: trades

  # 4) El exchange, como fuente de verdad. Usa claves de SOLO LECTURA.
  # binance:
  #   tipo: binance
  #   api_key: ${BINANCE_API_KEY}
  #   api_secret: ${BINANCE_API_SECRET}
  #   simbolos: [BTCUSDT, ETHUSDT]

# Envio automatico por Telegram (opcional).
telegram:
  token: ${TELEGRAM_BOT_TOKEN}
  chat_id: ${TELEGRAM_CHAT_ID}
"""


@dataclass
class Config:
    capital_inicial: float = 0.0
    moneda: str = "USDT"
    zona_horaria: str = "UTC"
    fuentes: dict[str, dict] = field(default_factory=dict)
    telegram: dict[str, str] = field(default_factory=dict)
    ruta: Path | None = None

    @classmethod
    def desde_dict(cls, datos: dict[str, Any], ruta: Path | None = None) -> "Config":
        datos = _expandir(datos)
        return cls(
            capital_inicial=float(datos.get("capital_inicial", 0) or 0),
            moneda=str(datos.get("moneda", "USDT")),
            zona_horaria=str(datos.get("zona_horaria", "UTC")),
            fuentes=dict(datos.get("fuentes") or {}),
            telegram=dict(datos.get("telegram") or {}),
            ruta=ruta,
        )


def buscar_config(inicio: Path | None = None) -> Path | None:
    """Busca el archivo de configuracion desde el directorio actual hacia arriba."""
    directorio = (inicio or Path.cwd()).resolve()
    for carpeta in [directorio, *directorio.parents]:
        for nombre in NOMBRES_POR_DEFECTO:
            candidato = carpeta / nombre
            if candidato.exists():
                return candidato
    casa = Path.home() / ".config" / "jarvis" / "jarvis.yaml"
    return casa if casa.exists() else None


def cargar(ruta: Path | str | None = None) -> Config:
    """Carga la configuracion. Sin archivo devuelve valores por defecto."""
    archivo = Path(ruta).expanduser() if ruta else buscar_config()
    if not archivo or not archivo.exists():
        if ruta:
            raise FileNotFoundError(f"no existe el archivo de configuracion {ruta}")
        return Config()

    texto = archivo.read_text(encoding="utf-8")
    try:
        import yaml

        datos = yaml.safe_load(texto) or {}
    except ImportError:
        datos = _yaml_minimo(texto)

    if not isinstance(datos, dict):
        raise ValueError(f"{archivo} no contiene un mapa de configuracion valido")
    return Config.desde_dict(datos, archivo)


def _expandir(valor: Any) -> Any:
    """Sustituye ``${VARIABLE}`` por el valor del entorno, recursivamente."""
    if isinstance(valor, dict):
        return {k: _expandir(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_expandir(v) for v in valor]
    if isinstance(valor, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), valor)
    return valor


# -- lector YAML de emergencia -------------------------------------------

def _yaml_minimo(texto: str) -> dict:
    """Lector para el subconjunto de YAML que usa la plantilla de Jarvis.

    Soporta mapas anidados por indentacion, listas en linea (``[a, b]``) y
    escalares. No pretende ser YAML completo: si necesitas mas, instala PyYAML
    (``pip install pyyaml``) y se usara ese.
    """
    raiz: dict = {}
    pila: list[tuple[int, dict]] = [(-1, raiz)]

    for cruda in texto.splitlines():
        linea = cruda.split("#", 1)[0].rstrip() if not _dentro_de_comillas(cruda) else cruda.rstrip()
        if not linea.strip():
            continue

        sangria = len(linea) - len(linea.lstrip())
        contenido = linea.strip()
        if ":" not in contenido:
            continue

        clave, _, resto = contenido.partition(":")
        clave, resto = clave.strip(), resto.strip()

        while pila and sangria <= pila[-1][0]:
            pila.pop()
        if not pila:
            pila = [(-1, raiz)]
        padre = pila[-1][1]

        if resto:
            padre[clave] = _escalar(resto)
        else:
            nuevo: dict = {}
            padre[clave] = nuevo
            pila.append((sangria, nuevo))

    return raiz


def _dentro_de_comillas(linea: str) -> bool:
    """True si hay una almohadilla dentro de comillas (no es un comentario)."""
    pos = linea.find("#")
    if pos < 0:
        return False
    return linea[:pos].count('"') % 2 == 1 or linea[:pos].count("'") % 2 == 1


def _escalar(texto: str) -> Any:
    texto = texto.strip()
    if texto.startswith("[") and texto.endswith("]"):
        interior = texto[1:-1].strip()
        return [_escalar(p) for p in interior.split(",")] if interior else []
    if len(texto) >= 2 and texto[0] == texto[-1] and texto[0] in "\"'":
        return texto[1:-1]
    bajo = texto.lower()
    if bajo in ("true", "si", "yes"):
        return True
    if bajo in ("false", "no"):
        return False
    if bajo in ("null", "none", "~", ""):
        return None
    try:
        return int(texto)
    except ValueError:
        pass
    try:
        return float(texto)
    except ValueError:
        return texto
