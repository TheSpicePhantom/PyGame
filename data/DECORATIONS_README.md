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
└── biomes/                # Optional: Biome-Erweiterungen
    ├── forest.json
    ├── plains.json
    └── mountains.json
```

**Wichtig:** Alle JSON-Dateien werden beim Spielstart automatisch geladen. Du kannst während der Entwicklung mit `F5` neu laden (Hot-Reload).

---

## 🏷️ 1. Tags System

Tags kategorisieren Decorations und ermöglichen logische Gruppierungen. Sie werden in der Decoration-Datei als Array referenziert.

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

Tags werden in der Decoration-Datei als Array referenziert:

```json
{
  "decoration_id": "berry_bush",
  "tags": ["harvestable", "decorative", "mineable"]
}
```

**Hinweis:** Die Tags müssen in der Decoration-Datei angegeben werden. Die Tag-Dateien dienen hauptsächlich der Dokumentation und logischen Gruppierung.

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
      "item_id": "berry",
      "weight": 100,
      "quantity": {
        "min": 2,
        "max": 4
      },
      "conditions": []
    },
    {
      "item_id": "berry_seed",
      "weight": 30,
      "quantity": {
        "min": 0,
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

- **`item_id`** (string, erforderlich): Item-ID, die gedroppt wird (muss in ItemRegistry existieren)
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

**Beispiel:** 30% Chance, dass dieser Eintrag gedroppt wird.

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
  "tags": ["harvestable", "decorative", "mineable"],
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
    "bounding_box": [16, 16]
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
    "tool_required": null,
    "hardness": "wood",
    "mining_time": 1.0,
    "hardness_multiplier": 1.0,
    "durability": 20,
    "loot_table": "berry_bush_loot",
    "particles": {
      "hit": "leaf_particle",
      "break": "wood_break"
    }
  },
  "placement": {
    "valid_biomes": ["terrain:forest", "terrain:plains"],
    "invalid_biomes": ["terrain:desert", "terrain:snow", "water:deep", "water:shallow"],
    "stray_factor": 3,
    "density": 0.015,
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
  "radius": 0.4          // In Tiles (0.4 = 40% des Tiles)
}
```

- **`enabled`** (boolean): Ob Kollision aktiviert ist
- **`type`** (string): Kollisionstyp ("circle", "rectangle", "none")
- **`radius`** (float): Radius in Tiles (nur bei "circle")

#### Sprites

Definiert Sprite-Namen für verschiedene Zustände:

```json
"sprites": {
  "default": "oak_tree_1",           // Standard-Sprite (für mineable)
  "with_fruit": "berry_bush_2",       // Mit Früchten (für harvestable)
  "without_fruit": "berry_bush_1",   // Ohne Früchte (für harvestable)
  "damaged_50": "oak_tree_2",        // Bei 50% Gesundheit (für mineable)
  "stump": "tree_stump_1"            // Stumpf/Überrest (für mineable)
}
```

**Sprite-Namen:**
- **`default`**: Standard-Sprite (für mineable Decorations)
- **`with_fruit`**: Mit Früchten (für harvestable, initialer Zustand)
- **`without_fruit`**: Ohne Früchte (für harvestable, nach Ernte)
- **`damaged_50`**: Bei 50% Gesundheit (für mineable)
- **`stump`**: Stumpf/Überrest (für mineable, bei <10% Gesundheit)

**Sprite-Dateien müssen hier liegen:**
```
assets/decorations/{mod_id}/{sprite_name}.png
```

**Beispiele:**
- `assets/decorations/core/berry_bush_2.png`
- `assets/decorations/core/oak_tree_1.png`

#### Rendering

Definiert visuelle Darstellung:

```json
"rendering": {
  "size": [32, 32],           // [width, height] in Pixeln
  "offset": [0, 0],           // [x, y] Offset vom Tile-Zentrum
  "layer": 10,                // Rendering-Layer (höher = weiter oben)
  "bounding_box": [16, 16]    // [width, height] für Maus-Auswahl
}
```

- **`size`** (array, erforderlich): Sprite-Größe in Pixeln `[width, height]`
- **`offset`** (array, erforderlich): Offset vom Tile-Zentrum `[x, y]` (negativ Y = höher)
- **`layer`** (integer, erforderlich): Rendering-Layer (0=Tiles, 5=Shadows, 10=Decorations, 20=Player)
- **`bounding_box`** (array, optional): Maus-Auswahl-Box `[width, height]` (Standard: `size`)

**Hinweis:** Shadows werden separat gehandhabt und müssen nicht in der Decoration-Konfiguration definiert werden.

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
    "max_time": 180.0     // Maximale Regrowth-Zeit (Sekunden)
  }
}
```

- **`enabled`** (boolean): Ob Harvest aktiviert ist
- **`loot_table`** (string, erforderlich wenn enabled): Loot Table-ID
- **`regrowth`** (object, erforderlich wenn enabled):
  - **`min_time`** (float): Minimale Regrowth-Zeit in Sekunden
  - **`max_time`** (float): Maximale Regrowth-Zeit in Sekunden

**Regrowth-Mechanik:**
- Nach dem Ernten wird `has_fruit = false` gesetzt
- Sprite wechselt von `with_fruit` zu `without_fruit`
- Ein zufälliger Timer zwischen `min_time` und `max_time` startet
- Während des Timers wird eine Progress-Bar angezeigt
- Nach Ablauf wird `has_fruit = true` und das Sprite wechselt zurück zu `with_fruit`

#### Mining

Definiert Abbau-Verhalten (Left-Click + Hold):

```json
"mining": {
  "tool_required": null,        // "axe", "pickaxe", "hand", null (kein Werkzeug)
  "hardness": "wood",           // "wood", "stone", "metal", etc.
  "mining_time": 3.0,           // Basis-Zeit bis Abbau abgeschlossen (Sekunden)
  "hardness_multiplier": 1.0,   // Multiplikator für Mining-Zeit
  "durability": 100,            // Lebenspunkte (wird durch Mining reduziert)
  "loot_table": "oak_tree_loot",
  "particles": {
    "hit": "wood_particle",     // Partikel beim Treffen
    "break": "wood_break"       // Partikel beim Zerstören
  }
}
```

- **`tool_required`** (string, optional): Benötigtes Werkzeug (null = kein Werkzeug nötig)
- **`hardness`** (string, optional): Härte-Kategorie (für Tool-Mapping)
- **`mining_time`** (float): Basis-Zeit bis Abbau abgeschlossen (Sekunden)
- **`hardness_multiplier`** (float, optional): Multiplikator für Mining-Zeit (Standard: 1.0)
- **`durability`** (integer): Lebenspunkte (wird durch Mining reduziert)
- **`loot_table`** (string, optional): Loot Table-ID (falls vorhanden)
- **`particles`** (object, optional): Partikel-Effekte

**Mining-Mechanik:**
- Spieler hält Left-Click gedrückt
- `damage` wird kontinuierlich erhöht (basierend auf `mining_speed` des Werkzeugs und `hardness`)
- Bei `damage >= durability` wird die Decoration zerstört und Loot gedroppt
- Sprite wechselt basierend auf `health_percent`:
  - > 50%: `default`
  - 10-50%: `damaged_50` (falls vorhanden)
  - < 10%: `stump` (falls vorhanden)

#### Placement

Definiert Spawn-Verhalten in der Welt:

```json
"placement": {
  "valid_biomes": ["terrain:forest", "terrain:plains"],
  "invalid_biomes": ["terrain:desert", "terrain:snow", "water:deep", "water:shallow"],
  "stray_factor": 3,
  "density": 0.015,
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

- **`valid_biomes`** (array, erforderlich): Liste von Biome-IDs, in denen gespawnt wird
- **`invalid_biomes`** (array, optional): Liste von Biome-IDs, in denen NICHT gespawnt wird (hard block)
- **`stray_factor`** (integer, optional): Erlaubt Spawn in benachbarten Biomes (0 = nur in valid_biomes, höher = mehr Flexibilität)
- **`density`** (float, erforderlich): Dichte (0.0-1.0, höher = häufiger)
- **`noise_threshold`** (object, optional): Noise-Bereich für Spawn
  - **`min`** (float): Minimum (0.0-1.0, normalisiert)
  - **`max`** (float): Maximum (0.0-1.0, normalisiert)
- **`clustering`** (object, optional): Cluster-Verhalten
  - **`enabled`** (boolean): Ob Clustering aktiviert ist
  - **`cluster_size`** (integer): Anzahl Decorations pro Cluster
  - **`cluster_radius`** (integer): Radius des Clusters in Tiles

**Spawn-Logik:**
1. Prüfe ob Tile in `valid_biomes` ist (mit `stray_factor` Flexibilität)
2. Prüfe ob Tile NICHT in `invalid_biomes` ist (hard block)
3. Prüfe Noise-Wert gegen `noise_threshold`
4. Prüfe `density` (Zufallswert)
5. Wenn Clustering aktiviert: Spawne mehrere in der Nähe

**Hinweis:** Das alte `biomes` Feld wird noch unterstützt (als Fallback für `valid_biomes`), aber `valid_biomes` wird bevorzugt.

---

## 🌍 4. Biome-Integration

Biomes definieren, welche Decorations wo spawnen. Die Biome-Konfiguration wird im Terrain-Generator definiert, aber Decorations können Biome-Erweiterungen in `data/biomes/` definieren.

### Biome-IDs

Die verfügbaren Biome-IDs werden vom Terrain-Generator definiert:

- **Terrain-Biomes:** `terrain:forest`, `terrain:plains`, `terrain:desert`, `terrain:snow`, `terrain:mountains`
- **Water-Biomes:** `water:shallow`, `water:deep`

### Placement-Konfiguration

Decorations verwenden `valid_biomes` und `invalid_biomes` in der `placement` Sektion:

```json
"placement": {
  "valid_biomes": ["terrain:forest", "terrain:plains"],
  "invalid_biomes": ["terrain:desert", "terrain:snow"],
  "stray_factor": 3
}
```

**Erklärung:**
- **`valid_biomes`**: Erlaubte Biomes für Spawn
- **`invalid_biomes`**: Explizit verbotene Biomes (hard block)
- **`stray_factor`**: Erlaubt Spawn in benachbarten Biomes (0 = nur in valid_biomes)

---

## 🎨 5. Sprite-Platzierung

### Sprite-Dateien

Sprites müssen in folgendem Verzeichnis liegen:

```
assets/decorations/{mod_id}/{sprite_name}.png
```

**Beispiele:**
- `assets/decorations/core/berry_bush_2.png`
- `assets/decorations/core/oak_tree_1.png`

### Sprite-Größen

- **Tiles**: 16x16 Pixel (Standard)
- **Decorations**: Variable Größen (z.B. 32x32, 48x64)
- **Shadows**: Variable Größen (meist kleiner als Decoration)

### Sprite-Format

- **Format**: PNG mit Alpha-Kanal (RGBA)
- **Farbtiefe**: 32-bit (8-bit pro Kanal)
- **Transparenz**: Unterstützt (Alpha-Kanal)

**Wichtig:** Sprite-Namen in der JSON müssen exakt mit den Dateinamen übereinstimmen (ohne `.png` Endung).

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
    "bounding_box": [32, 32]
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
    "valid_biomes": ["terrain:forest"],
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
    "hardness": "stone",
    "mining_time": 2.0,
    "hardness_multiplier": 1.0,
    "durability": 50,
    "loot_table": "iron_ore_loot"
  },
  "placement": {
    "valid_biomes": ["terrain:mountains"],
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
- [ ] `mod_id` korrekt gesetzt
- [ ] `decoration_id` eindeutig
- [ ] Sprite-Namen in JSON stimmen mit Dateinamen überein
- [ ] Loot Table-ID korrekt referenziert
- [ ] `valid_biomes` korrekt konfiguriert
- [ ] Test: F5 drücken zum Hot-Reload
- [ ] Test: Decoration spawnen lassen
- [ ] Test: Interaktion (Harvest/Mining) funktioniert

---

## 🐛 9. Häufige Fehler

### Decoration wird nicht angezeigt

- ✅ Prüfe ob Sprite-Datei existiert
- ✅ Prüfe ob `mod_id` korrekt ist
- ✅ Prüfe ob Sprite-Name in JSON mit Dateiname übereinstimmt (ohne `.png`)
- ✅ Prüfe Console-Logs für Fehler
- ✅ Prüfe ob `rendering.size` und `rendering.offset` korrekt sind

### Loot wird nicht gedroppt

- ✅ Prüfe ob Loot Table existiert
- ✅ Prüfe ob `loot_table`-ID korrekt ist
- ✅ Prüfe ob `harvest.enabled` oder `mining` korrekt konfiguriert ist
- ✅ Prüfe ob `item_id` in ItemRegistry existiert

### Decoration spawnt nicht

- ✅ Prüfe ob `valid_biomes` korrekt konfiguriert ist
- ✅ Prüfe ob `invalid_biomes` die Decoration blockiert
- ✅ Prüfe `density` und `noise_threshold` Werte
- ✅ Prüfe ob Biome in der Welt generiert wird
- ✅ Prüfe Console-Logs für Spawn-Fehler

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
    "cluster_radius": 3     // 3 Tiles Radius
  }
}
```

### Stray Factor

Für natürliche Biome-Übergänge:

```json
"placement": {
  "valid_biomes": ["terrain:forest"],
  "stray_factor": 3         // Erlaubt Spawn in benachbarten Biomes
}
```

**Erklärung:**
- `stray_factor: 0` = Nur in `valid_biomes`
- `stray_factor: 1` = Erlaubt Spawn in direkt benachbarten Biomes
- `stray_factor: 3` = Erlaubt Spawn in 3 Tiles Umkreis

### Noise-basierte Spawn-Regeln

Für unterschiedliche Dichten basierend auf Terrain:

```json
"placement": {
  "noise_threshold": {
    "min": 0.6,    // Spawnt nur bei Noise-Werten >= 0.6
    "max": 1.0     // und <= 1.0
  }
}
```

**Hinweis:** Noise-Werte werden normalisiert (0.0-1.0), nicht -1.0 bis 1.0.

---

## 🎯 Zusammenfassung

1. **Tags**: Kategorisieren Decorations (`data/tags/`)
2. **Loot Tables**: Definieren Drops (`data/loot_tables/`)
3. **Decorations**: Haupt-Konfiguration (`data/decorations/{mod_id}/`)
4. **Biomes**: Integration via `valid_biomes` und `invalid_biomes`
5. **Sprites**: Bild-Dateien (`assets/decorations/{mod_id}/`)

**Wichtig:**
- Alle IDs müssen eindeutig sein
- Sprite-Namen müssen mit Dateinamen übereinstimmen (ohne `.png`)
- Loot Table-IDs müssen korrekt referenziert werden
- Biome-IDs müssen mit Terrain-Generator übereinstimmen
- `valid_biomes` ist erforderlich für Placement
- `F5` für Hot-Reload während der Entwicklung

Viel Erfolg beim Erstellen neuer Decorations! 🚀

