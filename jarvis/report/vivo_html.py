"""Panel de estado en vivo para el dashboard.

Va arriba del todo, antes del analisis historico: primero que esta pasando
ahora, despues como ha ido la cosa.
"""

from __future__ import annotations

import html as _html

from ..vivo import EstadoVivo
from .formato import dinero, pct


def _e(texto) -> str:
    return _html.escape(str(texto))


CSS_EXTRA = """
.vivo {
  border: 1px solid var(--borde); border-radius: 12px;
  padding: 16px 18px; margin-bottom: 16px; background: var(--panel);
}
.vivo.activo { border-color: var(--verde); }
.vivo.parado { border-color: var(--borde); }
.vivo.alerta { border-color: var(--rojo); background: var(--rojo-claro); }

.vivo-cabecera {
  display: flex; align-items: center; gap: 10px;
  flex-wrap: wrap; margin-bottom: 14px;
}
.vivo-punto {
  width: 9px; height: 9px; border-radius: 50%; flex: none;
  background: var(--tenue);
}
.vivo.activo .vivo-punto { background: var(--verde); animation: latido 2s ease-in-out infinite; }
.vivo.alerta .vivo-punto { background: var(--rojo); }
@keyframes latido { 0%,100% { opacity: 1 } 50% { opacity: .35 } }
@media (prefers-reduced-motion: reduce) {
  .vivo.activo .vivo-punto { animation: none; }
}

.vivo-titulo { font-weight: 640; font-size: 14px; }
.vivo-modo {
  font-size: 11px; padding: 2px 8px; border-radius: 999px;
  border: 1px solid var(--borde); color: var(--suave);
  text-transform: uppercase; letter-spacing: .04em;
}
.vivo-modo.real { border-color: var(--rojo); color: var(--rojo); font-weight: 620; }
.vivo-momento { margin-left: auto; font-size: 11.5px; color: var(--tenue); }

.vivo-datos {
  display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(118px, 1fr));
}
.vivo-dato .k {
  font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em;
  color: var(--tenue); margin-bottom: 3px;
}
.vivo-dato .v {
  font-size: 19px; font-weight: 620; font-variant-numeric: tabular-nums;
}
.vivo-dato .n { font-size: 11.5px; color: var(--suave); margin-top: 2px; }

.vivo-pares { margin-top: 14px; display: flex; flex-wrap: wrap; gap: 6px; }
.vivo-par {
  font-size: 11.5px; padding: 3px 9px; border-radius: 6px;
  border: 1px solid var(--borde); color: var(--suave);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.vivo-par.bloqueado {
  border-color: var(--rojo); color: var(--rojo); background: var(--rojo-claro);
}
.vivo-apagado { font-size: 13px; color: var(--suave); line-height: 1.55; }
.vivo-log {
  margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--rejilla);
}
.vivo-log ul {
  margin: 0; padding: 0; list-style: none;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11.5px; color: var(--suave); line-height: 1.65;
}
.vivo-log li { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
"""


def panel_apagado(mensaje: str, url: str) -> str:
    """Lo que se ve cuando el bot no responde: informativo, no alarmante."""
    return (
        f'<div class="vivo parado">'
        f'<div class="vivo-cabecera">'
        f'<span class="vivo-punto"></span>'
        f'<span class="vivo-titulo">Bot sin conexion</span>'
        f"</div>"
        f'<div class="vivo-apagado">{_e(mensaje)}<br>'
        f"El analisis de abajo sigue siendo valido: sale del historial "
        f"guardado, no del bot.</div>"
        f"</div>"
    )


def panel(estado: EstadoVivo, moneda: str) -> str:
    """Panel de estado en vivo del bot."""
    if estado.error or (estado.corriendo and not estado.conectado):
        clase, titulo = "alerta", "Bot con problemas"
    elif estado.corriendo:
        clase, titulo = "activo", "Bot operando"
    else:
        clase, titulo = "parado", "Bot detenido"

    modo = ""
    if estado.modo:
        clase_modo = "vivo-modo real" if estado.es_cuenta_real else "vivo-modo"
        etiqueta = "dinero real" if estado.es_cuenta_real else estado.modo
        modo = f'<span class="{clase_modo}">{_e(etiqueta)}</span>'

    partes = [
        f'<div class="vivo {clase}">',
        f'<div class="vivo-cabecera">',
        f'<span class="vivo-punto"></span>',
        f'<span class="vivo-titulo">{_e(titulo)}</span>',
        modo,
        f'<span class="vivo-momento">actualizado {estado.momento:%H:%M:%S} UTC</span>',
        f"</div>",
    ]

    if estado.error:
        partes.append(f'<div class="vivo-apagado">{_e(estado.error)}</div>')

    signo = "+" if estado.neto >= 0 else ""
    clase_neto = "pos" if estado.neto > 0 else "neg" if estado.neto < 0 else ""
    datos = [
        ("Balance", dinero(estado.balance), moneda, ""),
        ("Sesion", f"{signo}{dinero(estado.neto)}", moneda, clase_neto),
        ("Ganadas", str(estado.wins), f"de {estado.operaciones_sesion_total}", "pos"),
        ("Perdidas", str(estado.losses),
         pct(estado.efectividad_sesion) + " acierto", "neg"),
    ]

    if estado.exposicion > 0:
        nota = (
            f"{estado.exposicion / estado.balance * 100:.0f}% del balance"
            if estado.balance > 0 else "en operaciones abiertas"
        )
        datos.append(("En juego", dinero(estado.exposicion), nota, ""))

    if estado.martingala_nivel > 0:
        datos.append((
            "Martingala",
            f"nivel {estado.martingala_nivel}",
            f"proxima: {dinero(estado.martingala_monto)}",
            "neg" if estado.martingala_nivel >= 2 else "",
        ))
    elif estado.perdidas_seguidas > 0:
        datos.append(("Perdidas seguidas", str(estado.perdidas_seguidas), "en curso", "neg"))

    partes.append('<div class="vivo-datos">')
    for k, v, n, cls in datos:
        partes.append(
            f'<div class="vivo-dato"><div class="k">{_e(k)}</div>'
            f'<div class="v {cls}">{_e(v)}</div><div class="n">{_e(n)}</div></div>'
        )
    partes.append("</div>")

    pastillas = _pastillas_pares(estado)
    if pastillas:
        partes.append(f'<div class="vivo-pares">{pastillas}</div>')

    if estado.log:
        ultimas = "".join(f"<li>{_e(l)}</li>" for l in estado.log[:6])
        partes.append(f'<div class="vivo-log"><ul>{ultimas}</ul></div>')

    partes.append("</div>")
    return "".join(partes)


def _pastillas_pares(estado: EstadoVivo) -> str:
    """Pares en juego, marcando en rojo los bloqueados."""
    bloqueados = {p.par for p in estado.pares_bloqueados}
    nombres = list(dict.fromkeys([*estado.pares_operando, *sorted(bloqueados)]))
    if not nombres:
        return ""

    salida = []
    for par in nombres:
        if par in bloqueados:
            salida.append(f'<span class="vivo-par bloqueado">{_e(par)} · bloqueado</span>')
        else:
            senal = next((p.senal for p in estado.pares if p.par == par and p.senal), "")
            texto = f"{par} · {senal}" if senal and senal != "-" else par
            salida.append(f'<span class="vivo-par">{_e(texto)}</span>')
    return "".join(salida)
