// Atelier : le canard en 3D qu'on pilote et qu'on programme avec des blocs (façon Scratch).
//  - le canard SIMULE (duck-sim, /api/jumeau) est dessiné à l'échelle avec le vrai modèle ; sans simulateur, le modèle
//    statique est montré (les commandes partent quand même vers le vrai canard) ;
//  - « Programmer » : des blocs (tête, son, geste, assis, pause, répéter) compilés PAR LE CANARD en étapes de chorégraphie
//    (blocs.py) : jamais de code exécuté, tout est borné. Un programme se joue d'un clic ou s'enregistre comme tour.
import * as THREE from "./lib/three.module.min.js";
import { OrbitControls } from "./lib/OrbitControls.js";

const $ = (s) => document.querySelector(s);
const el = (tag, props, ...enfants) => { const e = Object.assign(document.createElement(tag), props || {}); e.append(...enfants.filter((x) => x != null)); return e; };
const SONS = { greet: "Bonjour", chirp: "Pépiement", coo: "Roucoulement", inquire: "Question", peck: "Petit coup", wheee: "Youpi", alarm: "Alarme" };
const GESTES = { content: "Content", non: "Non", oui: "Oui", curieux: "Curieux", surpris: "Surpris", fatigue: "Fatigué",
  etirement: "Étirement", ebouriffe: "S'ébouriffe", lissage: "Se lisse", eternuement: "Éternuement", fier: "Fier",
  baillement: "Bâillement", gene: "Gêné" };
const TETE = { cou: "Cou", tangage: "Haut / bas", lacet: "Gauche / droite", roulis: "Penché" };
const NOUVEAU = {
  tete: () => ({ type: "tete", cou: 0, tangage: 0, lacet: 0, roulis: 0, duree: 1 }),
  son: () => ({ type: "son", son: "greet" }),
  geste: () => ({ type: "geste", geste: "oui" }),
  assis: () => ({ type: "assis" }),
  pause: () => ({ type: "pause", duree: 1 }),
  repeter: () => ({ type: "repeter", n: 2, blocs: [] }),
};
const TITRES = { tete: "Tourner la tête", son: "Faire un son", geste: "Faire un geste", assis: "S'asseoir / se relever",
  pause: "Attendre", repeter: "Répéter" };
const CLE = "microduck-atelier";

let catalogue = { bornes: { cou: [-0.3, 0.4], tangage: [-0.5, 0.6], lacet: [-0.9, 0.9], roulis: [-0.4, 0.4] }, max_repetitions: 10 };
let programme = [];
try { const p = JSON.parse(localStorage.getItem(CLE)); if (Array.isArray(p)) programme = p; } catch (e) { /* vide */ }

// ---------- le canard en 3D ----------
let rendu, scene, camera, controles, racine, pret = false, ouvert = false, simulateur = false;
const parties = {};                 // nom du corps MuJoCo -> groupe three.js
const meshes = [];                  // { objet, m, l }
const balles = {};
let vers = null, derniereT = 0;
const trone = new THREE.Vector3(0, 0.1, 0);

const matrice = (a) => new THREE.Matrix4().set(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8], a[9], a[10], a[11], 0, 0, 0, 1);

async function chargerModele() {
  const [json, bin] = await Promise.all([fetch("design/microduck.json").then((r) => r.json()),
    fetch("design/microduck.bin").then((r) => r.arrayBuffer())]);
  const normales0 = json.octets_positions, indices0 = normales0 + (json.octets_normales || 0);
  const geometries = {};
  for (const [nom, p] of Object.entries(json.pieces)) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(bin, p.v[0] * 4, p.v[1]), 3));
    geo.setAttribute("normal", new THREE.BufferAttribute(new Int8Array(bin, normales0 + p.n, p.v[1]), 3, true));
    geo.setIndex(new THREE.BufferAttribute(new Uint16Array(bin, indices0 + p.f[0] * 2, p.f[1]), 1));
    geometries[nom] = geo;
  }
  const materiaux = {};
  for (const g of json.groupes) materiaux[g.id] = new THREE.MeshStandardMaterial({ color: g.origine, roughness: 0.55 });
  for (const inst of json.instances) {
    const nomCorps = inst.corps || "trunk_base";
    let groupe = parties[nomCorps];
    if (!groupe) { groupe = parties[nomCorps] = new THREE.Group(); racine.add(groupe); }
    const objet = new THREE.Mesh(geometries[inst.piece], materiaux[inst.groupe] || materiaux[json.groupes[0].id]);
    objet.matrixAutoUpdate = false;
    groupe.add(objet);
    meshes.push({ objet, m: matrice(inst.m), l: inst.l ? matrice(inst.l) : matrice(inst.m) });
  }
}

function modeSimulateur(actif) {
  simulateur = actif;
  for (const { objet, m, l } of meshes) { objet.matrix.copy(actif ? l : m); objet.matrixWorldNeedsUpdate = true; }
  if (!actif) for (const g of Object.values(parties)) { g.position.set(0, 0, 0); g.quaternion.identity(); }
  $("#atelier-etat").textContent = actif ? "Canard simulé, en direct" : "Modèle statique (pas de simulateur)";
  $("#atelier-sim").hidden = !actif;
}

function poser(e) {
  for (const [nom, g] of Object.entries(parties)) {
    const p = e.corps && e.corps[nom];
    if (!p || p.length < 7) continue;
    g.position.set(p[0], p[1], p[2]);
    g.quaternion.set(p[4], p[5], p[6], p[3]);        // la pose arrive en (w, x, y, z)
  }
  const t = e.corps && (e.corps.trunk_base || Object.values(e.corps)[0]);
  if (t) trone.set(t[0], t[2], -t[1]);               // simulateur (x, y, z haut) -> three.js (x, z, -y)
  for (const [nom, p] of Object.entries(e.balles || {})) {
    if (!balles[nom]) {
      balles[nom] = new THREE.Mesh(new THREE.SphereGeometry(0.035, 20, 14), new THREE.MeshStandardMaterial({ color: "#f26a1b", roughness: 0.5 }));
      racine.add(balles[nom]);
    }
    balles[nom].position.set(p[0], p[1], p[2]);
  }
  for (const nom of Object.keys(balles)) if (!(e.balles || {})[nom]) { racine.remove(balles[nom]); delete balles[nom]; }
  const sons = e.sons || [];
  if (sons.length) $("#atelier-son").textContent = "♪ " + (SONS[sons[sons.length - 1][1]] || sons[sons.length - 1][1]);
}

async function sonder() {
  if (!ouvert) return;
  let delai = 150;
  try {
    const e = await window.api("/api/jumeau?depuis=" + derniereT);
    if (!e || !e.corps) throw new Error("pas de simulateur");
    if (!simulateur) modeSimulateur(true);
    if (e.maintenant) derniereT = e.maintenant;
    poser(e);
  } catch (x) {
    if (x && x.message === "code") return;
    if (simulateur) modeSimulateur(false);
    delai = 2500;                                    // pas de simulateur : on retente de temps en temps
  }
  vers = setTimeout(sonder, delai);
}

function boucle() {
  if (!ouvert) return;
  controles.target.lerp(trone, 0.08);
  controles.update();
  rendu.render(scene, camera);
  requestAnimationFrame(boucle);
}

function taille() {
  const c = $("#atelier-3d"), w = c.clientWidth || 300, h = c.clientHeight || 260;
  rendu.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

async function init3d() {
  rendu = new THREE.WebGLRenderer({ antialias: true, alpha: true });       // fond transparent : celui de l'appli
  rendu.setPixelRatio(Math.min(devicePixelRatio, 2));
  $("#atelier-3d").prepend(rendu.domElement);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(36, 1, 0.01, 30);
  camera.position.set(0.4, 0.3, 0.55);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8478, 1.6));
  const soleil = new THREE.DirectionalLight(0xffffff, 1.9);
  soleil.position.set(0.6, 1.2, 0.9);
  scene.add(soleil);
  const sol = new THREE.GridHelper(6, 60, 0x888888, 0xbbbbbb);     // une case = 10 cm : le canard est à l'échelle
  sol.material.opacity = 0.45; sol.material.transparent = true;
  scene.add(sol);
  racine = new THREE.Group();
  racine.rotation.x = -Math.PI / 2;                                // le simulateur a z en haut, three.js y en haut
  scene.add(racine);
  controles = new OrbitControls(camera, rendu.domElement);
  controles.enableDamping = true;
  controles.maxDistance = 6; controles.minDistance = 0.25;
  controles.target.copy(trone);
  await chargerModele();
  modeSimulateur(false);
  window.addEventListener("resize", () => { if (ouvert) taille(); });
  pret = true;
}

// ---------- piloter ----------
const cap = (q) => Math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] * q[2] + q[3] * q[3]));   // q = (w, x, y, z)
async function lancerBalle() {
  try {
    const e = await window.api("/api/jumeau");
    const t = e.corps.trunk_base || Object.values(e.corps)[0];
    const c = Math.cos(cap(t.slice(3))), s = Math.sin(cap(t.slice(3)));
    // à 80 cm devant lui, roulant doucement vers lui
    await window.api("/api/jumeau-balle", { pos: [t[0] + 0.8 * c, t[1] + 0.8 * s, 0.05], vel: [-0.6 * c, -0.6 * s, 0] });
  } catch (x) { window.toast("Il faut le simulateur pour lancer une balle"); }
}
async function caresser() {
  try { await window.api("/api/jumeau-caresse", {}); } catch (x) { window.toast("Il faut le simulateur"); }
}

// ---------- programmer (blocs) ----------
function garder() { try { localStorage.setItem(CLE, JSON.stringify(programme)); } catch (e) { /* privé */ } }
let minuteurApercu = null;
function modifie() {
  garder();
  clearTimeout(minuteurApercu);
  minuteurApercu = setTimeout(apercu, 250);
}
async function apercu() {
  const info = $("#atelier-info");
  try {
    const r = await window.api("/api/atelier", { blocs: programme, action: "compiler" });
    const n = r.etapes.length;
    info.textContent = n ? `${n} étape${n > 1 ? "s" : ""} · ${Math.round(r.duree)} s` : "Ajoute un bloc pour commencer";
    if (r.tronque) info.textContent += " · trop long : la fin sera coupée";
    if (r.ignores) info.textContent += ` · ${r.ignores} bloc${r.ignores > 1 ? "s" : ""} ignoré${r.ignores > 1 ? "s" : ""}`;
    $("#atelier-jouer").disabled = !n; $("#atelier-enregistrer").disabled = !n;
  } catch (x) { info.textContent = "Microduck ne répond pas"; }
}

function curseur(b, cle, [min, max], pas, texte) {
  const sortie = el("output", { textContent: String(b[cle]) });
  const champ = el("input", { type: "range", min, max, step: pas, value: b[cle] });
  champ.addEventListener("input", () => { b[cle] = +champ.value; sortie.textContent = champ.value; modifie(); });
  return el("label", {}, el("span", { textContent: texte }), champ, sortie);
}
function choix(b, cle, options, texte) {
  const s = el("select", {}, ...Object.entries(options).map(([v, t]) => el("option", { value: v, textContent: t })));
  s.value = b[cle];
  s.addEventListener("change", () => { b[cle] = s.value; modifie(); });
  return el("label", {}, el("span", { textContent: texte }), s, el("span"));
}

function bloc(b, i, liste, profondeur) {
  const li = el("li", { className: "bloc bloc-" + b.type });
  const entete = el("header", {}, el("b", { textContent: TITRES[b.type] || b.type }));
  const bouger = (d) => { const j = i + d; if (j < 0 || j >= liste.length) return; [liste[i], liste[j]] = [liste[j], liste[i]]; redessiner(); };
  entete.append(el("button", { textContent: "↑", ariaLabel: "Monter", onclick: () => bouger(-1) }),
    el("button", { textContent: "↓", ariaLabel: "Descendre", onclick: () => bouger(1) }),
    el("button", { textContent: "✕", ariaLabel: "Retirer", className: "danger", onclick: () => { liste.splice(i, 1); redessiner(); } }));
  li.append(entete);
  if (b.type === "tete") {
    for (const k of Object.keys(TETE)) li.append(curseur(b, k, catalogue.bornes[k], 0.05, TETE[k]));
    li.append(curseur(b, "duree", [0.2, 5], 0.1, "Durée (s)"));
  } else if (b.type === "son") li.append(choix(b, "son", SONS, "Son"));
  else if (b.type === "geste") li.append(choix(b, "geste", GESTES, "Geste"));
  else if (b.type === "pause") li.append(curseur(b, "duree", [0.2, 10], 0.1, "Durée (s)"));
  else if (b.type === "repeter") {
    li.append(curseur(b, "n", [1, catalogue.max_repetitions || 10], 1, "Fois"));
    dessinerListe(b.blocs, li, profondeur + 1);
  }
  return li;
}

function dessinerListe(liste, parent, profondeur) {
  const ol = el("ol", { className: "blocs" });
  liste.forEach((b, i) => ol.append(bloc(b, i, liste, profondeur)));
  const types = Object.keys(NOUVEAU).filter((t) => t !== "repeter" || profondeur < 2);
  const menu = el("select", { className: "ajout-bloc", ariaLabel: "Ajouter un bloc" },
    el("option", { value: "", textContent: "+ Ajouter un bloc…" }), ...types.map((t) => el("option", { value: t, textContent: TITRES[t] })));
  menu.addEventListener("change", () => { if (menu.value) { liste.push(NOUVEAU[menu.value]()); redessiner(); } });
  parent.append(ol, menu);
}

function redessiner() {
  const zone = $("#atelier-blocs");
  zone.replaceChildren();
  dessinerListe(programme, zone, 0);
  modifie();
}

async function jouer() {
  try { await window.api("/api/atelier", { blocs: programme, action: "jouer" }); window.toast("C'est parti !"); }
  catch (x) { window.toast(x.message === "400" ? "Rien de jouable" : x.message); }
}
async function enregistrer() {
  const nom = $("#atelier-nom").value.trim() || "Mon programme";
  try {
    await window.api("/api/atelier", { blocs: programme, action: "enregistrer", nom });
    window.toast(`« ${nom} » est dans le Studio`);
    if (window.chargerTours) window.chargerTours();
  } catch (x) { window.toast(x.message); }
}

// ---------- écran ----------
function onglet(nom) {
  for (const b of document.querySelectorAll("#atelier [data-atelier-onglet]")) b.setAttribute("aria-pressed", String(b.dataset.atelierOnglet === nom));
  $("#atelier-piloter").hidden = nom !== "piloter";
  $("#atelier-programmer").hidden = nom !== "programmer";
}

async function ouvrir() {
  $("#atelier").hidden = false;
  history.pushState({ ecran: "atelier" }, "");
  ouvert = true;
  try { catalogue = Object.assign(catalogue, await window.api("/api/atelier")); } catch (x) { /* palette par défaut */ }
  try {
    if (!pret) { $("#atelier-attente").hidden = false; await init3d(); }
  } catch (x) { $("#atelier-attente").textContent = "La 3D ne démarre pas sur cet appareil"; ouvert = false; return; }
  $("#atelier-attente").hidden = true;
  taille();
  redessiner();
  clearTimeout(vers); sonder(); boucle();
  // l'écran se ferme par « retour » (app.js) : on arrête alors le dessin et les requêtes
  const fin = new MutationObserver(() => { if ($("#atelier").hidden) { ouvert = false; clearTimeout(vers); fin.disconnect(); } });
  fin.observe($("#atelier"), { attributes: true, attributeFilter: ["hidden"] });
}

$("#atelier-jouer").addEventListener("click", jouer);
$("#atelier-enregistrer").addEventListener("click", enregistrer);
$("#atelier-balle").addEventListener("click", lancerBalle);
$("#atelier-caresse").addEventListener("click", caresser);
$("#atelier-vider").addEventListener("click", () => { if (!programme.length || confirm("Tout effacer ?")) { programme.length = 0; redessiner(); } });
for (const b of document.querySelectorAll("#atelier [data-atelier-onglet]")) b.addEventListener("click", () => onglet(b.dataset.atelierOnglet));
onglet("piloter");

window.MicroduckAtelier = { ouvrir };
