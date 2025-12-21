"""
Core: GameState - Enum für Game States
"""
from enum import Enum


class GameState(Enum):
    """Game States"""
    WORLD_SELECT = "world_select"
    CREATE_WORLD = "create_world"
    INGAME = "ingame"
    PAUSED = "paused"
    SETTINGS = "settings"
    INVENTORY = "inventory"


