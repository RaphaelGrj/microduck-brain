// Design space : le vrai Microduck en 3D (modele officiel allege, outils/modele_3d.py), a recolorer piece par piece avant
// d'imprimer. Schemas et filaments sont gardes sur le canard (/api/design) ; un STL perso reste dans le telephone.
import * as THREE from "./lib/three.module.min.js";
import { OrbitControls } from "./lib/OrbitControls.js";
import { toCreasedNormals } from "./lib/BufferGeometryUtils.js";

const ARETE_VIVE = (35 * Math.PI) / 180;         // comme outils/modele_3d.py : lisse en dessous, arete nette au-dela

const $ = (s) => document.querySelector(s);
const PALETTE = [["Blanc", "#f4f4f2"], ["Gris clair", "#c9c9c4"], ["Gris", "#7d7f84"], ["Noir", "#26272b"],
  ["Orange Microduck", "#f26a1b"], ["Jaune", "#f4b023"], ["Rouge", "#d7322b"], ["Rose", "#e98bb5"], ["Violet", "#7a4fc4"],
  ["Bleu", "#2f6fd6"], ["Turquoise", "#25a5a0"], ["Vert", "#4c9a3d"], ["Beige", "#d9c7a7"], ["Bois", "#9b6b43"]];

let modele, groupes = {}, materiaux = {}, origine = {}, couleurs = {}, choix = null, pieceChoisie = null;
let donnees = { filaments: [], schemas: [], actif: null };
let rendu, scene, camera, controles, racine, geometries = {}, originales = {}, maillages = [], pret = null;

// ---------- chargement ----------
async function charger() {
  const [json, bin] = await Promise.all([fetch("/design/microduck.json").then((r) => r.json()),
    fetch("/design/microduck.bin").then((r) => r.arrayBuffer())]);
  modele = json;
  for (const g of modele.groupes) { groupes[g.id] = g; origine[g.id] = g.origine; }
  const normales0 = modele.octets_positions, indices0 = normales0 + (modele.octets_normales || 0);
  for (const [nom, p] of Object.entries(modele.pieces)) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(bin, p.v[0] * 4, p.v[1]), 3));
    // normales lissees precalculees (3 octets signes par sommet) : surfaces lisses, sans facettes visibles
    geo.setAttribute("normal", new THREE.BufferAttribute(new Int8Array(bin, normales0 + p.n, p.v[1]), 3, true));
    geo.setIndex(new THREE.BufferAttribute(new Uint16Array(bin, indices0 + p.f[0] * 2, p.f[1]), 1));
    geo.computeBoundingSphere();
    geometries[nom] = originales[nom] = geo;
  }

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(32, 1, 0.01, 10);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8478, 1.6));
  const soleil = new THREE.DirectionalLight(0xffffff, 1.9);
  soleil.position.set(0.6, 1.2, 0.9);
  scene.add(soleil);
  const contre = new THREE.DirectionalLight(0xffffff, 0.6);
  contre.position.set(-0.8, 0.4, -0.9);
  scene.add(contre);
  racine = new THREE.Group();
  racine.rotation.x = -Math.PI / 2;                     // le modele a z en haut, three.js y en haut
  scene.add(racine);
  for (const g of modele.groupes) {
    materiaux[g.id] = new THREE.MeshStandardMaterial({ color: g.origine, roughness: 0.55, metalness: 0.0 });
  }
  for (const inst of modele.instances) {
    const m = inst.m, mat = new THREE.Matrix4().set(m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8], m[9], m[10], m[11], 0, 0, 0, 1);
    const maillage = new THREE.Mesh(geometries[inst.piece], materiaux[inst.groupe]);
    maillage.matrixAutoUpdate = false;
    maillage.matrix.copy(mat);
    maillage.userData = inst;
    racine.add(maillage);
    maillages.push(maillage);
  }
  racine.updateMatrixWorld(true);
  const boite = new THREE.Box3().setFromObject(racine), centre = boite.getCenter(new THREE.Vector3());

  const vue = $("#vue3d");
  rendu = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  rendu.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  vue.append(rendu.domElement);
  $("#vue3d-attente").remove();
  controles = new OrbitControls(camera, rendu.domElement);
  controles.target.copy(centre);
  controles.enablePan = false;
  controles.minDistance = 0.18; controles.maxDistance = 1.2;
  controles.enableDamping = true;
  camera.position.set(centre.x + 0.32, centre.y + 0.1, centre.z + 0.42);
  new ResizeObserver(taille).observe(vue);
  taille();
  rendu.domElement.addEventListener("pointerdown", (e) => { appui = [e.clientX, e.clientY]; });
  rendu.domElement.addEventListener("pointerup", toucher);
  rendu.setAnimationLoop(() => { if (!$("#design").hidden) { controles.update(); rendu.render(scene, camera); } });
}

function taille() {
  const v = $("#vue3d");
  rendu.setSize(v.clientWidth, v.clientHeight, false);
  camera.aspect = v.clientWidth / Math.max(1, v.clientHeight);
  camera.updateProjectionMatrix();
}

// ---------- choisir une piece ----------
let appui = null;
const rayon = new THREE.Raycaster();
function toucher(e) {
  if (!appui || Math.hypot(e.clientX - appui[0], e.clientY - appui[1]) > 8) return;   // c'etait un glisser : on tourne
  const r = rendu.domElement.getBoundingClientRect();
  rayon.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
  const touche = rayon.intersectObjects(maillages, false)[0];
  choisir(touche ? touche.object.userData.groupe : null, touche ? touche.object.userData.piece : null);
}

let eclair = null;
function choisir(groupe, piece) {
  clearTimeout(eclair);
  for (const id in materiaux) materiaux[id].emissive.setHex(0x000000);
  choix = groupe; pieceChoisie = piece;
  if (choix) {                                 // un bref eclair montre la piece choisie, sans fausser sa couleur ensuite
    materiaux[choix].emissive.set("#f26a1b"); materiaux[choix].emissiveIntensity = 0.35;
    eclair = setTimeout(() => materiaux[groupe].emissive.setHex(0x000000), 450);
  }
  const g = groupes[choix];
  $("#groupe-nom").textContent = g ? g.nom : "Touche une pièce";
  $("#groupe-info").textContent = !g ? "" : g.imprimable ? "à imprimer" : "pièce achetée";
  const actif = !!(g && g.imprimable);
  document.querySelectorAll("#nuancier button, #groupe-origine").forEach((b) => { b.disabled = !actif; });
  $("#couleur-libre").disabled = !actif;
  $("#stl-perso").disabled = !actif;
  $("#stl-retirer").disabled = !(piece && geometries[piece] !== originales[piece]);
  if (actif) $("#couleur-libre").value = couleurs[choix] || origine[choix];
  nuancier();
}

// ---------- couleurs ----------
function peindre(groupe, couleur) {
  couleurs[groupe] = couleur;
  materiaux[groupe].color.set(couleur);
  $("#design-schema").textContent = (donnees.actif ? donnees.actif : "Nouveau schéma") + " · modifié";
  nuancier();
}

function appliquer(table) {
  couleurs = {};
  for (const id in materiaux) materiaux[id].color.set((table || {})[id] || origine[id]);
  Object.assign(couleurs, table || {});
}

function nuancier() {
  const actuelle = choix ? (couleurs[choix] || origine[choix]).toLowerCase() : null;
  const pastille = ([nom, hex]) => {
    const b = document.createElement("button");
    b.style.background = hex; b.title = nom; b.setAttribute("aria-label", nom);
    b.setAttribute("aria-pressed", String(actuelle === hex.toLowerCase()));
    b.disabled = !(choix && groupes[choix].imprimable);
    b.addEventListener("click", () => peindre(choix, hex));
    return b;
  };
  const sep = document.createElement("span"); sep.className = "separateur";
  $("#nuancier").replaceChildren(...donnees.filaments.map((f) => pastille([f.nom, f.couleur])),
    ...(donnees.filaments.length ? [sep] : []), ...PALETTE.map(pastille));
}

// ---------- schemas et filaments (sur le canard) ----------
let minuteur = null;
function sauver() {
  clearTimeout(minuteur);
  minuteur = setTimeout(() => window.api("/api/design", donnees).catch(() => window.toast("Microduck ne répond pas")), 400);
}

function listeSchemas() {
  $("#schemas").replaceChildren(...(donnees.schemas.length ? donnees.schemas.map((s) => {
    const li = document.createElement("li");
    const ap = document.createElement("span"); ap.className = "apercu-schema";
    for (const g of ["dessus_tete", "face", "bec", "coques", "pieds"]) {
      const i = document.createElement("i"); i.style.background = s.couleurs[g] || origine[g]; ap.append(i);
    }
    const nom = document.createElement("span"); nom.textContent = s.nom;
    nom.className = "nom" + (s.nom === donnees.actif ? " actif" : "");
    const voir = document.createElement("button"); voir.textContent = "Voir";
    voir.addEventListener("click", () => { appliquer(s.couleurs); donnees.actif = s.nom; sauver(); maj(); });
    const suppr = document.createElement("button"); suppr.textContent = "✕"; suppr.setAttribute("aria-label", "Supprimer " + s.nom);
    suppr.addEventListener("click", () => {
      if (!confirm(`Supprimer le schéma « ${s.nom} » ?`)) return;
      donnees.schemas = donnees.schemas.filter((x) => x !== s);
      if (donnees.actif === s.nom) donnees.actif = null;
      sauver(); maj();
    });
    li.append(ap, nom, voir, suppr);
    return li;
  }) : [Object.assign(document.createElement("li"), { textContent: "Aucun schéma enregistré pour l'instant." })]));
}

function listeFilaments() {
  $("#filaments").replaceChildren(...donnees.filaments.map((f) => {
    const li = document.createElement("li");
    const p = document.createElement("span"); p.className = "pastille-couleur"; p.style.background = f.couleur;
    const nom = document.createElement("span"); nom.textContent = f.nom; nom.className = "nom";
    const suppr = document.createElement("button"); suppr.textContent = "✕"; suppr.setAttribute("aria-label", "Retirer " + f.nom);
    suppr.addEventListener("click", () => { donnees.filaments = donnees.filaments.filter((x) => x !== f); sauver(); maj(); });
    li.append(p, nom, suppr);
    return li;
  }));
}

function maj() {
  listeSchemas(); listeFilaments(); nuancier();
  $("#design-schema").textContent = donnees.actif || "Couleurs d'origine";
}

// ---------- STL perso ----------
function lireStl(tampon) {
  const vue = new DataView(tampon), n = tampon.byteLength >= 84 ? vue.getUint32(80, true) : 0;
  let pos;
  if (n > 0 && 84 + n * 50 === tampon.byteLength) {                 // binaire
    pos = new Float32Array(n * 9);
    for (let i = 0; i < n; i++) for (let k = 0; k < 9; k++) pos[i * 9 + k] = vue.getFloat32(84 + i * 50 + 12 + k * 4, true);
  } else {                                                           // texte
    const v = [...new TextDecoder().decode(tampon).matchAll(/vertex\s+(\S+)\s+(\S+)\s+(\S+)/g)].flatMap((m) => [+m[1], +m[2], +m[3]]);
    if (!v.length) throw new Error("STL illisible");
    pos = new Float32Array(v);
  }
  let max = 0;
  for (const x of pos) max = Math.max(max, Math.abs(x));
  if (max > 1) for (let i = 0; i < pos.length; i++) pos[i] *= 0.001;   // dessine en mm : le modele est en metres
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const lisse = toCreasedNormals(geo, ARETE_VIVE);   // ta piece aussi : lisse, aretes vives gardees
  lisse.computeBoundingSphere();
  return lisse;
}

function remplacer(piece, geo) {
  geometries[piece] = geo;
  for (const m of maillages) if (m.userData.piece === piece) m.geometry = geo;
  $("#stl-retirer").disabled = geo === originales[piece];
}

async function essayer(url, piece, nom) {
  // depuis la marketplace : une piece du catalogue posee sur le Microduck (le design prend la place de la marketplace)
  await ouvrir(true);
  const tampon = await fetch(url).then((r) => { if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); });
  if (!originales[piece]) throw new Error("pièce inconnue : " + piece);
  remplacer(piece, lireStl(tampon));
  const inst = modele.instances.find((i) => i.piece === piece);
  choisir(inst.groupe, piece);
  window.toast(nom ? `« ${nom} » posée sur le Microduck` : "Pièce posée");
}

// ---------- ecran ----------
async function ouvrir(remplacer) {
  $("#design").hidden = false;
  if (remplacer) history.replaceState({ ecran: "design" }, ""); else history.pushState({ ecran: "design" }, "");
  if (!pret) {
    pret = (async () => {
      try { Object.assign(donnees, await window.api("/api/design")); } catch (e) { /* vide : on garde les valeurs par defaut */ }
      await charger();
      const s = donnees.schemas.find((x) => x.nom === donnees.actif);
      appliquer(s ? s.couleurs : null);
      maj(); choisir(null, null);
    })().catch((e) => { pret = null; $("#vue3d-attente").textContent = "Impossible de charger le modèle 3D."; throw e; });
  }
  await pret;
  taille();
}

$("#couleur-libre").addEventListener("input", (e) => { if (choix) peindre(choix, e.target.value); });
$("#groupe-origine").addEventListener("click", () => { if (choix) { delete couleurs[choix]; materiaux[choix].color.set(origine[choix]); nuancier(); } });
$("#stl-perso").addEventListener("change", async (e) => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f || !pieceChoisie) return;
  try { remplacer(pieceChoisie, lireStl(await f.arrayBuffer())); window.toast("Ta pièce est posée"); }
  catch (x) { window.toast("Ce fichier n'est pas un STL lisible"); }
});
$("#stl-retirer").addEventListener("click", () => { if (pieceChoisie) remplacer(pieceChoisie, originales[pieceChoisie]); });
$("#schema-sauver").addEventListener("click", () => {
  const nom = prompt("Nom du schéma", donnees.actif || "Mon Microduck");
  if (!nom || !nom.trim()) return;
  const n = nom.trim().slice(0, 40);
  donnees.schemas = donnees.schemas.filter((s) => s.nom !== n).concat([{ nom: n, couleurs: { ...couleurs } }]).slice(-50);
  donnees.actif = n;
  sauver(); maj(); window.toast("Schéma enregistré");
});
$("#schema-nouveau").addEventListener("click", () => { appliquer(null); donnees.actif = null; sauver(); maj(); });
$("#filament-ajouter").addEventListener("click", () => {
  const nom = $("#filament-nom").value.trim().slice(0, 40);
  if (!nom) { $("#filament-nom").focus(); return; }
  donnees.filaments = donnees.filaments.concat([{ nom, couleur: $("#filament-couleur").value }]).slice(-50);
  $("#filament-nom").value = "";
  sauver(); maj();
});
const comparer = $("#design-comparer");
const montrerOrigine = (oui) => { for (const id in materiaux) materiaux[id].color.set(oui ? origine[id] : (couleurs[id] || origine[id])); };
comparer.addEventListener("pointerdown", () => montrerOrigine(true));
for (const ev of ["pointerup", "pointerleave", "pointercancel"]) comparer.addEventListener(ev, () => montrerOrigine(false));

window.MicroduckDesign = { ouvrir, essayer };
