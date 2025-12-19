import pyglet
import moderngl
import numpy as np

WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
TILE_SIZE = 32
GRID_W = 15
GRID_H = 15


class TestWindow(pyglet.window.Window):
    def __init__(self):
        config = pyglet.gl.Config(double_buffer=True)
        super().__init__(
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            caption="ModernGL Top-Down Grid (NDC)",
            config=config,
            resizable=False,
        )

        self.switch_to()
        self.ctx = moderngl.create_context()
        print("GL_VERSION:", self.ctx.info.get("GL_VERSION", "unknown"))

        self.ctx.enable_only(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        # Kein projection-Uniform, wir rechnen direkt in NDC um
        self.prog = self.ctx.program(
            vertex_shader="""
                #version 330 core

                in vec2 in_position;
                in vec3 in_color;

                out vec3 frag_color;

                void main() {
                    gl_Position = vec4(in_position, 0.0, 1.0);
                    frag_color = in_color;
                }
            """,
            fragment_shader="""
                #version 330 core

                in vec3 frag_color;
                out vec4 out_color;

                void main() {
                    out_color = vec4(frag_color, 1.0);
                }
            """,
        )

        vertices = self._build_grid_vertices_ndc()
        print("[grid-ndc] Vertex array shape:", vertices.shape)
        print("[grid-ndc] First 3 vertices:", vertices[:3])

        self.vbo = self.ctx.buffer(vertices.astype("f4").tobytes())
        self.vao = self.ctx.vertex_array(
            self.prog,
            [(self.vbo, "2f 3f", "in_position", "in_color")],
        )

    def _to_ndc(self, x: float, y: float) -> tuple[float, float]:
        """Pixel (0..W,0..H, Y nach unten) -> NDC (-1..1)"""
        x_ndc = 2.0 * x / WINDOW_WIDTH - 1.0
        y_ndc = 1.0 - 2.0 * y / WINDOW_HEIGHT
        return x_ndc, y_ndc

    def _build_grid_vertices_ndc(self) -> np.ndarray:
        verts = []
        margin = 20

        for gy in range(GRID_H):
            for gx in range(GRID_W):
                x = margin + gx * TILE_SIZE
                y = margin + gy * TILE_SIZE

                if (gx + gy) % 2 == 0:
                    r, g, b = 0.2, 0.6, 0.2
                else:
                    r, g, b = 0.3, 0.8, 0.3

                x0, y0 = x, y
                x1, y1 = x + TILE_SIZE, y + TILE_SIZE

                # Pixel -> NDC
                x0n, y0n = self._to_ndc(x0, y0)
                x1n, y1n = self._to_ndc(x1, y1)

                verts.extend(
                    [
                        [x0n, y0n, r, g, b],
                        [x1n, y0n, r, g, b],
                        [x1n, y1n, r, g, b],
                        [x0n, y0n, r, g, b],
                        [x1n, y1n, r, g, b],
                        [x0n, y1n, r, g, b],
                    ]
                )

        return np.array(verts, dtype=np.float32)

    def on_draw(self):
        self.clear()
        self.ctx.clear(0.0, 0.0, 0.2, 1.0)
        self.vao.render(mode=moderngl.TRIANGLES)


if __name__ == "__main__":
    win = TestWindow()
    pyglet.app.run()
