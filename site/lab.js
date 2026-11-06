// Figure 2. Pronos at work. Eight clay stations, one per step of the loop, around the agent (the vault in the middle).
// The figure replays Pronos's real latest steps from the record: a hypothesis token travels to the station each step used,
// takes the colour of its outcome (teal pass, red fail, grey inconclusive), and every step drops a receipt on the stack.
import * as THREE from "./vendor/three/three.module.min.js";

const canvas = document.getElementById("lab");
if (canvas) {
const wrap = canvas.parentElement, cap = document.getElementById("lab-cap"), labelsEl = document.getElementById("lab-labels");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 200);
scene.add(new THREE.HemisphereLight(0xfffdf6, 0xe4ddcd, 1.1));
const key = new THREE.DirectionalLight(0xfff7ea, 2.0); key.position.set(6, 14, 9); key.castShadow = true;
key.shadow.mapSize.set(2048, 2048); Object.assign(key.shadow.camera, {left: -12, right: 12, top: 12, bottom: -12, near: 1, far: 50});
scene.add(key);
const floor = new THREE.Mesh(new THREE.CircleGeometry(30, 80), new THREE.ShadowMaterial({opacity: 0.1}));
floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
const clay = (c, x = {}) => new THREE.MeshStandardMaterial({color: c, roughness: 0.8, ...x});
const C = {teal: 0x2f7565, tealL: 0x5aa592, gold: 0xc99a3b, red: 0xb5523f, grey: 0x9a968a, ivory: 0xf1e6da, sand: 0xd9c3a8, ink: 0x3b3a36};

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h;
  // fit the whole ring (radius R plus the pedestals) across the width; desktop keeps its framing
  const halfW = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.aspect;
  const dist = Math.max(22.7, 8.2 / halfW);
  camera.position.set(0, dist * 0.66, dist * 0.77); camera.lookAt(0, 0.2, 0.6); camera.updateProjectionMatrix();
}
addEventListener("resize", resize); resize();

/* ---------- stations ---------- */
const NAMES = ["Ask", "Compete", "Freeze", "Test", "Attack", "Hidden test", "Replicate", "Judge"];
const R = 6, stations = [];
function cast(m) { m.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } }); return m; }
function prop(i) {
  const g = new THREE.Group();
  if (i === 0) { // Ask: a lens on a stem
    g.add(new THREE.Mesh(new THREE.TorusGeometry(0.32, 0.07, 12, 32), clay(C.ink)));
    const h = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.45, 10), clay(C.ink)); h.position.set(0.28, -0.32, 0); h.rotation.z = 0.7; g.add(h);
    g.rotation.x = -0.3; g.position.y = 0.55;
  } else if (i === 1) { // Compete: three rival pillars
    [-0.3, 0, 0.3].forEach((x, k) => { const p = new THREE.Mesh(new THREE.CapsuleGeometry(0.11, 0.3 + k * 0.12, 4, 10), clay([C.tealL, C.gold, C.red][k])); p.position.set(x, 0.35 + k * 0.06, 0); g.add(p); });
  } else if (i === 2) { // Freeze: an ice block with a seal
    const b = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.5, 0.62), new THREE.MeshPhysicalMaterial({color: 0xdfeef0, roughness: 0.15, transmission: 0.55, thickness: 0.4}));
    b.position.y = 0.3; g.add(b); const s = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.06, 20), clay(C.gold)); s.position.set(0, 0.3, 0.33); s.rotation.x = Math.PI / 2; g.add(s);
  } else if (i === 3) { // Test: a flask
    const prof = [[0, 0], [0.32, 0], [0.34, 0.05], [0.32, 0.3], [0.12, 0.55], [0.1, 0.78], [0.13, 0.8]].map(([x, y]) => new THREE.Vector2(x, y));
    const f = new THREE.Mesh(new THREE.LatheGeometry(prof, 28), clay(0xe9e3d6, {side: THREE.DoubleSide})); g.add(f);
    const liq = new THREE.Mesh(new THREE.CylinderGeometry(0.27, 0.31, 0.22, 24), clay(C.tealL)); liq.position.y = 0.12; g.add(liq);
  } else if (i === 4) { // Attack: the skeptic's spike
    const c = new THREE.Mesh(new THREE.ConeGeometry(0.26, 0.75, 6), clay(C.red)); c.position.y = 0.4; g.add(c);
  } else if (i === 5) { // Hidden test: a closed box
    const b = new THREE.Mesh(new THREE.BoxGeometry(0.66, 0.42, 0.66), clay(C.ink)); b.position.y = 0.24; g.add(b);
    const lid = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.08, 0.72), clay(0x55524b)); lid.position.y = 0.49; g.add(lid); g.userData.lid = lid;
  } else if (i === 6) { // Replicate: two identical barrels
    [-0.2, 0.2].forEach(x => { const b = new THREE.Mesh(new THREE.CapsuleGeometry(0.15, 0.25, 4, 12), clay(C.teal)); b.position.set(x, 0.33, 0); g.add(b); });
  } else { // Judge: a balance
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.7, 10), clay(C.ink)); post.position.y = 0.35; g.add(post);
    const beam = new THREE.Group(); beam.position.y = 0.7; g.add(beam); g.userData.beam = beam;
    const bar = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.04, 0.05), clay(C.ink)); beam.add(bar);
    [-0.42, 0.42].forEach(x => { const pan = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.12, 0.04, 18), clay(C.gold)); pan.position.set(x, -0.16, 0); beam.add(pan); });
  }
  return g;
}
NAMES.forEach((n, i) => {
  const a = -Math.PI / 2 + i / NAMES.length * Math.PI * 2;
  const g = new THREE.Group(); g.position.set(Math.cos(a) * R, 0, Math.sin(a) * R);
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.95, 1.05, 0.38, 40), clay(C.ivory)); base.position.y = 0.19; g.add(base);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(1.0, 0.045, 10, 60), clay(C.sand, {emissive: 0x000000})); ring.rotation.x = Math.PI / 2; ring.position.y = 0.39; g.add(ring);
  const p = prop(i); p.position.y += 0.38; g.add(p);
  scene.add(cast(g));
  const lab = document.createElement("span"); lab.className = "lab-l"; lab.textContent = n; labelsEl.appendChild(lab);
  stations.push({g, ring, prop: p, angle: a, label: lab, glow: 0});
});
// the path between stations
const path = new THREE.Mesh(new THREE.TorusGeometry(R, 0.03, 8, 160), clay(C.sand)); path.rotation.x = Math.PI / 2; path.position.y = 0.02; scene.add(path);

/* ---------- the agent: a small vault in the middle ---------- */
const agent = new THREE.Group(); scene.add(agent);
const prof = []; for (let k = 0; k <= 24; k++) { const t = k / 24, a = (t - 0.5) * Math.PI; prof.push(new THREE.Vector2(0.95 * Math.cos(a * 0.92), t * 2.4 - 1.2)); }
const body = new THREE.Mesh(new THREE.LatheGeometry(prof, 48), clay(C.teal)); agent.add(body);
for (let k = 0; k < 18; k++) {
  const a = k / 18 * Math.PI * 2, pts = [];
  for (let j = 0; j <= 16; j++) { const t = j / 16, b = (t - 0.5) * Math.PI; pts.push(new THREE.Vector3(Math.cos(a + t * 0.8) * 0.97 * Math.cos(b * 0.92), t * 2.4 - 1.2, Math.sin(a + t * 0.8) * 0.97 * Math.cos(b * 0.92))); }
  agent.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 24, 0.045, 6), clay(C.tealL)));
}
const waistMat = clay(C.gold, {emissive: 0x3a2400, emissiveIntensity: 0.2});
const waist = new THREE.Mesh(new THREE.TorusGeometry(0.97, 0.07, 10, 60), waistMat); waist.rotation.x = Math.PI / 2; agent.add(waist);
agent.position.y = 1.6; cast(agent);

/* ---------- token, beam, receipts ---------- */
const tokMat = clay(C.gold, {emissive: 0x000000});
const token = cast(new THREE.Mesh(new THREE.CapsuleGeometry(0.18, 0.28, 4, 12), tokMat)); scene.add(token);
const beamMat = new THREE.LineBasicMaterial({color: C.gold, transparent: true, opacity: 0});
const beamGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
const beamLine = new THREE.Line(beamGeo, beamMat); scene.add(beamLine);
const slips = [], slipGeo = new THREE.BoxGeometry(0.62, 0.025, 0.42), slipMat = clay(0xfbf8f1);
const STACK = new THREE.Vector3(2.1, 0, 2.3);
function dropSlip() {
  if (slips.length >= 28) { for (const s of slips) scene.remove(s); slips.length = 0; }
  const s = cast(new THREE.Mesh(slipGeo, slipMat)); s.position.set(STACK.x, 3, STACK.z); s.rotation.y = (Math.random() - 0.5) * 0.5;
  s.userData.target = 0.03 + slips.length * 0.03; scene.add(s); slips.push(s);
}

/* ---------- events from the record ---------- */
let events = [], idx = 0, cur = null, tStart = 0, from = 0, to = 0, lastKey = "";
const STEP = 2.6;
function stationOf(e) {
  const k = e.kind, a = e.agent;
  if (k === "ask") return 0; if (k === "hypothesis") return 1; if (k === "freeze") return 2;
  if (k === "experiment") return a === "Held-out evaluator" ? 5 : 3;
  if (k === "review") return 4; if (k === "replication") return 6;
  if (k === "confidence" || k === "contradiction" || k === "correction") return 7;
  return -1;   // scheduler, memory, census, structures: the agent itself
}
function outcome(e) {
  const t = e.text;
  if (/\(pass\)|reproduced E\d+ \(original pass/.test(t)) return "pass";
  if (/\(fail\)|reproduced E\d+ \(original fail|disagreed/.test(t)) return "fail";
  if (/inconclusive|could not settle/.test(t)) return "maybe";
  const m = t.match(/confidence ([\d.]+) -> ([\d.]+)/); if (m) return +m[2] >= +m[1] ? "pass" : "fail";
  return "";
}
const who = a => a === "Corbel" ? "Pronos" : a;
const hm = ts => new Date(ts * 1000).toISOString().slice(11, 16);
function setCap(e) {
  if (!e) { cap.textContent = "Reading the record…"; return; }
  cap.innerHTML = "";
  const t = document.createElement("span"); t.className = "lab-t"; t.textContent = hm(e.ts) + " UTC";
  const w = document.createElement("b"); w.textContent = " " + who(e.agent) + " · ";
  const x = document.createElement("span"); x.textContent = e.text; x.dataset.full = e.text; x.textContent = "";
  cap.append(t, w, x); cap.dataset.typing = "1"; cap._x = x; cap._n = 0;
}
async function load() {
  try {
    const s = await (await fetch("status.json", {cache: "no-store"})).json();
    const ev = s.events.slice(0, 48).reverse();
    const k = ev.length ? ev[ev.length - 1].ts + ":" + ev.length : "";
    if (k !== lastKey) { events = ev; lastKey = k; if (idx >= events.length) idx = 0; }
  } catch (e) {}
}
load(); setInterval(load, 60000);

function stationPos(i, out = new THREE.Vector3()) { const a = stations[i].angle; return out.set(Math.cos(a) * (R - 1.35), 0.55, Math.sin(a) * (R - 1.35)); }
const restPos = new THREE.Vector3(0, 0.3, 1.6);
function next(now) {
  if (!events.length) return;
  cur = events[idx % events.length]; idx++;
  from = to; to = stationOf(cur); tStart = now;
  setCap(cur); dropSlip();
  const o = outcome(cur);
  tokMat.color.setHex(o === "pass" ? C.teal : o === "fail" ? C.red : o === "maybe" ? C.grey : C.gold);
  if (to >= 0) stations[to].glow = 1;
}

/* ---------- loop ---------- */
let visible = true;
new IntersectionObserver(es => { visible = es[0].isIntersecting; }, {threshold: 0.05}).observe(canvas);
const clock = new THREE.Clock(); let last = -STEP;
const v1 = new THREE.Vector3(), v2 = new THREE.Vector3(), scr = new THREE.Vector3();
function frame() {
  requestAnimationFrame(frame);
  if (!visible) return;
  const now = clock.getElapsedTime();
  if (now - last >= (reduce ? STEP * 2 : STEP)) { next(now); last = now; }
  const k = Math.min(1, (now - tStart) / 1.1), e = k * k * (3 - 2 * k);
  // token: glide around the ring from the previous station to this one (or rest by the agent)
  const pa = from >= 0 ? stationPos(from, v1) : v1.copy(restPos), pb = to >= 0 ? stationPos(to, v2) : v2.copy(restPos);
  token.position.lerpVectors(pa, pb, e); token.position.y = 0.55 + Math.sin(e * Math.PI) * 1.2;
  token.rotation.y += 0.04;
  // the agent turns toward its work and its waist glows on its own steps
  agent.rotation.y += reduce ? 0 : 0.004;
  agent.position.y = 1.6 + Math.sin(now * 1.3) * 0.06;
  waistMat.emissiveIntensity = 0.15 + (to < 0 ? 0.9 * (1 - k) : 0.1);
  // beam from the agent to the active station
  beamMat.opacity = to >= 0 ? 0.55 * (1 - Math.abs(0.5 - k) * 1.2) : 0;
  const bp = beamGeo.attributes.position; bp.setXYZ(0, 0, 1.6, 0); bp.setXYZ(1, token.position.x, token.position.y, token.position.z); bp.needsUpdate = true;
  // stations: glow decays; lid of the hidden box lifts while it is being tested; the balance tips with the verdict
  stations.forEach((s, i) => {
    s.glow = Math.max(0, s.glow - 0.012);
    s.ring.material.color.setHex(s.glow > 0.05 ? C.gold : C.sand); s.ring.scale.setScalar(1 + s.glow * 0.08);
    s.label.classList.toggle("on", s.glow > 0.3);
    if (s.prop.userData.lid) s.prop.userData.lid.position.y = 0.49 + (i === to ? Math.sin(e * Math.PI) * 0.35 : 0);
    if (s.prop.userData.beam) s.prop.userData.beam.rotation.z += (((i === to && cur) ? (outcome(cur) === "fail" ? 0.3 : outcome(cur) === "pass" ? -0.3 : 0) : 0) - s.prop.userData.beam.rotation.z) * 0.08;
    // labels follow the stations on screen
    scr.copy(s.g.position); scr.y = 1.7; scr.project(camera);
    s.label.style.transform = `translate(${(scr.x + 1) / 2 * canvas.clientWidth}px, ${(1 - scr.y) / 2 * canvas.clientHeight}px) translate(-50%, -100%)`;
  });
  for (const s of slips) s.position.y += (s.userData.target - s.position.y) * 0.18;
  // caption types itself
  if (cap.dataset.typing && cap._x) {
    const full = cap._x.dataset.full; cap._n = Math.min(full.length, cap._n + (reduce ? full.length : 3)); cap._x.textContent = full.slice(0, cap._n);
    if (cap._n >= full.length) delete cap.dataset.typing;
  }
  renderer.render(scene, camera);
}
frame();
}
