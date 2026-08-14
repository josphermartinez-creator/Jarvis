"""Salidas de Jarvis: terminal, HTML, Telegram."""

from __future__ import annotations

from .console import render as render_consola
from .formato import dinero, duracion, pct

__all__ = ["dinero", "duracion", "pct", "render_consola"]
