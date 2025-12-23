# ModernGL Migrationsplan

## 🎯 Warum ModernGL?

**Aktuelle Probleme:**
- Render-Zeit: 2.95ms (3x höher als Update)
- Chunk-Rendering: CPU-basiert, begrenzte Optimierung
- Sprite-Rendering: Einzelne `blit()` Calls
- Frame-Spikes: 376ms Maximum

**ModernGL Vorteile:**
- ✅ GPU-Beschleunigung (10-100x schneller für viele Objekte)
- ✅ Instanced Rendering (Tausende Tiles in einem Draw-Call)
- ✅ Shader-basierte Effekte (Lighting, Fog, etc.)
- ✅ Bessere Skalierbarkeit für große Welten
- ✅ Parallele Verarbeitung auf GPU

## 📋 Migrationsstrategie

### Phase 1: Hybrid-Ansatz (Pygame + ModernGL)
**Ziel:** ModernGL für Chunk-Rendering, Pygame für UI/Menüs

**Vorteile:**
- Minimale Änderungen am bestehenden Code
- UI bleibt unverändert (Pygame ist gut für UI)
- Schrittweise Migration möglich
- Einfaches Rollback bei Problemen

### Phase 2: Vollständige Migration
**Ziel:** Alles auf ModernGL (optional)

## 🏗️ Architektur-Plan

```
┌─────────────────────────────────────────┐
│         Main Game Loop                  │
│  (Pygame für Events, ModernGL für GPU) │
└─────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
┌───────▼────────┐    ┌─────────▼────────┐
│  Pygame UI     │    │  ModernGL Engine │
│  - Menüs       │    │  - Chunks        │
│  - HUD         │    │  - Sprites       │
│  - Text        │    │  - Terrain       │
└────────────────┘    └──────────────────┘
```

## 🔧 Technische Umsetzung

### 1. ModernGL Setup

```python
import moderngl
import pygame
from pygame.locals import *

# Pygame mit OpenGL Context initialisieren
pygame.init()
pygame.display.set_mode((1920, 1080), DOUBLEBUF | OPENGL)

# ModernGL Context erstellen
ctx = moderngl.create_context()
```

### 2. Chunk-Rendering mit Instanced Rendering

**Aktuell (CPU):**
```python
# Pro Chunk: 225 einzelne draw.rect() Calls
for chunk in loaded_chunks:
    for tile in chunk.tiles:
        pygame.draw.rect(surface, tile.color, rect)  # CPU
```

**Mit ModernGL (GPU):**
```python
# Alle Chunks in einem Draw-Call
chunk_buffer = create_chunk_vertex_buffer(all_chunks)  # GPU Buffer
shader_program['chunks'].write(chunk_buffer)
shader_program.render(mode=moderngl.TRIANGLES, vertices=len(chunks) * 6)
```

**Performance-Gewinn:** ~50-100x schneller für viele Chunks!

### 3. Sprite-Batching

**Aktuell:**
```python
for sprite in all_sprites:
    screen.blit(sprite.image, camera.apply(sprite))  # Einzelne Calls
```

**Mit ModernGL:**
```python
sprite_buffer = create_sprite_buffer(all_sprites)  # Ein Buffer
shader_program['sprites'].write(sprite_buffer)
shader_program.render(instances=len(all_sprites))  # Instanced Rendering
```

## 📦 Dependencies

```txt
moderngl>=5.8.0
pygame>=2.5.0  # Für Events/UI
numpy>=1.24.0  # Für Buffer-Daten
```

## 🎨 Shader-Beispiel

### Vertex Shader (chunk.vert)
```glsl
#version 330 core

in vec2 in_position;
in vec3 in_color;
in vec2 in_chunk_offset;

uniform mat4 projection;
uniform mat4 view;

out vec3 frag_color;

void main() {
    vec2 world_pos = in_position + in_chunk_offset;
    gl_Position = projection * view * vec4(world_pos, 0.0, 1.0);
    frag_color = in_color;
}
```

### Fragment Shader (chunk.frag)
```glsl
#version 330 core

in vec3 frag_color;
out vec4 out_color;

void main() {
    out_color = vec4(frag_color, 1.0);
}
```

## 🔄 Migrations-Schritte

### Schritt 1: ModernGL Context Setup
- [ ] ModernGL installieren
- [ ] Pygame mit OpenGL Context initialisieren
- [ ] ModernGL Context erstellen
- [ ] Basis-Shader laden

### Schritt 2: Chunk-Rendering migrieren
- [ ] Chunk-Daten in GPU-Buffer konvertieren
- [ ] Chunk-Shader erstellen
- [ ] `world.draw_grid()` auf ModernGL umstellen
- [ ] Performance testen

### Schritt 3: Sprite-Rendering migrieren
- [ ] Sprite-Atlas erstellen
- [ ] Sprite-Shader erstellen
- [ ] Instanced Rendering implementieren
- [ ] Performance testen

### Schritt 4: UI bleibt Pygame
- [ ] UI weiterhin mit Pygame rendern
- [ ] Framebuffer für UI-Overlay
- [ ] Blending zwischen ModernGL und Pygame

## ⚠️ Herausforderungen

1. **Koordinaten-System:** Pygame (0,0 top-left) vs OpenGL (0,0 center)
2. **Text-Rendering:** Pygame Fonts → Texture-Atlas konvertieren
3. **Blending:** ModernGL und Pygame UI kombinieren
4. **Debugging:** Shader-Debugging ist schwieriger

## 📊 Erwartete Performance-Verbesserungen

| Bereich | Aktuell | Mit ModernGL | Verbesserung |
|---------|---------|--------------|--------------|
| Chunk-Rendering | 0.87ms | ~0.1-0.2ms | 4-8x |
| Sprite-Rendering | ~1-2ms | ~0.1-0.3ms | 5-10x |
| Frame-Spikes | 376ms | <16ms | Eliminiert |
| Skalierbarkeit | ~100 Chunks | ~1000+ Chunks | 10x |

## 🚀 Quick Start Proof-of-Concept

Soll ich einen Proof-of-Concept erstellen, der zeigt:
1. ModernGL Setup mit Pygame
2. Einfaches Chunk-Rendering mit Shader
3. Performance-Vergleich?

Dies würde zeigen, ob die Migration sinnvoll ist, bevor wir alles umbauen.









