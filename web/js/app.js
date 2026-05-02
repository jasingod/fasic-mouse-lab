import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  mouseA: 0,
  mouseB: 1,
  morphT: 0,
  deform: {},
};

// ── Parts definition ──────────────────────────────────────────────────────────
const PARTS = {
  front:   { label: 'Front',        dims: ['width','height','length','flare'] },
  back:    { label: 'Back / Hump',  dims: ['width','height','length','curve'] },
  left:    { label: 'Left Side',    dims: ['width','flare'] },
  right:   { label: 'Right Side',   dims: ['width','flare'] },
  top:     { label: 'Top Surface',  dims: ['height','curve'] },
  buttons: { label: 'Button Area',  dims: ['height','length','curve'] },
  thumb:   { label: 'Thumb Rest',   dims: ['width','height','flare'] },
};
const DIM_LABELS  = { width:'Width', height:'Height', length:'Length', flare:'Flare', curve:'Curve' };
const DIM_DEFAULT = { width:1.0, height:1.0, length:1.0, flare:0.0, curve:0.0 };
const DIM_RANGE   = {
  width: [0.80,1.25], height:[0.75,1.30], length:[0.85,1.20],
  flare:[-0.15,0.15], curve:[-0.20,0.20],
};

// ── Three.js setup ────────────────────────────────────────────────────────────
const canvas   = document.getElementById('canvas');
const viewport = document.getElementById('viewport');

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x080814);
scene.fog = new THREE.FogExp2(0x080814, 0.0018);

// Grid
const grid = new THREE.GridHelper(400, 20, 0x161630, 0x111128);
scene.add(grid);

// Camera — will be repositioned after mesh loads
const camera = new THREE.PerspectiveCamera(42, 1, 0.5, 3000);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping  = true;
controls.dampingFactor  = 0.07;
controls.minDistance    = 30;
controls.maxDistance    = 800;
controls.rotateSpeed    = 0.6;
controls.zoomSpeed      = 1.0;

// Lighting
const ambient = new THREE.AmbientLight(0xffffff, 0.30);
const key     = new THREE.DirectionalLight(0xffffff, 1.05);
key.position.set(1.5, 2.5, 2.0);
const fill    = new THREE.DirectionalLight(0x9aaaff, 0.20);
fill.position.set(-1.5, 0.5, -1.0);
const rim     = new THREE.DirectionalLight(0xffffff, 0.12);
rim.position.set(0, -1.5, -2.5);
scene.add(ambient, key, fill, rim);

// Mesh
const geo = new THREE.BufferGeometry();
const mat = new THREE.MeshStandardMaterial({
  color: 0xc8d2e8,
  roughness: 0.40,
  metalness: 0.05,
  side: THREE.DoubleSide,
});
const meshObj = new THREE.Mesh(geo, mat);
scene.add(meshObj);

// Resize
function resize() {
  const w = viewport.clientWidth, h = viewport.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(viewport);
resize();

// ── Smooth animation state ────────────────────────────────────────────────────
let animFrom   = null;   // Float32Array — start verts
let animTo     = null;   // Float32Array — target verts
let animT      = 1.0;    // 0→1 progress (1 = done)
const ANIM_DUR = 0.22;   // seconds

let lastTime = 0;
function easeOutQuart(t) { return 1 - Math.pow(1 - t, 4); }

function animateTo(newVerts) {
  const pos = geo.getAttribute('position');
  animFrom = pos ? pos.array.slice() : newVerts.slice();
  animTo   = newVerts;
  animT    = 0.0;
}

// ── Render loop ───────────────────────────────────────────────────────────────
renderer.setAnimationLoop((now) => {
  const dt = Math.min((now - lastTime) / 1000, 0.05);
  lastTime = now;
  controls.update();

  // Smooth vertex animation
  if (animT < 1.0 && animFrom && animTo) {
    animT = Math.min(1.0, animT + dt / ANIM_DUR);
    const et  = easeOutQuart(animT);
    const pos = geo.getAttribute('position');
    if (pos && pos.array.length === animTo.length) {
      for (let i = 0; i < pos.array.length; i++)
        pos.array[i] = animFrom[i] * (1 - et) + animTo[i] * et;
      pos.needsUpdate = true;
      geo.computeVertexNormals();
    }
  }
  renderer.render(scene, camera);
});

// ── Client-side morph data (pre-aligned A & B) ────────────────────────────────
let clientAVerts = null;   // Float32Array — A vertices resampled to B topology
let clientBVerts = null;   // Float32Array — B vertices
let baseMorphVerts = null; // Current morph result (before deform)

function applyClientMorph(t) {
  if (!clientAVerts || !clientBVerts) return null;
  const out = new Float32Array(clientBVerts.length);
  const mt  = 1 - t;
  for (let i = 0; i < out.length; i++)
    out[i] = clientAVerts[i] * mt + clientBVerts[i] * t;
  return out;
}

function setGeomVerts(verts, faces) {
  let posAttr = geo.getAttribute('position');
  if (!posAttr || posAttr.count !== verts.length / 3) {
    geo.setAttribute('position', new THREE.BufferAttribute(verts.slice(), 3));
  } else {
    posAttr.array.set(verts);
    posAttr.needsUpdate = true;
  }
  if (faces) {
    geo.setIndex(new THREE.BufferAttribute(faces.slice(), 1));
  }
  geo.computeVertexNormals();
  geo.computeBoundingSphere();
}

// ── Camera fit — TOP VIEW ──────────────────────────────────────────────────────
let cameraFitted = false;
function fitCameraTopView() {
  geo.computeBoundingSphere();
  const s = geo.boundingSphere;
  if (!s || s.radius === 0) return;

  const c = s.center;
  const r = s.radius;

  // Top-down view: camera sits above (Z+), mouse length axis (Y) is "up" on screen
  controls.target.set(c.x, c.y, c.z);
  camera.position.set(c.x, c.y, c.z + r * 3.0);
  camera.up.set(0, 1, 0);
  controls.update();

  grid.position.set(c.x, c.y, c.z - r * 1.05);
  cameraFitted = true;
}

// ── Binary helpers ────────────────────────────────────────────────────────────
function parseMeshBinary(buf) {
  const view   = new DataView(buf);
  const nVerts = view.getUint32(0, true);
  const nFaces = view.getUint32(4, true);
  return {
    nVerts,
    nFaces,
    verts: new Float32Array(buf, 8, nVerts * 3),
    faces: new Uint32Array (buf, 8 + nVerts * 12, nFaces * 3),
  };
}

// ── Loading indicator ─────────────────────────────────────────────────────────
const overlay = document.getElementById('loadingOverlay');
let loadCount = 0;
function setLoading(on) {
  loadCount = Math.max(0, loadCount + (on ? 1 : -1));
  overlay.classList.toggle('active', loadCount > 0);
}

const statusEl  = document.getElementById('statusText');
let   mouseNames = [];
function setStatus(msg) { statusEl.textContent = msg; }

// ── Prepare: fetch pre-aligned A+B meshes for client morph ───────────────────
async function prepareMeshes(resetCamera = false) {
  setLoading(true);
  setStatus('Loading meshes…');
  try {
    const res = await fetch('/api/prepare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ a: state.mouseA, b: state.mouseB }),
    });
    const buf  = await res.arrayBuffer();
    const view = new DataView(buf);
    const nV   = view.getUint32(0, true);
    const nF   = view.getUint32(4, true);

    clientAVerts = new Float32Array(buf, 8,            nV * 3).slice();
    clientBVerts = new Float32Array(buf, 8 + nV * 12,  nV * 3).slice();
    const faces  = new Uint32Array (buf, 8 + nV * 24,  nF * 3).slice();

    // Apply current morph
    const morphVerts = applyClientMorph(state.morphT);
    baseMorphVerts   = morphVerts;

    if (hasDeform()) {
      // If deform active, fetch deformed version
      await fetchDeformed(morphVerts, faces, resetCamera || !cameraFitted);
    } else {
      setGeomVerts(morphVerts, faces);
      if (resetCamera || !cameraFitted) fitCameraTopView();
      document.getElementById('exportBtn').disabled = false;
      setStatus(statusLine());
    }
  } catch (e) {
    setStatus('Error: ' + e.message);
  } finally {
    setLoading(false);
  }
}

function hasDeform() {
  return Object.entries(state.deform).some(([k, v]) => {
    const dim = k.split(',')[1];
    return Math.abs(v - DIM_DEFAULT[dim]) > 1e-5;
  });
}

// ── Morph slider: instant client-side lerp ───────────────────────────────────
const morphSlider = document.getElementById('morphSlider');
const morphPct    = document.getElementById('morphPct');

morphSlider.addEventListener('input', () => {
  state.morphT = morphSlider.value / 100;
  morphPct.textContent = morphSlider.value + ' %';
  updateSliderFill(morphSlider);

  if (!clientAVerts) return;
  const morphVerts = applyClientMorph(state.morphT);
  baseMorphVerts   = morphVerts;

  if (hasDeform()) {
    scheduleDeformUpdate();   // server call, debounced
  } else {
    // Pure morph: animate directly (no server needed)
    animateTo(morphVerts);
  }
});

// ── Parts deform: server-side with smooth animation ──────────────────────────
let deformTimer = null;
function scheduleDeformUpdate(delay = 150) {
  clearTimeout(deformTimer);
  deformTimer = setTimeout(() => fetchDeformed(baseMorphVerts, null, false), delay);
}

async function fetchDeformed(morphVerts, faces, resetCam) {
  setLoading(true);
  try {
    const res = await fetch('/api/mesh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        a: state.mouseA, b: state.mouseB,
        t: state.morphT, deform: state.deform,
      }),
    });
    const buf    = await res.arrayBuffer();
    const parsed = parseMeshBinary(buf);

    if (faces) {
      geo.setIndex(new THREE.BufferAttribute(faces.slice(), 1));
    } else if (!geo.getIndex()) {
      // Faces should already be set
    }

    // Animate from current position to deformed result
    animateTo(parsed.verts.slice());
    if (resetCam || !cameraFitted) {
      // Set geometry immediately so bounding sphere is correct
      setGeomVerts(parsed.verts, parsed.faces);
      fitCameraTopView();
    }
    document.getElementById('exportBtn').disabled = false;
    setStatus(statusLine());
  } catch (e) {
    setStatus('Error: ' + e.message);
  } finally {
    setLoading(false);
  }
}

function statusLine() {
  const a = mouseNames[state.mouseA] || '';
  const b = mouseNames[state.mouseB] || '';
  const pct = Math.round(state.morphT * 100);
  return pct > 0 ? `${a}  →  ${b}  (${pct}%)` : a;
}

// ── Export ────────────────────────────────────────────────────────────────────
document.getElementById('exportBtn').addEventListener('click', async () => {
  setStatus('Exporting full-resolution STL…');
  try {
    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        a: state.mouseA, b: state.mouseB,
        t: state.morphT, deform: state.deform,
      }),
    });
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = 'fasic_custom_mouse.stl'; a.click();
    URL.revokeObjectURL(url);
    setStatus('Exported ✓');
  } catch (e) { setStatus('Export failed: ' + e.message); }
});

// ── Slider fill ───────────────────────────────────────────────────────────────
function updateSliderFill(el) {
  const pct = ((el.value - el.min) / (el.max - el.min) * 100).toFixed(1);
  el.style.setProperty('--pct', pct + '%');
}
updateSliderFill(morphSlider);

// ── Mouse selects ─────────────────────────────────────────────────────────────
async function loadMiceList() {
  setStatus('Loading mouse database…');
  const res  = await fetch('/api/mice');
  const mice = await res.json();
  mouseNames = mice.map(m => m.name);

  const selA = document.getElementById('selectA');
  const selB = document.getElementById('selectB');
  mice.forEach(m => {
    selA.add(new Option(m.name, m.id));
    selB.add(new Option(m.name, m.id));
  });
  selB.value = 1;

  selA.addEventListener('change', () => {
    state.mouseA = +selA.value;
    cameraFitted = false;
    prepareMeshes(true);
  });
  selB.addEventListener('change', () => {
    state.mouseB = +selB.value;
    prepareMeshes(false);
  });

  // Init deform state defaults
  for (const [part, { dims }] of Object.entries(PARTS))
    for (const dim of dims)
      state.deform[`${part},${dim}`] = DIM_DEFAULT[dim];

  buildPartsPanel();
  await prepareMeshes(true);
}

// ── Parts panel ───────────────────────────────────────────────────────────────
function buildPartsPanel() {
  const container = document.getElementById('partSections');
  container.innerHTML = '';

  for (const [partKey, { label, dims }] of Object.entries(PARTS)) {
    const block  = document.createElement('div');
    block.className = 'part-block';

    const header = document.createElement('div');
    header.className = 'part-header';
    header.textContent = label.toUpperCase();
    block.appendChild(header);

    for (const dim of dims) {
      const [lo, hi]  = DIM_RANGE[dim];
      const def        = DIM_DEFAULT[dim];
      const stateKey   = `${partKey},${dim}`;
      const toSlider   = v => Math.round((v - lo) / (hi - lo) * 200);
      const toValue    = s => lo + (s / 200) * (hi - lo);
      const fmt        = v => (dim === 'width' || dim === 'height' || dim === 'length')
                              ? v.toFixed(2) + '×'
                              : (v >= 0 ? '+' : '') + v.toFixed(2);

      const row    = document.createElement('div');
      row.className = 'dim-row';

      const lbl    = document.createElement('div');
      lbl.className = 'dim-label';
      lbl.textContent = DIM_LABELS[dim];

      const slider = document.createElement('input');
      slider.type  = 'range';
      slider.className = 'slider';
      slider.min = 0; slider.max = 200;
      slider.value = toSlider(def);
      slider.dataset.stateKey = stateKey;
      slider.dataset.lo = lo; slider.dataset.hi = hi;
      updateSliderFill(slider);

      const valLbl = document.createElement('div');
      valLbl.className = 'dim-value';
      valLbl.textContent = fmt(def);

      const resetBtn = document.createElement('button');
      resetBtn.className = 'btn-reset';
      resetBtn.textContent = '↺';

      slider.addEventListener('input', () => {
        const v = toValue(+slider.value);
        state.deform[stateKey] = v;
        valLbl.textContent = fmt(v);
        updateSliderFill(slider);
        scheduleDeformUpdate();
      });

      resetBtn.addEventListener('click', () => {
        slider.value = toSlider(def);
        state.deform[stateKey] = def;
        valLbl.textContent = fmt(def);
        updateSliderFill(slider);
        scheduleDeformUpdate();
      });

      row.append(lbl, slider, valLbl, resetBtn);
      block.appendChild(row);
    }
    container.appendChild(block);
  }
}

// ── Reset all ─────────────────────────────────────────────────────────────────
document.getElementById('resetAllBtn').addEventListener('click', () => {
  document.querySelectorAll('#partSections input[type=range]').forEach(sl => {
    const dim = sl.dataset.stateKey.split(',')[1];
    const def = DIM_DEFAULT[dim];
    const lo  = +sl.dataset.lo, hi = +sl.dataset.hi;
    sl.value = Math.round((def - lo) / (hi - lo) * 200);
    state.deform[sl.dataset.stateKey] = def;
    updateSliderFill(sl);
    sl.nextElementSibling.textContent = (dim === 'width'||dim==='height'||dim==='length')
      ? def.toFixed(2)+'×' : (def>=0?'+':'')+def.toFixed(2);
  });
  scheduleDeformUpdate();
});

// ── Boot ──────────────────────────────────────────────────────────────────────
loadMiceList();
