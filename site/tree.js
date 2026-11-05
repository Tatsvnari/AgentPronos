// Figure 2. The census as a clay tree. Root in the middle; arches run out to the three domains, then phyla, then genera.
// Every vault-family protein in the census is one small barrel stacked on its genus. Domains are spaced by the square
// root of their genus count, so the rare prokaryotic vaults stay visible; the caption says so.
import * as THREE from "./vendor/three/three.module.min.js";
import { OrbitControls } from "./vendor/three/OrbitControls.js";

const canvas = document.getElementById("tree");
const tip = document.getElementById("tree-tip");
const info = document.getElementById("tree-info");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const COL = {Bacteria: 0x3f8f7d, Archaea: 0xc99a3b, Eukaryota: 0x9c7fa8};

const renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 300);
camera.position.set(0, 19, 31);
const controls = new OrbitControls(camera, canvas);
controls.enableZoom = true; controls.minDistance = 10; controls.maxDistance = 45; controls.enablePan = false; controls.enableDamping = true;
controls.maxPolarAngle = 1.35; controls.autoRotate = !reduce; controls.autoRotateSpeed = 0.35;
scene.add(new THREE.HemisphereLight(0xfffdf6, 0xe4ddcd, 1.1));
const key = new THREE.DirectionalLight(0xfff7ea, 2.0); key.position.set(8, 16, 10); key.castShadow = true;
key.shadow.mapSize.set(2048, 2048); Object.assign(key.shadow.camera, {left: -16, right: 16, top: 16, bottom: -16, near: 1, far: 60});
scene.add(key);
const floor = new THREE.Mesh(new THREE.CircleGeometry(30, 96), new THREE.ShadowMaterial({opacity: 0.1}));
floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
function resize() { const w = canvas.clientWidth, h = canvas.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
addEventListener("resize", resize); resize();
const clay = (c, x = {}) => new THREE.MeshStandardMaterial({color: c, roughness: 0.8, ...x});

let built = false, genusMeshes = [], hovered = null;
const R = {domain: 3.2, phylum: 7.5, genus: 12};

function arch(a, b, h, mat, rad) {
  const mid = a.clone().add(b).multiplyScalar(0.5); mid.y += h;
  const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
  const m = new THREE.Mesh(new THREE.TubeGeometry(curve, 24, rad, 7), mat); m.castShadow = true; scene.add(m);
}
const at = (r, a, y = 0) => new THREE.Vector3(Math.cos(a) * r, y, Math.sin(a) * r);

export function buildTree(leaves) {
  if (built || !leaves || !leaves.length) return; built = true;
  // group: domain -> phylum -> genus -> proteins
  const T = new Map();
  for (const l of leaves) {
    if (!T.has(l.domain)) T.set(l.domain, new Map());
    const P = T.get(l.domain); if (!P.has(l.phylum)) P.set(l.phylum, new Map());
    const G = P.get(l.phylum); if (!G.has(l.genus)) G.set(l.genus, []);
    G.get(l.genus).push(l);
  }
  const order = ["Bacteria", "Archaea", "Eukaryota"].filter(d => T.has(d));
  const gcount = d => [...T.get(d).values()].reduce((s, G) => s + G.size, 0);
  const wsum = order.reduce((s, d) => s + Math.sqrt(gcount(d)), 0);
  const root = new THREE.Vector3(0, 0, 0);
  const rootMesh = new THREE.Mesh(new THREE.SphereGeometry(0.45, 24, 18), clay(0xd8c6ad)); rootMesh.position.y = 0.3; rootMesh.castShadow = true; scene.add(rootMesh);
  const barrel = new THREE.CapsuleGeometry(0.075, 0.09, 4, 10);
  let a0 = -Math.PI / 2;
  for (const d of order) {
    const span = Math.sqrt(gcount(d)) / wsum * Math.PI * 2, mat = clay(COL[d]);
    const dA = a0 + span / 2, dP = at(R.domain, dA);
    arch(root, dP, 2.4, mat, 0.12);
    const phyla = [...T.get(d).entries()].sort((x, y) => y[1].size - x[1].size);
    const ng = gcount(d); let pa = a0;
    for (const [p, G] of phyla) {
      const pspan = G.size / ng * span, pA = pa + pspan / 2, pP = at(R.phylum, pA);
      arch(dP, pP, 1.6, mat, 0.06);
      // one arch down to a floor ring that runs under all of this phylum's genera
      const a1 = pa + pspan / G.size / 2, a2 = pa + pspan - pspan / G.size / 2, rr = R.genus - 0.55;
      arch(pP, at(rr, pA, 0.04), 1.0, mat, 0.04);
      if (G.size > 1) {
        const ring = new THREE.EllipseCurve(0, 0, rr, rr, a1, a2, false);
        const pts = ring.getPoints(Math.max(8, G.size * 2)).map(v => new THREE.Vector3(v.x, 0.04, v.y));
        const m = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), Math.max(8, G.size * 2), 0.035, 6), mat);
        m.receiveShadow = true; scene.add(m);
      }
      let ga = pa;
      for (const [g, prots] of G) {
        const gA = ga + pspan / G.size / 2, gP = at(R.genus, gA);
        // the stack: one barrel per protein
        const inst = new THREE.InstancedMesh(barrel, clay(0xffffff, {roughness: 0.7}), prots.length);
        const m4 = new THREE.Matrix4(), cDisc = new THREE.Color(COL[d]), cVal = new THREE.Color(0xeee6d8);
        prots.forEach((l, i) => {
          const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), i * 0.7);
          const step = Math.min(0.26, 7 / prots.length);
          m4.compose(new THREE.Vector3(gP.x, 0.12 + i * step, gP.z), q, new THREE.Vector3(1, Math.min(1, step / 0.26 * 1.4), 1));
          inst.setMatrixAt(i, m4);
          inst.setColorAt(i, l.partition === "validation" ? cVal : cDisc);   // pale = held out for validation
        });
        inst.castShadow = true;
        inst.userData = {domain: d, phylum: p, genus: g, prots};
        scene.add(inst); genusMeshes.push(inst);
        ga += pspan / G.size;
      }
      pa += pspan;
    }
    a0 += span;
  }
}

const ray = new THREE.Raycaster(), mouse = new THREE.Vector2(-9, -9);
canvas.addEventListener("pointermove", e => {
  const r = canvas.getBoundingClientRect();
  mouse.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
  tip.style.left = (e.clientX - r.left + 14) + "px"; tip.style.top = (e.clientY - r.top + 10) + "px";
});
canvas.addEventListener("pointerleave", () => { mouse.set(-9, -9); tip.hidden = true; });
canvas.addEventListener("pointerdown", () => { controls.autoRotate = false; });
canvas.addEventListener("click", e => {
  const r = canvas.getBoundingClientRect(), p = new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
  ray.setFromCamera(p, camera);
  let hit = ray.intersectObjects(genusMeshes, false)[0];
  if (!hit) {   // thin stacks: take the nearest stack on screen within 14 px
    let best = null, bd = 14;
    const mat = new THREE.Matrix4(), a = new THREE.Vector3(), b = new THREE.Vector3();
    const px = v => [(v.x + 1) * r.width / 2, (1 - v.y) * r.height / 2], P = px(p);
    for (const m of genusMeshes) {   // distance from the pointer to the stack's projected base-to-top segment
      m.getMatrixAt(0, mat); a.setFromMatrixPosition(mat).project(camera);
      m.getMatrixAt(m.count - 1, mat); b.setFromMatrixPosition(mat).project(camera);
      const [ax, ay] = px(a), [bx, by] = px(b), dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy || 1;
      const t = Math.max(0, Math.min(1, ((P[0] - ax) * dx + (P[1] - ay) * dy) / L));
      const d = Math.hypot(P[0] - ax - t * dx, P[1] - ay - t * dy);
      if (d < bd) { bd = d; best = m; }
    }
    if (best) hit = {object: best};
  }
  if (hit) show(hit.object.userData);
});

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
function show(u) {
  const reps = u.prots.map(p => p.repeats), lens = u.prots.map(p => p.length);
  const loc = u.prots.filter(p => p.located).length, val = u.prots.filter(p => p.partition === "validation").length;
  info.innerHTML = `<p><b><i>${esc(u.genus)}</i></b> · ${esc(u.phylum)} · ${esc(u.domain)}. ${u.prots.length} vault-family protein${u.prots.length > 1 ? "s" : ""};
    length ${Math.min(...lens)}–${Math.max(...lens)} residues; ${Math.max(...reps) ? `${Math.min(...reps)}–${Math.max(...reps)} annotated MVP repeat domains` : "no annotated MVP repeat domains"};
    ${loc} located on a genome record; ${val ? "held out for validation" : "in the discovery set"}. [OBSERVATION]</p>
    <ol class="accs">${u.prots.slice(0, 40).map(p => `<li><a href="https://www.uniprot.org/uniprotkb/${esc(p.acc)}" rel="noopener">${esc(p.acc)}</a> <i>${esc(p.organism)}</i> · ${p.length} aa</li>`).join("")}</ol>
    ${u.prots.length > 40 ? `<p class="dim">and ${u.prots.length - 40} more.</p>` : ""}`;
}

function frame() {
  ray.setFromCamera(mouse, camera);
  const hit = ray.intersectObjects(genusMeshes, false)[0];
  const h = hit ? hit.object : null;
  if (h !== hovered) {
    if (hovered) hovered.material.emissive.setHex(0);
    hovered = h;
    if (h) { h.material.emissive.setHex(0x2a2a1a); const u = h.userData; tip.hidden = false; tip.innerHTML = `<i>${esc(u.genus)}</i> · ${esc(u.phylum)} · ${u.prots.length}`; canvas.style.cursor = "pointer"; }
    else { tip.hidden = true; canvas.style.cursor = "grab"; }
  }
  controls.update(); renderer.render(scene, camera); requestAnimationFrame(frame);
}
frame();
