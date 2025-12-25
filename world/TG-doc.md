# Terrain Generator Dokumentation

## Übersicht

Der `TerrainGenerator` ist ein prozeduraler Terrain-Generator, der kontinuierliche Weltkarten mit OpenSimplex Noise erzeugt. Das System verwendet ein mehrschichtiges Architekturmodell mit verschiedenen Klima- und Geländeschichten, um realistische Biome-Verteilungen zu generieren.

**Basis:** [loady.one/blog/terrain_mesh.html](https://loady.one/blog/terrain_mesh.html)

## Architektur

Das System besteht aus mehreren unabhängigen Layern:

1. **Height Layer**: Basis-Geländehöhe mit Noise, Spikes (Gebirgsketten) und Fluss-Tälern
2. **Temperature Layer**: Temperatur basierend auf Breitengrad, Kontinentalität, Höhe und lokaler Variation
3. **Humidity Layer**: Feuchtigkeit basierend auf Noise, Küstennähe, Orographie und Flüssen
4. **Biome Resolution**: Distanz-basierte Biome-Auswahl im 3D-Klima-Raum (Height × Temp × Humidity)

---

## Klasse: TerrainGenerator

### `__init__(config_path="data/worldgen/biomes.json", seed=None)`

Initialisiert den Terrain-Generator mit Konfiguration und Noise-Generatoren.

**Parameter:**
- `config_path` (str): Pfad zur Biome-Konfigurationsdatei (JSON)
- `seed` (int, optional): Zufallsseed für reproduzierbare Generierung. Wenn `None`, wird ein zufälliger Seed verwendet.

**Initialisierung:**
- Lädt Biome-Konfiguration aus JSON
- Erstellt 6 separate OpenSimplex Noise-Generatoren:
  - `noise` (Seed + 0): Basis-Höhen-Noise
  - `temp_noise` (Seed + 1): Temperatur-Variation
  - `cont_noise` (Seed + 2): Kontinentalität (Küste ↔ Inland)
  - `humidity_noise` (Seed + 3): Feuchtigkeits-Noise
  - `ridge_noise` (Seed + 4): Gebirgsketten/Spikes
  - `river_noise` (Seed + 5): Flussnetzwerke
- Lädt Noise-Parameter aus Konfiguration
- Verarbeitet Biome-Daten für effiziente Suche

**Konfigurierbare Parameter:**
- `scale`: Skalierung des Basis-Noise (Standard: 200.0)
- `octaves`: Anzahl der Noise-Oktaven (Standard: 6)
- `persistence`: Persistenz zwischen Oktaven (Standard: 0.5)
- `lacunarity`: Frequenz-Multiplikator zwischen Oktaven (Standard: 2.0)
- `temp_scale`: Skalierung für Temperatur-Noise (Standard: 400.0)
- `height_exponent`: Exponent für Geländeformung (Standard: 1.0)
- `water_level`: Meeresspiegel-Schwelle (Standard: 0.24)

---

### `set_seed(seed: int)`

Setzt einen neuen Seed und initialisiert alle Noise-Generatoren neu.

**Parameter:**
- `seed` (int): Neuer Seed-Wert

**Verwendung:**
```python
generator.set_seed(12345)
```

---

### `load_config(path)`

Lädt die Biome-Konfiguration aus einer JSON-Datei.

**Parameter:**
- `path` (str): Relativer Pfad zur JSON-Datei (z.B. "data/worldgen/biomes.json")

**Funktionsweise:**
- Verwendet `Path` für robuste Pfadbehandlung
- Löst relative Pfade relativ zur `terrain_generator.py` auf
- Lädt JSON und speichert in `self.config`

---

### `_process_biomes()`

Verarbeitet Biome-Daten für effiziente Suche und distanzbasiertes Matching.

**Funktionsweise:**
- Normalisiert Höhenbereiche von `[-1, 1]` auf `[0, 1]`
- Extrahiert `target_height`, `target_temp`, `target_humidity` für jedes Biome
- Falls `target_height` nicht vorhanden, wird der Mittelpunkt des Höhenbereichs verwendet
- Erstellt `self.biomes_by_height` Liste mit normalisierten Werten
- Sortiert Biome nach `height_min` für effiziente Suche

**Struktur der verarbeiteten Biome:**
```python
{
    "id": "terrain:plains",
    "data": {...},  # Original-Biome-Daten
    "height_min": 0.24,
    "height_max": 0.55,
    "temp_min": 0.50,
    "temp_max": 0.85,
    "humidity_min": 0.0,
    "humidity_max": 1.0,
    "target_height": 0.40,
    "target_temp": 0.5,
    "target_humidity": 0.55
}
```

---

### `_get_noise_value(x: float, y: float) -> float`

Generiert Multi-Oktaven-Noise-Wert an Weltkoordinaten.

**Parameter:**
- `x` (float): Welt-X-Koordinate
- `y` (float): Welt-Y-Koordinate

**Rückgabewert:**
- `float`: Noise-Wert im Bereich `[-1, 1]`

**Funktionsweise:**
- Multi-Oktaven-Noise für natürliche Variation
- Jede Oktave hat reduzierte Amplitude (`persistence`) und erhöhte Frequenz (`lacunarity`)
- Normalisiert auf `[-1, 1]` Bereich

**Formel:**
```
noise_value = Σ(noise2(x/scale * freq, y/scale * freq) * amplitude)
normalized = noise_value / max_value
```

---

### `_normalize_heightmap(heightmap, min_val=None, max_val=None)`

Normalisiert eine Heightmap auf den Bereich `[0, 1]`.

**Parameter:**
- `heightmap`: 2D-Liste oder Array von Höhenwerten
- `min_val` (float, optional): Minimalwert (wenn `None`, wird aus Heightmap berechnet)
- `max_val` (float, optional): Maximalwert (wenn `None`, wird aus Heightmap berechnet)

**Rückgabewert:**
- Normalisierte Heightmap im Bereich `[0, 1]`

**Funktionsweise:**
- Findet Min/Max-Werte falls nicht angegeben
- Normalisiert jeden Wert: `(value - min) / (max - min)`
- Begrenzt auf `[0, 1]` Bereich

---

### `_apply_height_exponent(heightmap)`

Wendet eine Exponentialfunktion auf die Heightmap an für Geländeformung.

**Parameter:**
- `heightmap`: 2D-Liste normalisierter Höhenwerte `[0, 1]`

**Rückgabewert:**
- Modifizierte Heightmap mit Exponentialkurve

**Funktionsweise:**
- `exponent > 1.0`: Erzeugt mehr Gipfel (steilere Berge)
- `exponent < 1.0`: Erzeugt mehr Plateaus (flachere Hochebenen)
- `exponent = 1.0`: Keine Änderung
- Re-normalisiert nach Anwendung des Exponenten

**Formel:**
```
new_height = height ** exponent
```

---

### `_get_spikes_at(world_x: int, world_y: int, base_height: float) -> float`

Berechnet zusätzliche Höhe durch Ridge/Spikes-Noise für Gebirgsketten.

**Parameter:**
- `world_x` (int): Welt-X-Koordinate (Tile-Koordinate)
- `world_y` (int): Welt-Y-Koordinate (Tile-Koordinate)
- `base_height` (float): Basis-Höhenwert (vor Spikes)

**Rückgabewert:**
- Zusätzliche Höhe im Bereich `[0.0, ridge_strength]`

**Funktionsweise:**
- Fügt nur Höhe hinzu, wenn `base_height >= ridge_threshold` (Standard: 0.6)
- Erzeugt klare Gebirgsketten statt zufälliger Spikes überall
- Stärkere Spikes in höheren Gebieten
- Skaliert mit `ridge_strength` (Standard: 0.15)

**Formel:**
```
if base_height < ridge_threshold:
    return 0.0
    
ridge_factor = (ridge_noise + 1.0) / 2.0
threshold_excess = (base_height - ridge_threshold) / (1.0 - ridge_threshold)
spike_height = ridge_factor * ridge_strength * threshold_excess
```

---

### `_get_height_at(world_x: int, world_y: int) -> float`

Berechnet normalisierte Höhe an Weltkoordinaten.

**Parameter:**
- `world_x` (int): Welt-X-Koordinate (Tile-Koordinate)
- `world_y` (int): Welt-Y-Koordinate (Tile-Koordinate)

**Rückgabewert:**
- Normalisierte Höhe im Bereich `[0.0, 1.0]`

**Funktionsweise:**
1. **Basis-Höhe**: Multi-Oktaven-Noise normalisiert auf `[0, 1]`
2. **Exponent-Shaping**: Optional exponentielles Formen (`height_exponent`)
3. **Spikes hinzufügen**: Gebirgsketten nur auf erhöhtem Terrain
4. **Fluss-Täler**: Reduziert Höhe entlang Flüssen

**Pipeline:**
```
base_height = normalize(noise_value)
if height_exponent != 1.0:
    base_height = base_height ** height_exponent
height = base_height + spikes(base_height)
height -= river_influence * river_depth_reduction
return clamp(height, 0.0, 1.0)
```

---

### `_get_river_influence_at(world_x: int, world_y: int) -> float`

Berechnet Fluss-Einfluss an Weltkoordinaten.

**Parameter:**
- `world_x` (int): Welt-X-Koordinate (Tile-Koordinate)
- `world_y` (int): Welt-Y-Koordinate (Tile-Koordinate)

**Rückgabewert:**
- Fluss-Einfluss im Bereich `[0.0, 1.0]` (1.0 = direkt am Fluss, 0.0 = weit entfernt)

**Funktionsweise:**
- Verwendet großskaliges Noise für Flussnetzwerke (`river_scale`: 800.0)
- Prüft ob Noise über `river_threshold` (Standard: 0.65)
- Exponentieller Falloff vom Flusszentrum
- Skaliert mit `river_width` (Standard: 3.0) für Einflussradius

**Formel:**
```
river_noise = normalize(river_noise2(x/river_scale, y/river_scale))
if river_noise > river_threshold:
    distance = (river_noise - threshold) / (1.0 - threshold)
    influence = (1.0 - distance^0.5) / river_width
    return clamp(influence, 0.0, 1.0)
return 0.0
```

---

### `_get_continentalness_at(world_x: int, world_y: int) -> float`

Berechnet Kontinentalitätswert (Distanz zum Meer).

**Parameter:**
- `world_x` (int): Welt-X-Koordinate (Tile-Koordinate)
- `world_y` (int): Welt-Y-Koordinate (Tile-Koordinate)

**Rückgabewert:**
- Kontinentalität im Bereich `[0.0, 1.0]` (0.0 = Küste, 1.0 = Inland)

**Funktionsweise:**
- Großskaliges Noise (`cont_scale`: 600.0) für kontinentale Muster
- Niedrige Werte = Küstengebiete (wärmer, feuchter)
- Hohe Werte = Inland (kälter, trockener)

**Verwendung:**
- Temperatur-Gradient: Küste wärmer, Inland kälter
- Feuchtigkeit: Küste feuchter, Inland trockener

---

### `_get_temperature_at(world_x: int, world_y: int, height: float = None) -> float`

Berechnet normalisierte Temperatur an Weltkoordinaten.

**Parameter:**
- `world_x` (int): Welt-X-Koordinate (Tile-Koordinate)
- `world_y` (int): Welt-Y-Koordinate (Tile-Koordinate)
- `height` (float, optional): Höhenwert (wenn `None`, wird berechnet)

**Rückgabewert:**
- Normalisierte Temperatur im Bereich `[0.0, 1.0]` (0.0 = kalt, 1.0 = heiß)

**Temperatur-Faktoren:**

1. **Breitengrad-Gradient** (`latitude_effect`: 0.3):
   - Kosinus-basierte Kurve: Kalt an Polen (0.0, 1.0), warm am Äquator (0.5)
   - Formel: `lat_temp = 0.5 - 0.4 * cos(π * latitude_factor)`

2. **Kontinentalitäts-Gradient** (`continentalness_effect`: 0.2):
   - Küste wärmer, Inland kälter
   - Formel: `cont_temp = 1.0 - continentalness * 0.3`

3. **Höhen-Abkühlung** (`height_cooling`: 0.4):
   - Höhere Lagen sind kälter
   - Formel: `cooling = (height - 0.5) * height_cooling`

4. **Lokale Noise-Variation**:
   - Kleinskalige Temperaturschwankungen
   - Gewicht: `1.0 - latitude_effect - continentalness_effect`

5. **Spike-Abkühlung** (`spike_cooling`: 0.2):
   - Zusätzliche Abkühlung in Gebirgsketten (Schneegipfel)

6. **Fluss-Abkühlung** (`river_cooling`: 0.1):
   - Leichte Abkühlung entlang Flüssen (kühlere Täler)

**Kombination:**
```
base_temp = lat_temp * latitude_effect + cont_temp * continentalness_effect
temp = base_temp + noise_temp * noise_weight
temp -= height_cooling_factor
temp -= spike_cooling_factor
temp -= river_cooling_factor
return clamp(temp, 0.0, 1.0)
```

---

### `_get_humidity_at(world_x: int, world_y: int, height: float = None) -> float`

Berechnet normalisierte Feuchtigkeit an Weltkoordinaten.

**Parameter:**
- `world_x` (int): Welt-X-Koordinate (Tile-Koordinate)
- `world_y` (int): Welt-Y-Koordinate (Tile-Koordinate)
- `height` (float, optional): Höhenwert (wenn `None`, wird berechnet)

**Rückgabewert:**
- Normalisierte Feuchtigkeit im Bereich `[0.0, 1.0]` (0.0 = trocken, 1.0 = feucht)

**Feuchtigkeits-Faktoren:**

1. **Basis-Noise** (`humidity_scale`: 500.0):
   - Großskalige Feuchtigkeitsvariation
   - Normalisiert auf `[0, 1]`

2. **Küsten-Boost** (`coastal_humidity_boost`: 0.3):
   - Küstengebiete sind feuchter
   - Formel: `boost = (1.0 - continentalness) * coastal_humidity_boost`

3. **Orographischer Effekt** (`orographic_effect`: 0.4):
   - Luv-Seite (windzugewandt) = feuchter
   - Lee-Seite (windabgewandt) = trockener
   - Nur auf erhöhtem Terrain (`height > 0.5`)
   - Annahme: Vorherrschende Winde von Westen
   - Formel: `modifier = -gradient_x * orographic_effect`

4. **Fluss-Boost** (`river_humidity_boost`: 0.25):
   - Erhöhte Feuchtigkeit entlang Flüssen
   - Ermöglicht grüne Flusstäler in trockenen Klimazonen

**Kombination:**
```
humidity = normalize(humidity_noise)
humidity += coastal_boost
humidity += orographic_modifier
humidity += river_boost
return clamp(humidity, 0.0, 1.0)
```

---

### `_get_biome_for_height_temp_humidity(height: float, temperature: float, humidity: float)`

Findet passendes Biome durch distanzbasiertes Matching im 3D-Klima-Raum.

**Parameter:**
- `height` (float): Normalisierte Höhe `[0.0, 1.0]`
- `temperature` (float): Normalisierte Temperatur `[0.0, 1.0]`
- `humidity` (float): Normalisierte Feuchtigkeit `[0.0, 1.0]`

**Rückgabewert:**
- Tupel `(biome_id, biome_data)`

**Funktionsweise:**

1. **Distanz-Berechnung**:
   - Für jedes Biome wird die gewichtete euklidische Distanz zum Zielvektor berechnet:
   ```
   distance = sqrt(
       WEIGHT_HEIGHT * (height - target_height)² +
       WEIGHT_TEMP * (temperature - target_temp)² +
       WEIGHT_HUMIDITY * (humidity - target_humidity)²
   )
   ```
   - Standard-Gewichte: `WEIGHT_HEIGHT = 1.0`, `WEIGHT_TEMP = 1.0`, `WEIGHT_HUMIDITY = 1.0`

2. **Höhen-Penalty**:
   - Biome außerhalb des Höhenbereichs erhalten einen Penalty (keine vollständige Ausschließung)
   - Ermöglicht weiche Übergänge, verhindert aber unrealistische Kombinationen
   ```
   if height < height_min:
       penalty = (height_min - height) * 2.0
   elif height > height_max:
       penalty = (height - height_max) * 2.0
   distance += penalty
   ```

3. **Bestes Match**:
   - Biome mit kleinster Distanz wird gewählt
   - Erzeugt weiche Übergänge wie:
     - **Plains → Savanna → Desert** (steigende Temp, fallende Humidity)
     - **Plains → Forest → Rainforest** (steigende Humidity)
     - **Plains → Steppe → Desert** (fallende Humidity)

4. **Fallback-Logik**:
   - Wenn `height <= water_level`: Fallback zu `water:shallow`
   - Sonst: Fallback zu `terrain:plains`
   - Letzter Fallback: Erstes verfügbares Biome

**Vorteile:**
- Weiche Übergänge statt harter Schwellen
- Natürliche Gradienten basierend auf Klima-Variationen
- Biome konkurrieren im 3D-Klima-Raum
- Kontinuierliche Übergänge wie in echten Ökosystemen

---

### `generate_chunk(chunk_x, chunk_y, chunk_size=None)`

Generiert einen kompletten Chunk mit Heightmap-basiertem Terrain.

**Parameter:**
- `chunk_x` (int): Chunk-X-Koordinate
- `chunk_y` (int): Chunk-Y-Koordinate
- `chunk_size` (int, optional): Tiles pro Chunk (Standard: `settings.CHUNK_SIZE`)

**Rückgabewert:**
- 2D-Liste von Tile-Dictionaries

**Funktionsweise:**

1. **Welt-Offset berechnen**:
   ```
   world_offset_x = chunk_x * chunk_size
   world_offset_y = chunk_y * chunk_size
   ```

2. **Heightmap generieren**:
   - Für jedes Tile: `height = _get_height_at(world_x, world_y)`
   - Normalisiert auf `[0, 1]`

3. **Tiles generieren**:
   - Für jedes Tile:
     - Höhe aus Heightmap
     - Temperatur: `_get_temperature_at(world_x, world_y, height)`
     - Feuchtigkeit: `_get_humidity_at(world_x, world_y, height)`
     - Biome: `_get_biome_for_height_temp_humidity(height, temp, humidity)`

4. **Tile-Dictionary erstellen**:
   ```python
   {
       "biome": "terrain:plains",
       "base_biome": "terrain:plains",
       "height": 0.45,
       "temperature": 0.52,
       "humidity": 0.55,
       "tileid": "terrain:grass",
       "color": (100, 180, 80),
       "traversable": True
   }
   ```

**Tile-Struktur:**
- `biome`: Biome-ID (z.B. "terrain:plains")
- `base_biome`: Basis-Biome-ID (für Overlays)
- `height`: Normalisierte Höhe `[0.0, 1.0]`
- `temperature`: Normalisierte Temperatur `[0.0, 1.0]`
- `humidity`: Normalisierte Feuchtigkeit `[0.0, 1.0]`
- `tileid`: Tile-ID für Rendering (z.B. "terrain:grass")
- `color`: RGB-Farbe als Tupel
- `traversable`: Ob das Tile begehbar ist

---

## Konfigurationsdatei: biomes.json

Die Biome-Konfiguration definiert alle verfügbaren Biome mit ihren Eigenschaften.

### Struktur:

```json
{
  "noisesettings": {
    "seed": null,
    "octaves": 7,
    "persistence": 0.5,
    "lacunarity": 2.2,
    "scale": 200.0,
    "temp_scale": 400.0,
    ...
  },
  "biomes": {
    "terrain:plains": {
      "height_min": 0.24,
      "height_max": 0.55,
      "temp_min": 0.50,
      "temp_max": 0.85,
      "target_height": 0.40,
      "target_temp": 0.5,
      "target_humidity": 0.55,
      "color": [100, 180, 80],
      "tile_id": "core:grass",
      "traversable": true
    }
  }
}
```

### Biome-Eigenschaften:

- **height_min/max**: Höhenbereich `[-1, 1]` (wird intern auf `[0, 1]` normalisiert)
- **temp_min/max**: Temperaturbereich `[0, 1]`
- **humidity_min/max**: Feuchtigkeitsbereich `[0, 1]` (optional)
- **target_height**: Ziel-Höhe für Distanz-Berechnung (optional, sonst Mittelpunkt)
- **target_temp**: Ziel-Temperatur für Distanz-Berechnung
- **target_humidity**: Ziel-Feuchtigkeit für Distanz-Berechnung
- **color**: RGB-Farbe `[R, G, B]`
- **tile_id**: Tile-ID für Rendering
- **traversable**: Ob das Tile begehbar ist

---

## Verwendungsbeispiel

```python
from world.terrain_generator import TerrainGenerator

# Generator initialisieren
generator = TerrainGenerator(seed=12345)

# Chunk generieren
chunk = generator.generate_chunk(chunk_x=0, chunk_y=0, chunk_size=32)

# Tile-Daten abrufen
tile = chunk[10][15]  # Tile bei (10, 15) im Chunk
print(f"Biome: {tile['biome']}")
print(f"Höhe: {tile['height']:.2f}")
print(f"Temperatur: {tile['temperature']:.2f}")
print(f"Feuchtigkeit: {tile['humidity']:.2f}")
```

---

## Performance-Hinweise

- **Caching**: Kein explizites Caching implementiert. Für wiederholte Zugriffe sollte ein LRU-Cache erwogen werden.
- **Noise-Berechnung**: Jede Layer-Berechnung erfordert separate Noise-Aufrufe. Optimierung möglich durch gemeinsame Noise-Werte.
- **Chunk-Größe**: Standard `CHUNK_SIZE` aus `settings`. Größere Chunks = mehr Berechnungen pro Aufruf.

---

## Erweiterungsmöglichkeiten

- **Region-Layer**: Großskalige Meta-Biome (feucht, neutral, trocken)
- **Erosion-Layer**: Zusätzliche Geländeformung durch Erosion
- **Vegetation-Layer**: Baum-/Gras-Dichte basierend auf Biome
- **Resource-Layer**: Ressourcen-Generierung basierend auf Biome und Höhe
- **Caching**: LRU-Cache für generierte Chunks
- **Multi-Threading**: Parallele Chunk-Generierung

---

## Referenzen

- [OpenSimplex Noise](https://github.com/lmas/opensimplex)
- [Terrain Mesh Generation](https://loady.one/blog/terrain_mesh.html)
- [Procedural Terrain Generation](https://en.wikipedia.org/wiki/Procedural_generation)

