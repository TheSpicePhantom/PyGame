# Isometrisches Test-Spiel mit Pygame

Ein kleines Test-Spiel mit isometrischer Ansicht, erstellt mit Pygame.

## Projektstruktur

Das Projekt folgt dem MVA-Prinzip (Model, View, Adapter):

### Model
- `model/map.py` - Karten-Logik (10x10 Felder)
- `model/player.py` - Spieler-Logik mit Position und Bewegung
- `model/game.py` - Haupt-Spiellogik, verwaltet alle Spielelemente

### View
- `view/isometric.py` - Isometrische Projektion und Koordinatenumrechnung
- `view/renderer.py` - Haupt-Rendering-Engine

### Adapter
- `adapter/input_handler.py` - Tastatureingaben (WASD-Steuerung)
- `adapter/game_loop.py` - Haupt-Spielloop und Event-Management

### Konfiguration
- `config/game_config.json` - Spielkonfiguration (Fenster, Karte, Spieler, isometrische Einstellungen)
- `data/game_data.json` - Spielstand-Datenmodell

## Features

- ✅ Isometrische Ansicht
- ✅ WASD-Steuerung für den Charakter
- ✅ Grüner Block als Spieler
- ✅ 10x10 Karte mit frei begehbaren Feldern
- ✅ MVA-Architektur für Übersichtlichkeit und Wiederverwendbarkeit

## Installation

1. Pygame installieren:
```bash
pip install pygame
```

## Ausführung

```bash
python main.py
```

## Steuerung

- **W** - Nach oben bewegen
- **S** - Nach unten bewegen
- **A** - Nach links bewegen
- **D** - Nach rechts bewegen

## Architektur

### Model-Schicht
Verwaltet die Spiellogik und Datenstrukturen:
- `Map`: Verwaltet die 10x10 Karte
- `Player`: Verwaltet Spielerposition und Bewegung
- `Game`: Haupt-Spielklasse, koordiniert alle Model-Komponenten

### View-Schicht
Verwaltet das Rendering:
- `IsometricRenderer`: Konvertiert kartesische in isometrische Koordinaten
- `Renderer`: Zeichnet Karte und Spieler auf den Bildschirm

### Adapter-Schicht
Verwaltet Input und Events:
- `InputHandler`: Verarbeitet Tastatureingaben (WASD)
- `GameLoop`: Haupt-Loop, koordiniert Update und Render

## Konfiguration

Die Spielparameter können in `config/game_config.json` angepasst werden:
- Fenstergröße
- Kartengröße
- Spielerfarbe und -größe
- Bewegungsgeschwindigkeit
- Isometrische Tile-Dimensionen





