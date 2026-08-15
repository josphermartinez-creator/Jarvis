# Jarvis

Reportes y dashboard para tu bot de trading. Lee tus operaciones desde donde ya
las tengas, las fusiona en un único libro sin duplicados y te dice cómo va
realmente: cuánto ganas después de comisiones, dónde pierdes y cuánto riesgo
estás corriendo.

El núcleo **no tiene dependencias**: solo la librería estándar de Python. Se
instala en el mismo servidor que el bot sin arrastrar nada.

```
                 ┌── Opciones binarias ───┐
                 ├── CSV / JSON del bot ──┤        ┌── Terminal
   tu bot  ───►  ├── SQLite / Postgres ───┤─► Jarvis ─┤── Dashboard HTML
                 ├── API del exchange ────┤        ├── Dashboard en vivo
                 └── MetaTrader 5 ────────┘        └── Telegram
```

---

## Empezar

```bash
git clone https://github.com/josphermartinez-creator/Jarvis.git
cd Jarvis
pip install -e .
```

Comprueba si el archivo que ya escribe tu bot le sirve a Jarvis:

```bash
jarvis inspeccionar ~/mi-bot/operaciones.csv
```

Te dirá qué columnas reconoció, cuáles ignora y qué le falta, si es que falta
algo. Si sale `LISTO`, ya puedes pedir el reporte:

```bash
jarvis reporte --fuente ~/mi-bot/operaciones.csv --periodo mes
jarvis dashboard --fuente ~/mi-bot/operaciones.csv     # se abre en el navegador
```

---

## Opciones binarias (BOT JPH TRADING / IQ Option)

Jarvis lee directamente el `datos/historial_operaciones.csv` que escribe el bot.
No hay que configurar nada ni tocar el bot:

```bash
jarvis reporte --fuente ~/BotIFCAuto/datos/historial_operaciones.csv
jarvis dashboard --fuente ~/BotIFCAuto/datos/historial_operaciones.csv
```

Las binarias no se miden como el spot, así que el reporte es distinto. La cifra
que manda es el **punto de equilibrio**:

> Con un pago del 85%, ganas 0,85 cuando aciertas pero pierdes 1,00 cuando
> fallas. Necesitas acertar el **54,1%** solo para quedarte igual. Un bot con
> 52% de efectividad está perdiendo por construcción, aunque la racha de esta
> semana haya salido bien.

Jarvis calcula ese umbral con el pago real que te está dando el bróker y lo
compara con tu efectividad real. El resultado es un margen en puntos: positivo,
la estrategia se sostiene; negativo, a la larga pierde.

Y lo calcula **por separado para cada par y cada estrategia**, porque cada uno
paga distinto: un par al 87% necesita 53,5% de aciertos y uno al 79% necesita
55,9%. Un par puede tener mejor efectividad que otro y aun así ser el que te
está costando dinero.

Además:

- **Efectividad honesta.** Los empates y las operaciones que la API dejó como
  `desconocido` se excluyen del cálculo en vez de contarse como fallos o
  aciertos. Aparecen aparte, contadas.
- **Curva de balance real**, la que reporta el bróker, no una suma acumulada:
  si hubo depósitos o retiros, se ven.
- **Máxima caída del balance**, en dinero y en porcentaje desde el pico.
- **Desglose según pérdidas seguidas previas.** Muestra si la efectividad mejora
  al profundizar en la cadena de martingala. No mejora nunca: doblar el monto no
  cambia la probabilidad de acertar, solo agranda lo que hay en juego. El monto
  medio de cada nivel deja ver cuándo saltó tu límite de pérdidas por par y el
  bot reinició la cadena.
- **Por franja horaria y día de la semana**, con su umbral en cada fila.

La profundidad de la cadena Jarvis la deduce recorriendo el historial, no de la
columna `racha_perdidas_momento`: el bot escribe esa columna después de procesar
el resultado, así que en una operación ganadora siempre vale 0 y no dice desde
qué nivel se entró.

---

## Ver el bot en vivo

El CSV solo cuenta el pasado: una fila aparece cuando la operación **ya cerró**.
Para saber qué está pasando ahora mismo, Jarvis consulta el panel del propio bot
en `http://127.0.0.1:5000`.

```bash
jarvis vivo              # una foto del estado actual
jarvis vivo --seguir     # se refresca solo hasta que pulses Ctrl+C
```

Desde la misma PC no hace falta contraseña. Si Jarvis corre en otro equipo de tu
red, pon la del panel en `bot.password`.

Lo que ves en vivo, que el histórico no puede darte:

| | |
|---|---|
| **Estado** | si está corriendo, si sigue conectado al bróker |
| **Modo** | práctica o **dinero real** — marcado en rojo |
| **Balance** | el de ahora, no el de la última operación cerrada |
| **En juego** | dinero comprometido en operaciones abiertas en este instante |
| **Martingala** | nivel actual y cuánto sería la próxima apuesta |
| **Pares** | cuáles están operando y cuáles bloqueados por pérdidas |
| **Log** | las últimas líneas, las mismas que ves en el panel |

Y en el dashboard aparecen **las dos cosas juntas**: el estado en vivo arriba,
el análisis del histórico debajo.

```bash
jarvis dashboard
```

Si el bot está cerrado no pasa nada: sale un aviso discreto y el análisis del
histórico se muestra igual, porque sale del CSV guardado.

> Jarvis solo lee. Nunca llama a `/api/iniciar` ni a `/api/detener`: quien
> decide si el bot opera eres tú, no el panel de reportes.

---

## Qué necesita Jarvis de tu bot

**Nada especial.** Solo que deje constancia de sus operaciones en algún sitio.
Estos son los campos mínimos:

| Campo | Ejemplo | ¿Obligatorio? |
|---|---|---|
| fecha | `2026-08-14 10:32:00` | sí |
| símbolo | `BTCUSDT` | sí |
| lado | `buy` / `sell` | sí |
| cantidad | `0.05` | sí |
| precio | `62150.5` | sí |
| comisión | `0.31` | no, pero sin ella el PnL sale optimista |

**Los nombres de las columnas no importan.** Jarvis reconoce `fecha`, `date`,
`timestamp`, `hora`, `time`; `simbolo`, `symbol`, `par`, `ticker`; `cantidad`,
`qty`, `size`, `volumen`; y así con todo — en español y en inglés, con
mayúsculas, guiones bajos o espacios. Las fechas las acepta en epoch (segundos
o milisegundos), ISO, `dd/mm/aaaa` y varios formatos más. Los números, con
separador de miles europeo o anglosajón.

Si tu bot ya calcula el resultado de cada operación cerrada, mejor: Jarvis usa
ese valor directamente. Si solo registra compras y ventas sueltas, las empareja
por FIFO y calcula el PnL él mismo, incluyendo posiciones cortas, cierres
parciales y reversiones.

### Si tu bot todavía no guarda nada

Añade esto donde ejecutas las órdenes:

```python
import csv, datetime

def registrar(symbol, side, qty, price, fee=0.0, ruta="operaciones.csv"):
    nuevo = not os.path.exists(ruta)
    with open(ruta, "a", newline="") as fh:
        w = csv.writer(fh)
        if nuevo:
            w.writerow(["fecha", "simbolo", "lado", "cantidad", "precio", "comision"])
        w.writerow([
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
            symbol, side, qty, price, fee,
        ])

# y en tu código, después de cada orden ejecutada:
registrar("BTCUSDT", "buy", 0.05, 62150.5, fee=0.31)
```

Con eso Jarvis ya tiene todo lo que necesita.

---

## Fusionar varias fuentes

Esta es la parte interesante. Puedes tener el historial de tu bot de binarias
**y** el CSV de otro bot **y** la API de un exchange: Jarvis lee todas, detecta
los duplicados y deja un libro único.

Sirve para lo que más cuesta ver de otro modo: si el bot cree que ganó algo que
el exchange no confirma, la diferencia salta a la vista.

Crea tu configuración:

```bash
cp jarvis.example.yaml jarvis.yaml
```

```yaml
capital_inicial: 250
moneda: USD

fuentes:
  bot_binarias:
    tipo: iqoption
    ruta: ~/BotIFCAuto/datos/historial_operaciones.csv

  otro_bot:
    tipo: archivo
    ruta: ~/mi-bot/operaciones.csv
```

Y ya:

```bash
jarvis reporte          # usa jarvis.yaml automáticamente
jarvis fuentes          # comprueba que todas responden
```

La deduplicación usa el identificador del exchange cuando existe; si no,
compara símbolo, fechas, cantidad y precios, con un margen de 2 segundos para
absorber desfases de reloj entre fuentes. Dos órdenes iguales a propósito (un
bot de rejilla, por ejemplo) **no** se consideran duplicadas.

Si una fuente falla, el reporte se genera igual con las demás y te avisa de
cuál se cayó.

---

## Comandos

```bash
jarvis reporte                      # resumen del mes en la terminal
jarvis reporte -p hoy               # hoy, ayer, semana, mes, anio, todo, 7d, 3m
jarvis reporte -p 2026-01-01:2026-03-31
jarvis reporte --comparar           # frente al periodo anterior
jarvis reporte --html reporte.html  # genera el dashboard
jarvis reporte --breve              # solo las cifras principales

jarvis dashboard                    # dashboard en vivo, se refresca solo
jarvis dashboard --puerto 8080 --periodo semana

jarvis telegram                     # manda el resumen al móvil
jarvis telegram --adjuntar          # con el dashboard adjunto

jarvis inspeccionar datos.csv       # ¿le sirve este archivo a Jarvis?
jarvis fuentes                      # ¿responden todas las fuentes?
jarvis init                         # crea jarvis.yaml
```

Cualquier comando acepta `--fuente archivo.csv` (repetible) para saltarse la
configuración y apuntar directamente a uno o varios archivos.

---

## Qué te dice el reporte

**Resultado:** PnL bruto, comisiones pagadas y PnL neto. Las comisiones se
separan a propósito: hay bots que ganan en bruto y pierden en neto, y esa es
justo la cifra que no conviene esconder.

**Rendimiento:** aciertos, profit factor (lo ganado ÷ lo perdido), expectativa
por operación, ratio ganancia/pérdida media, Sharpe y Sortino anualizados.

**Riesgo:** máxima caída desde el pico en dinero y en porcentaje, rachas
ganadoras y perdedoras consecutivas, duración media, mejor y peor operación.

**Desglose:** por símbolo, por día, por día de la semana y por hora del día —
esta última suele revelar franjas horarias en las que el bot solo pierde.

**Posiciones abiertas:** lo que quedó sin cerrar se reporta aparte, para que el
resumen no mienta por omisión.

---

## El dashboard

`jarvis reporte --html` genera un archivo HTML **autocontenido**: sin CDN, sin
JavaScript, sin conexión a internet. Las gráficas son SVG generado directamente.
Se abre en cualquier navegador, se puede mandar por correo o guardar como
histórico, y seguirá funcionando dentro de diez años. Se adapta al tema claro u
oscuro del sistema.

`jarvis dashboard` levanta un servidor local que relee las fuentes y se refresca
solo. Escucha únicamente en `127.0.0.1`: el reporte contiene tu historial de
operaciones, así que no lo expongas a internet sin poner algo delante que lo
proteja.

---

## Reportes automáticos

Resumen diario a las 23:00 por Telegram, con `cron`:

```cron
0 23 * * * cd ~/Jarvis && /usr/bin/jarvis telegram --periodo hoy
0 9 * * 1 cd ~/Jarvis && /usr/bin/jarvis telegram --periodo semana --adjuntar
```

Para configurar Telegram: crea un bot con [@BotFather](https://t.me/BotFather),
guarda el token, escríbele algo a tu bot y saca tu `chat_id` de
`https://api.telegram.org/bot<TOKEN>/getUpdates`. Ponlos como variables de
entorno (`TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`) — nunca escritos en el
archivo de configuración.

---

## Seguridad

- Las claves de API se leen del entorno con `${VARIABLE}`, no del archivo.
- **Usa claves de solo lectura.** Jarvis nunca manda órdenes, pero si le das una
  clave con permiso de trading estás asumiendo un riesgo innecesario.
- Las bases de datos se abren en modo solo lectura.
- `jarvis.yaml` está en `.gitignore`.

---

## Como librería

```python
from jarvis import analizar, reporte

print(reporte("operaciones.csv", periodo="mes"))

metricas, libro = analizar("operaciones.csv", periodo="7d")
print(metricas.pnl_neto, metricas.winrate, metricas.max_drawdown)

for bloque in metricas.por_simbolo:
    print(bloque.clave, bloque.pnl, bloque.operaciones)
```

---

## Desarrollo

```bash
pip install -e ".[dev]"
python -m pytest
```

## Extras opcionales

```bash
pip install "jarvis-trading[yaml]"      # lector YAML completo
pip install "jarvis-trading[postgres]"  # fuente PostgreSQL
pip install "jarvis-trading[mysql]"     # fuente MySQL
```

Para MetaTrader 5 en modo directo hace falta `pip install MetaTrader5` (solo
Windows, con el terminal abierto). Desde cualquier otro sistema, exporta el
informe desde la pestaña Historial del terminal y usa el modo `informe`.
