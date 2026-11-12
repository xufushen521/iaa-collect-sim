"""Core engine for the IAA collect match-three project."""

from .loader import load_config, validate_config
from .model import GameState, Tile, generate_tiles
from .simulator import simulate_campaign, simulate_experiment, simulate_level

__all__ = [
    "GameState",
    "Tile",
    "generate_tiles",
    "load_config",
    "validate_config",
    "simulate_campaign",
    "simulate_experiment",
    "simulate_level",
]
