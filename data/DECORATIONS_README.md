# Decorations, Tags & Loot Tables - Vollständige Anleitung

Diese Anleitung erklärt, wie du neue Decorations, Tags und Loot Tables zum Spiel hinzufügst.

## 📁 Datei-Struktur

```
data/
├── tags/
│   ├── harvestable.json
│   ├── mineable.json
│   └── decorative.json
├── decorations/
│   └── core/              # Mod-Ordner (z.B. "core", "seasonal", etc.)
│       ├── berry_bush.json
│       ├── oak_tree.json
│       └── stone_rock.json
├── loot_tables/
│   ├── berry_bush_loot.json
│   ├── oak_tree_loot.json
│   └── stone_rock_loot.json
└── biomes/
    ├── forest.json
    ├── plains.json
    └── mountains.json
```

---

## 🏷️ 1. Tags System

Tags kategorisieren Decorations und ermöglichen logische Gruppierungen.

### Tag-Datei erstellen

**Datei:** `data/tags/{tag_name}.json`

```json
{
  "tag_id": "harvestable",
  "description": "Can be harvested by right-clicking (berries, fruits, etc.)",
  "members": [
    "berry_bush",
    "apple_tree",
    "wheat_field"
  ]
}
```

### Felder

- **`tag_id`** (string, erforderlich): Eindeutige Tag-ID (z.B. "harvestable", "mineable")
- **`description`** (string, optional): Beschreibung des Tags
- **`members`** (array, erforderlich): Liste von `decoration_id`s, die diesen Tag haben

### Verwendung in Decorations

Tags werden in der Decoration-Datei referenziert:

```json
{
  "decoration_id": "berry_bush",
  "tags": ["harvestable", "decorative"]
}
```

### Verfügbare Tags (Beispiele)

- **`harvestable`**: Kann geerntet werden (Right-Click)
- **`mineable`**: Kann abgebaut werden (Left-Click + Hold)
- **`decorative`**: Nur dekorativ, keine Interaktion
- **`resource`**: Ressourcen-Quelle (Ore, etc.)

---

## 🎁 2. Loot Tables

Loot Tables definieren, welche Items beim Ernten/Abbauen fallen.

### Loot Table-Datei erstellen

**Datei:** `data/loot_tables/{loot_table_name}.json`

```json
{
  "loot_table_id": "berry_bush_loot",
  "description": "Drops from harvesting berry bushes",
  "rolls": 1,
  "entries": [
    {
      "item_id": "berries",
      "weight": 100,
      "quantity": {
        "min": 2,
        "max": 4
      },
      "conditions": []
    },
    {
      "item_id": "seeds",
      "weight": 30,
      "quantity": {
        "min": 1,
        "max": 2
      },
      "conditions": [
        {
          "type": "random_chance",
          "chance": 0.3
        }
      ]
    }
  ]
}
```

### Felder

#### Top-Level

- **`loot_table_id`** (string, erforderlich): Eindeutige Loot Table-ID
- **`description`** (string, optional): Beschreibung
- **`rolls`** (integer, optional): Anzahl der Würfe (Standard: 1)
- **`entries`** (array, erforderlich): Liste von Loot-Einträgen

#### Entry-Felder

- **`item_id`** (string, erforderlich): Item-ID, die gedroppt wird
- **`weight`** (integer, erforderlich): Gewichtung für Wahrscheinlichkeit (höher = häufiger)
- **`quantity`** (object, erforderlich):
  - **`min`** (integer): Minimale Anzahl
  - **`max`** (integer): Maximale Anzahl
- **`conditions`** (array, optional): Liste von Bedingungen

#### Conditions

**`random_chance`**: Zufällige Chance (0.0-1.0)

```json
{
  "type": "random_chance",
  "chance": 0.3
}
```

### Beispiel: Komplexe Loot Table

```json
{
  "loot_table_id": "oak_tree_loot",
  "description": "Drops from cutting down oak trees",
  "rolls": 1,
  "entries": [
    {
      "item_id": "wood",
      "weight": 100,
      "quantity": {
        "min": 3,
        "max": 6
      }
    },
    {
      "item_id": "apple",
      "weight": 30,
      "quantity": {
        "min": 1,
        "max": 2
      },
      "conditions": [
        {
          "type": "random_chance",
          "chance": 0.3
        }
      ]
    },
    {
      "item_id": "stick",
      "weight": 50,
      "quantity": {
        "min": 1,
        "max": 3
      },
      "conditions": [
        {
          "type": "random_chance",
          "chance": 0.5
        }
      ]
    }
  ]
}
```

---

## 🌳 3. Decorations

Decorations sind Objekte in der Welt (Bäume, Büsche, Steine, etc.).

### Decoration-Datei erstellen

**Datei:** `data/decorations/{mod_id}/{decoration_id}.json`

**Beispiel:** `data/decorations/core/berry_bush.json`

### Vollständige Struktur

```json
{
  "decoration_id": "berry_bush",
  "display_name": "Berry Bush",
  "mod_id": "core",
  "tags": ["harvestable", "decorative"],
  "collision": {
    "enabled": false,
    "type": "none",
    "radius": 0.0
  },
  "health": 0,
  "sprites": {
    "with_fruit": "berry_bush_2",
    "without_fruit": "berry_bush_1"
  },
  "rendering": {
    "size": [32, 32],
    "offset": [0, 0],
    "layer": 10,
    "bounding_box": [16, 16],
    "shadow": {
      "enabled": true,
      "sprite": "shadow_small",
      "offset": [0, 0]
    }
  },
  "animation": {
    "enabled": false,
    "type": "none",
    "speed": 1.0,
    "amplitude": 0.0
  },
  "harvest": {
    "enabled": true,
    "loot_table": "berry_bush_loot",
    "regrowth": {
      "min_time": 30.0,
      "max_time": 180.0
    }
  },
  "mining": {
    "tool_required": "axe",
    "mining_time": 3.0,
    "durability": 100,
    "loot_table": "oak_tree_loot",
    "particles": {
      "hit": "wood_particle",
      "break": "wood_break"
    }
  },
  "placement": {
    "biomes": ["terrain:forest", "terrain:plains"],
    "density": 1,
    "noise_threshold": {
      "min": 0.3,
      "max": 0.7
    },
    "clustering": {
      "enabled": true,
      "cluster_size": 5,
      "cluster_radius": 3
    }
  }
}
```

### Felder im Detail

#### Basis-Felder

- **`decoration_id`** (string, erforderlich): Eindeutige ID (z.B. "berry_bush", "oak_tree")
- **`display_name`** (string, erforderlich): Anzeigename im Spiel
- **`mod_id`** (string, erforderlich): Mod-Identifier (z.B. "core", "seasonal")
- **`tags`** (array, optional): Liste von Tag-IDs (z.B. ["harvestable", "decorative"])
- **`health`** (integer, optional): Lebenspunkte (0 = unzerstörbar, Standard: 0)

#### Collision

Definiert Kollisionsverhalten:

```json
"collision": {
  "enabled": true,
  "type": "circle",      // "circle", "rectangle", "none"
  "radius": 0.3          // In Tiles (0.3 = 30% des Tiles)
}
```

- **`enabled`** (boolean): Ob Kollision aktiviert ist
- **`type`** (string): Kollisionstyp ("circle", "rectangle", "none")
- **`radius`** (float): Radius in Tiles (nur bei "circle")

#### Sprites

Definiert Sprite-Namen für verschiedene Zustände:

```json
"sprites": {
  "default": "oak_tree",
  "with_fruit": "berry_bush_2",
  "without_fruit": "berry_bush_1",
  "damaged_50": "oak_tree_damaged",
  "stump": "oak_tree_stump"
}
```

**Sprite-Namen:**
- **`default`**: Standard-Sprite (immer erforderlich)
- **`with_fruit`**: Mit Früchten (für harvestable)
- **`without_fruit`**: Ohne Früchte (für harvestable)
- **`damaged_50`**: Bei 50% Gesundheit (für mineable)
- **`stump`**: Stumpf/Überrest (für mineable)

**Sprite-Dateien müssen hier liegen:**
```
assets/decorations/{mod_id}/{sprite_name}.png
```

**Beispiel:**
- `assets/decorations/core/berry_bush_2.png`
- `assets/decorations/core/oak_tree.png`

#### Rendering

Definiert visuelle Darstellung:

```json
"rendering": {
  "size": [32, 32],           // [width, height] in Pixeln
  "offset": [0, 0],           // [x, y] Offset vom Tile-Zentrum
  "layer": 10,                // Rendering-Layer (höher = weiter oben)
  "bounding_box": [16, 16],   // [width, height] für Maus-Auswahl
  "shadow": {
    "enabled": true,
    "sprite": "shadow_small",  // Shadow-Sprite-Name
    "offset": [0, 0]           // Shadow-Offset
  }
}
```

- **`size`** (array): Sprite-Größe in Pixeln `[width, height]`
- **`offset`** (array): Offset vom Tile-Zentrum `[x, y]` (negativ Y = höher)
- **`layer`** (integer): Rendering-Layer (0=Tiles, 5=Shadows, 10=Decorations, 20=Player)
- **`bounding_box`** (array, optional): Maus-Auswahl-Box `[width, height]` (Standard: `size`)
- **`shadow`** (object, optional):
  - **`enabled`** (boolean): Ob Shadow gerendert wird
  - **`sprite`** (string): Shadow-Sprite-Name
  - **`offset`** (array): Shadow-Offset `[x, y]`

#### Animation

Definiert Animationen (aktuell Platzhalter für zukünftige Features):

```json
"animation": {
  "enabled": false,
  "type": "none",        // "sway", "pulse", "glow", "rotate", "none"
  "speed": 1.0,          // Animations-Geschwindigkeit
  "amplitude": 0.0       // Amplitude in Pixeln
}
```

#### Harvest

Definiert Ernte-Verhalten (Right-Click):

```json
"harvest": {
  "enabled": true,
  "loot_table": "berry_bush_loot",
  "regrowth": {
    "min_time": 30.0,    // Minimale Regrowth-Zeit (Sekunden)
    "max_time": 180.0    // Maximale Regrowth-Zeit (Sekunden)
  }
}
```

- **`enabled`** (boolean): Ob Harvest aktiviert ist
- **`loot_table`** (string): Loot Table-ID
- **`regrowth`** (object, erforderlich wenn enabled):
  - **`min_time`** (float): Minimale Regrowth-Zeit in Sekunden
  - **`max_time`** (float): Maximale Regrowth-Zeit in Sekunden

**Regrowth-Mechanik:**
- Nach dem Ernten wird `has_fruit = false` gesetzt
- Ein zufälliger Timer zwischen `min_time` und `max_time` startet
- Während des Timers wird eine Progress-Bar angezeigt
- Nach Ablauf wird `has_fruit = true` und das Sprite wechselt zu `with_fruit`

#### Mining

Definiert Abbau-Verhalten (Left-Click + Hold):

```json
"mining": {
  "tool_required": "axe",      // "axe", "pickaxe", "hand", etc.
  "mining_time": 3.0,          // Zeit bis Abbau abgeschlossen (Sekunden)
  "durability": 100,            // Lebenspunkte (wird durch Mining reduziert)
  "loot_table": "oak_tree_loot",
  "particles": {
    "hit": "wood_particle",     // Partikel beim Treffen
    "break": "wood_break"       // Partikel beim Zerstören
  }
}
```

- **`tool_required`** (string, optional): Benötigtes Werkzeug (null = kein Werkzeug)
- **`mining_time`** (float): Zeit bis Abbau abgeschlossen (Sekunden)
- **`durability`** (integer): Lebenspunkte (wird durch Mining reduziert)
- **`loot_table`** (string): Loot Table-ID
- **`particles`** (object, optional): Partikel-Effekte

**Mining-Mechanik:**
- Spieler hält Left-Click gedrückt
- `damage` wird kontinuierlich erhöht (basierend auf `mining_speed` des Werkzeugs)
- Bei `damage >= durability` wird die Decoration zerstört und Loot gedroppt
- Sprite wechselt basierend auf `health_percent`:
  - > 50%: `default`
  - 10-50%: `damaged_50` (falls vorhanden)
  - < 10%: `stump` (falls vorhanden)

#### Placement

Definiert Spawn-Verhalten in der Welt:

```json
"placement": {
  "biomes": ["terrain:forest", "terrain:plains"],
  "density": 0.5,
  "noise_threshold": {
    "min": 0.3,
    "max": 0.7
  },
  "clustering": {
    "enabled": true,
    "cluster_size": 5,
    "cluster_radius": 3
  }
}
```

- **`biomes`** (array, erforderlich): Liste von Biome-IDs, in denen gespawnt wird
- **`density`** (float): Dichte (0.0-1.0, höher = häufiger)
- **`noise_threshold`** (object, optional): Noise-Bereich für Spawn
  - **`min`** (float): Minimum (-1.0 bis 1.0)
  - **`max`** (float): Maximum (-1.0 bis 1.0)
- **`clustering`** (object, optional): Cluster-Verhalten
  - **`enabled`** (boolean): Ob Clustering aktiviert ist
  - **`cluster_size`** (integer): Anzahl Decorations pro Cluster
  - **`cluster_radius`** (integer): Radius des Clusters in Tiles

**Spawn-Logik:**
1. Prüfe ob Tile in erlaubtem Biome ist
2. Prüfe Noise-Wert gegen `noise_threshold`
3. Prüfe `density` (Zufallswert)
4. Wenn Clustering aktiviert: Spawne mehrere in der Nähe

---

## 🌍 4. Biome-Integration

Biomes definieren, welche Decorations wo spawnen.

### Biome-Datei erstellen

**Datei:** `data/biomes/{biome_id}.json`

```json
{
  "biome_id": "terrain:forest",
  "display_name": "Forest",
  "noise_range": {
    "min": 0.4,
    "max": 1.0
  },
  "decorations": [
    {
      "decoration_id": "oak_tree",
      "density": 0.3,
      "spawn_chance": 0.8,
      "spawn_rules": [
        {
          "noise_range": [0.6, 0.8],
          "density": 0.2,
          "spawn_chance": 0.7
        },
        {
          "noise_range": [0.8, 1.0],
          "density": 0.4,
          "spawn_chance": 0.9
        }
      ]
    },
    {
      "decoration_id": "berry_bush",
      "density": 0.15,
      "spawn_chance": 0.5
    }
  ],
  "ground_tiles": [
    {
      "tile_id": "grass",
      "weight": 80
    },
    {
      "tile_id": "dirt",
      "weight": 20
    }
  ]
}
```

### Felder

- **`biome_id`** (string, erforderlich): Eindeutige Biome-ID (z.B. "terrain:forest")
- **`display_name`** (string, erforderlich): Anzeigename
- **`noise_range`** (object, erforderlich): Noise-Bereich für Biome-Generierung
  - **`min`** (float): Minimum
  - **`max`** (float): Maximum
- **`decorations`** (array, optional): Liste von Decorations, die in diesem Biome spawnen
- **`ground_tiles`** (array, optional): Liste von Ground-Tiles mit Gewichtungen

### Decoration-Einträge in Biomes

Jeder Eintrag kann folgende Felder haben:

- **`decoration_id`** (string, erforderlich): Decoration-ID
- **`density`** (float, optional): Dichte (0.0-1.0)
- **`spawn_chance`** (float, optional): Spawn-Chance (0.0-1.0)
- **`spawn_rules`** (array, optional): Liste von Spawn-Regeln mit Noise-Bereichen

**Spawn-Rules:**
- Ermöglicht unterschiedliche Dichten basierend auf Noise-Werten
- Mehrere Rules können definiert werden (z.B. dichter bei höherem Noise)

---

## 🎨 5. Sprite-Platzierung

### Sprite-Dateien

Sprites müssen in folgendem Verzeichnis liegen:

```
assets/decorations/{mod_id}/{sprite_name}.png
```

**Beispiele:**
- `assets/decorations/core/berry_bush_2.png`
- `assets/decorations/core/oak_tree.png`
- `assets/decorations/core/shadow_small.png`

### Sprite-Größen

- **Tiles**: 16x16 Pixel (Standard)
- **Decorations**: Variable Größen (z.B. 32x32, 64x64)
- **Shadows**: Variable Größen (meist kleiner als Decoration)

### Sprite-Format

- **Format**: PNG mit Alpha-Kanal (RGBA)
- **Farbtiefe**: 32-bit (8-bit pro Kanal)
- **Transparenz**: Unterstützt (Alpha-Kanal)

---

## 📝 6. Vollständige Beispiele

### Beispiel 1: Einfache Harvestable Decoration

**`data/decorations/core/apple_tree.json`:**
```json
{
  "decoration_id": "apple_tree",
  "display_name": "Apple Tree",
  "mod_id": "core",
  "tags": ["harvestable", "decorative"],
  "collision": {
    "enabled": true,
    "type": "circle",
    "radius": 0.4
  },
  "health": 0,
  "sprites": {
    "with_fruit": "apple_tree_fruit",
    "without_fruit": "apple_tree_empty"
  },
  "rendering": {
    "size": [48, 64],
    "offset": [0, -16],
    "layer": 10,
    "bounding_box": [32, 32],
    "shadow": {
      "enabled": true,
      "sprite": "shadow_large",
      "offset": [0, 0]
    }
  },
  "harvest": {
    "enabled": true,
    "loot_table": "apple_tree_loot",
    "regrowth": {
      "min_time": 60.0,
      "max_time": 300.0
    }
  },
  "placement": {
    "biomes": ["terrain:forest"],
    "density": 0.2,
    "noise_threshold": {
      "min": 0.5,
      "max": 1.0
    }
  }
}
```

**`data/loot_tables/apple_tree_loot.json`:**
```json
{
  "loot_table_id": "apple_tree_loot",
  "description": "Drops from harvesting apple trees",
  "rolls": 1,
  "entries": [
    {
      "item_id": "apple",
      "weight": 100,
      "quantity": {
        "min": 1,
        "max": 3
      }
    }
  ]
}
```

**Tag hinzufügen:**
In `data/tags/harvestable.json`:
```json
{
  "tag_id": "harvestable",
  "description": "Can be harvested by right-clicking",
  "members": [
    "berry_bush",
    "apple_tree"
  ]
}
```

### Beispiel 2: Mineable Resource

**`data/decorations/core/iron_ore.json`:**
```json
{
  "decoration_id": "iron_ore",
  "display_name": "Iron Ore",
  "mod_id": "core",
  "tags": ["mineable", "resource"],
  "collision": {
    "enabled": true,
    "type": "circle",
    "radius": 0.3
  },
  "health": 50,
  "sprites": {
    "default": "iron_ore"
  },
  "mining": {
    "tool_required": "pickaxe",
    "mining_time": 2.0,
    "durability": 50,
    "loot_table": "iron_ore_loot"
  },
  "placement": {
    "biomes": ["terrain:mountains"],
    "density": 0.3,
    "noise_threshold": {
      "min": -1.0,
      "max": -0.5
    }
  },
  "rendering": {
    "size": [32, 32],
    "offset": [0, 0],
    "layer": 10
  }
}
```

---

## 🔄 7. Hot-Reload (Development)

Während der Entwicklung kannst du Decorations ohne Neustart neu laden:

**Taste:** `F5`

Dies lädt alle Decoration-Dateien neu:
- Tags
- Loot Tables
- Decorations
- Biome-Erweiterungen

**Hinweis:** Änderungen an Sprites erfordern einen Neustart (Texturen werden beim Start geladen).

---

## ✅ 8. Checkliste für neue Decorations

- [ ] Decoration-JSON erstellt (`data/decorations/{mod_id}/{decoration_id}.json`)
- [ ] Sprite-Dateien erstellt (`assets/decorations/{mod_id}/{sprite_name}.png`)
- [ ] Loot Table erstellt (falls harvestable/mineable)
- [ ] Tags aktualisiert (falls neue Tags benötigt)
- [ ] Biome-Integration (in `data/biomes/{biome_id}.json`)
- [ ] `mod_id` korrekt gesetzt
- [ ] `decoration_id` eindeutig
- [ ] Sprite-Namen in JSON stimmen mit Dateinamen überein
- [ ] Loot Table-ID korrekt referenziert
- [ ] Test: F5 drücken zum Hot-Reload
- [ ] Test: Decoration spawnen lassen
- [ ] Test: Interaktion (Harvest/Mining) funktioniert

---

## 🐛 9. Häufige Fehler

### Decoration wird nicht angezeigt

- ✅ Prüfe ob Sprite-Datei existiert
- ✅ Prüfe ob `mod_id` korrekt ist
- ✅ Prüfe ob Sprite-Name in JSON mit Dateiname übereinstimmt
- ✅ Prüfe Console-Logs für Fehler

### Loot wird nicht gedroppt

- ✅ Prüfe ob Loot Table existiert
- ✅ Prüfe ob `loot_table`-ID korrekt ist
- ✅ Prüfe ob `harvest.enabled` oder `mining` korrekt konfiguriert ist

### Decoration spawnt nicht

- ✅ Prüfe ob Biome-Integration korrekt ist
- ✅ Prüfe `placement.biomes` Liste
- ✅ Prüfe `density` und `noise_threshold` Werte
- ✅ Prüfe ob Biome in der Welt generiert wird

### Progress-Bar wird nicht angezeigt

- ✅ Prüfe ob `harvest.enabled = true`
- ✅ Prüfe ob `regrowth` konfiguriert ist
- ✅ Prüfe ob Decoration geerntet wurde (`has_fruit = false`)

---

## 📚 10. Erweiterte Features

### Custom Bounding Box

Für präzise Maus-Auswahl:

```json
"rendering": {
  "size": [64, 64],        // Sprite-Größe (groß)
  "bounding_box": [32, 32] // Maus-Auswahl (kleiner, präziser)
}
```

### Clustering

Für natürliche Gruppierungen (z.B. Bäume in Wäldern):

```json
"placement": {
  "clustering": {
    "enabled": true,
    "cluster_size": 5,      // 5 Decorations pro Cluster
    "cluster_radius": 3      // 3 Tiles Radius
  }
}
```

### Noise-basierte Spawn-Regeln

Für unterschiedliche Dichten basierend auf Terrain:

```json
"spawn_rules": [
  {
    "noise_range": [0.6, 0.8],
    "density": 0.2,
    "spawn_chance": 0.7
  },
  {
    "noise_range": [0.8, 1.0],
    "density": 0.4,
    "spawn_chance": 0.9
  }
]
```

---

## 🎯 Zusammenfassung

1. **Tags**: Kategorisieren Decorations (`data/tags/`)
2. **Loot Tables**: Definieren Drops (`data/loot_tables/`)
3. **Decorations**: Haupt-Konfiguration (`data/decorations/{mod_id}/`)
4. **Biomes**: Integration in Welt-Generierung (`data/biomes/`)
5. **Sprites**: Bild-Dateien (`assets/decorations/{mod_id}/`)

**Wichtig:**
- Alle IDs müssen eindeutig sein
- Sprite-Namen müssen mit Dateinamen übereinstimmen
- Loot Table-IDs müssen korrekt referenziert werden
- Biome-IDs müssen mit Terrain-Generator übereinstimmen

Viel Erfolg beim Erstellen neuer Decorations! 🚀

