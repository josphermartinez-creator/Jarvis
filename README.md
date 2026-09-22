# Jarvis

## Viaje infinito — video de 30 segundos

Animación de un viaje continuo por un universo imaginario: estrellas con movimiento en perspectiva, cinco planetas, anillos, galaxias y nubes de gas. Formato vertical **1080 × 1920**, **30 fps**, sin texto, con ambiente sonoro original.

El movimiento es periódico cada 30 segundos: la cámara nunca se detiene y el final conecta con el inicio al reproducir el archivo en bucle. Es una composición artística; los tamaños y las distancias de los cuerpos celestes no están a escala astronómica.

### Resultado

- `exports/viaje-infinito.mp4`: video H.264 / AAC, compatible con navegadores y teléfonos.
- `exports/viaje-infinito.jpg`: imagen de portada.

El MP4 y su portada están incluidos en esta rama del repositorio para poder descargarlos sin ejecutar código. Las exportaciones alternativas se mantienen fuera de Git.

**[Descargar el video MP4](https://github.com/josphermartinez-creator/Jarvis/raw/refs/heads/arena/01a0c9ee-jarvis/exports/viaje-infinito.mp4)**

### Verlo en un reproductor

```bash
python3 serve_video.py --port 8080
```

Abre la vista previa del puerto 8080. Muestra un reproductor con sonido opcional, repetición continua y un botón para descargar el MP4. El servidor escucha en `0.0.0.0`, soporta peticiones por rangos para poder adelantar el video y solo expone el reproductor y los archivos multimedia, nunca `.git` ni otros archivos del proyecto.

### Recrear el video

Requiere Python 3.11 o posterior. No necesita GPU, claves de API ni una instalación del sistema de FFmpeg: `imageio-ffmpeg` incluye su propio ejecutable para las plataformas compatibles.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python render_video.py
```

Para una versión más pequeña o sin sonido:

```bash
.venv/bin/python render_video.py --width 720 --height 1280 --silent \
  --output exports/viaje-infinito-720p.mp4
```

Las dimensiones deben ser pares. La duración siempre es de 30 segundos. El archivo MP4 se prepara con `faststart` para comenzar a reproducirse sin descargarlo por completo.

### Vista previa y pruebas

```bash
.venv/bin/python render_video.py --preview
.venv/bin/python -m unittest discover -s tests -v
```

La vista previa crea una hoja de contacto en `.cache/space-flight/` y verifica que el fotograma de los 30 segundos coincida exactamente con el de los 0 segundos. Las pruebas también comprueban el movimiento y la continuidad en la unión del bucle.

### Composición

- `assets/nebula-source.jpg` y `assets/galaxy-source.jpg` son imágenes generadas con IA para esta pieza; no son fotografías de una misión espacial.
- Los planetas, sus texturas, iluminación, atmósferas y anillos se generan por código.
- Las estrellas se proyectan desde coordenadas 3D, con paralaje y pequeñas estelas de movimiento.
- Las capas de nebulosa se expanden continuamente y se reciclan cuando su opacidad es cero.
- El audio se sintetiza de forma original con ondas y ruido filtrado; no contiene voz ni grabaciones de terceros.
- Los fotogramas se envían directamente al codificador, sin almacenar cientos de imágenes en disco.
