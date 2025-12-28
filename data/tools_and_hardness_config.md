# Tools and Hardness Configuration Guide

Diese Dokumentation erklärt, wie du das Tool- und Hardness-System konfigurierst, um eigene Tools, Hardness-Levels und Mining-Modifier für Decorations zu definieren.

## Übersicht

Das System verwendet drei Hauptkomponenten:

1. **Tool-Mapping** (`data/mappings/tool_mapping.json`): Definiert Tool-Tiers, Hardness-Levels und Mining-Geschwindigkeiten
2. **Item-Definitionen** (`data/items/`): Definiert konkrete Tool-Items mit Tool-Tier-Referenzen
3. **Decoration-Mining-Config** (`data/decorations/*.json`): Definiert Hardness und Mining-Zeit für Decorations

## 1. Tool-Mapping konfigurieren

Die Datei `data/mappings/tool_mapping.json` definiert die Hierarchie und Eigenschaften von Tools und Hardness-Levels.

### Struktur

```json
{
  "tool_tiers": {
    "tier_name": {
      "tier": 0,
      "mining_speed_multiplier": 1.0,
      "tools": ["item_id_1", "item_id_2"],
      "can_mine": ["hardness_level_1", "hardness_level_2"]
    }
  },
  "hardness_levels": {
    "hardness_name": {
      "tier": 0,
      "display_name": "Display Name"
    }
  }
}
```

### Tool-Tiers

**Felder:**

- **`tier`** (integer): Numerischer Tier-Wert (0 = niedrigste, höhere Zahl = höher)
  - Bestimmt, welche Ressourcen das Tool abbauen kann
  - Höhere Tiers können niedrigere Ressourcen abbauen
- **`mining_speed_multiplier`** (float): Mining-Geschwindigkeits-Multiplikator
  - `1.0` = normale Geschwindigkeit
  - `> 1.0` = schneller (z.B. `2.0` = doppelt so schnell)
  - `< 1.0` = langsamer (z.B. `0.5` = halb so schnell)
- **`tools`** (array): Liste von Item-IDs, die diesem Tier zugeordnet sind
  - Format: `"tools:iron_axe"` oder `"core:iron_axe"`
  - Diese Items müssen in `data/items/` definiert sein
- **`can_mine`** (array): Liste von Hardness-Levels, die dieses Tool explizit abbauen kann
  - Wird für Modding-Flexibilität verwendet
  - Falls nicht in Liste: Tool kann Ressource abbauen, wenn `tool_tier >= resource_tier`

**Beispiel:**

```json
{
  "tool_tiers": {
    "iron": {
      "tier": 3,
      "mining_speed_multiplier": 1.0,
      "tools": ["tools:iron_axe", "tools:iron_pickaxe"],
      "can_mine": ["iron", "copper", "wood", "stone"]
    },
    "copper": {
      "tier": 2,
      "mining_speed_multiplier": 0.8,
      "tools": ["tools:copper_axe", "tools:copper_pickaxe"],
      "can_mine": ["copper", "wood", "stone"]
    },
    "wood": {
      "tier": 1,
      "mining_speed_multiplier": 0.5,
      "tools": ["tools:wooden_axe", "tools:wooden_pickaxe"],
      "can_mine": ["wood", "stone"]
    },
    "hand": {
      "tier": 0,
      "mining_speed_multiplier": 0.3,
      "tools": [],
      "can_mine": ["wood"]
    }
  }
}
```

### Hardness-Levels

**Felder:**

- **`tier`** (integer): Numerischer Tier-Wert (muss mit Tool-Tiers übereinstimmen)
  - Bestimmt, welche Tools diese Ressource abbauen können
  - Tool-Tier muss >= Ressource-Tier sein
- **`display_name`** (string): Anzeigename für UI/Tooltips (optional)

**Beispiel:**

```json
{
  "hardness_levels": {
    "iron": {
      "tier": 3,
      "display_name": "Iron"
    },
    "copper": {
      "tier": 2,
      "display_name": "Copper"
    },
    "stone": {
      "tier": 2,
      "display_name": "Stone"
    },
    "wood": {
      "tier": 1,
      "display_name": "Wood"
    }
  }
}
```

### Vollständiges Beispiel

```json
{
  "tool_tiers": {
    "diamond": {
      "tier": 5,
      "mining_speed_multiplier": 2.0,
      "tools": ["tools:diamond_axe", "tools:diamond_pickaxe"],
      "can_mine": ["diamond", "iron", "copper", "stone", "wood"]
    },
    "iron": {
      "tier": 3,
      "mining_speed_multiplier": 1.0,
      "tools": ["tools:iron_axe", "tools:iron_pickaxe"],
      "can_mine": ["iron", "copper", "wood", "stone"]
    },
    "copper": {
      "tier": 2,
      "mining_speed_multiplier": 0.8,
      "tools": ["tools:copper_axe", "tools:copper_pickaxe"],
      "can_mine": ["copper", "wood", "stone"]
    },
    "wood": {
      "tier": 1,
      "mining_speed_multiplier": 0.5,
      "tools": ["tools:wooden_axe", "tools:wooden_pickaxe"],
      "can_mine": ["wood", "stone"]
    },
    "hand": {
      "tier": 0,
      "mining_speed_multiplier": 0.3,
      "tools": [],
      "can_mine": ["wood"]
    }
  },
  "hardness_levels": {
    "diamond": {
      "tier": 5,
      "display_name": "Diamond"
    },
    "iron": {
      "tier": 3,
      "display_name": "Iron"
    },
    "copper": {
      "tier": 2,
      "display_name": "Copper"
    },
    "stone": {
      "tier": 2,
      "display_name": "Stone"
    },
    "wood": {
      "tier": 1,
      "display_name": "Wood"
    }
  }
}
```

## 2. Tool-Items definieren

Tool-Items werden in `data/items/` definiert (z.B. `data/items/tools/iron_axe.json`).

### Struktur

```json
{
  "item_id": "tools:iron_axe",
  "display_name": "Iron Axe",
  "description": "A sturdy iron axe for chopping wood",
  "sprite": "iron_axe.png",
  "max_stack_size": 1,
  "category": "tool",
  "tool_type": "axe",
  "tool_tier": "iron"
}
```

**Wichtige Felder für Tools:**

- **`item_id`** (string): Eindeutige Item-ID
  - Muss mit der ID in `tool_tiers.tools` übereinstimmen
  - Format: `"tools:iron_axe"` oder `"core:iron_axe"`
- **`tool_tier`** (string): Verweist auf einen Tier-Namen aus `tool_tiers`
  - Muss in `tool_mapping.json` existieren
  - Beispiel: `"iron"`, `"copper"`, `"wood"`
- **`tool_type`** (string): Tool-Typ (optional, für zukünftige Features)
  - Beispiele: `"axe"`, `"pickaxe"`, `"shovel"`
- **`max_stack_size`** (integer): Normalerweise `1` für Tools
- **`sprite`** (string): Sprite-Dateiname (muss in `assets/items/core/` existieren)

**Beispiel: Iron Axe**

```json
{
  "item_id": "tools:iron_axe",
  "display_name": "Iron Axe",
  "description": "A sturdy iron axe for chopping wood efficiently",
  "sprite": "iron_axe.png",
  "max_stack_size": 1,
  "category": "tool",
  "tags": ["tool", "axe", "mining"],
  "tool_type": "axe",
  "tool_tier": "iron"
}
```

**Beispiel: Diamond Pickaxe**

```json
{
  "item_id": "tools:diamond_pickaxe",
  "display_name": "Diamond Pickaxe",
  "description": "The ultimate mining tool",
  "sprite": "diamond_pickaxe.png",
  "max_stack_size": 1,
  "category": "tool",
  "tags": ["tool", "pickaxe", "mining"],
  "tool_type": "pickaxe",
  "tool_tier": "diamond"
}
```

## 3. Decoration-Mining-Config

Decorations definieren ihre Mining-Eigenschaften in der `mining`-Sektion ihrer JSON-Datei.

### Struktur

```json
{
  "decoration_id": "oak_tree",
  "mining": {
    "hardness": "wood",
    "mining_time": 3.0,
    "hardness_multiplier": 1.0,
    "tool_required": null,
    "loot_table": "oak_tree_loot"
  }
}
```

**Felder:**

- **`hardness`** (string): Hardness-Level der Ressource
  - Muss in `hardness_levels` in `tool_mapping.json` existieren
  - Bestimmt, welche Tools diese Ressource abbauen können
  - Default: `"wood"` (falls nicht angegeben)
- **`mining_time`** (float): Basis-Mining-Zeit in Sekunden
  - Die tatsächliche Zeit wird berechnet als: `(mining_time * hardness_multiplier) / mining_speed_multiplier`
  - Beispiel: `3.0` = 3 Sekunden mit Standard-Tool
- **`hardness_multiplier`** (float, optional): Zusätzlicher Faktor für Variance
  - `1.0` = normale Zeit
  - `> 1.0` = länger (z.B. `2.0` = doppelt so lang)
  - `< 1.0` = kürzer (z.B. `0.5` = halb so lang)
  - Default: `1.0` (falls nicht angegeben)
- **`tool_required`** (string | null, optional): Legacy-Feld für Tool-Typ-Anforderung
  - `null` = kein spezifisches Tool erforderlich (verwendet Hardness-System)
  - `"axe"` = erfordert Axt (für spezielle Fälle)
  - Wird durch Hardness-System überschrieben
- **`loot_table`** (string): Loot-Table-ID für Drops beim Abbauen

**Beispiel: Oak Tree (Wood Hardness)**

```json
{
  "decoration_id": "oak_tree",
  "mining": {
    "hardness": "wood",
    "mining_time": 3.0,
    "hardness_multiplier": 1.0,
    "tool_required": null,
    "loot_table": "oak_tree_loot"
  }
}
```

**Beispiel: Iron Ore (Iron Hardness, länger zum Abbauen)**

```json
{
  "decoration_id": "iron_ore",
  "mining": {
    "hardness": "iron",
    "mining_time": 5.0,
    "hardness_multiplier": 1.5,
    "tool_required": null,
    "loot_table": "iron_ore_loot"
  }
}
```

**Beispiel: Harter Stein (Stone Hardness, mit Multiplier)**

```json
{
  "decoration_id": "hard_stone",
  "mining": {
    "hardness": "stone",
    "mining_time": 5.0,
    "hardness_multiplier": 2.0,
    "tool_required": null,
    "loot_table": "stone_loot"
  }
}
```

## 4. Mining-Zeit-Berechnung

Die tatsächliche Mining-Zeit wird wie folgt berechnet:

```
time_to_mine = (mining_time * hardness_multiplier) / mining_speed_multiplier
```

**Beispiel-Berechnungen:**

**Oak Tree (wood hardness, 3.0s mining_time, hardness_multiplier: 1.0):**

- Mit Eisen-Axt (mining_speed_multiplier: 1.0): `(3.0 * 1.0) / 1.0 = 3.0s`
- Mit Kupfer-Axt (mining_speed_multiplier: 0.8): `(3.0 * 1.0) / 0.8 = 3.75s`
- Mit Hand (mining_speed_multiplier: 0.3): `(3.0 * 1.0) / 0.3 = 10.0s`

**Iron Ore (iron hardness, 5.0s mining_time, hardness_multiplier: 1.5):**

- Mit Eisen-Pickaxe (tier: 3, mining_speed_multiplier: 1.0): `(5.0 * 1.5) / 1.0 = 7.5s` ✓
- Mit Kupfer-Pickaxe (tier: 2): Kann nicht abbauen ✗ (tier 2 < tier 3)

**Harter Stein (stone hardness, 5.0s mining_time, hardness_multiplier: 2.0):**

- Mit Eisen-Pickaxe: `(5.0 * 2.0) / 1.0 = 10.0s` (doppelt so lang wegen hardness_multiplier)

## 5. Tool-Hardness-Prüfung

Das System verwendet einen Hybrid-Ansatz zur Prüfung, ob ein Tool eine Ressource abbauen kann:

1. **Explizite Liste**: Wenn `resource_hardness` in `tool_tier.can_mine` enthalten ist → erlaubt
2. **Tier-Vergleich**: Wenn `tool_tier >= resource_tier` → erlaubt

**Beispiel:**

- **Eisen-Axt (tier: 3)** kann abbauen:
  - `"iron"` (tier: 3) ✓ (tier 3 >= tier 3)
  - `"copper"` (tier: 2) ✓ (tier 3 >= tier 2)
  - `"wood"` (tier: 1) ✓ (tier 3 >= tier 1)
  - `"diamond"` (tier: 5) ✗ (tier 3 < tier 5)

- **Kupfer-Axt (tier: 2)** kann abbauen:
  - `"copper"` (tier: 2) ✓ (tier 2 >= tier 2)
  - `"wood"` (tier: 1) ✓ (tier 2 >= tier 1)
  - `"iron"` (tier: 3) ✗ (tier 2 < tier 3)

## 6. Schritt-für-Schritt: Neues Tool hinzufügen

### Schritt 1: Tool-Tier in `tool_mapping.json` definieren

```json
{
  "tool_tiers": {
    "diamond": {
      "tier": 5,
      "mining_speed_multiplier": 2.0,
      "tools": ["tools:diamond_axe", "tools:diamond_pickaxe"],
      "can_mine": ["diamond", "iron", "copper", "stone", "wood"]
    }
  }
}
```

### Schritt 2: Hardness-Level definieren (falls neu)

```json
{
  "hardness_levels": {
    "diamond": {
      "tier": 5,
      "display_name": "Diamond"
    }
  }
}
```

### Schritt 3: Tool-Item erstellen

Erstelle `data/items/tools/diamond_axe.json`:

```json
{
  "item_id": "tools:diamond_axe",
  "display_name": "Diamond Axe",
  "description": "The ultimate chopping tool",
  "sprite": "diamond_axe.png",
  "max_stack_size": 1,
  "category": "tool",
  "tool_type": "axe",
  "tool_tier": "diamond"
}
```

### Schritt 4: Sprite hinzufügen

Füge `assets/items/core/diamond_axe.png` hinzu (32x32 Pixel empfohlen).

### Schritt 5: Decoration mit Hardness konfigurieren

In `data/decorations/core/diamond_ore.json`:

```json
{
  "decoration_id": "diamond_ore",
  "mining": {
    "hardness": "diamond",
    "mining_time": 10.0,
    "hardness_multiplier": 1.0,
    "loot_table": "diamond_ore_loot"
  }
}
```

## 7. Best Practices

### Tool-Tier-Hierarchie

- Verwende konsistente Tier-Werte (0, 1, 2, 3, ...)
- Höhere Tiers sollten höhere `mining_speed_multiplier` haben
- Dokumentiere die Hierarchie in Kommentaren

### Mining-Zeit-Balance

- **Hand**: 0.3x Speed (langsam, aber universell)
- **Holz-Tools**: 0.5x Speed (frühes Spiel)
- **Kupfer-Tools**: 0.8x Speed (mittleres Spiel)
- **Eisen-Tools**: 1.0x Speed (Standard)
- **Diamant-Tools**: 2.0x Speed (Endgame)

### Hardness-Multiplier

- Verwende `hardness_multiplier` für Variance zwischen ähnlichen Ressourcen
- Beispiel: Normaler Stein (1.0x) vs. Harter Stein (2.0x)
- Vermeide extreme Werte (> 5.0 oder < 0.1)

### Item-IDs

- Verwende konsistente Namenskonventionen: `"tools:material_tooltype"`
- Beispiele: `"tools:iron_axe"`, `"tools:copper_pickaxe"`
- Verwende `:` als Trennzeichen für Mod-ID (z.B. `"core:iron_axe"`)

## 8. Hot-Reload

Das System unterstützt Hot-Reload mit **F5**:

1. Ändere `tool_mapping.json`, Item-Definitionen oder Decoration-Configs
2. Drücke **F5** im Spiel
3. Änderungen werden sofort geladen (kein Neustart nötig)

**Hinweis:** Tool-Mappings werden automatisch neu geladen, wenn `ToolMappingRegistry.reload()` aufgerufen wird.

## 9. Fehlerbehebung

### Tool kann Ressource nicht abbauen

- Prüfe, ob `tool_tier` in `tool_mapping.json` existiert
- Prüfe, ob `hardness` in `hardness_levels` existiert
- Prüfe, ob `tool_tier >= resource_tier` oder `hardness` in `can_mine` Liste

### Mining dauert zu lange/kurz

- Passe `mining_time` in Decoration-Config an
- Passe `mining_speed_multiplier` in Tool-Tier an
- Verwende `hardness_multiplier` für feine Anpassungen

### Progress-Bar wird nicht angezeigt

- Prüfe, ob `elapsed_time > 0.0` in Decoration-Daten
- Prüfe, ob `mining_config` vorhanden ist
- Prüfe, ob `time_to_mine > 0` berechnet wird

## 10. Erweiterte Konfiguration

### Spezielle Tool-Anforderungen

Falls du ein spezifisches Tool-Typ erfordern möchtest (z.B. nur Axt für Bäume):

```json
{
  "mining": {
    "hardness": "wood",
    "mining_time": 3.0,
    "tool_required": "axe",  // Legacy, wird durch Hardness überschrieben
    "loot_table": "oak_tree_loot"
  }
}
```

**Hinweis:** `tool_required` wird durch das Hardness-System überschrieben. Verwende es nur für spezielle Fälle.

### Modding-Support

Das System ist vollständig modding-freundlich:

- Neue Tool-Tiers können einfach hinzugefügt werden
- Neue Hardness-Levels können definiert werden
- `can_mine` Liste ermöglicht explizite Kontrolle
- Tier-Hierarchie wird dynamisch aus `tool_tiers` ermittelt

## Zusammenfassung

1. **Tool-Mapping**: Definiere Tiers und Hardness-Levels in `data/mappings/tool_mapping.json`
2. **Tool-Items**: Erstelle Item-Definitionen in `data/items/tools/` mit `tool_tier` Referenz
3. **Decoration-Config**: Füge `hardness`, `mining_time` und optional `hardness_multiplier` hinzu
4. **Berechnung**: `time_to_mine = (mining_time * hardness_multiplier) / mining_speed_multiplier`
5. **Prüfung**: Tool kann abbauen, wenn `tool_tier >= resource_tier` oder `hardness` in `can_mine` Liste

Viel Erfolg beim Konfigurieren! 🛠️
