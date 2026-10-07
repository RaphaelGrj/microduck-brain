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
let donnees = { filaments: [], couleurs: [], schemas: [], actif: null };
const CATALOGUE = "https://raw.githubusercontent.com/RaphaelGrj/microduck-catalogue/main/catalogue.json";

// code couleur saisi : "#f26a1b", "f26a1b", "#f6b" -> "#f26a1b" (ou null)
function hexNormal(v) {
  let h = String(v || "").trim().toLowerCase().replace(/^#/, "");
  if (/^[0-9a-f]{3}$/.test(h)) h = h.split("").map((c) => c + c).join("");
  return /^[0-9a-f]{6}$/.test(h) ? "#" + h : null;
}
let rendu, scene, camera, controles, racine, geometries = {}, originales = {}, maillages = [], pret = null;

// ---------- chargement ----------
async function charger() {
  const [json, bin] = await Promise.all([fetch("design/microduck.json").then((r) => r.json()),
    fetch("design/microduck.bin").then((r) => r.arrayBuffer())]);
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
  $("#couleur-hex").disabled = !actif; $("#couleur-garder").disabled = !actif;
  $("#stl-perso").disabled = !actif;
  $("#stl-retirer").disabled = !(piece && geometries[piece] !== originales[piece]);
  if (actif) montrerCode(couleurs[choix] || origine[choix]);
  else $("#couleur-hex").value = "";
  nuancier();
}

// ---------- couleurs ----------
function montrerCode(hex) {
  $("#couleur-libre").value = hex;
  if (document.activeElement !== $("#couleur-hex")) $("#couleur-hex").value = hex;
  $("#couleur-hex").removeAttribute("aria-invalid");
}

function peindre(groupe, couleur) {
  couleur = couleur.toLowerCase();
  couleurs[groupe] = couleur;
  if (groupe === choix) montrerCode(couleur);
  materiaux[groupe].color.set(couleur);
  $("#design-schema").textContent = (donnees.actif ? donnees.actif : "Nouveau schéma") + " · modifié";
  nuancier();
  versCasque();
}

function appliquer(table) {
  couleurs = {};
  for (const id in materiaux) materiaux[id].color.set((table || {})[id] || origine[id]);
  Object.assign(couleurs, table || {});
  versCasque();
}

// « Voir dans le casque » : chaque retouche part aussitot vers le canard du casque (mode Jumeau), sans enregistrer
let casque = false, minuteurCasque = null;
function versCasque() {
  if (!casque) return;
  clearTimeout(minuteurCasque);
  minuteurCasque = setTimeout(() => {
    const table = {};
    for (const id in origine) table[id] = couleurs[id] || origine[id];       // complet : jamais vide
    window.api("/api/design-apercu", { couleurs: table }).catch(() => window.toast("Microduck ne répond pas"));
  }, 250);
}
function casqueActif(on) {
  if (casque === on) return;
  casque = on;
  $("#design-casque").setAttribute("aria-pressed", String(on));
  if (on) { versCasque(); window.toast("Visible dans le casque (mode Jumeau)"); }
  else { clearTimeout(minuteurCasque); window.api("/api/design-apercu", { couleurs: {} }).catch(() => {}); }
}
$("#design-casque").addEventListener("click", () => casqueActif(!casque));
$("#design").addEventListener("click", (e) => { if (e.target.closest("[data-fermer]")) casqueActif(false); });

function nuancier() {
  const actuelle = choix ? (couleurs[choix] || origine[choix]).toLowerCase() : null;
  const pastille = ([nom, hex]) => {
    const b = document.createElement("button");
    b.style.background = hex; b.title = `${nom} (${hex})`; b.setAttribute("aria-label", nom);
    b.setAttribute("aria-pressed", String(actuelle === hex.toLowerCase()));
    b.disabled = !(choix && groupes[choix].imprimable);
    b.addEventListener("click", () => peindre(choix, hex));
    return b;
  };
  const sep = () => Object.assign(document.createElement("span"), { className: "separateur" });
  const perso = donnees.couleurs || [];
  $("#nuancier").replaceChildren(...donnees.filaments.map((f) => pastille([f.nom, f.couleur])),
    ...(donnees.filaments.length ? [sep()] : []), ...perso.map((f) => pastille([f.nom, f.couleur])),
    ...(perso.length ? [sep()] : []), ...PALETTE.map(pastille));
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
    const partager = document.createElement("button"); partager.textContent = "⇪"; partager.setAttribute("aria-label", "Partager " + s.nom);
    partager.addEventListener("click", () => partagerSchema(s));
    const suppr = document.createElement("button"); suppr.textContent = "✕"; suppr.setAttribute("aria-label", "Supprimer " + s.nom);
    suppr.addEventListener("click", () => {
      if (!confirm(`Supprimer le schéma « ${s.nom} » ?`)) return;
      donnees.schemas = donnees.schemas.filter((x) => x !== s);
      if (donnees.actif === s.nom) donnees.actif = null;
      sauver(); maj();
    });
    li.append(ap, nom, voir, partager, suppr);
    return li;
  }) : [Object.assign(document.createElement("li"), { textContent: "Aucun schéma enregistré pour l'instant." })]));
}

function listeCouleurs() {
  const perso = donnees.couleurs || [];
  $("#couleurs-perso").replaceChildren(...(perso.length ? perso.map((f) => {
    const li = document.createElement("li");
    const p = document.createElement("span"); p.className = "pastille-couleur"; p.style.background = f.couleur;
    const nom = document.createElement("span"); nom.className = "nom"; nom.textContent = f.nom;
    const code = document.createElement("code"); code.textContent = f.couleur;
    const suppr = document.createElement("button"); suppr.textContent = "✕"; suppr.setAttribute("aria-label", "Retirer " + f.nom);
    suppr.addEventListener("click", () => { donnees.couleurs = perso.filter((x) => x !== f); sauver(); maj(); });
    li.append(p, nom, code, suppr);
    return li;
  }) : [Object.assign(document.createElement("li"), { className: "discret", textContent: "Aucune couleur gardée pour l'instant." })]));
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
  listeSchemas(); listeCouleurs(); listeFilaments(); nuancier();
  const s = donnees.schemas.find((x) => x.nom === donnees.actif);
  if (window.appliquerLook) window.appliquerLook(s ? s.couleurs : null);     // son look sur l'accueil
  $("#design-schema").textContent = donnees.actif || "Couleurs d'origine";
}

// ---------- fiche d'impression ----------
const NOMS_PIECES = {
  top_head_shell: "Dessus de la tête", bottom_head_shell: "Dessous de la tête", face_part: "Face", jaw: "Bec",
  jaw_soft: "Bec souple", soft_mouth_top: "Bec souple (haut)", noenoeil: "Tour de l'œil", left_shell: "Coque gauche",
  right_shell: "Coque droite", trunk_base: "Châssis", motor_support: "Support moteur", yaw2roll: "Pièce de hanche",
  yaw_roll_motion: "Pièce de hanche (rotation)", bearing_roll: "Roulement de hanche", neck: "Cou", neck_pitch: "Cou (tangage)",
  hip_l: "Hanche", upper_leg_left: "Cuisse gauche", upper_leg_right: "Cuisse droite", leg: "Jambe",
  upper_leg_rigidity_plate: "Plaque de cuisse", foot_left: "Pied gauche", foot_right: "Pied droit",
  ankle_left: "Cheville gauche", ankle_right: "Cheville droite", sole_left: "Semelle gauche", sole_right: "Semelle droite",
  power_support: "Support de batterie", banana_pcb_locker: "Verrou de carte",
};
const STL = "https://github.com/pollen-robotics/microduck_rl/blob/main/src/mjlab_microduck/robot/microduck/assets/";

function nomCouleur(hex) {
  hex = hex.toLowerCase();
  const f = donnees.filaments.find((x) => x.couleur.toLowerCase() === hex);
  if (f) return f.nom;
  const p = PALETTE.find((x) => x[1].toLowerCase() === hex);
  if (p) return p[0];
  const rgb = (h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));
  const [r, g, b] = rgb(hex);                     // sinon : la couleur de la palette la plus proche
  const proche = PALETTE.map(([nom, h]) => { const [r2, g2, b2] = rgb(h); return [(r - r2) ** 2 + (g - g2) ** 2 + (b - b2) ** 2, nom]; })
    .sort((a, b2) => a[0] - b2[0])[0][1];
  return `≈ ${proche} (${hex})`;
}

function fiche() {
  // couleur -> pieces imprimables (avec leur nombre : deux hanches, deux jambes...)
  const parCouleur = new Map();
  for (const inst of modele.instances) {
    const g = groupes[inst.groupe];
    if (!g.imprimable) continue;
    const c = (couleurs[g.id] || origine[g.id]).toLowerCase();
    if (!parCouleur.has(c)) parCouleur.set(c, new Map());
    const m = parCouleur.get(c);
    m.set(inst.piece, (m.get(inst.piece) || 0) + 1);
  }
  const titre = donnees.actif || "Schéma en cours";
  const lignes = [`Microduck — ${titre}`, ""];
  const blocs = [...parCouleur.entries()].sort((a, b) => b[1].size - a[1].size).map(([hex, pieces]) => {
    const h3 = document.createElement("h3");
    const p = document.createElement("span"); p.className = "pastille-couleur"; p.style.background = hex;
    h3.append(p, nomCouleur(hex));
    const ul = document.createElement("ul");
    lignes.push(`${nomCouleur(hex)} (${hex}) :`);
    for (const [piece, n] of [...pieces.entries()].sort()) {
      const li = document.createElement("li"), a = document.createElement("a");
      a.href = STL + piece + ".stl"; a.target = "_blank"; a.rel = "noopener";
      a.textContent = (NOMS_PIECES[piece] || piece) + (n > 1 ? ` × ${n}` : "");
      li.append(a); ul.append(li);
      lignes.push(`  - ${NOMS_PIECES[piece] || piece}${n > 1 ? " x" + n : ""} : ${piece}.stl`);
    }
    lignes.push("");
    return [h3, ul];
  }).flat();
  lignes.push("STL d'origine : " + STL);
  $("#fiche-schema").textContent = `${titre} · ${parCouleur.size} couleur${parCouleur.size > 1 ? "s" : ""}`;
  $("#fiche-contenu").replaceChildren(...blocs);
  ficheTexte = lignes.join("\n");
  $("#vue-fiche").showModal();
}
let ficheTexte = "";

// ---------- photo (4:3, pour partager un schema ou illustrer une fiche du catalogue) ----------
function photo() {
  const L = 1200, H = 900, avant = rendu.getSize(new THREE.Vector2()), ratio = rendu.getPixelRatio();
  for (const id in materiaux) materiaux[id].emissive.setHex(0x000000);
  rendu.setPixelRatio(1); rendu.setSize(L, H, false);
  camera.aspect = L / H; camera.updateProjectionMatrix();
  rendu.setClearColor(0xf5f4f2, 1);
  rendu.render(scene, camera);
  const url = rendu.domElement.toDataURL("image/jpeg", 0.92);
  rendu.setClearColor(0x000000, 0);
  rendu.setPixelRatio(ratio); rendu.setSize(avant.x, avant.y, false);
  taille();
  const nom = (donnees.actif || "microduck").normalize("NFD").replace(/[^\w]+/g, "-").replace(/^-|-$/g, "").toLowerCase();
  window.enregistrerFichier(`${nom || "microduck"}.jpg`, "image/jpeg", url);
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
      maj(); choisir(null, null); chargerCatalogue();
    })().catch((e) => { pret = null; $("#vue3d-attente").textContent = "Impossible de charger le modèle 3D."; throw e; });
  }
  await pret;
  taille();
}

$("#couleur-libre").addEventListener("input", (e) => { if (choix) peindre(choix, e.target.value); });
$("#couleur-hex").addEventListener("input", (e) => {
  const h = hexNormal(e.target.value);
  e.target.setAttribute("aria-invalid", String(!h && e.target.value.trim().length >= 3));
  if (h && choix) peindre(choix, h);
});
$("#couleur-hex").addEventListener("change", (e) => { if (choix) montrerCode(couleurs[choix] || origine[choix]); e.target.value = $("#couleur-libre").value; });
$("#couleur-garder").addEventListener("click", () => {
  const hex = hexNormal($("#couleur-hex").value) || $("#couleur-libre").value;
  const nom = prompt(`Nom de cette couleur (${hex})`, hex);
  if (nom === null) return;
  donnees.couleurs = (donnees.couleurs || []).filter((c) => c.couleur !== hex)
    .concat([{ nom: nom.trim().slice(0, 40) || hex, couleur: hex }]).slice(-50);
  sauver(); maj(); window.toast("Couleur gardée");
});

// ---------- partage des schemas : fichier, texte, QR code, catalogue ----------
const PREFIXE = "MICRODUCK-SCHEMA:";
const groupeConnu = (g) => Object.prototype.hasOwnProperty.call(origine, g);
function schemaPropre(s) {
  if (!s || typeof s !== "object" || typeof s.couleurs !== "object") return null;
  const c = {};
  for (const [g, v] of Object.entries(s.couleurs)) { const h = hexNormal(v); if (h && (!modele || groupeConnu(g))) c[g] = h; }
  return Object.keys(c).length ? { nom: String(s.nom || "Schéma importé").trim().slice(0, 40), couleurs: c } : null;
}
function partagerSchema(s) {
  const texte = PREFIXE + JSON.stringify({ nom: s.nom, couleurs: s.couleurs });
  if (window.montrerQR) window.montrerQR(s.nom, texte, "Scanne ce code, copie le texte, puis « Coller un schéma » dans le design de l'autre téléphone. « Exporter mes schémas » donne un fichier.");
}
function importer(texte) {
  texte = String(texte || "").trim();
  if (texte.startsWith(PREFIXE)) texte = texte.slice(PREFIXE.length);
  const d = JSON.parse(texte);
  const liste = (d.schemas || (d.schema ? [d.schema] : [d])).map(schemaPropre).filter(Boolean);
  let n = 0;
  for (const s of liste) {
    let nom = s.nom, k = 2;
    const pareil = donnees.schemas.find((x) => x.nom === nom);
    if (pareil && JSON.stringify(pareil.couleurs) === JSON.stringify(s.couleurs)) continue;
    while (donnees.schemas.some((x) => x.nom === nom)) nom = `${s.nom.slice(0, 36)} ${k++}`;
    donnees.schemas = donnees.schemas.concat([{ nom, couleurs: s.couleurs }]).slice(-50);
    n++;
  }
  for (const cle of ["filaments", "couleurs"]) {          // (fichier « Exporter mes schemas » : bobines et couleurs aussi)
    for (const f of d[cle] || []) {
      const h = hexNormal(f && f.couleur);
      if (h && !(donnees[cle] || []).some((x) => x.couleur === h && x.nom === f.nom)) {
        donnees[cle] = (donnees[cle] || []).concat([{ nom: String(f.nom || h).slice(0, 40), couleur: h }]).slice(-50);
      }
    }
  }
  if (!liste.length && !(d.filaments || d.couleurs)) throw new Error("vide");
  sauver(); maj();
  window.toast(n ? `${n} schéma${n > 1 ? "s" : ""} ajouté${n > 1 ? "s" : ""}` : "Rien de nouveau");
}
$("#schemas-exporter").addEventListener("click", () => {
  if (!donnees.schemas.length && !(donnees.couleurs || []).length) { window.toast("Aucun schéma à exporter"); return; }
  window.enregistrerFichier(`microduck-schemas-${new Date().toISOString().slice(0, 10)}.json`, "application/json",
    JSON.stringify({ format: "microduck-schemas", version: 1, schemas: donnees.schemas, filaments: donnees.filaments,
      couleurs: donnees.couleurs || [] }, null, 1));
});
$("#schemas-importer").addEventListener("change", async (e) => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f) return;
  try { importer(await f.text()); } catch (x) { window.toast("Ce fichier n'est pas un schéma de Microduck"); }
});
$("#schemas-coller").addEventListener("click", async () => {
  let texte = "";
  try { texte = await navigator.clipboard.readText(); } catch (x) { /* pas d'acces au presse-papiers */ }
  if (!texte || !texte.includes("couleurs")) texte = prompt("Colle le texte du schéma :", "") || "";
  if (!texte) return;
  try { importer(texte); } catch (x) { window.toast("Ce texte n'est pas un schéma de Microduck"); }
});
let catalogueSchemas = null;
async function chargerCatalogue() {
  try {
    if (!catalogueSchemas) catalogueSchemas = ((await (await fetch(CATALOGUE, { cache: "no-cache" })).json()).schemas || []);
  } catch (x) {
    $("#schemas-catalogue").replaceChildren(Object.assign(document.createElement("li"), { className: "discret", textContent: "Catalogue injoignable (Internet ?)" }));
    return;
  }
  $("#schemas-catalogue").replaceChildren(...(catalogueSchemas.length ? catalogueSchemas.map((s) => {
    const li = document.createElement("li");
    const ap = document.createElement("span"); ap.className = "apercu-schema";
    for (const g of ["dessus_tete", "face", "bec", "coques", "pieds"]) {
      const i = document.createElement("i"); i.style.background = s.couleurs[g] || origine[g]; ap.append(i);
    }
    const nom = document.createElement("span"); nom.className = "nom"; nom.textContent = s.nom + (s.auteur ? ` · ${s.auteur}` : "");
    const voir = document.createElement("button"); voir.textContent = "Voir";
    voir.addEventListener("click", () => { appliquer(s.couleurs); $("#design-schema").textContent = "Aperçu : " + s.nom; });
    const ajouter = document.createElement("button"); ajouter.textContent = "Ajouter";
    ajouter.addEventListener("click", () => { try { importer(JSON.stringify(s)); } catch (x) { window.toast("Schéma illisible"); } });
    li.append(ap, nom, voir, ajouter);
    return li;
  }) : [Object.assign(document.createElement("li"), { className: "discret", textContent: "Pas encore de schéma partagé." })]));
}
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

$("#fiche-impression").addEventListener("click", fiche);
$("#design-photo").addEventListener("click", photo);
$("#fiche-enregistrer").addEventListener("click", () => window.enregistrerFichier(
  `impression-${(donnees.actif || "microduck").toLowerCase().replace(/[^\w]+/g, "-")}.txt`, "text/plain", ficheTexte));
$("#fiche-copier").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(ficheTexte); }
  catch (e) {                                  // http sur le reseau local : pas de presse-papiers « moderne »
    const t = document.createElement("textarea"); t.value = ficheTexte; document.body.append(t); t.select();
    document.execCommand("copy"); t.remove();
  }
  window.toast("Fiche copiée");
});

window.MicroduckDesign = { ouvrir, essayer };
