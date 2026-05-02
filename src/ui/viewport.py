"""
3D viewport — pure PySide6 QOpenGLWidget, Phong shading.
Key fix: mesh data is queued and applied only after initializeGL() runs.
"""
import numpy as np
import trimesh
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt
from OpenGL.GL import *
import ctypes

# ── GLSL ──────────────────────────────────────────────────────────────────────
_VERT = """
#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aNorm;
uniform mat4 uMVP;
uniform mat4 uModel;
out vec3 vNorm;
out vec3 vPos;
void main(){
    vec4 wp = uModel * vec4(aPos,1.0);
    vPos  = wp.xyz;
    vNorm = mat3(transpose(inverse(uModel))) * aNorm;
    gl_Position = uMVP * vec4(aPos,1.0);
}
"""
_FRAG = """
#version 330 core
in vec3 vNorm; in vec3 vPos;
out vec4 fColor;
uniform vec3 uLightDir;
uniform vec3 uCamPos;
void main(){
    vec3 N = normalize(vNorm);
    vec3 L = normalize(uLightDir);
    vec3 base = vec3(0.78,0.83,0.92);
    float diff = max(dot(N,L),0.0);
    vec3 V = normalize(uCamPos - vPos);
    vec3 H = normalize(L+V);
    float spec = pow(max(dot(N,H),0.0),48.0);
    // Two-sided: use abs(dot) for back faces
    float backDiff = abs(dot(N,L)) * 0.4;
    float front = max(dot(N,L),0.0);
    vec3 col = 0.22*base
             + (front*0.65 + backDiff*0.35)*base
             + spec*0.30*vec3(1.0);
    fColor = vec4(col,1.0);
}
"""

def _compile_shader(src, kind):
    sh = glCreateShader(kind)
    glShaderSource(sh, src)
    glCompileShader(sh)
    if not glGetShaderiv(sh, GL_COMPILE_STATUS):
        raise RuntimeError(glGetShaderInfoLog(sh).decode())
    return sh

def _make_program():
    prog = glCreateProgram()
    vs = _compile_shader(_VERT, GL_VERTEX_SHADER)
    fs = _compile_shader(_FRAG, GL_FRAGMENT_SHADER)
    glAttachShader(prog, vs); glAttachShader(prog, fs)
    glLinkProgram(prog)
    if not glGetProgramiv(prog, GL_LINK_STATUS):
        raise RuntimeError(glGetProgramInfoLog(prog).decode())
    return prog

def _perspective(fov, aspect, near, far):
    f = 1.0 / np.tan(np.radians(fov)/2)
    return np.array([
        [f/aspect, 0, 0, 0],
        [0, f, 0, 0],
        [0, 0, (far+near)/(near-far), -1],
        [0, 0, 2*far*near/(near-far), 0],
    ], np.float32)

# ── GL Widget ─────────────────────────────────────────────────────────────────
class _GLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._prog  = None
        self._vao   = None
        self._vbo   = None
        self._ebo   = None
        self._n_idx = 0

        # Pending upload: stored before GL context exists
        self._pending: tuple | None = None   # (data_f32, faces_u32)

        # Camera (azimuth/elevation, degrees)
        self._azim = 0.0    # 0 = top-view (camera along +Z)
        self._elev = 0.0
        self._dist = 280.0
        self._last_pos = None

        self.setMinimumSize(400, 300)

    # ── GL lifecycle ──────────────────────────────────────────────────────────
    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glClearColor(0.04, 0.04, 0.09, 1.0)
        self._prog = _make_program()
        self._vao  = glGenVertexArrays(1)
        self._vbo, self._ebo = glGenBuffers(2)

        glBindVertexArray(self._vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        stride = 6 * 4
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(12))
        glEnableVertexAttribArray(1)
        glBindVertexArray(0)

        # Apply any mesh that arrived before context was ready
        if self._pending is not None:
            self._do_upload(*self._pending)
            self._pending = None
            self.update()

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if not self._prog or self._n_idx == 0:
            return

        w, h = max(self.width(), 1), max(self.height(), 1)
        proj  = _perspective(42, w/h, 1.0, 2000.0)

        az = np.radians(self._azim)
        el = np.radians(self._elev)
        cx = self._dist * np.cos(el) * np.sin(az)
        cy = self._dist * np.sin(el)
        cz = self._dist * np.cos(el) * np.cos(az)
        eye = np.array([cx, cy, cz], np.float32)

        fwd = -eye / (np.linalg.norm(eye) + 1e-9)
        up  = np.array([0.0, 1.0, 0.0], np.float32)
        # Handle near-gimbal case
        if abs(np.dot(fwd, up)) > 0.999:
            up = np.array([0.0, 0.0, 1.0], np.float32)
        r   = np.cross(fwd, up); r /= np.linalg.norm(r)
        u   = np.cross(r, fwd)
        view = np.array([
            [r[0], u[0], -fwd[0], 0],
            [r[1], u[1], -fwd[1], 0],
            [r[2], u[2], -fwd[2], 0],
            [-np.dot(r,eye), -np.dot(u,eye), np.dot(fwd,eye), 1],
        ], np.float32)

        model = np.eye(4, np.float32)
        mvp   = model @ view @ proj

        glUseProgram(self._prog)
        def ul(n): return glGetUniformLocation(self._prog, n)
        glUniformMatrix4fv(ul("uMVP"),   1, False, mvp.flatten())
        glUniformMatrix4fv(ul("uModel"), 1, False, model.flatten())
        light = np.array([0.45, 0.70, 0.55], np.float32)
        light /= np.linalg.norm(light)
        glUniform3fv(ul("uLightDir"), 1, light)
        glUniform3fv(ul("uCamPos"),   1, eye)

        glBindVertexArray(self._vao)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self._ebo)
        glDrawElements(GL_TRIANGLES, self._n_idx, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)

    # ── Mesh upload ───────────────────────────────────────────────────────────
    def upload(self, verts: np.ndarray, normals: np.ndarray, faces: np.ndarray):
        """Upload new geometry. Safe to call before or after GL init."""
        data  = np.hstack([
            verts.astype(np.float32),
            normals.astype(np.float32)
        ])
        faces = faces.astype(np.uint32)

        if self._vbo is None:
            # Context not ready — queue it
            self._pending = (data, faces)
            return

        self.makeCurrent()
        self._do_upload(data, faces)
        self.doneCurrent()
        self.update()

    def _do_upload(self, data: np.ndarray, faces: np.ndarray):
        data  = np.ascontiguousarray(data.reshape(-1),  dtype=np.float32)
        faces = np.ascontiguousarray(faces.reshape(-1), dtype=np.uint32)

        glBindVertexArray(self._vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, GL_DYNAMIC_DRAW)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self._ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, faces.nbytes, faces, GL_DYNAMIC_DRAW)
        self._n_idx = len(faces)
        glBindVertexArray(0)

    # ── Mouse interaction ─────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._last_pos = e.position()

    def mouseMoveEvent(self, e):
        if self._last_pos is None:
            return
        dx = e.position().x() - self._last_pos.x()
        dy = e.position().y() - self._last_pos.y()
        self._azim += dx * 0.45
        self._elev  = float(np.clip(self._elev - dy * 0.45, -89, 89))
        self._last_pos = e.position()
        self.update()

    def mouseReleaseEvent(self, e):
        self._last_pos = None

    def wheelEvent(self, e):
        self._dist = float(np.clip(self._dist - e.angleDelta().y() * 0.18, 40, 900))
        self.update()


# ── Public widget ─────────────────────────────────────────────────────────────
class Viewport3D(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._gl = _GLWidget()
        layout.addWidget(self._gl)

    def show_mesh(self, mesh: trimesh.Trimesh):
        """Upload trimesh object — safe at any time."""
        self._gl.upload(
            np.array(mesh.vertices),
            np.array(mesh.vertex_normals),
            np.array(mesh.faces),
        )

    def show_verts(self, verts: np.ndarray, mesh_ref: trimesh.Trimesh):
        """Upload pre-computed vertex array with normals from ref topology."""
        tmp = mesh_ref.copy()
        tmp.vertices = verts
        self._gl.upload(
            np.array(tmp.vertices),
            np.array(tmp.vertex_normals),
            np.array(tmp.faces),
        )
