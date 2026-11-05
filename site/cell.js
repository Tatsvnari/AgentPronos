// Figure 1. A cell cut open, vault particles drifting in its cytoplasm. Clay, like everything here.
// The large vault follows the reported phage vault L05: 48 chains per half wound in from the waist toward the cap,
// the cap closing in three tiers (of every three neighbouring chains one stops at the first tier, one at the second,
// one reaches the tip), about 54 nm long and 45 nm wide. The gold beads are the 96 pockets that hold a molecule
// no one has identified. One small vault has come apart into its two halves.
import * as THREE from "./vendor/three/three.module.min.js";
import { OrbitControls } from "./vendor/three/OrbitControls.js";

const canvas = document.getElementById("cell");
const tip = document.getElementById("cell-tip");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const rnd = (() => { let s = 11; return () => (s = (s * 16807) % 2147483647) / 2147483647; })();

const renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 200);
camera.position.set(0.8, 3.0, 25.5);
const controls = new OrbitControls(camera, canvas);
controls.target.set(0, 0.2, 0); controls.enableZoom = false; controls.enablePan = false; controls.enableDamping = true;
controls.minPolarAngle = 1.0; controls.maxPolarAngle = 1.9; controls.minAzimuthAngle = -0.9; controls.maxAzimuthAngle = 0.9;
controls.rotateSpeed = 0.45;

scene.add(new THREE.HemisphereLight(0xfffdf6, 0xe7e1d3, 1.05));
const key = new THREE.DirectionalLight(0xfff8ec, 2.1); key.position.set(5, 9, 8); key.castShadow = true;
key.shadow.mapSize.set(2048, 2048); key.shadow.radius = 6;
Object.assign(key.shadow.camera, {left: -9, right: 9, top: 9, bottom: -9, near: 1, far: 40});
scene.add(key);
const rim = new THREE.DirectionalLight(0xe9f2ee, 0.6); rim.position.set(-7, 2, -4); scene.add(rim);

// On narrow screens the camera steps back along its own line of sight so the whole cut-open cell fits the width.
const BASE_DIST = 25.5, FIT_R = 8.4;
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  const halfH = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)), halfW = halfH * camera.aspect;
  const dist = Math.max(BASE_DIST, FIT_R / halfW);   // only narrow screens move; desktop keeps its framing
  const dir = camera.position.clone().sub(controls.target).normalize();
  camera.position.copy(controls.target).addScaledVector(dir, dist);
}
addEventListener("resize", resize); resize();

// speckled clay: a canvas of dots used as the colour map
function speckle(base, dot, n, size = 512) {
  const c = document.createElement("canvas"); c.width = c.height = size; const g = c.getContext("2d");
  g.fillStyle = base; g.fillRect(0, 0, size, size);
  for (let i = 0; i < n; i++) {
    g.fillStyle = dot; g.globalAlpha = 0.25 + rnd() * 0.5;
    g.beginPath(); g.arc(rnd() * size, rnd() * size, 0.6 + rnd() * 1.9, 0, 7); g.fill();
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; return t;
}
const clay = (color, map, extra = {}) => new THREE.MeshStandardMaterial({color, map, roughness: 0.82, metalness: 0, ...extra});

function lumpy(geo, amp, f) {
  const p = geo.attributes.position, v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    const k = 1 + amp * (Math.sin(v.x * f + 1.3) * Math.sin(v.y * f * 0.8) + 0.6 * Math.sin(v.z * f * 1.3 + v.x));
    p.setXYZ(i, v.x * k, v.y * k, v.z * k);
  }
  geo.computeVertexNormals(); return geo;
}

/* ---------- the cell: a lumpy membrane, cut open toward the viewer ---------- */
const CELL_R = 7.2;
const cell = new THREE.Group(); scene.add(cell);
const memTex = speckle("#efe6dc", "#b9a58f", 2600); memTex.repeat.set(3, 2);
const cut = 1.05;
const memGeo = lumpy(new THREE.SphereGeometry(CELL_R, 120, 90, 0, Math.PI * 2, cut, Math.PI - cut), 0.025, 0.9);
const outer = new THREE.Mesh(memGeo, clay(0xf1e6da, memTex, {side: THREE.FrontSide}));
const inner = new THREE.Mesh(memGeo, clay(0xe9d2c6, memTex, {side: THREE.BackSide, roughness: 0.9}));
for (const m of [outer, inner]) { m.rotation.x = Math.PI / 2; m.castShadow = m === outer; m.receiveShadow = true; cell.add(m); }
// the membrane's cut edge: a soft, thick lip
const lipR = CELL_R * Math.sin(cut), lipZ = CELL_R * Math.cos(cut);
const lip = new THREE.Mesh(new THREE.TorusGeometry(lipR, 0.2, 18, 160), clay(0xe2c9b8, memTex));
lip.position.z = lipZ; cell.add(lip);

// nucleus at the back, with pores
const nucTex = speckle("#cdb9c9", "#7d6683", 3000);
const nucleus = new THREE.Mesh(lumpy(new THREE.SphereGeometry(2.6, 90, 70), 0.035, 1.4), clay(0xcbb6c8, nucTex));
nucleus.position.set(-2.6, -0.9, -3.4); nucleus.castShadow = nucleus.receiveShadow = true; cell.add(nucleus);
const poreGeo = new THREE.TorusGeometry(0.17, 0.06, 10, 22), poreMat = clay(0x8f7894);
for (let i = 0; i < 46; i++) {
  const v = new THREE.Vector3(rnd() * 2 - 1, rnd() * 2 - 1, rnd() * 2 - 1).normalize();
  if (v.z < -0.2) continue;
  const p = new THREE.Mesh(poreGeo, poreMat); p.position.copy(v.multiplyScalar(2.62)).add(nucleus.position);
  p.lookAt(nucleus.position); cell.add(p);
}

// ribosome-sized specks and a few microtubules through the cytoplasm
const ribo = new THREE.InstancedMesh(new THREE.SphereGeometry(0.075, 10, 8), clay(0x9a7f8f), 900);
const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3();
let ri = 0;
while (ri < 900) {
  const v = new THREE.Vector3(rnd() * 2 - 1, rnd() * 2 - 1, rnd() * 2 - 1).multiplyScalar(CELL_R - 0.6);
  if (v.length() > CELL_R - 0.5 || v.distanceTo(nucleus.position) < 2.9 || v.z > lipZ - 0.2) continue;
  const s = 0.7 + rnd() * 0.7; sc.set(s, s, s);
  ribo.setMatrixAt(ri++, m4.compose(v, q, sc));
}
ribo.castShadow = true; cell.add(ribo);
const tubeMat = clay(0xd9c3a8);
for (let k = 0; k < 5; k++) {
  const pts = []; const a = rnd() * 6.28, b = rnd() * 6.28;
  for (let i = 0; i <= 8; i++) {
    const t = i / 8 - 0.5;
    pts.push(new THREE.Vector3(Math.cos(a) * t * 11 + Math.sin(b + i) * 0.5, Math.sin(a) * t * 7 + Math.cos(b * i) * 0.4, -2.2 + Math.sin(i + b) * 1.6));
  }
  const tube = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 90, 0.07, 8), tubeMat);
  tube.castShadow = true; cell.add(tube);
}

/* ---------- vaults ---------- */
const TEAL = [0x3f8f7d, 0x5aa592, 0x2f7565], GOLD = 0xc99a3b;
const ribMats = TEAL.map(c => clay(c, null, {roughness: 0.7}));
const goldMat = clay(GOLD, null, {roughness: 0.45, metalness: 0.15, emissive: 0x3a2400, emissiveIntensity: 0.2});
const HALF = 1.2;    // half-length / radius: 27 nm / 22.5 nm

// one point on the vault's meridian: t = 0 at the waist, 1 at the tip
function meridian(t) {
  if (t < 0.48) { const u = t / 0.48; return [1 - 0.04 * u * u, u * 0.58 * HALF]; }
  const a = (t - 0.48) / 0.52 * Math.PI / 2;
  return [0.96 * Math.cos(a), (0.58 + 0.42 * Math.sin(a)) * HALF];
}

function half(n, sign, pockets) {
  const g = new THREE.Group();
  const tubR = Math.min(0.075, 2.6 / n);
  for (let i = 0; i < n; i++) {
    const tier = i % 3, tEnd = [0.7, 0.85, 0.995][tier], th0 = i / n * Math.PI * 2;
    const pts = [];
    for (let k = 0; k <= 28; k++) {
      const t = tEnd * k / 28, [r, y] = meridian(t), th = th0 + 0.95 * t * sign;
      pts.push(new THREE.Vector3(Math.cos(th) * r, y * sign, Math.sin(th) * r));
    }
    const rib = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 40, tubR * (tier === 2 ? 0.95 : 1), 7), ribMats[tier]);
    rib.castShadow = true; g.add(rib);
    // the end of each chain is a little rounded knuckle
    const kn = new THREE.Mesh(new THREE.SphereGeometry(tubR * 1.35, 10, 8), ribMats[tier]); kn.position.copy(pts[pts.length - 1]); g.add(kn);
    if (pockets) {
      const [r, y] = meridian(0.38), th = th0 + 0.95 * 0.38 * sign;
      const b = new THREE.Mesh(new THREE.SphereGeometry(tubR * 0.9, 10, 8), goldMat);
      b.position.set(Math.cos(th) * (r + tubR * 0.8), y * sign, Math.sin(th) * (r + tubR * 0.8));
      b.userData.pocket = true; g.add(b); pockets.push(b);
    }
  }
  // inner wall so the barrel reads as a closed shell
  const prof = []; for (let k = 0; k <= 24; k++) { const [r, y] = meridian(k / 24); prof.push(new THREE.Vector2(r * 0.93, y)); }
  const wall = new THREE.Mesh(new THREE.LatheGeometry(prof, 64), clay(0x2a5c50, null, {side: THREE.DoubleSide, roughness: 0.95}));
  wall.scale.y = sign; g.add(wall);
  return g;
}

function vault(n, pockets) {
  const v = new THREE.Group();
  v.add(half(n, 1, pockets)); v.add(half(n, -1, pockets));
  const waist = new THREE.Mesh(new THREE.TorusGeometry(1.0, 0.06, 10, 90), goldMat); waist.rotation.x = Math.PI / 2; v.add(waist);
  return v;
}

const pockets = [];
const hero = vault(48, pockets); hero.scale.setScalar(2.05); hero.position.set(1.9, 0.35, 1.8);
hero.rotation.set(0.25, 0, -0.42); scene.add(hero); hero.userData.name = "hero";

const others = [];
const spots = [[-3.6, 3.0, -0.4, 0.62], [4.4, -2.6, -1.6, 0.55], [-0.6, -3.2, 0.4, 0.5], [3.6, 3.4, -3.0, 0.48], [-4.8, -0.2, 1.4, 0.5]];
for (const [x, y, z, s] of spots) {
  const v = vault(24, null); v.scale.setScalar(s); v.position.set(x, y, z);
  v.rotation.set(rnd() * 3, rnd() * 3, rnd() * 3); v.userData.spin = (rnd() - 0.5) * 0.4; scene.add(v); others.push(v);
}
// one vault come apart: its two halves drifting a little way from each other
const openV = new THREE.Group(), hA = half(24, 1, null), hB = half(24, -1, null);
openV.add(hA, hB); openV.scale.setScalar(0.6); openV.position.set(-1.4, 2.4, 2.2); openV.rotation.set(0.9, 0.3, 0.7); scene.add(openV);

/* ---------- hover: what you are looking at ---------- */
const ray = new THREE.Raycaster(), mouse = new THREE.Vector2(-9, -9);
let over = "";
canvas.addEventListener("pointermove", e => {
  const r = canvas.getBoundingClientRect();
  mouse.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
  tip.style.left = (e.clientX - r.left + 14) + "px"; tip.style.top = (e.clientY - r.top + 10) + "px";
});
canvas.addEventListener("pointerleave", () => { mouse.set(-9, -9); tip.hidden = true; });
const TIPS = {
  pocket: "One of 96 pockets. Each holds a small molecule seen in the map and not yet identified.",
  hero: "A vault particle: 96 copies of one protein, two halves of 48 joined at the gold waist.",
  open: "A vault come apart into its two halves.",
  nucleus: "The nucleus.",
  vault: "A vault particle in the cytoplasm.",
};
function pick() {
  ray.setFromCamera(mouse, camera);
  const hit = ray.intersectObjects([hero, openV, nucleus, ...others], true)[0];
  let w = "";
  if (hit) {
    if (hit.object.userData.pocket) w = "pocket";
    else { let o = hit.object; while (o.parent && o.parent !== scene) o = o.parent; w = o === hero ? "hero" : o === openV ? "open" : o === nucleus || hit.object === nucleus ? "nucleus" : "vault"; }
  }
  if (w !== over) { over = w; tip.hidden = !w; if (w) tip.textContent = TIPS[w]; canvas.style.cursor = w ? "help" : "grab"; }
}

/* ---------- life ---------- */
const clock = new THREE.Clock();
let pulse = 0, lastT = 0;
addEventListener("vfs:event", () => { pulse = 1; });   // a new record entry makes the pockets flare once
function frame() {
  const t = clock.getElapsedTime(), dt = Math.min(t - lastT, 0.05); lastT = t;
  if (!reduce) {
    hero.rotateY(0.0025);
    hero.position.y = 0.35 + Math.sin(t * 0.6) * 0.12;
    for (const v of others) { v.rotation.y += v.userData.spin * 0.01; v.position.y += Math.sin(t * 0.5 + v.position.x) * 0.0015; }
    const gap = 0.35 + 0.25 * (0.5 + 0.5 * Math.sin(t * 0.35));
    hA.position.y = gap; hB.position.y = -gap; hA.rotation.z = 0.12 * Math.sin(t * 0.35); hB.rotation.z = -0.1 * Math.sin(t * 0.35 + 0.5);
    openV.rotation.y += 0.002;
    pulse = Math.max(0, pulse - dt * 0.6);
    goldMat.emissiveIntensity = 0.18 + 0.12 * Math.sin(t * 1.4) + pulse * 1.2;
  }
  pick();
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
frame();
