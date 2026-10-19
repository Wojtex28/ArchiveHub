"""Ustawienia dla testów: tryb deweloperski, reszta jak w produkcji."""

import os

os.environ.setdefault("DJANGO_DEBUG", "1")

from .settings import *  # noqa: E402, F403
