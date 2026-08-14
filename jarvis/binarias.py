"""Metricas propias de opciones binarias.

Las binarias no se miden como el spot. Aqui no hay precio de entrada y salida:
hay un monto apostado y un pago fijo si aciertas. Eso cambia que cifras
importan.

La mas importante, y la que casi ningun panel muestra, es el **punto de
equilibrio**: con un pago del 85%, ganas 0,85 cuando aciertas y pierdes 1,00
cuando fallas, asi que necesitas acertar el 54,1% de las veces solo para no
perder dinero. Un bot con 52% de efectividad y buen aspecto en la racha corta
esta perdiendo por construccion. Comparar la efectividad real contra ese umbral
es lo que dice si la estrategia se sostiene o solo tuvo suerte.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from .models import Trade


def es_binaria(t: Trade) -> bool:
    return bool(t.meta.get("binarias"))


def filtrar_binarias(trades: Sequence[Trade]) -> list[Trade]:
    return [t for t in trades if es_binaria(t)]


@dataclass
class BloqueBinario:
    """Resultado agrupado por par, estrategia, franja horaria o dia."""

    clave: str
    total: int = 0
    ganadas: int = 0
    perdidas: int = 0
    empates: int = 0
    invertido: float = 0.0
    neto: float = 0.0
    pagos: list[float] = field(default_factory=list, repr=False)

    @property
    def decididas(self) -> int:
        return self.ganadas + self.perdidas

    @property
    def efectividad(self) -> float:
        return self.ganadas / self.decididas * 100 if self.decididas else 0.0

    @property
    def payout(self) -> float:
        """Pago medio obtenido al acertar, en tanto por uno (0.85 = 85%)."""
        return statistics.fmean(self.pagos) if self.pagos else 0.0

    @property
    def punto_equilibrio(self) -> float:
        """Efectividad minima necesaria para no perder dinero, en porcentaje."""
        return 100 / (1 + self.payout) if self.payout > 0 else 0.0

    @property
    def margen(self) -> float:
        """Puntos por encima (o por debajo) del punto de equilibrio.

        Positivo: la estrategia se sostiene. Negativo: pierde a la larga aunque
        el neto de hoy sea bueno.
        """
        return self.efectividad - self.punto_equilibrio if self.pagos else 0.0

    @property
    def rentable(self) -> bool:
        return self.margen > 0

    @property
    def roi(self) -> float:
        return self.neto / self.invertido * 100 if self.invertido else 0.0


@dataclass
class Profundidad:
    """Comportamiento segun cuantas perdidas seguidas llevaba el par.

    ``monto_medio`` deja ver la martingala en accion: si crece con la
    profundidad, el bot esta doblando; si vuelve al monto base, es que salto el
    limite de perdidas por par y el bot bloqueo el par y reinicio la cadena.
    """

    perdidas_previas: int
    operaciones: int = 0
    ganadas: int = 0
    invertido: float = 0.0
    neto: float = 0.0

    @property
    def efectividad(self) -> float:
        return self.ganadas / self.operaciones * 100 if self.operaciones else 0.0

    @property
    def monto_medio(self) -> float:
        return self.invertido / self.operaciones if self.operaciones else 0.0


@dataclass
class MetricasBinarias:
    """Todo lo que Jarvis sabe decir de un historial de opciones binarias."""

    desde: datetime | None = None
    hasta: datetime | None = None

    total: int = 0
    ganadas: int = 0
    perdidas: int = 0
    empates: int = 0
    desconocidas: int = 0

    invertido: float = 0.0
    neto: float = 0.0
    monto_medio: float = 0.0

    payout_medio: float = 0.0
    racha_ganadas: int = 0
    racha_perdidas: int = 0

    balance_inicial: float = 0.0
    balance_final: float = 0.0
    balance_maximo: float = 0.0
    max_caida: float = 0.0
    max_caida_pct: float = 0.0

    dias_operados: int = 0
    mejor_dia: BloqueBinario | None = None
    peor_dia: BloqueBinario | None = None

    profundidad: list[Profundidad] = field(default_factory=list)
    por_par: list[BloqueBinario] = field(default_factory=list)
    por_estrategia: list[BloqueBinario] = field(default_factory=list)
    por_franja: list[BloqueBinario] = field(default_factory=list)
    por_dia_semana: list[BloqueBinario] = field(default_factory=list)
    por_dia: list[BloqueBinario] = field(default_factory=list)

    curva_balance: list[tuple[datetime, float]] = field(default_factory=list)

    @property
    def hay_datos(self) -> bool:
        return self.total > 0

    @property
    def decididas(self) -> int:
        return self.ganadas + self.perdidas

    @property
    def efectividad(self) -> float:
        """Porcentaje de acierto sobre las operaciones que se decidieron.

        Los empates y las no confirmadas quedan fuera: no son aciertos ni
        fallos, y meterlas dentro maquilla la cifra.
        """
        return self.ganadas / self.decididas * 100 if self.decididas else 0.0

    @property
    def punto_equilibrio(self) -> float:
        return 100 / (1 + self.payout_medio) if self.payout_medio > 0 else 0.0

    @property
    def margen(self) -> float:
        return self.efectividad - self.punto_equilibrio if self.payout_medio > 0 else 0.0

    @property
    def rentable(self) -> bool:
        return self.margen > 0

    @property
    def roi(self) -> float:
        return self.neto / self.invertido * 100 if self.invertido else 0.0

    @property
    def esperanza_por_operacion(self) -> float:
        return self.neto / self.total if self.total else 0.0

    @property
    def veredicto(self) -> str:
        """Resumen en una linea de si la estrategia se sostiene."""
        if not self.hay_datos:
            return "sin datos"
        if self.payout_medio <= 0:
            return "sin operaciones ganadoras: no se puede medir el pago"
        if self.decididas < 50:
            return (
                f"muestra corta ({self.decididas} operaciones decididas): "
                f"todavia no es concluyente"
            )
        if self.margen > 2:
            return "la estrategia se sostiene por encima del punto de equilibrio"
        if self.margen > 0:
            return "apenas por encima del equilibrio: el margen es fragil"
        return "por debajo del punto de equilibrio: a la larga pierde"


def _agrupar(trades: Sequence[Trade], obtener_clave) -> list[BloqueBinario]:
    grupos: dict[str, BloqueBinario] = {}

    for t in trades:
        clave = obtener_clave(t) or "(sin dato)"
        b = grupos.setdefault(clave, BloqueBinario(clave=clave))
        b.total += 1

        resultado = t.meta.get("resultado", "")
        monto = t.meta.get("monto", 0.0)
        b.invertido += monto
        b.neto += t.pnl

        if resultado == "win":
            b.ganadas += 1
            if monto > 0:
                b.pagos.append(t.pnl / monto)
        elif resultado == "loss":
            b.perdidas += 1
        else:
            b.empates += 1

    return list(grupos.values())


def _rachas(trades: Sequence[Trade]) -> tuple[int, int]:
    mejor_g = mejor_p = actual_g = actual_p = 0
    for t in sorted(trades, key=lambda t: t.close_ts):
        resultado = t.meta.get("resultado")
        if resultado == "win":
            actual_g += 1
            actual_p = 0
            mejor_g = max(mejor_g, actual_g)
        elif resultado == "loss":
            actual_p += 1
            actual_g = 0
            mejor_p = max(mejor_p, actual_p)
        else:
            actual_g = actual_p = 0
    return mejor_g, mejor_p


def _profundidades(trades: Sequence[Trade]) -> list[Profundidad]:
    """Agrupa las operaciones por cuantas perdidas seguidas llevaba el par.

    La profundidad se deduce recorriendo el historial de cada par, no de la
    columna ``racha_perdidas_momento``: el bot escribe esa columna despues de
    procesar el resultado, asi que en una ganadora siempre vale 0 y no dice
    desde donde se entro. Aqui interesa justo lo contrario.

    Es el desglose que desmonta la ilusion de la martingala: si la efectividad
    se mantiene plana al aumentar la profundidad, doblar el monto no mejora las
    probabilidades, solo agranda lo que hay en juego.
    """
    grupos: dict[int, Profundidad] = {}
    racha: dict[str, int] = {}

    for t in sorted(trades, key=lambda t: t.close_ts):
        previas = racha.get(t.symbol, 0)
        p = grupos.setdefault(previas, Profundidad(perdidas_previas=previas))
        p.operaciones += 1
        p.invertido += t.meta.get("monto", 0.0)
        p.neto += t.pnl

        resultado = t.meta.get("resultado")
        if resultado == "win":
            p.ganadas += 1
            racha[t.symbol] = 0
        elif resultado == "loss":
            racha[t.symbol] = previas + 1
        else:
            # El bot corta la cadena tanto en un empate como en una operacion
            # sin confirmar: sin saber si acerto, seguir doblando seria apostar
            # a ciegas.
            racha[t.symbol] = 0

    return [grupos[k] for k in sorted(grupos)]


def _curva_y_caida(
    trades: Sequence[Trade],
) -> tuple[list[tuple[datetime, float]], float, float, float, float, float]:
    """Curva de balance real y su maxima caida.

    Se usa el balance que reporta el bróker en cada fila, no una suma
    acumulada: si hubo depositos o retiros, la curva real los refleja.
    """
    ordenadas = sorted(trades, key=lambda t: t.close_ts)
    curva = [(t.close_ts, t.meta.get("balance", 0.0)) for t in ordenadas]
    curva = [(fecha, saldo) for fecha, saldo in curva if saldo]

    if not curva:
        return [], 0.0, 0.0, 0.0, 0.0, 0.0

    primero = ordenadas[0]
    inicial = curva[0][1] - primero.pnl  # antes de la primera operacion
    pico = inicial
    max_caida = max_caida_pct = 0.0

    for _, saldo in curva:
        pico = max(pico, saldo)
        caida = pico - saldo
        if caida > max_caida:
            max_caida = caida
            max_caida_pct = caida / pico * 100 if pico > 0 else 0.0

    return curva, inicial, curva[-1][1], pico, max_caida, max_caida_pct


def calcular(trades: Sequence[Trade]) -> MetricasBinarias:
    """Calcula las metricas de opciones binarias del historial dado."""
    binarias = filtrar_binarias(trades)
    m = MetricasBinarias()
    if not binarias:
        return m

    ordenadas = sorted(binarias, key=lambda t: t.close_ts)
    m.total = len(ordenadas)
    m.desde = ordenadas[0].close_ts
    m.hasta = ordenadas[-1].close_ts

    pagos: list[float] = []
    for t in ordenadas:
        resultado = t.meta.get("resultado", "")
        monto = t.meta.get("monto", 0.0)
        m.invertido += monto
        m.neto += t.pnl

        if resultado == "win":
            m.ganadas += 1
            if monto > 0:
                pagos.append(t.pnl / monto)
        elif resultado == "loss":
            m.perdidas += 1
        elif resultado == "desconocido":
            m.desconocidas += 1
        else:
            m.empates += 1

    m.payout_medio = statistics.fmean(pagos) if pagos else 0.0
    m.monto_medio = m.invertido / m.total
    m.racha_ganadas, m.racha_perdidas = _rachas(ordenadas)

    (
        m.curva_balance,
        m.balance_inicial,
        m.balance_final,
        m.balance_maximo,
        m.max_caida,
        m.max_caida_pct,
    ) = _curva_y_caida(ordenadas)

    m.profundidad = _profundidades(ordenadas)

    m.por_par = sorted(
        _agrupar(ordenadas, lambda t: t.symbol), key=lambda b: b.neto, reverse=True
    )
    m.por_estrategia = sorted(
        _agrupar(ordenadas, lambda t: t.meta.get("estrategia", "")),
        key=lambda b: b.neto,
        reverse=True,
    )
    m.por_franja = sorted(
        _agrupar(ordenadas, lambda t: t.meta.get("franja") or f"{t.close_ts.hour:02d}:00"),
        key=lambda b: b.clave,
    )
    m.por_dia_semana = _ordenar_dias(
        _agrupar(ordenadas, lambda t: t.meta.get("dia_semana", ""))
    )
    m.por_dia = sorted(
        _agrupar(ordenadas, lambda t: t.close_ts.date().isoformat()),
        key=lambda b: b.clave,
    )

    m.dias_operados = len(m.por_dia)
    if m.por_dia:
        m.mejor_dia = max(m.por_dia, key=lambda b: b.neto)
        m.peor_dia = min(m.por_dia, key=lambda b: b.neto)

    return m


ORDEN_DIAS = ("lunes", "martes", "miércoles", "miercoles", "jueves",
              "viernes", "sábado", "sabado", "domingo")


def _ordenar_dias(bloques: list[BloqueBinario]) -> list[BloqueBinario]:
    """Ordena de lunes a domingo en vez de alfabeticamente."""
    def posicion(b: BloqueBinario) -> int:
        clave = b.clave.strip().lower()
        return ORDEN_DIAS.index(clave) if clave in ORDEN_DIAS else len(ORDEN_DIAS)

    return sorted(bloques, key=posicion)


def _avisos_profundidad(m: MetricasBinarias) -> list[str]:
    """Lo que dicen los datos sobre la cadena de perdidas y la martingala."""
    salida: list[str] = []
    if not m.profundidad:
        return salida

    profundo = max(p.perdidas_previas for p in m.profundidad)
    if profundo >= 2:
        arriesgada = max(m.profundidad, key=lambda p: p.monto_medio)
        salida.append(
            f"El bot encadeno hasta {profundo} perdidas seguidas en un mismo par. "
            f"Lo mas que llego a arriesgar de media en una operacion fue "
            f"{arriesgada.monto_medio:,.2f}, tras "
            f"{arriesgada.perdidas_previas} perdida(s) seguida(s)."
        )

    # El punto que no se ve solo: doblar el monto no cambia la probabilidad de
    # acertar. Si la efectividad se mantiene plana al profundizar, la martingala
    # solo esta agrandando la apuesta.
    base = next((p for p in m.profundidad if p.perdidas_previas == 0), None)
    hondas = [p for p in m.profundidad if p.perdidas_previas >= 1 and p.operaciones >= 15]
    if base and base.operaciones >= 30 and hondas:
        conjunta = sum(p.ganadas for p in hondas) / sum(p.operaciones for p in hondas) * 100
        if conjunta <= base.efectividad + 1:
            salida.append(
                f"Tras una perdida el bot acierta un {conjunta:.1f}%, frente al "
                f"{base.efectividad:.1f}% cuando parte de cero: recuperar no es "
                f"mas facil, solo se apuesta mas."
            )

    return salida


def avisos(m: MetricasBinarias) -> list[str]:
    """Problemas que conviene que el usuario vea, en orden de gravedad."""
    salida: list[str] = []
    if not m.hay_datos:
        return salida

    if m.payout_medio > 0 and m.decididas >= 30:
        if m.margen < 0:
            salida.append(
                f"La efectividad ({m.efectividad:.1f}%) esta por debajo del punto "
                f"de equilibrio ({m.punto_equilibrio:.1f}%) que exige un pago del "
                f"{m.payout_medio * 100:.0f}%. Con estos numeros, a la larga pierde."
            )
        elif m.margen < 2:
            salida.append(
                f"La efectividad ({m.efectividad:.1f}%) supera el punto de "
                f"equilibrio ({m.punto_equilibrio:.1f}%) por solo "
                f"{m.margen:.1f} puntos: margen fragil."
            )

    if m.decididas < 50:
        salida.append(
            f"Solo {m.decididas} operaciones decididas: la muestra es corta y "
            f"cualquier conclusion es provisional."
        )

    perdedores = [b for b in m.por_par if b.decididas >= 20 and not b.rentable]
    if perdedores:
        nombres = ", ".join(f"{b.clave} ({b.margen:+.1f})" for b in perdedores[:4])
        salida.append(f"Pares por debajo de su punto de equilibrio: {nombres}")

    flojas = [b for b in m.por_estrategia if b.decididas >= 20 and not b.rentable]
    if flojas:
        nombres = ", ".join(f"{b.clave} ({b.margen:+.1f})" for b in flojas[:4])
        salida.append(f"Estrategias por debajo de su punto de equilibrio: {nombres}")

    salida.extend(_avisos_profundidad(m))

    if m.desconocidas:
        salida.append(
            f"{m.desconocidas} operacion(es) sin resultado confirmado por la API, "
            f"excluidas del calculo."
        )

    if m.max_caida_pct >= 25:
        salida.append(
            f"La caida maxima del balance fue del {m.max_caida_pct:.1f}% "
            f"({m.max_caida:,.2f})."
        )

    return salida
