"""La linea de comandos y el diagnostico de archivos."""

from __future__ import annotations

import pytest

from jarvis.cli import main
from jarvis.inspect import formatear, inspeccionar

CSV = """\
fecha,simbolo,lado,cantidad,precio,comision
2026-03-02 09:00:00,BTCUSDT,buy,1,100,0.1
2026-03-02 10:00:00,BTCUSDT,sell,1,110,0.11
2026-03-02 11:00:00,ETHUSDT,buy,2,50,0.05
2026-03-02 12:00:00,ETHUSDT,sell,2,48,0.048
"""


@pytest.fixture
def csv_ops(tmp_path):
    ruta = tmp_path / "ops.csv"
    ruta.write_text(CSV, encoding="utf-8")
    return ruta


# -- inspeccionar ---------------------------------------------------------

def test_inspeccionar_reconoce_un_csv_valido(csv_ops):
    diag = inspeccionar(csv_ops)

    assert diag.sirve
    assert diag.formato == "csv"
    assert diag.filas == 4
    assert diag.detectado["symbol"] == "simbolo"
    assert not diag.faltan


def test_inspeccionar_avisa_de_lo_que_falta(tmp_path):
    ruta = tmp_path / "incompleto.csv"
    ruta.write_text("simbolo,precio\nBTCUSDT,100\n", encoding="utf-8")

    diag = inspeccionar(ruta)

    assert not diag.sirve
    assert "side" in diag.faltan
    assert "qty" in diag.faltan


def test_el_diagnostico_sugiere_como_configurar_lo_que_falta(tmp_path):
    ruta = tmp_path / "incompleto.csv"
    ruta.write_text("simbolo,precio\nBTCUSDT,100\n", encoding="utf-8")

    texto = formatear(inspeccionar(ruta))

    assert "FALTA" in texto
    assert "columnas:" in texto
    assert "NOMBRE_DE_TU_COLUMNA" in texto


def test_el_diagnostico_confirma_cuando_todo_esta_bien(csv_ops):
    texto = formatear(inspeccionar(csv_ops))

    assert "LISTO" in texto
    assert "jarvis reporte --fuente" in texto


def test_inspeccionar_detecta_una_columna_de_fecha_invalida(tmp_path):
    ruta = tmp_path / "malas_fechas.csv"
    ruta.write_text(
        "fecha,simbolo,lado,cantidad,precio\n"
        "el lunes,BTCUSDT,buy,1,100\n",
        encoding="utf-8",
    )

    diag = inspeccionar(ruta)
    assert any("fecha valida" in p for p in diag.problemas)


def test_inspeccionar_avisa_si_no_hay_comisiones(tmp_path):
    ruta = tmp_path / "sin_comision.csv"
    ruta.write_text(
        "fecha,simbolo,lado,cantidad,precio\n"
        "2026-03-02 09:00:00,BTCUSDT,buy,1,100\n",
        encoding="utf-8",
    )

    diag = inspeccionar(ruta)
    assert any("comisiones" in p for p in diag.problemas)


def test_inspeccionar_un_archivo_que_no_existe(tmp_path):
    diag = inspeccionar(tmp_path / "fantasma.csv")

    assert not diag.sirve
    assert any("no existe" in p for p in diag.problemas)


def test_inspeccionar_un_archivo_vacio(tmp_path):
    ruta = tmp_path / "vacio.csv"
    ruta.write_text("", encoding="utf-8")

    diag = inspeccionar(ruta)
    assert not diag.sirve


# -- comandos -------------------------------------------------------------

def test_reporte_desde_un_archivo(csv_ops, capsys):
    codigo = main(["reporte", "-f", str(csv_ops), "-p", "todo", "--sin-color"])
    salida = capsys.readouterr().out

    assert codigo == 0
    assert "JARVIS" in salida
    assert "Operaciones" in salida


def test_reporte_escribe_el_dashboard(csv_ops, tmp_path):
    destino = tmp_path / "sub" / "dash.html"
    codigo = main([
        "reporte", "-f", str(csv_ops), "-p", "todo",
        "--html", str(destino), "--silencioso",
    ])

    assert codigo == 0
    assert destino.exists()
    assert destino.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_se_pueden_fusionar_varios_archivos(tmp_path, capsys):
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_text(CSV, encoding="utf-8")
    b.write_text(
        "fecha,simbolo,lado,cantidad,precio,comision\n"
        "2026-03-03 09:00:00,SOLUSDT,buy,10,20,0.02\n"
        "2026-03-03 10:00:00,SOLUSDT,sell,10,22,0.022\n",
        encoding="utf-8",
    )

    codigo = main(["reporte", "-f", str(a), "-f", str(b), "-p", "todo", "--sin-color"])
    salida = capsys.readouterr().out

    assert codigo == 0
    assert "SOLUSDT" in salida
    assert "BTCUSDT" in salida


def test_inspeccionar_desde_la_linea_de_comandos(csv_ops, capsys):
    assert main(["inspeccionar", str(csv_ops)]) == 0
    assert "LISTO" in capsys.readouterr().out


def test_inspeccionar_devuelve_error_si_el_archivo_no_sirve(tmp_path, capsys):
    ruta = tmp_path / "malo.csv"
    ruta.write_text("a,b\n1,2\n", encoding="utf-8")

    assert main(["inspeccionar", str(ruta)]) == 1


def test_init_crea_la_configuracion(tmp_path, capsys):
    destino = tmp_path / "jarvis.yaml"
    assert main(["init", "-o", str(destino)]) == 0
    assert destino.exists()
    assert "fuentes:" in destino.read_text(encoding="utf-8")


def test_init_no_pisa_un_archivo_existente(tmp_path):
    destino = tmp_path / "jarvis.yaml"
    destino.write_text("mio: si\n", encoding="utf-8")

    assert main(["init", "-o", str(destino)]) == 1
    assert destino.read_text(encoding="utf-8") == "mio: si\n"


def test_init_con_forzar_si_sobrescribe(tmp_path):
    destino = tmp_path / "jarvis.yaml"
    destino.write_text("mio: si\n", encoding="utf-8")

    assert main(["init", "-o", str(destino), "--forzar"]) == 0
    assert "fuentes:" in destino.read_text(encoding="utf-8")


def test_fuentes_comprueba_que_responden(csv_ops, capsys):
    codigo = main(["fuentes", "-f", str(csv_ops)])
    salida = capsys.readouterr().out

    assert codigo == 0
    assert "OK" in salida
    assert "4 ejecuciones" in salida


def test_un_periodo_invalido_da_error_claro(csv_ops, capsys):
    codigo = main(["reporte", "-f", str(csv_ops), "-p", "cuando sea"])

    assert codigo == 1
    assert "periodo desconocido" in capsys.readouterr().err


def test_sin_fuentes_explica_las_opciones(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    with pytest.raises(SystemExit) as e:
        main(["reporte"])

    assert "jarvis init" in str(e.value)


def test_sin_argumentos_muestra_la_ayuda(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert main([]) == 0
    assert "reporte" in capsys.readouterr().out
