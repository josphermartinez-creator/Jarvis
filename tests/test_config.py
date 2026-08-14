"""Configuracion: sin PyYAML instalado tambien tiene que funcionar."""

from __future__ import annotations

import pytest

from jarvis.config import Config, _yaml_minimo, buscar_config, cargar

EJEMPLO = """\
# comentario inicial
capital_inicial: 5000
moneda: EUR

fuentes:
  mi_bot:
    tipo: archivo
    ruta: ~/bot/ops.csv
  binance:
    tipo: binance
    api_key: ${MI_CLAVE}
    simbolos: [BTCUSDT, ETHUSDT]

telegram:
  token: ${MI_TOKEN}
"""


def test_el_lector_minimo_entiende_la_plantilla():
    datos = _yaml_minimo(EJEMPLO)

    assert datos["capital_inicial"] == 5000
    assert datos["moneda"] == "EUR"
    assert datos["fuentes"]["mi_bot"]["tipo"] == "archivo"
    assert datos["fuentes"]["binance"]["simbolos"] == ["BTCUSDT", "ETHUSDT"]


def test_el_lector_minimo_ignora_los_comentarios():
    datos = _yaml_minimo("moneda: USDT  # esto es un comentario\n")
    assert datos["moneda"] == "USDT"


def test_las_variables_de_entorno_se_sustituyen(monkeypatch):
    monkeypatch.setenv("MI_CLAVE", "clave-secreta")
    config = Config.desde_dict(_yaml_minimo(EJEMPLO))

    assert config.fuentes["binance"]["api_key"] == "clave-secreta"


def test_una_variable_sin_definir_queda_vacia(monkeypatch):
    monkeypatch.delenv("MI_TOKEN", raising=False)
    config = Config.desde_dict(_yaml_minimo(EJEMPLO))

    assert config.telegram["token"] == ""


def test_cargar_un_archivo_de_configuracion(tmp_path):
    ruta = tmp_path / "jarvis.yaml"
    ruta.write_text(EJEMPLO, encoding="utf-8")

    config = cargar(ruta)

    assert config.capital_inicial == 5000
    assert config.moneda == "EUR"
    assert len(config.fuentes) == 2
    assert config.ruta == ruta


def test_sin_configuracion_se_usan_los_valores_por_defecto(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    config = cargar()

    assert config.fuentes == {}
    assert config.moneda == "USDT"


def test_una_ruta_inexistente_indicada_a_mano_falla(tmp_path):
    with pytest.raises(FileNotFoundError):
        cargar(tmp_path / "no_existe.yaml")


def test_la_configuracion_se_busca_hacia_arriba(tmp_path, monkeypatch):
    (tmp_path / "jarvis.yaml").write_text(EJEMPLO, encoding="utf-8")
    hondo = tmp_path / "a" / "b" / "c"
    hondo.mkdir(parents=True)
    monkeypatch.chdir(hondo)

    assert buscar_config() == tmp_path / "jarvis.yaml"


def test_la_plantilla_generada_es_valida():
    from jarvis.config import PLANTILLA

    config = Config.desde_dict(_yaml_minimo(PLANTILLA))

    assert config.capital_inicial == 1000
    assert "bot_binarias" in config.fuentes
    assert config.fuentes["bot_binarias"]["tipo"] == "iqoption"
    # Solo la primera fuente viene activa; el resto son ejemplos comentados.
    assert len(config.fuentes) == 1
