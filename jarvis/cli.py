"""Interfaz de linea de comandos de Jarvis.

    jarvis reporte                    resumen del mes en la terminal
    jarvis reporte --periodo hoy      solo hoy
    jarvis reporte --html r.html      genera el dashboard
    jarvis dashboard                  dashboard en vivo en el navegador
    jarvis telegram                   manda el resumen al movil
    jarvis inspeccionar datos.csv     dice si tu archivo sirve y que le falta
    jarvis init                       crea el archivo de configuracion
    jarvis fuentes                    comprueba que las fuentes responden
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, binarias
from .config import PLANTILLA, Config, buscar_config, cargar
from .merge import fusionar
from .metrics import (
    Metricas,
    calcular,
    comparar,
    filtrar_periodo,
    periodo_anterior,
    rango_periodo,
)
from .sources import crear_fuente
from .sources.base import ErrorDeFuente

PERIODOS_AYUDA = "hoy, ayer, semana, mes, anio, todo, 7d, 3m o AAAA-MM-DD:AAAA-MM-DD"


def _config_para(args) -> Config:
    """Construye la configuracion combinando archivo y argumentos.

    ``--fuente`` permite usar Jarvis sin configuracion ninguna, apuntando
    directamente a un archivo de operaciones.
    """
    if args.fuente:
        config = Config()
        for i, ruta in enumerate(args.fuente):
            nombre = Path(ruta).stem or f"fuente{i}"
            config.fuentes[nombre] = {"tipo": "archivo", "ruta": ruta}
    else:
        config = cargar(args.config)

    if getattr(args, "capital", None):
        config.capital_inicial = args.capital
    if getattr(args, "moneda", None):
        config.moneda = args.moneda

    if not config.fuentes:
        raise SystemExit(
            "No hay ninguna fuente configurada.\n\n"
            "Opciones:\n"
            "  jarvis reporte --fuente operaciones.csv    apunta a un archivo\n"
            "  jarvis init                                crea jarvis.yaml\n"
            "  jarvis inspeccionar operaciones.csv        comprueba tu archivo"
        )
    return config


def _analizar(config: Config, periodo: str):
    """Lee, fusiona y calcula. Devuelve (metricas, operaciones, libro).

    Si el libro trae opciones binarias, ``libro.binarias`` lleva ademas sus
    metricas propias y sus avisos se suman a los de las fuentes.
    """
    fuentes = [crear_fuente(n, c) for n, c in config.fuentes.items()]
    desde, hasta = rango_periodo(periodo)
    libro = fusionar(fuentes, desde, hasta)
    trades = filtrar_periodo(libro.trades, desde, hasta)

    libro.binarias = binarias.calcular(trades)
    if libro.binarias.hay_datos:
        libro.errores.extend(binarias.avisos(libro.binarias))

    return calcular(trades, config.capital_inicial), trades, libro


# -- comandos -------------------------------------------------------------

def cmd_reporte(args) -> int:
    from .report import console

    config = _config_para(args)
    metricas, trades, libro = _analizar(config, args.periodo)

    if args.html:
        from .report import html as reporte_html

        salida = Path(args.html).expanduser()
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text(
            reporte_html.render(
                metricas,
                trades=trades,
                moneda=config.moneda,
                periodo=args.periodo,
                abiertas=libro.abiertas,
                avisos=libro.errores,
                fuentes=libro.fuentes_ok,
                binarias=libro.binarias,
            ),
            encoding="utf-8",
        )
        print(f"Dashboard escrito en {salida}")
        if not args.silencioso:
            print()

    if not args.silencioso:
        color = False if args.sin_color else None
        print(console.render(
            metricas,
            moneda=config.moneda,
            periodo=args.periodo,
            abiertas=libro.abiertas,
            avisos=libro.errores,
            color=color,
            detalle=not args.breve,
            binarias=libro.binarias,
        ))

        if args.comparar:
            _imprimir_comparativa(config, args.periodo, metricas)

    if libro.duplicados:
        print(f"\n({libro.duplicados} registros duplicados descartados al fusionar)")

    return 1 if libro.errores and not metricas.hay_datos else 0


def _imprimir_comparativa(config: Config, periodo: str, actual: Metricas) -> None:
    desde, hasta = rango_periodo(periodo)
    p_desde, p_hasta = periodo_anterior(desde, hasta)
    if not p_desde:
        print("\n(el periodo 'todo' no se puede comparar con el anterior)")
        return

    fuentes = [crear_fuente(n, c) for n, c in config.fuentes.items()]
    libro = fusionar(fuentes, p_desde, p_hasta)
    previo = calcular(filtrar_periodo(libro.trades, p_desde, p_hasta), config.capital_inicial)

    if not previo.hay_datos:
        print("\n(no hay datos del periodo anterior para comparar)")
        return

    dif = comparar(actual, previo)
    print("  FRENTE AL PERIODO ANTERIOR")
    print("  " + "─" * 62)
    for etiqueta, clave, sufijo, decimales in (
        ("PnL neto", "pnl_neto", f" {config.moneda}", 2),
        ("Operaciones", "operaciones", "", 0),
        ("Aciertos", "winrate", " puntos", 1),
        ("Profit factor", "profit_factor", "", 2),
    ):
        valor = dif[clave]
        signo = "+" if valor > 0 else ""
        print(f"  {etiqueta:<24} {signo}{valor:,.{decimales}f}{sufijo}")
    print()


def cmd_dashboard(args) -> int:
    from .web import servir

    config = _config_para(args)
    servir(
        config,
        puerto=args.puerto,
        host=args.host,
        periodo=args.periodo,
        refresco=args.refresco,
        abrir=not args.sin_navegador,
    )
    return 0


def cmd_telegram(args) -> int:
    from .report import telegram as tg

    config = _config_para(args)
    token = args.token or config.telegram.get("token", "")
    chat_id = args.chat_id or config.telegram.get("chat_id", "")

    metricas, trades, libro = _analizar(config, args.periodo)
    if libro.binarias is not None and libro.binarias.hay_datos:
        texto = tg.resumen_binarias(
            libro.binarias, moneda=config.moneda, periodo=args.periodo
        )
    else:
        texto = tg.resumen(metricas, moneda=config.moneda, periodo=args.periodo)

    adjunto = None
    if args.adjuntar:
        from tempfile import mkdtemp

        from .report import html as reporte_html

        adjunto = Path(mkdtemp()) / f"jarvis-{args.periodo}.html"
        adjunto.write_text(
            reporte_html.render(
                metricas,
                trades=trades,
                moneda=config.moneda,
                periodo=args.periodo,
                abiertas=libro.abiertas,
                avisos=libro.errores,
                fuentes=libro.fuentes_ok,
                binarias=libro.binarias,
            ),
            encoding="utf-8",
        )

    try:
        tg.enviar(token, chat_id, texto, adjunto)
    except tg.ErrorTelegram as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Reporte de '{args.periodo}' enviado por Telegram.")
    return 0


def cmd_inspeccionar(args) -> int:
    from .inspect import formatear, inspeccionar

    codigo = 0
    for ruta in args.archivos:
        diag = inspeccionar(ruta)
        print(formatear(diag))
        print()
        if not diag.sirve:
            codigo = 1
    return codigo


def cmd_init(args) -> int:
    destino = Path(args.salida).expanduser()
    if destino.exists() and not args.forzar:
        print(f"Ya existe {destino}. Usa --forzar para sobrescribirlo.", file=sys.stderr)
        return 1

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(PLANTILLA, encoding="utf-8")
    print(f"Configuracion creada en {destino}")
    print("Edita la ruta de tu archivo de operaciones y luego ejecuta: jarvis reporte")
    return 0


def cmd_fuentes(args) -> int:
    """Comprueba que cada fuente responde y cuantas operaciones trae."""
    config = _config_para(args)
    print(f"Configuracion: {config.ruta or 'valores por defecto'}")
    print(f"Capital inicial: {config.capital_inicial:,.2f} {config.moneda}")
    print()

    fallos = 0
    for nombre, ajustes in config.fuentes.items():
        tipo = ajustes.get("tipo", "archivo")
        try:
            fuente = crear_fuente(nombre, ajustes)
            lote = fuente.leer()
        except ErrorDeFuente as e:
            print(f"  FALLO  {nombre:<16} ({tipo})")
            print(f"          {e}")
            fallos += 1
            continue
        except Exception as e:  # noqa: BLE001
            print(f"  FALLO  {nombre:<16} ({tipo})  error inesperado: {e}")
            fallos += 1
            continue

        detalle = []
        if lote.fills:
            detalle.append(f"{len(lote.fills)} ejecuciones")
        if lote.trades:
            detalle.append(f"{len(lote.trades)} operaciones cerradas")
        print(f"  OK     {nombre:<16} ({tipo})  {', '.join(detalle) or 'sin datos'}")

    print()
    print(f"{len(config.fuentes) - fallos} de {len(config.fuentes)} fuentes disponibles.")
    return 1 if fallos else 0


# -- parser ---------------------------------------------------------------

def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jarvis",
        description="Reportes de tu bot de trading.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--version", action="version", version=f"jarvis {__version__}")
    sub = p.add_subparsers(dest="comando")

    def comunes(sp, con_periodo: bool = True) -> None:
        sp.add_argument("-c", "--config", help="ruta del archivo de configuracion")
        sp.add_argument(
            "-f", "--fuente", action="append",
            help="archivo de operaciones; repetible para fusionar varios",
        )
        sp.add_argument("--capital", type=float, help="capital inicial, para el drawdown en %%")
        sp.add_argument("--moneda", help="moneda en la que se expresa el resultado")
        if con_periodo:
            sp.add_argument(
                "-p", "--periodo", default="mes", help=f"periodo a analizar: {PERIODOS_AYUDA}"
            )

    sp = sub.add_parser("reporte", help="resumen en la terminal y/o dashboard HTML")
    comunes(sp)
    sp.add_argument("--html", help="ruta donde escribir el dashboard HTML")
    sp.add_argument("--breve", action="store_true", help="solo las cifras principales")
    sp.add_argument("--comparar", action="store_true", help="comparar con el periodo anterior")
    sp.add_argument("--sin-color", action="store_true", help="salida sin colores")
    sp.add_argument("--silencioso", action="store_true", help="no imprimir nada en la terminal")
    sp.set_defaults(func=cmd_reporte)

    sp = sub.add_parser("dashboard", help="dashboard en vivo en el navegador")
    comunes(sp)
    sp.set_defaults(periodo="mes")
    sp.add_argument("--puerto", type=int, default=8000)
    sp.add_argument("--host", default="127.0.0.1", help="interfaz de escucha")
    sp.add_argument("--refresco", type=int, default=30, help="segundos entre recargas")
    sp.add_argument("--sin-navegador", action="store_true", help="no abrir el navegador")
    sp.set_defaults(func=cmd_dashboard)

    sp = sub.add_parser("telegram", help="enviar el resumen por Telegram")
    comunes(sp)
    sp.add_argument("--token", help="token del bot; mejor por configuracion")
    sp.add_argument("--chat-id", help="identificador del chat de destino")
    sp.add_argument("--adjuntar", action="store_true", help="adjuntar el dashboard HTML")
    sp.set_defaults(func=cmd_telegram)

    sp = sub.add_parser(
        "inspeccionar", help="comprobar si un archivo de operaciones sirve"
    )
    sp.add_argument("archivos", nargs="+", help="archivos a analizar")
    sp.set_defaults(func=cmd_inspeccionar)

    sp = sub.add_parser("init", help="crear el archivo de configuracion")
    sp.add_argument("-o", "--salida", default="jarvis.yaml")
    sp.add_argument("--forzar", action="store_true", help="sobrescribir si ya existe")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("fuentes", help="comprobar que las fuentes responden")
    comunes(sp, con_periodo=False)
    sp.set_defaults(func=cmd_fuentes)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "comando", None):
        # Sin subcomando: si hay configuracion a mano, el reporte es lo que
        # casi siempre se quiere; si no, se muestra la ayuda.
        if buscar_config():
            args = parser.parse_args(["reporte"])
        else:
            parser.print_help()
            return 0

    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except (ErrorDeFuente, FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
