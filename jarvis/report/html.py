"""Dashboard HTML: un solo archivo, sin internet, sin librerias.

Las graficas son SVG generado a mano. Eso significa que el archivo se abre en
cualquier navegador, se puede mandar por correo o Telegram, y funciona igual
dentro de diez anios sin depender de ningun CDN.

Se adapta al tema claro u oscuro del sistema.
"""

from __future__ import annotations

import html
import math
from datetime import datetime

from ..matching import PosicionAbierta
from ..metrics import Bloque, Metricas
from ..models import Trade
from .formato import dinero, duracion, pct

DIAS = ("Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo")

CSS = """
:root {
  --fondo: #f7f8fa; --panel: #ffffff; --borde: #e4e7ec;
  --texto: #1a1d23; --suave: #6b7280; --tenue: #9ca3af;
  --verde: #0f9960; --verde-claro: #d7f0e4;
  --rojo: #d1453b; --rojo-claro: #fbe0de;
  --acento: #3b6ef5; --rejilla: #eef0f4;
  --sombra: 0 1px 2px rgba(16,24,40,.05), 0 1px 3px rgba(16,24,40,.06);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --fondo: #0f1115; --panel: #171a21; --borde: #262b36;
    --texto: #e8eaed; --suave: #9aa2b1; --tenue: #6b7280;
    --verde: #34d399; --verde-claro: #10291f;
    --rojo: #f87171; --rojo-claro: #2b1618;
    --acento: #6d8dfa; --rejilla: #222732;
    --sombra: 0 1px 2px rgba(0,0,0,.3);
  }
}
:root[data-theme="dark"] {
  --fondo: #0f1115; --panel: #171a21; --borde: #262b36;
  --texto: #e8eaed; --suave: #9aa2b1; --tenue: #6b7280;
  --verde: #34d399; --verde-claro: #10291f;
  --rojo: #f87171; --rojo-claro: #2b1618;
  --acento: #6d8dfa; --rejilla: #222732;
  --sombra: 0 1px 2px rgba(0,0,0,.3);
}

* { box-sizing: border-box; }
body {
  margin: 0; padding: 24px 20px 48px;
  background: var(--fondo); color: var(--texto);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.envoltorio { max-width: 1120px; margin: 0 auto; }

header { margin-bottom: 24px; }
h1 { font-size: 20px; font-weight: 650; margin: 0 0 4px; letter-spacing: -.01em; }
.subtitulo { color: var(--suave); font-size: 13px; }

.resultado { margin: 24px 0 28px; }
.resultado .cifra {
  font-size: 42px; font-weight: 680; letter-spacing: -.025em;
  font-variant-numeric: tabular-nums; line-height: 1.1;
}
.resultado .etiqueta {
  font-size: 12px; color: var(--suave); text-transform: uppercase;
  letter-spacing: .06em; margin-bottom: 2px;
}

.rejilla {
  display: grid; gap: 12px; margin-bottom: 20px;
  grid-template-columns: repeat(auto-fit, minmax(158px, 1fr));
}
.tarjeta {
  background: var(--panel); border: 1px solid var(--borde);
  border-radius: 10px; padding: 13px 15px; box-shadow: var(--sombra);
}
.tarjeta .k {
  font-size: 11px; color: var(--suave); text-transform: uppercase;
  letter-spacing: .05em; margin-bottom: 5px; white-space: nowrap;
}
.tarjeta .v {
  font-size: 21px; font-weight: 620; font-variant-numeric: tabular-nums;
  letter-spacing: -.015em;
}
.tarjeta .n { font-size: 11.5px; color: var(--tenue); margin-top: 3px; }

.panel {
  background: var(--panel); border: 1px solid var(--borde);
  border-radius: 12px; padding: 18px 20px; margin-bottom: 16px;
  box-shadow: var(--sombra); overflow: hidden;
}
.panel h2 {
  font-size: 13px; font-weight: 620; margin: 0 0 16px;
  text-transform: uppercase; letter-spacing: .05em; color: var(--suave);
}
.dos-columnas { display: grid; gap: 16px; grid-template-columns: 1fr 1fr; }
@media (max-width: 820px) { .dos-columnas { grid-template-columns: 1fr; } }

.pos { color: var(--verde); }
.neg { color: var(--rojo); }
.gris { color: var(--suave); }

svg { display: block; width: 100%; height: auto; overflow: visible; }
.rejilla-linea { stroke: var(--rejilla); stroke-width: 1; }
.eje { fill: var(--tenue); font-size: 10px; font-variant-numeric: tabular-nums; }

.desplazable { overflow-x: auto; margin: 0 -20px; padding: 0 20px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: right; padding: 7px 10px; color: var(--suave);
  font-weight: 550; font-size: 11px; text-transform: uppercase;
  letter-spacing: .04em; border-bottom: 1px solid var(--borde);
  white-space: nowrap;
}
th:first-child, td:first-child { text-align: left; }
td {
  padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--rejilla);
  font-variant-numeric: tabular-nums; white-space: nowrap;
}
tbody tr:last-child td { border-bottom: none; }
.simbolo { font-weight: 560; }

.medidor {
  display: inline-block; height: 6px; border-radius: 3px;
  background: var(--acento); min-width: 2px; vertical-align: middle;
}
.pastilla {
  display: inline-block; padding: 1px 7px; border-radius: 4px;
  font-size: 11px; font-weight: 560;
}
.pastilla.larga { background: var(--verde-claro); color: var(--verde); }
.pastilla.corta { background: var(--rojo-claro); color: var(--rojo); }

.aviso {
  background: var(--rojo-claro); border: 1px solid var(--rojo);
  border-radius: 10px; padding: 13px 16px; margin-bottom: 16px;
  font-size: 13px; color: var(--rojo); line-height: 1.5;
}
.aviso-titulo { font-weight: 620; margin-bottom: 6px; }
.aviso ul { margin: 0; padding-left: 20px; }
.aviso li { margin-bottom: 4px; }
.aviso li:last-child { margin-bottom: 0; }
.vacio { color: var(--suave); text-align: center; padding: 36px 0; }
footer {
  margin-top: 26px; color: var(--tenue); font-size: 12px; text-align: center;
}
"""


def _e(texto) -> str:
    return html.escape(str(texto))


def _clase(valor: float) -> str:
    return "pos" if valor > 0 else "neg" if valor < 0 else "gris"


def _firmado(valor: float, moneda: str = "") -> str:
    signo = "+" if valor > 0 else ""
    sufijo = f" {moneda}" if moneda else ""
    return f"{signo}{dinero(valor)}{sufijo}"


# -- graficas -------------------------------------------------------------

def _curva_equity(m: Metricas, moneda: str) -> str:
    """Curva de capital como area rellena, con la maxima caida marcada."""
    puntos = m.equity
    if len(puntos) < 2:
        return '<p class="vacio">Hacen falta al menos dos operaciones.</p>'

    an, al = 1000, 260
    izq, der, arr, aba = 62, 12, 14, 26
    ancho, alto = an - izq - der, al - arr - aba

    valores = [p.equity for p in puntos]
    minimo, maximo = min(valores), max(valores)
    margen = (maximo - minimo) * 0.12 or max(1.0, abs(maximo) * 0.02)
    minimo, maximo = minimo - margen, maximo + margen
    rango = maximo - minimo

    def x(i: int) -> float:
        return izq + i * ancho / (len(valores) - 1)

    def y(v: float) -> float:
        return arr + (maximo - v) * alto / rango

    linea = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(valores))
    area = f"{izq},{arr + alto} {linea} {izq + ancho},{arr + alto}"
    sube = valores[-1] >= valores[0]
    trazo = "var(--verde)" if sube else "var(--rojo)"

    partes = [f'<svg viewBox="0 0 {an} {al}" role="img" aria-label="Curva de capital">']
    partes.append(
        f'<defs><linearGradient id="deg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{trazo}" stop-opacity=".22"/>'
        f'<stop offset="100%" stop-color="{trazo}" stop-opacity="0"/>'
        f"</linearGradient></defs>"
    )

    # Rejilla horizontal con las referencias de capital.
    for i in range(5):
        valor = maximo - rango * i / 4
        py = arr + alto * i / 4
        partes.append(
            f'<line class="rejilla-linea" x1="{izq}" y1="{py:.1f}" '
            f'x2="{izq + ancho}" y2="{py:.1f}"/>'
        )
        partes.append(
            f'<text class="eje" x="{izq - 8}" y="{py + 3.5:.1f}" '
            f'text-anchor="end">{dinero(valor, 0)}</text>'
        )

    partes.append(f'<polygon points="{area}" fill="url(#deg)"/>')
    partes.append(
        f'<polyline points="{linea}" fill="none" stroke="{trazo}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
    )

    # Marca del punto de maxima caida, que es el dato que mas duele y mas importa.
    if m.max_drawdown > 0:
        i_peor = max(range(len(puntos)), key=lambda i: puntos[i].drawdown)
        partes.append(
            f'<circle cx="{x(i_peor):.1f}" cy="{y(valores[i_peor]):.1f}" r="4" '
            f'fill="var(--rojo)" stroke="var(--panel)" stroke-width="2"/>'
        )
        ancla = "start" if i_peor < len(valores) / 2 else "end"
        desvio = 9 if ancla == "start" else -9
        partes.append(
            f'<text class="eje" x="{x(i_peor) + desvio:.1f}" '
            f'y="{y(valores[i_peor]) + 18:.1f}" text-anchor="{ancla}" '
            f'fill="var(--rojo)">caida maxima {pct(m.max_drawdown_pct)}</text>'
        )

    for i, etiqueta in ((0, puntos[0].ts), (len(valores) - 1, puntos[-1].ts)):
        ancla = "start" if i == 0 else "end"
        partes.append(
            f'<text class="eje" x="{x(i):.1f}" y="{al - 8}" '
            f'text-anchor="{ancla}">{etiqueta:%d/%m/%y}</text>'
        )

    partes.append("</svg>")
    return "".join(partes)


def _barras_diarias(bloques: list[Bloque], moneda: str) -> str:
    """PnL por dia: barras verdes arriba, rojas abajo, cero en el medio."""
    if not bloques:
        return '<p class="vacio">Sin datos diarios.</p>'

    bloques = bloques[-45:]
    an, al = 1000, 200
    izq, der, arr, aba = 62, 12, 12, 28
    ancho, alto = an - izq - der, al - arr - aba

    tope = max((abs(b.pnl) for b in bloques), default=1) or 1
    cero = arr + alto / 2
    paso = ancho / len(bloques)
    grosor = max(2.0, min(26.0, paso * 0.68))

    partes = [f'<svg viewBox="0 0 {an} {al}" role="img" aria-label="Resultado por dia">']
    for i in range(3):
        valor = tope - tope * i
        py = arr + alto * i / 2
        partes.append(
            f'<line class="rejilla-linea" x1="{izq}" y1="{py:.1f}" '
            f'x2="{izq + ancho}" y2="{py:.1f}"/>'
        )
        partes.append(
            f'<text class="eje" x="{izq - 8}" y="{py + 3.5:.1f}" '
            f'text-anchor="end">{_firmado(valor) if valor else "0"}</text>'
        )

    for i, b in enumerate(bloques):
        cx = izq + paso * (i + 0.5)
        altura = abs(b.pnl) / tope * (alto / 2)
        py = cero - altura if b.pnl >= 0 else cero
        color = "var(--verde)" if b.pnl >= 0 else "var(--rojo)"
        titulo = f"{b.clave}: {_firmado(b.pnl, moneda)} en {b.operaciones} ops"
        partes.append(
            f'<rect x="{cx - grosor / 2:.1f}" y="{py:.1f}" width="{grosor:.1f}" '
            f'height="{max(1.0, altura):.1f}" rx="2" fill="{color}">'
            f"<title>{_e(titulo)}</title></rect>"
        )

    # Solo unas pocas fechas en el eje, para que no se amontonen.
    salto = max(1, len(bloques) // 8)
    for i in range(0, len(bloques), salto):
        fecha = datetime.fromisoformat(bloques[i].clave)
        partes.append(
            f'<text class="eje" x="{izq + paso * (i + 0.5):.1f}" y="{al - 8}" '
            f'text-anchor="middle">{fecha:%d/%m}</text>'
        )

    partes.append("</svg>")
    return "".join(partes)


def _barras_horas(bloques: list[Bloque], moneda: str) -> str:
    """Resultado por hora del dia: revela a que horas conviene dejarlo operar."""
    if not bloques:
        return '<p class="vacio">Sin datos por hora.</p>'

    por_hora = {int(b.clave): b for b in bloques}
    an, al = 1000, 190
    izq, der, arr, aba = 54, 12, 12, 28
    ancho, alto = an - izq - der, al - arr - aba

    tope = max((abs(b.pnl) for b in bloques), default=1) or 1
    cero = arr + alto / 2
    paso = ancho / 24

    partes = [f'<svg viewBox="0 0 {an} {al}" role="img" aria-label="Resultado por hora">']
    partes.append(
        f'<line class="rejilla-linea" x1="{izq}" y1="{cero:.1f}" '
        f'x2="{izq + ancho}" y2="{cero:.1f}"/>'
    )

    for h in range(24):
        b = por_hora.get(h)
        cx = izq + paso * (h + 0.5)
        if b:
            altura = abs(b.pnl) / tope * (alto / 2)
            py = cero - altura if b.pnl >= 0 else cero
            color = "var(--verde)" if b.pnl >= 0 else "var(--rojo)"
            titulo = f"{h:02d}:00 — {_firmado(b.pnl, moneda)} en {b.operaciones} ops"
            partes.append(
                f'<rect x="{cx - paso * 0.34:.1f}" y="{py:.1f}" '
                f'width="{paso * 0.68:.1f}" height="{max(1.0, altura):.1f}" rx="2" '
                f'fill="{color}"><title>{_e(titulo)}</title></rect>'
            )
        if h % 2 == 0:
            partes.append(
                f'<text class="eje" x="{cx:.1f}" y="{al - 8}" '
                f'text-anchor="middle">{h:02d}</text>'
            )

    partes.append("</svg>")
    return "".join(partes)


# -- tablas ---------------------------------------------------------------

def _tabla_simbolos(bloques: list[Bloque], moneda: str) -> str:
    if not bloques:
        return '<p class="vacio">Sin operaciones.</p>'

    tope = max((abs(b.pnl) for b in bloques), default=1) or 1
    filas = []
    for b in bloques:
        ancho = max(2, round(abs(b.pnl) / tope * 90))
        color = "var(--verde)" if b.pnl >= 0 else "var(--rojo)"
        filas.append(
            f"<tr>"
            f'<td class="simbolo">{_e(b.clave)}</td>'
            f"<td>{b.operaciones}</td>"
            f"<td>{pct(b.winrate)}</td>"
            f'<td class="{_clase(b.pnl)}">{_firmado(b.pnl)}</td>'
            f'<td style="width:104px"><span class="medidor" '
            f'style="width:{ancho}px;background:{color}"></span></td>'
            f"</tr>"
        )

    return (
        '<div class="desplazable"><table><thead><tr>'
        "<th>Simbolo</th><th>Ops</th><th>Aciertos</th>"
        f"<th>PnL ({_e(moneda)})</th><th></th>"
        f"</tr></thead><tbody>{''.join(filas)}</tbody></table></div>"
    )


def _tabla_operaciones(trades: list[Trade], moneda: str, limite: int = 40) -> str:
    if not trades:
        return '<p class="vacio">Sin operaciones.</p>'

    recientes = sorted(trades, key=lambda t: t.close_ts, reverse=True)[:limite]
    filas = []
    for t in recientes:
        etiqueta = "LARGO" if t.direction == "long" else "CORTO"
        clase = "larga" if t.direction == "long" else "corta"
        filas.append(
            f"<tr>"
            f"<td>{t.close_ts:%d/%m %H:%M}</td>"
            f'<td class="simbolo">{_e(t.symbol)}</td>'
            f'<td><span class="pastilla {clase}">{etiqueta}</span></td>'
            f"<td>{t.qty:g}</td>"
            f"<td>{dinero(t.entry_price, 4).rstrip('0').rstrip('.')}</td>"
            f"<td>{dinero(t.exit_price, 4).rstrip('0').rstrip('.')}</td>"
            f"<td>{duracion(t.duracion_seg)}</td>"
            f'<td class="{_clase(t.pnl_neto)}">{_firmado(t.pnl_neto)}</td>'
            f'<td class="{_clase(t.pnl_neto)}">{pct(t.retorno_pct)}</td>'
            f"</tr>"
        )

    nota = (
        f'<p class="gris" style="font-size:12px;margin:12px 0 0">'
        f"Mostrando las {limite} mas recientes de {len(trades)}.</p>"
        if len(trades) > limite else ""
    )
    return (
        '<div class="desplazable"><table><thead><tr>'
        "<th>Cierre</th><th>Simbolo</th><th>Dir</th><th>Cant.</th>"
        "<th>Entrada</th><th>Salida</th><th>Duracion</th>"
        f"<th>PnL ({_e(moneda)})</th><th>Ret.</th>"
        f"</tr></thead><tbody>{''.join(filas)}</tbody></table></div>{nota}"
    )


def _tabla_abiertas(abiertas: list[PosicionAbierta], moneda: str) -> str:
    filas = []
    for p in abiertas:
        etiqueta = "LARGO" if p.direction == "long" else "CORTO"
        clase = "larga" if p.direction == "long" else "corta"
        filas.append(
            f"<tr>"
            f'<td class="simbolo">{_e(p.symbol)}</td>'
            f'<td><span class="pastilla {clase}">{etiqueta}</span></td>'
            f"<td>{p.qty:g}</td>"
            f"<td>{dinero(p.precio_medio, 4).rstrip('0').rstrip('.')}</td>"
            f"<td>{dinero(p.capital_empleado)}</td>"
            f"<td>{p.desde:%d/%m %H:%M}</td>"
            f"</tr>"
        )
    return (
        '<div class="desplazable"><table><thead><tr>'
        "<th>Simbolo</th><th>Dir</th><th>Cantidad</th><th>Precio medio</th>"
        f"<th>Capital ({_e(moneda)})</th><th>Abierta desde</th>"
        f"</tr></thead><tbody>{''.join(filas)}</tbody></table></div>"
    )


def _tarjetas(m: Metricas, moneda: str) -> str:
    pf = "∞" if math.isinf(m.profit_factor) else f"{m.profit_factor:.2f}"
    payoff = "—" if math.isinf(m.payoff) else f"{m.payoff:.2f}"

    tarjetas = [
        ("Operaciones", str(m.operaciones), f"{m.ganadoras} ganadas · {m.perdedoras} perdidas", ""),
        ("Aciertos", pct(m.winrate), "porcentaje de acierto", ""),
        ("Profit factor", pf, "ganado ÷ perdido", _clase(m.profit_factor - 1)),
        ("Expectativa", _firmado(m.expectativa), f"por operacion, {moneda}", _clase(m.expectativa)),
        ("Maxima caida", f"-{dinero(m.max_drawdown)}", f"{pct(m.max_drawdown_pct)} desde el pico", "neg"),
        ("Sharpe", f"{m.sharpe:.2f}", "anualizado", ""),
        ("Ratio G/P", payoff, "ganancia media ÷ perdida media", ""),
        ("Comisiones", f"-{dinero(m.comisiones)}", f"{moneda} pagados", ""),
        ("Racha ganadora", str(m.racha_ganadora), "seguidas", "pos"),
        ("Racha perdedora", str(m.racha_perdedora), "seguidas", "neg"),
        ("Duracion media", duracion(m.duracion_media_seg), "por operacion", ""),
        ("Volumen", dinero(m.volumen_operado, 0), f"{moneda} movidos", ""),
    ]
    return "".join(
        f'<div class="tarjeta"><div class="k">{_e(k)}</div>'
        f'<div class="v {cls}">{_e(v)}</div><div class="n">{_e(n)}</div></div>'
        for k, v, n, cls in tarjetas
    )


def _seccion_dia_semana(bloques: list[Bloque], moneda: str) -> str:
    if not bloques:
        return ""
    filas = []
    for b in sorted(bloques, key=lambda b: int(b.clave)):
        filas.append(
            f"<tr><td>{DIAS[int(b.clave)]}</td><td>{b.operaciones}</td>"
            f"<td>{pct(b.winrate)}</td>"
            f'<td class="{_clase(b.pnl)}">{_firmado(b.pnl)}</td></tr>'
        )
    return (
        '<div class="desplazable"><table><thead><tr>'
        f"<th>Dia</th><th>Ops</th><th>Aciertos</th><th>PnL ({_e(moneda)})</th>"
        f"</tr></thead><tbody>{''.join(filas)}</tbody></table></div>"
    )


def _panel_avisos(avisos: list[str]) -> str:
    """Todos los avisos en un solo bloque.

    Uno por caja llenaba la parte de arriba de banderas rojas y acababa
    pareciendo decoracion; agrupados se leen.
    """
    if len(avisos) == 1:
        return f'<div class="aviso">{_e(avisos[0])}</div>'

    puntos = "".join(f"<li>{_e(a)}</li>" for a in avisos)
    return (
        f'<div class="aviso">'
        f'<div class="aviso-titulo">{len(avisos)} cosas que conviene mirar</div>'
        f"<ul>{puntos}</ul></div>"
    )


def _css_binarias() -> str:
    """Estilos extra que solo hacen falta en el dashboard de binarias."""
    from .binarias_html import CSS_EXTRA

    return CSS_EXTRA


def _css_vivo() -> str:
    """Estilos del panel de estado en vivo."""
    from .vivo_html import CSS_EXTRA

    return CSS_EXTRA


def _cuerpo_binarias(b, trades: list[Trade], moneda: str) -> list[str]:
    """Paneles del dashboard cuando el historial es de opciones binarias."""
    from . import binarias_html as bh

    signo = "+" if b.neto >= 0 else ""
    partes = [
        f'<div class="resultado">'
        f'<div class="etiqueta">Resultado neto</div>'
        f'<div class="cifra {_clase(b.neto)}">{signo}{dinero(b.neto)} {_e(moneda)}</div>'
        f'<div class="subtitulo">{b.total} operaciones · '
        f"{dinero(b.invertido)} {_e(moneda)} invertidos · "
        f"balance {dinero(b.balance_inicial)} → {dinero(b.balance_final)}</div></div>",
        bh.panel_veredicto(b),
        f'<div class="panel"><h2>Efectividad frente al punto de equilibrio</h2>'
        f"{bh.medidor_equilibrio(b)}</div>",
        f'<div class="rejilla">{bh.tarjetas(b, moneda)}</div>',
        f'<div class="panel"><h2>Balance</h2>{bh.curva_balance(b, moneda)}</div>',
    ]

    if len(b.por_par) > 1:
        partes.append(
            f'<div class="panel"><h2>Por par</h2>'
            f"{bh.tabla_bloques(b.por_par, moneda, 'Par')}</div>"
        )
    if len(b.por_estrategia) > 1:
        partes.append(
            f'<div class="panel"><h2>Por estrategia</h2>'
            f"{bh.tabla_bloques(b.por_estrategia, moneda, 'Estrategia')}</div>"
        )
    if len(b.profundidad) > 1:
        partes.append(
            f'<div class="panel"><h2>Segun perdidas seguidas previas</h2>'
            f"{bh.tabla_profundidad(b.profundidad, moneda)}</div>"
        )
    if len(b.por_franja) > 2:
        partes.append(
            f'<div class="panel"><h2>Resultado por franja horaria</h2>'
            f"{bh.barras_franja(b.por_franja, moneda)}</div>"
        )
    if len(b.por_dia_semana) > 1:
        partes.append(
            f'<div class="panel"><h2>Por dia de la semana</h2>'
            f"{bh.tabla_bloques(b.por_dia_semana, moneda, 'Dia')}</div>"
        )

    partes.append(
        f'<div class="panel"><h2>Operaciones</h2>'
        f"{bh.tabla_operaciones(trades, moneda)}</div>"
    )
    return partes


# -- documento ------------------------------------------------------------

def render(
    m: Metricas,
    trades: list[Trade] | None = None,
    moneda: str = "USDT",
    titulo: str = "Reporte de trading",
    periodo: str = "",
    abiertas: list[PosicionAbierta] | None = None,
    avisos: list[str] | None = None,
    fuentes: list[str] | None = None,
    autorecarga: int = 0,
    binarias=None,
    vivo=None,
    vivo_error: str = "",
) -> str:
    """Genera el dashboard completo como un unico documento HTML.

    Con ``binarias`` se muestran los paneles de opciones binarias en lugar de
    los de spot, que ahi no significan nada.

    ``vivo`` es el estado actual del bot leido de su panel. Va arriba del todo:
    primero que esta pasando ahora, despues el analisis del historial.
    """
    trades = trades or []
    abiertas = abiertas or []
    avisos = avisos or []
    es_binarias = binarias is not None and binarias.hay_datos
    hay_vivo = vivo is not None or bool(vivo_error)

    recarga = (
        f'<meta http-equiv="refresh" content="{autorecarga}">' if autorecarga > 0 else ""
    )

    if m.desde and m.hasta:
        rango = f"{m.desde:%d/%m/%Y %H:%M} → {m.hasta:%d/%m/%Y %H:%M} UTC"
    else:
        rango = "sin operaciones en el periodo"
    if periodo:
        rango = f"{periodo} · {rango}"
    if fuentes:
        rango += f" · fuentes: {', '.join(fuentes)}"

    cuerpo: list[str] = []
    if hay_vivo:
        from . import vivo_html

        cuerpo.append(
            vivo_html.panel(vivo, moneda) if vivo is not None
            else vivo_html.panel_apagado(vivo_error, "")
        )
    if avisos:
        cuerpo.append(_panel_avisos(avisos))

    if not m.hay_datos:
        cuerpo.append(
            '<div class="panel"><p class="vacio">No hay operaciones cerradas '
            "en este periodo.</p></div>"
        )
        if abiertas:
            cuerpo.append(
                f'<div class="panel"><h2>Posiciones abiertas ({len(abiertas)})</h2>'
                f"{_tabla_abiertas(abiertas, moneda)}</div>"
            )
    elif es_binarias:
        cuerpo.extend(_cuerpo_binarias(binarias, trades, moneda))
    else:
        signo = "+" if m.pnl_neto >= 0 else ""
        cuerpo.append(
            f'<div class="resultado">'
            f'<div class="etiqueta">Resultado neto</div>'
            f'<div class="cifra {_clase(m.pnl_neto)}">'
            f"{signo}{dinero(m.pnl_neto)} {_e(moneda)}</div>"
            f'<div class="subtitulo">bruto {_firmado(m.pnl_bruto)} · '
            f"comisiones -{dinero(m.comisiones)}</div></div>"
        )
        cuerpo.append(f'<div class="rejilla">{_tarjetas(m, moneda)}</div>')
        cuerpo.append(
            f'<div class="panel"><h2>Curva de capital</h2>{_curva_equity(m, moneda)}</div>'
        )
        cuerpo.append(
            f'<div class="panel"><h2>Resultado por dia</h2>'
            f"{_barras_diarias(m.por_dia, moneda)}</div>"
        )
        cuerpo.append(
            f'<div class="dos-columnas">'
            f'<div class="panel"><h2>Por simbolo</h2>'
            f"{_tabla_simbolos(m.por_simbolo, moneda)}</div>"
            f'<div class="panel"><h2>Por dia de la semana</h2>'
            f"{_seccion_dia_semana(m.por_dia_semana, moneda)}</div>"
            f"</div>"
        )
        cuerpo.append(
            f'<div class="panel"><h2>Resultado por hora (UTC)</h2>'
            f"{_barras_horas(m.por_hora, moneda)}</div>"
        )
        if abiertas:
            cuerpo.append(
                f'<div class="panel"><h2>Posiciones abiertas ({len(abiertas)})</h2>'
                f"{_tabla_abiertas(abiertas, moneda)}</div>"
            )
        cuerpo.append(
            f'<div class="panel"><h2>Operaciones</h2>'
            f"{_tabla_operaciones(trades, moneda)}</div>"
        )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{recarga}
<title>Jarvis · {_e(titulo)}</title>
<style>{CSS}{_css_binarias() if es_binarias else ""}{_css_vivo() if hay_vivo else ""}</style>
</head>
<body>
<div class="envoltorio">
<header>
  <h1>Jarvis · {_e(titulo)}</h1>
  <div class="subtitulo">{_e(rango)}</div>
</header>
{''.join(cuerpo)}
<footer>Generado por Jarvis el {datetime.now():%d/%m/%Y a las %H:%M}</footer>
</div>
</body>
</html>"""
