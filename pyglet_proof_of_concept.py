"""
Pyglet + ModernGL Proof-of-Concept
Zeigt, wie man ModernGL mit pyglet verwendet (ohne Pygame)
"""
import pyglet
from pyglet.window import key, mouse
import moderngl
import numpy as np

# Window erstellen
window = pyglet.window.Window(width=1920, height=1080, caption="ModernGL Test")
window.set_location(0, 0)

# ModernGL Context erstellen
ctx = moderngl.create_context()
print(f"[Pyglet] ModernGL context created")
print(f"[Pyglet] OpenGL version: {ctx.info.get('GL_VERSION', 'unknown')}")

# Shader-Programm
vertex_shader = """
#version 330 core

in vec2 in_position;
in vec3 in_color;

uniform mat4 projection;

out vec3 frag_color;

void main() {
    vec4 pos = projection * vec4(in_position, 0.0, 1.0);
    gl_Position = pos;
    frag_color = in_color;
}
"""

fragment_shader = """
#version 330 core

in vec3 frag_color;
out vec4 out_color;

void main() {
    out_color = vec4(frag_color / 255.0, 1.0);
}
"""

program = ctx.program(vertex_shader=vertex_shader, fragment_shader=fragment_shader)

# Projektions-Matrix - Identity (direkt NDC-Koordinaten)
# Wenn wir bereits NDC-Koordinaten verwenden, brauchen wir keine Transformation
proj = np.eye(4, dtype=np.float32)
program['projection'].write(proj.tobytes())
print(f"[Pyglet] Using identity projection matrix")

# Test-Quad erstellen - direkt in NDC-Koordinaten (-1 bis 1)
# Das ist einfacher als Screen-Koordinaten zu transformieren
vertices = np.array([
    # x (NDC), y (NDC), r, g, b
    [-0.5, -0.5, 255, 0, 0],    # Red - bottom-left
    [0.5, -0.5, 0, 255, 0],      # Green - bottom-right
    [0.0, 0.5, 0, 0, 255],       # Blue - top-center
], dtype=np.float32)

vbo = ctx.buffer(vertices.tobytes())
vao = ctx.simple_vertex_array(program, vbo, 'in_position', 'in_color')

@window.event
def on_draw():
    """Render-Funktion"""
    ctx.clear(0.1, 0.1, 0.15)  # Dark background
    
    # Enable blending
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    
    # Disable depth test (not needed for 2D)
    ctx.disable(moderngl.DEPTH_TEST)
    
    # Render triangle (program is automatically used by vao)
    vao.render(moderngl.TRIANGLES)
    
    # Debug: Print once
    if not hasattr(on_draw, '_debug_printed'):
        print(f"[Render] Triangle rendered with {len(vertices)} vertices")
        print(f"[Render] Vertex data: {vertices}")
        on_draw._debug_printed = True

@window.event
def on_key_press(symbol, modifiers):
    """Keyboard-Events"""
    if symbol == key.ESCAPE:
        pyglet.app.exit()
    print(f"[Pyglet] Key pressed: {symbol}")

@window.event
def on_mouse_press(x, y, button, modifiers):
    """Mouse-Events"""
    print(f"[Pyglet] Mouse pressed: ({x}, {y}), button: {button}")

if __name__ == "__main__":
    print("[Pyglet] Starting application...")
    print("[Pyglet] Press ESC to exit")
    pyglet.app.run()

