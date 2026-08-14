# Jarvis

Reportes y dashboard para tu bot de trading. Lee tus operaciones desde donde ya
las tengas, las fusiona en un único libro sin duplicados y te dice cómo va
realmente: cuánto ganas después de comisiones, dónde pierdes y cuánto riesgo
estás corriendo.

El núcleo **no tiene dependencias**: solo la librería estándar de Python. Se
instala en el mismo servidor que el bot sin arrastrar nada.

```
                 ┌── CSV / JSON del bot ──┐
                 ├── SQLite / Postgres ───┤        ┌── Terminal
   tu bot  ───►  ├── API del exchange ────┤─► Jarvis ─┤── Dashboard HTML
                 └── MetaTrader 5 ────────┘        ├── Dashboard en vivo
                                                   └── Telegram
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

Esta es la parte interesante. Puedes tener el CSV de tu bot **y** la API del
exchange apuntando a las mismas operaciones: Jarvis lee ambas, detecta los
duplicados y deja un libro único.

Sirve para lo que más cuesta ver de otro modo: si el bot cree que ganó algo que
el exchange no confirma, la diferencia salta a la vista.

Crea tu configuración:

```bash
cp jarvis.example.yaml jarvis.yaml
```

```yaml
capital_inicial: 1000
moneda: USDT

fuentes:
  mi_bot:
    tipo: archivo
    ruta: ~/mi-bot/operaciones.csv

  binance:
    tipo: binance
    api_key: ${BINANCE_API_KEY}
    api_secret: ${BINANCE_API_SECRET}
    simbolos: [BTCUSDT, ETHUSDT]
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
