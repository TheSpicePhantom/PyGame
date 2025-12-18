# Sprite Editor Tool

Ein flexibler Sprite Editor für 8x8 und 16x16 Pixel Sprites mit dynamischer Farbpalette und Live-Vorschau.

## Features

- **8x8 und 16x16 Modi**: Umschaltbar per Dropdown
- **Paste-freundlich**: Einfach Muster kopieren und einfügen
- **Live-Vorschau**: Änderungen werden automatisch nach 500ms angezeigt
- **Dynamische Farbpalette**: Automatische Erkennung verwendeter Indizes
- **Color Picker**: Klicken Sie auf Farben, um sie anzupassen
- **Grid-Ansicht**: 512x512 Pixel Vorschau mit Raster
- **PNG Export**: Speichert Original (8x8/16x16) + skalierte Version (512x512)
- **Tiling-Ready**: 8x8 Sprites perfekt für gekachelte Texturen

## Installation

```bash
# Benötigte Pakete (sollten bereits installiert sein)
pip install pillow
```

## Verwendung

```bash
python tools/sprite_editor.py
```

## Bedienung

### 1. Text-Eingabe (Paste-freundlich)
Das Tool akzeptiert verschiedene Formate:

```
R1: 1 1 2 1 1 2 1 1 2 1 1 2 1 1 2 1
R2: 1 2 1 1 2 1 1 1 2 1 1 1 2 1 1 1
...
```

Oder:
```
Row01: 1 1 2 1 1 2 1 1 2 1 1 2 1 1 2 1
Row02: 1 2 1 1 2 1 1 1 2 1 1 1 2 1 1 1
...
```

Oder einfach:
```
1 1 2 1 1 2 1 1 2 1 1 2 1 1 2 1
1 2 1 1 2 1 1 1 2 1 1 1 2 1 1 1
...
```

- Einfach kopieren und einfügen!
- Die Vorschau aktualisiert sich automatisch nach 500ms
- Jede Zahl repräsentiert einen Farbindex

### 2. Farbpalette
- **Detect Colors**: Erkennt alle verwendeten Indizes automatisch
- **Color Picker**: Klicken Sie auf eine Farbe, um sie zu ändern
- Farben werden als Hex-Code mit Alpha-Kanal gespeichert

### 3. Standard-Palette

| Index | Farbe | Hex Code | Verwendung |
|-------|-------|----------|------------|
| 0 | Dunkelgrün | #1E4E1FFF | Schatten, Bodentiefe |
| 1 | Grundgrün | #348C31FF | Hauptfläche |
| 2 | Hellgrün | #5CAF28FF | Beleuchtete Halme |
| 3 | Highlight | #79D021FF | Spitzen-Highlights |

## Buttons

- **Update Preview**: Manuelle Aktualisierung der Vorschau
- **Clear All**: Alle Eingabefelder leeren
- **Detect Colors**: Automatische Erkennung verwendeter Farbindizes
- **Save PNG**: Sprite als PNG speichern (16x16 + 512x512)

## Workflow

1. **Sprite-Daten pasten**: Kopieren Sie Ihr Muster und fügen Sie es ein
2. **Farben erkennen**: "Detect Colors" klicken (automatisch)
3. **Farben anpassen**: Auf Farbfelder klicken und neue Farben wählen
4. **Speichern**: "Save PNG" für Export

## Beispiel-Eingabe

### 8x8 Sprite (Standard):
```
R1: 1 1 2 1 1 2 1 1
R2: 1 2 1 1 2 1 1 1
R3: 1 1 1 2 1 1 2 1
R4: 1 1 2 1 1 1 1 2
R5: 1 1 1 1 1 2 1 1
R6: 1 0 1 1 1 1 0 1
R7: 1 1 0 1 1 0 1 1
R8: 0 1 1 0 1 1 1 0
```

### 16x16 Sprite:
```
R1: 1 1 2 1 1 2 1 1 2 1 1 2 1 1 2 1
R2: 1 2 1 1 2 1 1 1 2 1 1 1 2 1 1 1
... (14 weitere Zeilen)
```

Das Tool lädt automatisch ein Beispiel-Sprite beim Start.

## Warum 8x8?

- **Kleine Dateigröße**: 8x8 Sprites sind nur 64 Pixel
- **Tiling-perfekt**: Nahtlos kachelbar für Texturen
- **Performance**: Schnelleres Laden und Rendering
- **Skalierbar**: Im Spiel auf beliebige Größe skalieren (16x16, 32x32, etc.)
- **Retro-Look**: Klassischer Pixel-Art-Stil

## Tipps

- **Copy & Paste**: Einfach Muster aus anderen Tools einfügen
- **Format-Flexibilität**: R1:, Row01:, oder ohne Prefix - alles funktioniert
- **Auto-Update**: Die Vorschau aktualisiert sich automatisch
- **Grid-Ansicht**: 32x vergrößerte Vorschau mit Pixel-Raster
- **Beliebige Indizes**: Verwenden Sie 0-15 oder mehr
- **Leere Zeilen**: Werden automatisch ignoriert
