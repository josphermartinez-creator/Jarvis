"""Paneles del dashboard propios de opciones binarias.

El elemento central es el medidor de punto de equilibrio: una barra con el
umbral marcado y la efectividad real encima. De un vistazo se ve si la
estrategia esta por encima o por debajo de lo que exige el pago del broker,
que es la pregunta que de verdad importa en binarias.
"""

from __future__ import annotations

import html as _html

from ..binarias import BloqueBinario, MetricasBinarias, Profundidad
from .formato import dinero, pct


def _e(texto) -> str:
    return _html.escape(str(texto))


def _clase(valor: float) -> str:
    return "pos" if valor > 0 else "neg" if valor < 0 else "gris"


CSS_EXTRA = """
.veredicto {
  border-radius: 12px; padding: 18px 20px; margin-bottom: 16px;
  border: 1px solid; display: flex; gap: 18px; align-items: center;
  flex-wrap: wrap;
}
.veredicto.bien { background: var(--verde-claro); border-color: var(--verde); }
.veredicto.mal  { background: var(--rojo-claro);  border-color: var(--rojo); }
.veredicto .icono { font-size: 26px; line-height: 1; }
.veredicto .texto { flex: 1; min-width: 240px; }
.veredicto .titular { font-weight: 640; font-size: 15px; margin-bottom: 3px; }
.veredicto.bien .titular { color: var(--verde); }
.veredicto.mal  .titular { color: var(--rojo); }
.veredicto .detalle { font-size: 13px; color: var(--texto); opacity: .85; }

/* El margen superior deja sitio a la etiqueta del umbral, que sobresale por
   encima de la barra. La pista no lleva overflow:hidden justamente para que esa
   etiqueta no quede recortada; el relleno se redondea por su cuenta. */
.equilibrio { margin: 24px 0 2px; }
.equilibrio .pista {
  position: relative; height: 30px; background: var(--rejilla);
  border-radius: 6px;
}
.equilibrio .relleno { height: 100%; border-radius: 6px; }
.equilibrio .umbral {
  position: absolute; top: -5px; bottom: -5px; width: 2px;
  background: var(--texto);
}
.equilibrio .umbral::after {
  content: attr(data-nota); position: absolute; top: -20px;
  left: 50%; transform: translateX(-50%); white-space: nowrap;
  font-size: 11px; color: var(--suave); font-variant-numeric: tabular-nums;
}
.equilibrio .escala {
  display: flex; justify-content: space-between;
  font-size: 11px; color: var(--tenue); margin-top: 5px;
}
.nota-panel {
  font-size: 12.5px; color: var(--suave); margin: 12px 0 0; line-height: 1.5;
}
td.marca { width: 26px; text-align: center; font-weight: 700; }
"""


def medidor_equilibrio(m: MetricasBinarias) -> str:
    """Barra con la efectividad real frente al umbral de rentabilidad."""
    if m.payout_medio <= 0:
        return ""

    # La escala arranca en 30% y acaba en 80%: fuera de ahi no hay nada que ver
    # y comprimirlo todo desde cero haria la diferencia ilegible.
    ini, fin = 30.0, 80.0
    def posicion(valor: float) -> float:
        return max(0.0, min(100.0, (valor - ini) / (fin - ini) * 100))

    color = "var(--verde)" if m.rentable else "var(--rojo)"
    return (
        f'<div class="equilibrio">'
        f'<div class="pista">'
        f'<div class="relleno" style="width:{posicion(m.efectividad):.1f}%;'
        f'background:{color};opacity:.55"></div>'
        f'<div class="umbral" style="left:{posicion(m.punto_equilibrio):.1f}%" '
        f'data-nota="equilibrio {pct(m.punto_equilibrio)}"></div>'
        f"</div>"
        f'<div class="escala"><span>{pct(ini, 0)}</span>'
        f"<span>efectividad real: <strong>{pct(m.efectividad)}</strong></span>"
        f"<span>{pct(fin, 0)}</span></div>"
        f"</div>"
    )


def panel_veredicto(m: MetricasBinarias) -> str:
    clase = "bien" if m.rentable else "mal"
    icono = "✓" if m.rentable else "⚠"
    if m.payout_medio > 0:
        detalle = (
            f"Con un pago medio del {pct(m.payout_medio * 100, 0)} necesitas acertar "
            f"el {pct(m.punto_equilibrio)} para no perder dinero. Estas acertando el "
            f"{pct(m.efectividad)}: {m.margen:+.1f} puntos."
        )
    else:
        detalle = "Todavia no hay operaciones ganadoras con las que medir el pago."

    return (
        f'<div class="veredicto {clase}">'
        f'<div class="icono">{icono}</div>'
        f'<div class="texto">'
        f'<div class="titular">{_e(m.veredicto.capitalize())}</div>'
        f'<div class="detalle">{_e(detalle)}</div>'
        f"</div></div>"
    )


def tarjetas(m: MetricasBinarias, moneda: str) -> str:
    fuera = []
    if m.empates:
        fuera.append(f"{m.empates} empate(s)")
    if m.desconocidas:
        fuera.append(f"{m.desconocidas} sin confirmar")

    filas = [
        ("Operaciones", str(m.total), " · ".join(fuera) or "todas decididas", ""),
        ("Efectividad", pct(m.efectividad), f"{m.ganadas} de {m.decididas}", ""),
        ("Punto de equilibrio", pct(m.punto_equilibrio), "minimo para no perder", ""),
        ("Margen", f"{m.margen:+.1f}", "puntos sobre el umbral", _clase(m.margen)),
        ("Pago medio", pct(m.payout_medio * 100, 0), "al acertar", ""),
        ("Resultado neto", f"{'+' if m.neto >= 0 else ''}{dinero(m.neto)}",
         moneda, _clase(m.neto)),
        ("Retorno", pct(m.roi), "sobre lo invertido", _clase(m.roi)),
        ("Por operacion", f"{'+' if m.esperanza_por_operacion >= 0 else ''}"
         f"{dinero(m.esperanza_por_operacion)}", f"esperanza, {moneda}",
         _clase(m.esperanza_por_operacion)),
        ("Maxima caida", f"-{dinero(m.max_caida)}",
         f"{pct(m.max_caida_pct)} del balance", "neg"),
        ("Monto medio", dinero(m.monto_medio), f"{moneda} por operacion", ""),
        ("Racha perdedora", str(m.racha_perdidas), "seguidas", "neg"),
        ("Dias operados", str(m.dias_operados), f"{dinero(m.invertido, 0)} invertidos", ""),
    ]
    return "".join(
        f'<div class="tarjeta"><div class="k">{_e(k)}</div>'
        f'<div class="v {cls}">{_e(v)}</div><div class="n">{_e(n)}</div></div>'
        for k, v, n, cls in filas
    )


def curva_balance(m: MetricasBinarias, moneda: str) -> str:
    """Balance real reportado por el broker, operacion a operacion."""
    puntos = m.curva_balance
    if len(puntos) < 2:
        return '<p class="vacio">Hacen falta al menos dos operaciones.</p>'

    an, al = 1000, 250
    izq, der, arr, aba = 66, 12, 14, 26
    ancho, alto = an - izq - der, al - arr - aba

    saldos = [s for _, s in puntos]
    minimo, maximo = min(saldos), max(saldos)
    margen = (maximo - minimo) * 0.12 or max(1.0, abs(maximo) * 0.02)
    minimo, maximo = minimo - margen, maximo + margen
    rango = maximo - minimo

    def x(i: int) -> float:
        return izq + i * ancho / (len(saldos) - 1)

    def y(v: float) -> float:
        return arr + (maximo - v) * alto / rango

    linea = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(saldos))
    area = f"{izq},{arr + alto} {linea} {izq + ancho},{arr + alto}"
    sube = saldos[-1] >= saldos[0]
    trazo = "var(--verde)" if sube else "var(--rojo)"

    partes = [f'<svg viewBox="0 0 {an} {al}" role="img" aria-label="Balance">']
    partes.append(
        f'<defs><linearGradient id="degbin" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{trazo}" stop-opacity=".22"/>'
        f'<stop offset="100%" stop-color="{trazo}" stop-opacity="0"/>'
        f"</linearGradient></defs>"
    )
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

    partes.append(f'<polygon points="{area}" fill="url(#degbin)"/>')
    partes.append(
        f'<polyline points="{linea}" fill="none" stroke="{trazo}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
    )
    for i, momento in ((0, puntos[0][0]), (len(saldos) - 1, puntos[-1][0])):
        ancla = "start" if i == 0 else "end"
        partes.append(
            f'<text class="eje" x="{x(i):.1f}" y="{al - 8}" '
            f'text-anchor="{ancla}">{momento:%d/%m %H:%M}</text>'
        )
    partes.append("</svg>")
    return "".join(partes)


def barras_franja(bloques: list[BloqueBinario], moneda: str) -> str:
    """Neto por franja horaria: en que horas conviene dejar el bot operando."""
    utiles = [b for b in bloques if b.total >= 3]
    if not utiles:
        return '<p class="vacio">Pocas operaciones por franja para comparar.</p>'

    an, al = 1000, 200
    izq, der, arr, aba = 58, 12, 12, 30
    ancho, alto = an - izq - der, al - arr - aba
    tope = max(abs(b.neto) for b in utiles) or 1
    cero = arr + alto / 2
    paso = ancho / len(utiles)
    grosor = max(3.0, min(34.0, paso * 0.66))

    partes = [f'<svg viewBox="0 0 {an} {al}" role="img" aria-label="Neto por franja">']
    partes.append(
        f'<line class="rejilla-linea" x1="{izq}" y1="{cero:.1f}" '
        f'x2="{izq + ancho}" y2="{cero:.1f}"/>'
    )
    partes.append(
        f'<text class="eje" x="{izq - 8}" y="{cero + 3.5:.1f}" text-anchor="end">0</text>'
    )

    for i, b in enumerate(utiles):
        cx = izq + paso * (i + 0.5)
        altura = abs(b.neto) / tope * (alto / 2)
        py = cero - altura if b.neto >= 0 else cero
        color = "var(--verde)" if b.neto >= 0 else "var(--rojo)"
        titulo = (
            f"{b.clave}: {b.neto:+,.2f} {moneda} · {b.total} ops · "
            f"efectividad {b.efectividad:.1f}%"
        )
        partes.append(
            f'<rect x="{cx - grosor / 2:.1f}" y="{py:.1f}" width="{grosor:.1f}" '
            f'height="{max(1.0, altura):.1f}" rx="2" fill="{color}">'
            f"<title>{_e(titulo)}</title></rect>"
        )
        if len(utiles) <= 14 or i % 2 == 0:
            partes.append(
                f'<text class="eje" x="{cx:.1f}" y="{al - 8}" text-anchor="middle">'
                f"{_e(b.clave.split('-')[0].split(':')[0])}</text>"
            )

    partes.append("</svg>")
    return "".join(partes)


def tabla_bloques(bloques: list[BloqueBinario], moneda: str, etiqueta: str) -> str:
    if not bloques:
        return '<p class="vacio">Sin datos.</p>'

    filas = []
    for b in bloques:
        if b.pagos:
            umbral = pct(b.punto_equilibrio)
            margen = f"{b.margen:+.1f}"
            marca = "✓" if b.rentable else "✗"
            clase_marca = "pos" if b.rentable else "neg"
        else:
            umbral = margen = marca = "—"
            clase_marca = "gris"
        filas.append(
            f"<tr>"
            f'<td class="simbolo">{_e(b.clave)}</td>'
            f"<td>{b.total}</td>"
            f"<td>{pct(b.efectividad)}</td>"
            f"<td>{umbral}</td>"
            f'<td class="{_clase(b.margen)}">{margen}</td>'
            f'<td class="{_clase(b.neto)}">{b.neto:+,.2f}</td>'
            f'<td class="marca {clase_marca}">{marca}</td>'
            f"</tr>"
        )

    return (
        '<div class="desplazable"><table><thead><tr>'
        f"<th>{_e(etiqueta)}</th><th>Ops</th><th>Efectividad</th>"
        f"<th>Equilibrio</th><th>Margen</th><th>Neto ({_e(moneda)})</th><th></th>"
        f"</tr></thead><tbody>{''.join(filas)}</tbody></table></div>"
        '<p class="nota-panel">El equilibrio es la efectividad minima que exige '
        "el pago del broker. Por debajo, pierde a la larga aunque el neto de hoy "
        "salga positivo.</p>"
    )


def tabla_profundidad(niveles: list[Profundidad], moneda: str) -> str:
    if not niveles:
        return '<p class="vacio">Sin datos.</p>'

    filas = []
    for p in niveles:
        etiqueta = "sin perdidas previas" if p.perdidas_previas == 0 else (
            f"tras {p.perdidas_previas} perdida"
            f"{'s' if p.perdidas_previas > 1 else ''} seguida"
            f"{'s' if p.perdidas_previas > 1 else ''}"
        )
        filas.append(
            f"<tr>"
            f"<td>{_e(etiqueta)}</td>"
            f"<td>{p.operaciones}</td>"
            f"<td>{pct(p.efectividad)}</td>"
            f"<td>{dinero(p.monto_medio)}</td>"
            f'<td class="{_clase(p.neto)}">{p.neto:+,.2f}</td>'
            f"</tr>"
        )

    return (
        '<div class="desplazable"><table><thead><tr>'
        f"<th>Situacion</th><th>Ops</th><th>Efectividad</th>"
        f"<th>Monto medio ({_e(moneda)})</th><th>Neto ({_e(moneda)})</th>"
        f"</tr></thead><tbody>{''.join(filas)}</tbody></table></div>"
        '<p class="nota-panel">Si la efectividad no mejora al bajar por la cadena, '
        "doblar el monto no aumenta las probabilidades de acertar: solo agranda lo "
        "que hay en juego. Cuando el monto medio vuelve al importe base es que "
        "salto el limite de perdidas por par y el bot reinicio la cadena.</p>"
    )


def tabla_operaciones(trades, moneda: str, limite: int = 50) -> str:
    if not trades:
        return '<p class="vacio">Sin operaciones.</p>'

    recientes = sorted(trades, key=lambda t: t.close_ts, reverse=True)[:limite]
    etiquetas = {
        "win": ("GANADA", "larga"),
        "loss": ("PERDIDA", "corta"),
        "empate": ("EMPATE", ""),
        "desconocido": ("SIN CONFIRMAR", ""),
    }

    filas = []
    for t in recientes:
        resultado = t.meta.get("resultado", "")
        texto, clase = etiquetas.get(resultado, (resultado.upper(), ""))
        direccion = "SUBE" if t.direction == "long" else "BAJA"
        filas.append(
            f"<tr>"
            f"<td>{t.close_ts:%d/%m %H:%M}</td>"
            f'<td class="simbolo">{_e(t.symbol)}</td>'
            f"<td>{_e(t.meta.get('estrategia', ''))}</td>"
            f"<td>{direccion}</td>"
            f'<td><span class="pastilla {clase}">{texto}</span></td>'
            f"<td>{dinero(t.meta.get('monto', 0))}</td>"
            f'<td class="{_clase(t.pnl)}">{t.pnl:+,.2f}</td>'
            f"<td>{dinero(t.meta.get('balance', 0))}</td>"
            f"</tr>"
        )

    nota = (
        f'<p class="nota-panel">Mostrando las {limite} mas recientes de '
        f"{len(trades)}.</p>" if len(trades) > limite else ""
    )
    return (
        '<div class="desplazable"><table><thead><tr>'
        "<th>Cierre</th><th>Par</th><th>Estrategia</th><th>Apuesta</th>"
        f"<th>Resultado</th><th>Monto</th><th>Neto ({_e(moneda)})</th>"
        f"<th>Balance</th>"
        f"</tr></thead><tbody>{''.join(filas)}</tbody></table></div>{nota}"
    )
