"""Pluggable Vergleichs-Engines für ``/api/compare``."""

from .base import Engine, EngineResult
from .registry import available_engines, build_engine

__all__ = ["Engine", "EngineResult", "available_engines", "build_engine"]
