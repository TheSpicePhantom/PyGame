---
name: Texture & Rendering System Overhaul
overview: Verbesserung des Texture-Loading/Atlas-Building und Implementierung eines strukturierten Layer-basierten Rendering-Systems, um sicherzustellen, dass alle Tiles und Decorations korrekt gerendert werden.
todos:
  - id: texture-1
    content: DecorationTextureManager entfernen - Referenzen in modern_gl_renderer.py finden und durch tile_texture_manager ersetzen
    status: completed
  - id: texture-2
    content: Fallback-Texturen hinzufügen - FALLBACK_COLOR, failed_textures set, _create_fallback_texture() Methode
    status: completed
  - id: texture-3
    content: _load_texture_from_path() erweitern - Fallback statt None zurückgeben, failed_textures tracken
    status: completed
    dependencies:
      - texture-2
  - id: texture-4
    content: Atlas-Validierung hinzufügen - _validate_atlas() Methode mit UV-Koordinaten-Prüfung und Statistiken
    status: completed
    dependencies:
      - texture-3
  - id: layer-1
    content: RenderLayerManager Klasse erstellen (view/render_layer_manager.py) mit Layer-Konstanten und Z-Index-Sorting
    status: completed
  - id: layer-2
    content: WorldRenderer.draw() refactoren um RenderLayerManager zu verwenden mit strukturierten Queue-Methoden
    status: completed
    dependencies:
      - layer-1
  - id: layer-3
    content: main_pyglet.py on_draw() vereinfachen und an WorldRenderer delegieren
    status: completed
    dependencies:
      - layer-2
  - id: render-1
    content: Rendering-Validierung implementieren (sicherstellen dass alle sichtbaren Chunks/Decorations gerendert werden)
    status: completed
    dependencies:
      - layer-3
  - id: render-2
    content: Cache-Invalidierung in WorldRenderer verbessern (invalidate_decoration_cache, mark_decoration_chunk_dirty)
    status: completed
    dependencies:
      - render-1
  - id: render-3
    content: Frustum-Culling in _render_decorations_and_player() korrigieren (Margin für große Decorations)
    status: completed
    dependencies:
      - render-2
---

# Texture & Rendering System Overhaul

## Problem-Analyse

### Problem 1: Texture-Loading und Atlas-Building

- **TileTextureManager** baut bereits ein Atlas mit Tiles und Decorations (✅ `_load_decoration_textures()` vorhanden)
- **DecorationTextureManager** lädt Texturen separat (nicht im Atlas) - muss entfernt werden
- ❌ Fehlende Fallback-Texturen bei fehlenden Assets
- ❌ Inkonsistente Fehlerbehandlung bei fehlenden Texturen
- ❌ Keine Validierung der UV-Koordinaten nach Atlas-Building
- ❌ Atlas-Building kann fehlschlagen ohne klare Fehlermeldungen

**Wichtig**: Der aktuelle TileTextureManager ist bereits sehr fortgeschritten (Rotation-System, Colorization, Multi-Octave-Noise, Season-Support, Shadow-Texturen). Wir machen **minimale Änderungen** statt kompletter Ersatz!

### Problem 2: Rendering-Struktur

- Keine klaren Render-Layers
- Rendering-Code verteilt über mehrere Dateien (main_pyglet.py, world_renderer.py, modern_gl_renderer.py)
- Tiles werden nicht konstant gerendert (graue Flächen)
- Decorations werden nicht gerendert obwohl sie existieren
- Kein Z-Ordering für korrekte Tiefensortierung

## Lösung

### Phase 1: Texture-System robuster machen (Minimale Änderungen)

#### 1.1 DecorationTextureManager entfernen

**Status**: `TileTextureManager` hat bereits `_load_decoration_textures()` (Zeile 467+) - Integration ist vorhanden!

**Schritte**:

1. Prüfen ob `DecorationTextureManager` in [view/modern_gl_renderer.py](view/modern_gl_renderer.py) verwendet wird
2. Alle Referenzen zu `self.decoration_texture_manager` durch `self.tile_texture_manager` ersetzen
3. Import und Initialisierung von `DecorationTextureManager` entfernen
4. Datei `view/decoration_texture_manager.py` löschen (nur wenn alle Referenzen entfernt)

#### 1.2 Fallback-Texturen hinzufügen

**Patch 1**: Fallback-Konstante und Tracking hinzufügen

- [view/tile_texture_manager.py](view/tile_texture_manager.py): `FALLBACK_COLOR = (255, 0, 255, 255)` (Pink) in Klasse hinzufügen
- `self.failed_textures = set()` in `__init__()` hinzufügen

**Patch 2**: `_create_fallback_texture()` Methode hinzufügen

- Erstellt pink Fallback-Textur für fehlende Assets
- Wird von `_load_texture_from_path()` verwendet

**Patch 3**: `_load_texture_from_path()` erweitern

- Statt `None` zurückzugeben bei fehlenden Texturen → Fallback-Textur zurückgeben
- Fehlgeschlagene Loads in `self.failed_textures` tracken
- Besseres Logging für fehlende Texturen

#### 1.3 Atlas-Building Validierung hinzufügen

**Patch 4**: `_validate_atlas()` Methode hinzufügen

- Validiert alle UV-Koordinaten (0.0-1.0 Range)
- Loggt fehlerhafte UV-Koordinaten
- Statistiken: Atlas-Größe, Anzahl Texturen, Anzahl fehlgeschlagener Loads

**Patch 5**: `_build_texture_atlas()` erweitern

- Am Ende von `_build_texture_atlas()`: `self._validate_atlas()` aufrufen
- Logging mit Statistiken: `✓ Atlas built: X textures, Y failed`

#### Code-Patches (Detailliert)

**Patch 1 - Fallback-Konstante**:

```python
# In tile_texture_manager.py - AM ANFANG DER KLASSE
class TileTextureManager:
    FALLBACK_COLOR = (255, 0, 255, 255)  # Pink für fehlende Texturen
    
    def __init__(self, ...):
        # ... existing code ...
        self.failed_textures = set()  # Track failed loads
```

**Patch 2 - Fallback-Methode**:

```python
# In tile_texture_manager.py - NACH _load_texture_from_path()
def _create_fallback_texture(self, texture_id: str) -> Image.Image:
    """Create pink fallback texture for missing assets."""
    img = Image.new('RGBA', (self.tile_size, self.tile_size), self.FALLBACK_COLOR)
    self._log("debug", f"Created fallback texture for: {texture_id}")
    return img
```

**Patch 3 - _load_texture_from_path() erweitern**:

```python
# In tile_texture_manager.py - _load_texture_from_path() ERSETZEN
def _load_texture_from_path(self, texture_path: Path) -> Optional[Image.Image]:
    if not texture_path.exists():
        self._log("warning", f"Texture not found: {texture_path}")
        self.failed_textures.add(str(texture_path))
        return self._create_fallback_texture(str(texture_path))  # Fallback statt None
    
    try:
        img = Image.open(texture_path).convert("RGBA")
        if img.size[0] != self.tile_size or img.size[1] != self.tile_size:
            img = img.resize((self.tile_size, self.tile_size), Image.Resampling.LANCZOS)
        return img
    except Exception as e:
        self._log("error", f"Error loading texture {texture_path}: {e}")
        self.failed_textures.add(str(texture_path))
        return self._create_fallback_texture(str(texture_path))  # Fallback statt None
```

**Patch 4 - Validierung**:

```python
# In tile_texture_manager.py - NACH _build_texture_atlas()
def _validate_atlas(self):
    """Validate texture atlas and UV coordinates."""
    invalid = []
    for texture_id, (u0, v0, u1, v1) in self.texture_coords.items():
        if not (0.0 <= u0 <= 1.0 and 0.0 <= v0 <= 1.0 and 
               0.0 <= u1 <= 1.0 and 0.0 <= v1 <= 1.0):
            invalid.append(texture_id)
    
    if invalid:
        self._log("error", f"Invalid UV coordinates: {invalid[:5]}...")
    else:
        self._log("debug", "All UV coordinates valid")
    
    self._log("info", f"Atlas size: {self.atlas_size}x{self.atlas_size}, "
                     f"Textures: {len(self.texture_coords)}, "
                     f"Failed: {len(self.failed_textures)}")
```

**Patch 5 - _build_texture_atlas() erweitern**:

```python
# In tile_texture_manager.py - AM ENDE von _build_texture_atlas()
def _build_texture_atlas(self):
    # ... existing code ...
    
    # NEU: Validierung nach Atlas-Build
    if self.texture_atlas:
        self._validate_atlas()
        self._log("info", f"✓ Atlas built: {len(self.texture_coords)} textures, "
                         f"{len(self.failed_textures)} failed")
```

### Phase 2: Layer-basiertes Rendering-System

#### 2.1 RenderLayerManager erstellen

- Neue Datei: [view/render_layer_manager.py](view/render_layer_manager.py)
- `RenderLayer` Klasse für einzelne Render-Layer
- `RenderLayerManager` Klasse für Layer-Verwaltung
- Layer-Konstanten (TERRAIN=0, SHADOWS=5, DECORATIONS=10, ENTITIES=20, etc.)
- Z-Index-Sorting innerhalb jedes Layers

#### 2.2 WorldRenderer refactoren

- [view/world_renderer.py](view/world_renderer.py): `draw()` Methode umbauen
- Verwendung von `RenderLayerManager`
- Strukturierte Queue-Methoden für jeden Layer:
- `_queue_terrain()` - Layer 0
- `_queue_shadows()` - Layer 5
- `_queue_decorations()` - Layer 10
- `_queue_entities()` - Layer 20
- `_queue_particles()` - Layer 25
- `_queue_effects()` - Layer 30
- `_queue_projectiles()` - Layer 40
- `_queue_ui_world()` - Layer 50
- `_render_screen_ui()` - Layer 100 (immer zuletzt)

#### 2.3 Rendering-Pipeline in main_pyglet.py anpassen

- [main_pyglet.py](main_pyglet.py): `on_draw()` Methode vereinfachen
- Delegation an `WorldRenderer.draw()` (verwendet jetzt Layer-System)
- UI-Rendering bleibt separat (Layer 100)

### Phase 3: Rendering-Garantien

#### 3.1 Rendering-Validierung

- Validierung dass alle sichtbaren Chunks gerendert werden
- Validierung dass alle Decorations in sichtbaren Chunks gerendert werden
- Debug-Logging für fehlende Renderables

#### 3.2 Cache-Invalidierung verbessern

- [view/world_renderer.py](view/world_renderer.py): Cache-Invalidierung bei Änderungen
- `invalidate_decoration_cache()` verbessern
- `mark_decoration_chunk_dirty()` für VBO-Updates
- Sicherstellen dass alle Caches korrekt invalidiert werden

#### 3.3 Frustum-Culling korrigieren

- [view/world_renderer.py](view/world_renderer.py): Frustum-Culling in `_render_decorations_and_player()`
- Sicherstellen dass Decorations nicht fälschlicherweise ausgeblendet werden
- Margin für große Decorations korrekt berechnen

## Implementierungsreihenfolge

1. **Texture-System robuster machen** (Phase 1) - **Minimale Änderungen**

- ✅ `_load_decoration_textures()` ist bereits vorhanden - keine Änderung nötig!
- DecorationTextureManager entfernen (Referenzen finden und ersetzen)
- Fallback-Texturen hinzufügen (3 kleine Patches)
- Atlas-Validierung hinzufügen (2 kleine Patches)

2. **Layer-System implementieren** (Phase 2)

- RenderLayerManager erstellen
- WorldRenderer refactoren
- main_pyglet.py anpassen

3. **Rendering-Garantien** (Phase 3)

- Validierung implementieren
- Cache-Invalidierung verbessern
- Frustum-Culling korrigieren

## Wichtige Hinweise

**✅ Was bereits vorhanden ist** (nicht ändern!):

- `_load_decoration_textures()` in TileTextureManager
- Rotation-System (4 Rotationen)
- Biome-Colorization
- Multi-Octave-Noise für Overlays
- Season-Support (Snowy/Fruit-Varianten)
- Shadow-Texturen

**❌ Was NICHT gebraucht wird**:

- Komplett neuer TileTextureManager
- Vereinfachte Version
- Retry-Mechanismus (Fallback-Texturen reichen)

**✅ Was wirklich gebraucht wird**:

- DecorationTextureManager entfernen
- Fallback-Texturen (Pink bei fehlenden Assets)
- Bessere Fehlerbehandlung (Logging)
- Validierung (UV-Koordinaten prüfen)

## Erwartete Ergebnisse

- **Robustes Texture-System**: Alle Texturen werden korrekt geladen und ins Atlas integriert
- **Strukturiertes Rendering**: Klare Layer-Struktur mit Z-Ordering
- **Zuverlässiges Rendering**: Alle Tiles und Decorations werden korrekt gerendert
- **Bessere Performance**: Weniger Draw-Calls durch besseres Batching
- **Einfachere Wartung**: Klare Trennung der Render-Layer

## Risiken und Mitigation

- **Risiko**: Breaking Changes beim Entfernen von DecorationTextureManager
- **Mitigation**: Schrittweise Migration, alle Referenzen finden und ersetzen

- **Risiko**: Performance-Einbußen durch Layer-System
- **Mitigation**: Layer-System ist optimiert für Batching, sollte Performance verbessern

- **Risiko**: Fehlerhafte Rendering-Order
- **Mitigation**: Umfassendes Testing, Debug-Visualisierung für Layer-Order