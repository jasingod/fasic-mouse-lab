import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ── State ─────────────────────────────────────────────────────────────────────
const state = { mouseA: 0, mouseB: 1, morphT: 0, deform: {} };

// ── Part / dim config ─────────────────────────────────────────────────────────
const PARTS_DEF = {
  front:   { label: 'Front',       dims: ['width','height','length','flare'] },
  back:    { label: 'Back / Hump', dims: ['width','height','length','curve'] },
  left:    { label: 'Left Side',   dims: ['width','flare'] },
  right:   { label: 'Right Side',  dims: ['width','flare'] },
  top:     { label: 'Top Surface', dims: ['height','curve'] },
  buttons: { label: 'Button Area', dims: ['height','length','curve'] },
  thumb:   { label: 'Thumb Rest',  dims: ['width','height','flare'] },
};
const PARTS_BOUNDS = {
  front:   { y: [0.00, 0.28] },
  back:    { y: [0.72, 1.00] },
  left:    { x: [0.00, 0.35] },
  right:   { x: [0.65, 1.00] },
  top:     { z: [0.62, 1.00] },
  buttons: { y: [0.00, 0.42], z: [0.52, 1.00] },
  thumb:   { x: [0.00, 0.32], z: [0.12, 0.68] },
};
const DIM_LABELS  = { width:'Width', height:'Height', length:'Length', flare:'Flare', curve:'Curve' };
const DIM_DEFAULT = { width:1.0, height:1.0, length:1.0, flare:0.0, curve:0.0 };
const DIM_RANGE   = {
  width:[0.80,1.25], height:[0.75,1.30], length:[0.85,1.20],
  flare:[-0.15,0.15], curve:[-0.20,0.20],
};

// ── Three.js setup ────────────────────────────────────────────────────────────
const canvas   = document.getElementById('canvas');
const viewport = document.getElementById('viewport');

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping      = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x080814);
scene.fog = new THREE.FogExp2(0x080814, 0.0018);

const grid = new THREE.GridHelper(400, 20, 0x161630, 0x111128);
scene.add(grid);

const camera = new THREE.PerspectiveCamera(42, 1, 0.5, 3000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.07;
controls.minDistance   = 30;
controls.maxDistance   = 800;
controls.rotateSpeed   = 0.6;
controls.zoomSpeed     = 1.0;

scene.add(
  Object.assign(new THREE.AmbientLight(0xffffff, 0.30)),
  Object.assign(new THREE.DirectionalLight(0xffffff, 1.05), { position: new THREE.Vector3(1.5,2.5,2.0) }),
  Object.assign(new THREE.DirectionalLight(0x9aaaff, 0.20), { position: new THREE.Vector3(-1.5,0.5,-1.0) }),
  Object.assign(new THREE.DirectionalLight(0xffffff, 0.12), { position: new THREE.Vector3(0,-1.5,-2.5) }),
);

const geo    = new THREE.BufferGeometry();
const mat    = new THREE.MeshStandardMaterial({ color:0xc8d2e8, roughness:0.40, metalness:0.05, side:THREE.DoubleSide });
const meshObj = new THREE.Mesh(geo, mat);
scene.add(meshObj);

function resize() {
  const w = viewport.clientWidth, h = viewport.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(viewport);
resize();

// ── Animation ─────────────────────────────────────────────────────────────────
let animFrom = null, animTo = null, animT = 1.0;
const ANIM_DUR = 0.22;
let lastTime = 0;
function easeOutQuart(t) { return 1 - (1-t)**4; }

function animateTo(newVerts) {
  const pos = geo.getAttribute('position');
  animFrom = pos ? new Float32Array(pos.array) : new Float32Array(newVerts);
  animTo   = newVerts;
  animT    = 0.0;
}

renderer.setAnimationLoop((now) => {
  const dt = Math.min((now - lastTime) / 1000, 0.05);
  lastTime = now;
  controls.update();
  if (animT < 1.0 && animFrom && animTo) {
    animT = Math.min(1.0, animT + dt / ANIM_DUR);
    const et  = easeOutQuart(animT);
    const pos = geo.getAttribute('position');
    if (pos && pos.array.length === animTo.length) {
      for (let i = 0; i < pos.array.length; i++)
        pos.array[i] = animFrom[i] * (1-et) + animTo[i] * et;
      pos.needsUpdate = true;
      geo.computeVertexNormals();
    }
  }
  renderer.render(scene, camera);
});

// ── Camera fit — top view ─────────────────────────────────────────────────────
let cameraFitted = false;
function fitCameraTopView() {
  geo.computeBoundingSphere();
  const s = geo.boundingSphere;
  if (!s || s.radius === 0) return;
  const { center: c, radius: r } = s;
  controls.target.set(c.x, c.y, c.z);
  camera.position.set(c.x, c.y, c.z + r * 3.0);
  camera.up.set(0, 1, 0);
  controls.update();
  grid.position.set(c.x, c.y, c.z - r * 1.05);
  cameraFitted = true;
}

// ── Upload geometry ───────────────────────────────────────────────────────────
function setGeom(verts, faces, fitCamera) {
  const pos = geo.getAttribute('position');
  if (!pos || pos.count !== verts.length / 3) {
    geo.setAttribute('position', new THREE.BufferAttribute(verts.slice(), 3));
  } else {
    pos.array.set(verts);
    pos.needsUpdate = true;
  }
  if (faces) geo.setIndex(new THREE.BufferAttribute(faces.slice(), 1));
  geo.computeVertexNormals();
  geo.computeBoundingSphere();
  if (fitCamera || !cameraFitted) fitCameraTopView();
  document.getElementById('exportBtn').disabled = false;
}

// ── Mesh cache (binary blobs) ─────────────────────────────────────────────────
const _meshCache = {};
async function getMesh(id) {
  if (!_meshCache[id]) {
    const res  = await fetch(`/data/mesh_${id}.bin`);
    const buf  = await res.arrayBuffer();
    const view = new DataView(buf);
    const nV   = view.getUint32(0, true);
    const nF   = view.getUint32(4, true);
    _meshCache[id] = {
      verts: new Float32Array(buf, 8,           nV * 3).slice(),
      faces: new Uint32Array (buf, 8 + nV * 12, nF * 3).slice(),
    };
  }
  return _meshCache[id];
}

// ── Nearest-neighbour correspondence (O(Na × Nb) — fast for ~2500 verts) ─────
function computeCorrespondence(aV, bV) {
  const nA = aV.length / 3, nB = bV.length / 3;
  const out = new Float32Array(nB * 3);
  for (let i = 0; i < nB; i++) {
    const bx = bV[i*3], by = bV[i*3+1], bz = bV[i*3+2];
    let minD = Infinity, minJ = 0;
    for (let j = 0; j < nA; j++) {
      const dx = bx-aV[j*3], dy = by-aV[j*3+1], dz = bz-aV[j*3+2];
      const d2 = dx*dx + dy*dy + dz*dz;
      if (d2 < minD) { minD = d2; minJ = j; }
    }
    out[i*3] = aV[minJ*3]; out[i*3+1] = aV[minJ*3+1]; out[i*3+2] = aV[minJ*3+2];
  }
  return out;
}

// ── Laplacian smoothing ───────────────────────────────────────────────────────
function laplacianSmooth(verts, faces, iters = 1, lam = 0.5) {
  const n = verts.length / 3;
  // Build adjacency lists
  const nb = Array.from({ length: n }, () => []);
  for (let i = 0; i < faces.length; i += 3) {
    const a = faces[i], b = faces[i+1], c = faces[i+2];
    nb[a].push(b,c); nb[b].push(a,c); nb[c].push(a,b);
  }
  const v = verts.slice();
  const t = new Float32Array(v.length);
  for (let iter = 0; iter < iters; iter++) {
    for (let i = 0; i < n; i++) {
      const nbrs = nb[i];
      if (!nbrs.length) { t[i*3]=v[i*3]; t[i*3+1]=v[i*3+1]; t[i*3+2]=v[i*3+2]; continue; }
      let sx=0,sy=0,sz=0;
      for (const j of nbrs) { sx+=v[j*3]; sy+=v[j*3+1]; sz+=v[j*3+2]; }
      const inv = 1/nbrs.length;
      t[i*3]   = v[i*3]   *(1-lam) + sx*inv*lam;
      t[i*3+1] = v[i*3+1] *(1-lam) + sy*inv*lam;
      t[i*3+2] = v[i*3+2] *(1-lam) + sz*inv*lam;
    }
    v.set(t);
  }
  return v;
}

// ── Pair cache: correspondence is reused as long as A/B don't change ─────────
const _pairCache = {};
async function getPair(aId, bId) {
  const key = `${aId},${bId}`;
  if (!_pairCache[key]) {
    const [a, b] = await Promise.all([getMesh(aId), getMesh(bId)]);
    const aAlignedRaw = computeCorrespondence(a.verts, b.verts);
    const aAligned    = laplacianSmooth(aAlignedRaw, b.faces, 1);
    _pairCache[key] = { aAligned, bVerts: b.verts, bFaces: b.faces };
  }
  return _pairCache[key];
}

function lerpVerts(pair, t) {
  const { aAligned, bVerts } = pair;
  const out = new Float32Array(bVerts.length);
  const mt  = 1 - t;
  for (let i = 0; i < out.length; i++)
    out[i] = aAligned[i] * mt + bVerts[i] * t;
  return out;
}

// ── Deform system (all client-side) ──────────────────────────────────────────
function _minMax(v, ax) {
  let mn = Infinity, mx = -Infinity;
  for (let i = ax; i < v.length; i += 3) { if (v[i] < mn) mn=v[i]; if (v[i] > mx) mx=v[i]; }
  return [mn, mx];
}

function _normVerts(verts) {
  const n = verts.length / 3;
  const ranges = [0,1,2].map(ax => _minMax(verts, ax));
  const ext = ranges.map(([mn,mx]) => (mx-mn) || 1);
  const mn  = ranges.map(([mn]) => mn);
  const vn  = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    vn[i*3]   = (verts[i*3]   - mn[0]) / ext[0];
    vn[i*3+1] = (verts[i*3+1] - mn[1]) / ext[1];
    vn[i*3+2] = (verts[i*3+2] - mn[2]) / ext[2];
  }
  return { vn, mn, ext };
}

function _partMask(vn, partKey) {
  const spec  = PARTS_BOUNDS[partKey];
  const axMap = { x:0, y:1, z:2 };
  const n     = vn.length / 3;
  const mask  = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    let ok = true;
    for (const [ax, [lo, hi]] of Object.entries(spec)) {
      const v = vn[i*3 + axMap[ax]];
      if (v < lo || v > hi) { ok = false; break; }
    }
    mask[i] = ok ? 1 : 0;
  }
  return mask;
}

function _weightMask(verts, hard, radius = 0.18) {
  const n = verts.length / 3;
  const spans = [0,1,2].map(ax => { const [mn,mx] = _minMax(verts, ax); return mx-mn; });
  const span  = Math.max(...spans);

  const inIdx = [];
  for (let i = 0; i < n; i++) if (hard[i]) inIdx.push(i);
  if (!inIdx.length || inIdx.length === n) {
    const w = new Float32Array(n);
    for (let i = 0; i < n; i++) w[i] = hard[i] ? 1.0 : 0.0;
    return w;
  }

  // Sample up to 80 "in" vertices to keep weight calc fast
  const step    = Math.max(1, Math.floor(inIdx.length / 80));
  const samples = inIdx.filter((_,k) => k % step === 0);
  const maxDist = span * radius;

  const w = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    if (hard[i]) { w[i] = 1.0; continue; }
    let minD = Infinity;
    for (const j of samples) {
      const dx = verts[i*3]-verts[j*3], dy = verts[i*3+1]-verts[j*3+1], dz = verts[i*3+2]-verts[j*3+2];
      const d = Math.sqrt(dx*dx+dy*dy+dz*dz);
      if (d < minD) minD = d;
    }
    w[i] = Math.max(0, 1 - minD / maxDist);
  }
  return w;
}

function applyPartDeform(verts, partKey, dim, value) {
  const n = verts.length / 3;
  const { vn, mn, ext } = _normVerts(verts);
  const hard = _partMask(vn, partKey);
  const w    = _weightMask(verts, hard);

  // Center of the part
  let cx=0,cy=0,cz=0,cnt=0;
  for (let i=0;i<n;i++) if(hard[i]){cx+=verts[i*3];cy+=verts[i*3+1];cz+=verts[i*3+2];cnt++;}
  if(!cnt){for(let i=0;i<n;i++){cx+=verts[i*3];cy+=verts[i*3+1];cz+=verts[i*3+2];}cx/=n;cy/=n;cz/=n;}
  else{cx/=cnt;cy/=cnt;cz/=cnt;}

  const out = verts.slice();
  if (dim === 'width') {
    for (let i=0;i<n;i++) out[i*3]   += (verts[i*3]   - cx) * (value-1.0) * w[i];
  } else if (dim === 'height') {
    for (let i=0;i<n;i++) out[i*3+2] += (verts[i*3+2] - cz) * (value-1.0) * w[i];
  } else if (dim === 'length') {
    for (let i=0;i<n;i++) out[i*3+1] += (verts[i*3+1] - cy) * (value-1.0) * w[i];
  } else if (dim === 'flare') {
    let gcx=0; for(let i=0;i<n;i++) gcx+=verts[i*3]; gcx/=n;
    for (let i=0;i<n;i++){
      const sign = verts[i*3]>gcx?1:verts[i*3]<gcx?-1:0;
      out[i*3] += sign * value * ext[0] * w[i];
    }
  } else if (dim === 'curve') {
    const yMin = mn[1], yRng = ext[1];
    for (let i=0;i<n;i++){
      const yn = (verts[i*3+1]-yMin)/yRng;
      out[i*3+2] += value * ext[2] * 4.0 * yn*(1-yn) * w[i];
    }
  }
  return out;
}

function hasDeform() {
  return Object.entries(state.deform).some(([k,v]) => {
    const dim = k.split(',')[1];
    return Math.abs(v - DIM_DEFAULT[dim]) > 1e-5;
  });
}

function applyAllDeforms(verts) {
  let v = verts;
  for (const [k, val] of Object.entries(state.deform)) {
    const [part, dim] = k.split(',');
    const def = DIM_DEFAULT[dim];
    if (Math.abs(val - def) > 1e-5)
      v = applyPartDeform(v, part, dim, val);
  }
  return v;
}

// ── Current render state ──────────────────────────────────────────────────────
let currentPair     = null;
let baseMorphVerts  = null;   // morph result before deform

async function loadPair(resetCamera = false) {
  setLoading(true);
  setStatus('Loading meshes…');
  try {
    currentPair = await getPair(state.mouseA, state.mouseB);
    refresh(resetCamera || !cameraFitted);
    setStatus(statusLine());
  } catch(e) {
    setStatus('Error: ' + e.message);
  } finally {
    setLoading(false);
  }
}

function refresh(fitCamera = false) {
  if (!currentPair) return;
  baseMorphVerts = lerpVerts(currentPair, state.morphT);
  const verts    = hasDeform() ? applyAllDeforms(baseMorphVerts) : baseMorphVerts;
  setGeom(verts, currentPair.bFaces, fitCamera);
  document.getElementById('exportBtn').disabled = false;
}

// ── Morph slider ──────────────────────────────────────────────────────────────
const morphSlider = document.getElementById('morphSlider');
const morphPct    = document.getElementById('morphPct');
morphSlider.addEventListener('input', () => {
  state.morphT = morphSlider.value / 100;
  morphPct.textContent = morphSlider.value + ' %';
  updateSliderFill(morphSlider);
  if (!currentPair) return;
  baseMorphVerts = lerpVerts(currentPair, state.morphT);
  const verts = hasDeform() ? applyAllDeforms(baseMorphVerts) : baseMorphVerts;
  animateTo(verts);
});

// ── Deform update (debounced) ─────────────────────────────────────────────────
let deformTimer = null;
function scheduleDeform(delay = 120) {
  clearTimeout(deformTimer);
  deformTimer = setTimeout(() => {
    if (!baseMorphVerts) return;
    const verts = applyAllDeforms(baseMorphVerts);
    animateTo(verts);
  }, delay);
}

// ── Export ────────────────────────────────────────────────────────────────────
document.getElementById('exportBtn').addEventListener('click', async () => {
  setStatus('Exporting full-res STL…');
  try {
    const res  = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ a:state.mouseA, b:state.mouseB, t:state.morphT, deform:state.deform }),
    });
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = 'fasic_custom_mouse.stl'; a.click();
    URL.revokeObjectURL(url);
    setStatus('Exported ✓');
  } catch(e) { setStatus('Export failed: ' + e.message); }
});

// ── Loading overlay ───────────────────────────────────────────────────────────
const overlay = document.getElementById('loadingOverlay');
let loadCount = 0;
function setLoading(on) {
  loadCount = Math.max(0, loadCount + (on?1:-1));
  overlay.classList.toggle('active', loadCount > 0);
}
const statusEl = document.getElementById('statusText');
let mouseNames = [];
function setStatus(msg) { statusEl.textContent = msg; }
function statusLine() {
  const a = mouseNames[state.mouseA]||'', b = mouseNames[state.mouseB]||'';
  const p = Math.round(state.morphT*100);
  return p > 0 ? `${a}  →  ${b}  (${p}%)` : a;
}

// ── Slider fill ───────────────────────────────────────────────────────────────
function updateSliderFill(el) {
  const pct = ((el.value - el.min) / (el.max - el.min) * 100).toFixed(1);
  el.style.setProperty('--pct', pct + '%');
}
updateSliderFill(morphSlider);

// ── Mouse selects ─────────────────────────────────────────────────────────────
async function loadMiceList() {
  setStatus('Loading mouse database…');
  const mice = await (await fetch('/api/mice')).json();
  mouseNames = mice.map(m => m.name);
  const selA = document.getElementById('selectA');
  const selB = document.getElementById('selectB');
  mice.forEach(m => { selA.add(new Option(m.name, m.id)); selB.add(new Option(m.name, m.id)); });
  selB.value = 1;

  selA.addEventListener('change', () => { state.mouseA = +selA.value; cameraFitted=false; loadPair(true); });
  selB.addEventListener('change', () => { state.mouseB = +selB.value; loadPair(false); });

  for (const [part, {dims}] of Object.entries(PARTS_DEF))
    for (const dim of dims)
      state.deform[`${part},${dim}`] = DIM_DEFAULT[dim];

  buildPartsPanel();

  // Prefetch both default meshes in parallel, then load pair
  setStatus('Loading meshes…');
  await Promise.all([getMesh(0), getMesh(1)]);
  await loadPair(true);
}

// ── Parts panel ───────────────────────────────────────────────────────────────
function buildPartsPanel() {
  const container = document.getElementById('partSections');
  container.innerHTML = '';
  for (const [partKey, {label, dims}] of Object.entries(PARTS_DEF)) {
    const block  = document.createElement('div'); block.className='part-block';
    const header = document.createElement('div'); header.className='part-header'; header.textContent=label.toUpperCase();
    block.appendChild(header);
    for (const dim of dims) {
      const [lo,hi] = DIM_RANGE[dim];
      const def     = DIM_DEFAULT[dim];
      const key     = `${partKey},${dim}`;
      const toSlider = v => Math.round((v-lo)/(hi-lo)*200);
      const toVal    = s => lo + (s/200)*(hi-lo);
      const fmt      = v => (dim==='width'||dim==='height'||dim==='length') ? v.toFixed(2)+'×' : (v>=0?'+':'')+v.toFixed(2);

      const row    = document.createElement('div'); row.className='dim-row';
      const lbl    = document.createElement('div'); lbl.className='dim-label'; lbl.textContent=DIM_LABELS[dim];
      const slider = document.createElement('input'); slider.type='range'; slider.className='slider';
      slider.min=0; slider.max=200; slider.value=toSlider(def);
      slider.dataset.stateKey=key; slider.dataset.lo=lo; slider.dataset.hi=hi;
      updateSliderFill(slider);
      const valLbl  = document.createElement('div'); valLbl.className='dim-value'; valLbl.textContent=fmt(def);
      const resetBtn = document.createElement('button'); resetBtn.className='btn-reset'; resetBtn.textContent='↺';

      slider.addEventListener('input', () => {
        const v = toVal(+slider.value);
        state.deform[key] = v;
        valLbl.textContent = fmt(v);
        updateSliderFill(slider);
        scheduleDeform();
      });
      resetBtn.addEventListener('click', () => {
        slider.value = toSlider(def);
        state.deform[key] = def;
        valLbl.textContent = fmt(def);
        updateSliderFill(slider);
        scheduleDeform();
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
    const lo=+sl.dataset.lo, hi=+sl.dataset.hi;
    sl.value = Math.round((def-lo)/(hi-lo)*200);
    state.deform[sl.dataset.stateKey] = def;
    updateSliderFill(sl);
    const valLbl = sl.nextElementSibling;
    valLbl.textContent = (dim==='width'||dim==='height'||dim==='length')?def.toFixed(2)+'×':(def>=0?'+':'')+def.toFixed(2);
  });
  scheduleDeform(0);
});

// ── Boot ──────────────────────────────────────────────────────────────────────
loadMiceList();
