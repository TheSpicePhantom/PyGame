"""
ModernGL Proof-of-Concept: Zeigt GPU-beschleunigtes Chunk-Rendering

Dieser Proof-of-Concept demonstriert:
1. ModernGL Setup mit Pygame
2. Chunk-Rendering mit Instanced Rendering
3. Performance-Vergleich CPU vs GPU

Usage:
    python moderngl_proof_of_concept.py
"""
import pygame
import moderngl
import numpy as np
import time
from pathlib import Path

# Pygame mit OpenGL Context initialisieren
pygame.init()
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# OpenGL Context erstellen
pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.DOUBLEBUF | pygame.OPENGL)
ctx = moderngl.create_context()

# Vertex Shader für Chunk-Rendering
VERTEX_SHADER = """
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
"""

# Fragment Shader
FRAGMENT_SHADER = """
#version 330 core

in vec3 frag_color;
out vec4 out_color;

void main() {
    out_color = vec4(frag_color, 1.0);
}
"""

class ModernGLChunkRenderer:
    """GPU-beschleunigter Chunk-Renderer mit ModernGL"""
    
    def __init__(self, ctx, screen_width, screen_height):
        self.ctx = ctx
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # Shader-Programm erstellen
        self.program = ctx.program(
            vertex_shader=VERTEX_SHADER,
            fragment_shader=FRAGMENT_SHADER
        )
        
        # Projektions-Matrix (Orthographic)
        proj = np.array([
            [2.0 / screen_width, 0.0, 0.0, -1.0],
            [0.0, -2.0 / screen_height, 0.0, 1.0],
            [0.0, 0.0, -1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float32)
        
        self.program['projection'].write(proj.tobytes())
        
        # View-Matrix (Identity für jetzt)
        view = np.eye(4, dtype=np.float32)
        self.program['view'].write(view.tobytes())
        
        # Vertex Buffer für ein Tile (Quadrat)
        # 2 Dreiecke = 6 Vertices
        tile_size = 16.0
        vertices = np.array([
            # Position (x, y), Color (r, g, b)
            [0.0, 0.0, 1.0, 0.0, 0.0],  # Bottom-left
            [tile_size, 0.0, 0.0, 1.0, 0.0],  # Bottom-right
            [tile_size, tile_size, 0.0, 0.0, 1.0],  # Top-right
            [0.0, 0.0, 1.0, 0.0, 0.0],  # Bottom-left
            [tile_size, tile_size, 0.0, 0.0, 1.0],  # Top-right
            [0.0, tile_size, 1.0, 1.0, 0.0],  # Top-left
        ], dtype=np.float32)
        
        # Vertex Buffer Object
        self.vbo = ctx.buffer(vertices.tobytes())
        
        # Vertex Array Object
        self.vao = ctx.simple_vertex_array(
            self.program,
            self.vbo,
            'in_position', 'in_color'
        )
        
        # Chunk-Offset Buffer (für Instanced Rendering)
        self.chunk_offsets = None
        self.chunk_offset_buffer = None
        
    def update_camera(self, camera_x, camera_y, zoom=1.0):
        """Aktualisiert die View-Matrix basierend auf Kamera-Position"""
        view = np.array([
            [zoom, 0.0, 0.0, -camera_x * zoom],
            [0.0, zoom, 0.0, -camera_y * zoom],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float32)
        
        self.program['view'].write(view.tobytes())
    
    def render_chunks(self, chunks_data):
        """
        Rendert mehrere Chunks mit Instanced Rendering
        
        chunks_data: Liste von (chunk_x, chunk_y, color) Tuples
        """
        if not chunks_data:
            return
        
        # Chunk-Offsets für Instanced Rendering vorbereiten
        chunk_size = 15 * 16  # 15 Tiles * 16px
        
        offsets = []
        colors = []
        
        for chunk_x, chunk_y, color in chunks_data:
            world_x = chunk_x * chunk_size
            world_y = chunk_y * chunk_size
            offsets.append([world_x, world_y])
            colors.append(color)
        
        # Buffer aktualisieren
        if len(offsets) != len(self.chunk_offsets) if self.chunk_offsets is not None else True:
            if self.chunk_offset_buffer:
                self.chunk_offset_buffer.release()
            
            offsets_array = np.array(offsets, dtype=np.float32)
            self.chunk_offset_buffer = self.ctx.buffer(offsets_array.tobytes())
            
            # Instanced Rendering Setup (vereinfacht - würde normalerweise per-vertex attributes nutzen)
            self.chunk_offsets = offsets
        
        # Render (vereinfacht - echte Instanced Rendering würde mehr Setup benötigen)
        # Für Proof-of-Concept: Einfaches Rendering pro Chunk
        for i, (chunk_x, chunk_y, color) in enumerate(chunks_data):
            world_x = chunk_x * chunk_size
            world_y = chunk_y * chunk_size
            
            # Offset-Matrix aktualisieren
            offset = np.array([world_x, world_y], dtype=np.float32)
            self.program['in_chunk_offset'].write(offset.tobytes())
            
            # Color aktualisieren
            color_array = np.array(color, dtype=np.float32)
            # (Würde normalerweise über Vertex-Attribute gehen)
            
            # Render
            self.vao.render()


def benchmark_cpu_rendering(chunks, surface):
    """Benchmark für CPU-basiertes Rendering (Pygame)"""
    start = time.perf_counter()
    
    chunk_size = 15 * 16
    for chunk_x, chunk_y, color in chunks:
        world_x = chunk_x * chunk_size
        world_y = chunk_y * chunk_size
        
        for x in range(15):
            for y in range(15):
                rect = pygame.Rect(
                    world_x + x * 16,
                    world_y + y * 16,
                    16, 16
                )
                pygame.draw.rect(surface, color, rect)
    
    return time.perf_counter() - start


def benchmark_gpu_rendering(renderer, chunks):
    """Benchmark für GPU-basiertes Rendering (ModernGL)"""
    start = time.perf_counter()
    
    renderer.render_chunks(chunks)
    ctx.finish()  # Warte auf GPU-Fertigstellung
    
    return time.perf_counter() - start


def main():
    """Hauptfunktion für Proof-of-Concept"""
    print("ModernGL Proof-of-Concept")
    print("=" * 50)
    
    # Test-Daten: 100 Chunks
    chunks = []
    for i in range(10):
        for j in range(10):
            color = (
                (i * 25) % 255,
                (j * 25) % 255,
                128
            )
            chunks.append((i, j, color))
    
    print(f"Teste mit {len(chunks)} Chunks ({len(chunks) * 15 * 15} Tiles)")
    
    # ModernGL Renderer erstellen
    renderer = ModernGLChunkRenderer(ctx, SCREEN_WIDTH, SCREEN_HEIGHT)
    
    # CPU-Benchmark (Pygame Surface)
    pygame_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    cpu_time = benchmark_cpu_rendering(chunks, pygame_surface)
    
    # GPU-Benchmark
    gpu_time = benchmark_gpu_rendering(renderer, chunks)
    
    print(f"\nCPU (Pygame): {cpu_time*1000:.2f}ms")
    print(f"GPU (ModernGL): {gpu_time*1000:.2f}ms")
    print(f"Speedup: {cpu_time/gpu_time:.2f}x")
    
    # Interaktive Demo
    print("\nInteraktive Demo startet...")
    print("ESC zum Beenden")
    
    clock = pygame.time.Clock()
    camera_x, camera_y = 0.0, 0.0
    zoom = 1.0
    running = True
    
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_PLUS or event.key == pygame.K_EQUALS:
                    zoom *= 1.1
                elif event.key == pygame.K_MINUS:
                    zoom /= 1.1
        
        # Kamera-Update
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            camera_x -= 5.0
        if keys[pygame.K_RIGHT]:
            camera_x += 5.0
        if keys[pygame.K_UP]:
            camera_y -= 5.0
        if keys[pygame.K_DOWN]:
            camera_y += 5.0
        
        # Render
        ctx.clear(0.1, 0.1, 0.15)  # Dunkelblauer Hintergrund
        renderer.update_camera(camera_x, camera_y, zoom)
        renderer.render_chunks(chunks)
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()


if __name__ == "__main__":
    main()







