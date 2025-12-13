"""
Hauptdatei: Startet das isometrische Test-Spiel
"""
from adapter.game_loop import GameLoop


def main():
    """Hauptfunktion"""
    game_loop = GameLoop()
    game_loop.run()


if __name__ == "__main__":
    main()

