// Application Microduck : interface servie par le canard (appli.py). Aucune dependance, aucun envoi hors du reseau local.
"use strict";

const ETATS = {
  chill: "Il se repose", look: "Il regarde autour de lui", turn: "Il se tourne", wander: "Il se promène",
  nap: "Il fait la sieste", startle: "Surpris !", curious: "Curieux", celebre: "Il fait la fête",
  alerte: "Il donne l'alerte", info: "Il a quelque chose à dire", regarde_chat: "Il regarde le chat",
  accueil: "Il accueille quelqu'un", rituel_depart: "Au revoir", ecoute: "Il écoute",
  etirement: "Il s'étire", ebouriffe: "Il s'ébouriffe", lissage: "Il se lisse les plumes", eternuement: "Atchoum",
  jeu_solitaire: "Il joue tout seul", cherche_attention: "Il cherche de la compagnie", bonjour: "Bonjour !",
  sonnette: "On sonne !", messager: "Il a un message", main_tendue: "Une main tendue", caresse: "Il se fait caresser",
  soleil: "1-2-3 soleil", va_au_coin: "Il va dans son coin", va_chargeur: "Il va se recharger",
  va_observer: "Il va observer", taquin: "Il fait le malin", appel: "Il répond", bravo: "Bravo !", danse: "Il danse",
  alarme: "ALARME", toupie: "Toupie", assis_demande: "Assis !", porte: "Dans les bras", salut: "Salut !",
  attentif: "Il t'écoute", hesite: "Il n'a pas compris", compliment: "Il est fier", chaud: "Il a chaud",
  remarque: "Tiens, quelque chose de nouveau", cache_cache: "Cache-cache", zoomies: "Folle course",
  picore: "Il picore", balle: "Il joue à la balle", autotest: "Diagnostic en cours", timide: "Il est timide",
  coup_oeil: "Un coup d'œil", compagnie: "Il te tient compagnie", va_compagnie: "Il vient te voir",
  penaud: "Penaud", cajole: "Content", compris: "Compris !", pas_guide: "Il marche (télécommande)",
  regard_guide: "Il regarde (télécommande)", retrait: "Trop de bruit, il s'éloigne", jour_special: "Jour spécial !",
  fier: "Il est fier", baillement: "Il bâille", baillement_contagieux: "Il bâille", fausse_chute: "Fausse chute !",
};
const JOUR = { promenades: ["promenade", "promenades"], siestes: ["sieste", "siestes"], jeux: ["jeu", "jeux"],
  danses: ["danse", "danses"], caresses: ["caresse", "caresses"], accueils: ["accueil", "accueils"],
  folles_courses: ["folle course", "folles courses"], blagues: ["blague", "blagues"] };
const TRAITS = { curiosite: "Curiosité", sociabilite: "Sociabilité", espieglerie: "Espièglerie", prudence: "Prudence" };
const VERIFS = { robotd: "Logiciel du robot", boucle: "Boucle de contrôle", bus: "Bus des moteurs", imu: "Centrale inertielle",
  tof: "Capteur de distance", camera: "Caméra", tete_lacet: "Tête (gauche-droite)", tete_tangage: "Tête (haut-bas)",
  batterie: "Batterie" };

const $ = (s) => document.querySelector(s);
let code = null, flux = null, dernier = null, minuteur = null;

function memoire(cle, valeur) {
  try {
    if (valeur === undefined) return localStorage.getItem(cle);
    if (valeur === null) localStorage.removeItem(cle); else localStorage.setItem(cle, valeur);
  } catch (e) { /* navigation privee : on redemandera le code */ }
  return null;
}

function toast(texte) {
  const t = $("#toast");
  t.textContent = texte;
  t.classList.add("visible");
  clearTimeout(minuteur);
  minuteur = setTimeout(() => t.classList.remove("visible"), 2200);
}

async function api(chemin, corps) {
  const r = await fetch(chemin, {
    method: corps ? "POST" : "GET",
    headers: { "X-Microduck-Code": code, "Content-Type": "application/json" },
    body: corps ? JSON.stringify(corps) : undefined,
  });
  if (r.status === 401) throw new Error("code");
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).erreur || r.status);
  return r.json();
}

async function commande(nom, quoi) {
  try {
    await api("/api/commande", { commande: nom });
    toast(quoi || "Envoyé");
  } catch (e) {
    toast(e.message === "code" ? "Code refusé" : "Le canard ne répond pas");
  }
}

function texte(sel, valeur) { $(sel).textContent = valeur; }
function pourcent(v) { return v == null ? "—" : Math.round(v) + " %"; }
function dl(sel, lignes) {
  $(sel).replaceChildren(...lignes.flatMap(([k, v]) => {
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); dd.textContent = v == null || v === "" ? "—" : v;
    return [dt, dd];
  }));
}
function barres(sel, valeurs, libelles, max = 1) {
  $(sel).replaceChildren(...Object.entries(valeurs).map(([k, v]) => {
    const d = document.createElement("div"); d.className = "trait";
    const l = document.createElement("div");
    const a = document.createElement("span"); a.textContent = libelles[k] || k;
    const b = document.createElement("span"); b.textContent = Math.round((v / max) * 100) + " %";
    l.append(a, b);
    const barre = document.createElement("div"); barre.className = "barre";
    const i = document.createElement("i"); i.style.width = Math.min(100, (v / max) * 100) + "%";
    barre.append(i); d.append(l, barre);
    return d;
  }));
}

function afficher(e) {
  dernier = e;
  dessiner(e);
  texte("#etat", e.tombe ? "Il est tombé" : e.porte ? "Dans les bras" : (ETATS[e.etat] || e.etat));
  texte("#sous-titre", e.tombe ? "Il est tombé…" : e.porte ? "Dans les bras" : e.assis ? "Assis" : "Debout");
  const alertes = [];
  if (e.modes.calme) alertes.push("Mode calme");
  if (e.modes.garde) alertes.push("Garde");
  if (e.modes.discret) alertes.push("Quelqu'un téléphone");
  if (e.modes.vacarme) alertes.push("Trop de bruit");
  if (e.modes.timidite > 0) alertes.push("Visiteur");
  if (e.tombe) alertes.push("Tombé");
  if (e.maintenance.diagnostic.ok === false) alertes.push("Diagnostic en échec");
  if (e.maintenance.batterie.a_remplacer) alertes.push("Batterie à remplacer");
  $("#alertes").replaceChildren(...alertes.map((a) => {
    const s = document.createElement("span"); s.className = "etiquette" + (/échec|Tombé|remplacer/.test(a) ? " alerte" : "");
    s.textContent = a; return s;
  }));
  for (const [k, v] of [["energie", e.energie], ["eveil", e.eveil]]) {
    $("#b-" + k).style.width = v * 100 + "%"; texte("#v-" + k, pourcent(v * 100));
  }
  $("#b-batterie").style.width = (e.batterie.pourcent || 0) + "%";
  texte("#v-batterie", pourcent(e.batterie.pourcent));
  texte("#presents", e.presents.length ? e.presents.join(", ") : "Personne");
  const jour = Object.entries(e.du_jour || {});
  $("#du-jour").replaceChildren(...(jour.length ? jour : [["rien", 0]]).map(([k, v]) => {
    const li = document.createElement("li");
    if (k === "rien") { li.textContent = "Rien encore aujourd'hui"; return li; }
    const b = document.createElement("b"); b.textContent = v; li.append(b, JOUR[k] ? JOUR[k][v > 1 ? 1 : 0] : k); return li;
  }));

  const d = e.maintenance.diagnostic;
  texte("#diag-resume", d.demande ? "Demandé : il le fera dès qu'il sera au repos." :
    d.le ? (d.ok ? "Tout va bien" : "Problème détecté") + " — " + d.le : "Pas encore de diagnostic.");
  $("#diag-detail").replaceChildren(...Object.entries(d.detail || {}).map(([k, v]) => {
    const li = document.createElement("li");
    const a = document.createElement("span"); a.textContent = VERIFS[k] || k;
    const b = document.createElement("span"); b.className = v.startsWith("OK") ? "ok-txt" : "ko-txt";
    b.textContent = v.replace(/^(OK|ECHEC) /, (m) => (m.startsWith("OK") ? "✓ " : "✗ "));
    li.append(a, b); return li;
  }));
  const bt = e.maintenance.batterie;
  dl("#batt", [["Niveau", pourcent(e.batterie.pourcent)], ["Tension", e.batterie.volts ? e.batterie.volts.toFixed(2) + " V" : null],
    ["Autonomie", bt.autonomie_h ? bt.autonomie_h.toFixed(1) + " h" : null], ["Santé", bt.sante_pct ? bt.sante_pct + " %" : null],
    ["Cycles mesurés", bt.cycles], ["À remplacer", bt.a_remplacer ? "oui" : "non"]]);
  const sv = e.maintenance.servos, t = e.temperatures || {};
  dl("#servos", [["Servo le plus chaud", t.moteurs != null ? Math.round(t.moteurs) + " °C" : null],
    ["Carte", t.cpu != null ? Math.round(t.cpu) + " °C" : null], ["Chauffe souvent", sv.plus_chaud_habituel],
    ["À surveiller", sv.derives.length ? sv.derives.join(", ") : "aucun"], ["Jours de mesure", sv.jours_mesures]]);
  const ch = e.maintenance.chutes;
  dl("#chutes", [["Sur 7 jours", ch.sept_jours], ["Activité risquée", ETATS[ch.activite_risquee] || ch.activite_risquee],
    ["Endroits à risque", ch.lieux_a_risque]]);
  texte("#version", e.version ? "Cerveau " + e.version : "");

  barres("#traits", e.caractere.traits || {}, TRAITS);
  const sons = e.caractere.sons || {};
  const total = Object.values(sons).reduce((a, b) => a + b, 0) || 1;
  barres("#sons", Object.fromEntries(Object.entries(sons).map(([k, v]) => [k, v / total])), {});
  $("#etres").replaceChildren(...(e.caractere.etres.length ? e.caractere.etres : [{ nom: "Personne encore", familiarite: null }])
    .map((x) => {
      const li = document.createElement("li");
      const a = document.createElement("span"); a.textContent = x.nom;
      const b = document.createElement("span"); b.className = "discret";
      b.textContent = x.familiarite == null ? "" : `familiarité ${Math.round(x.familiarite * 100)} % · ${x.rencontres} rencontres`;
      li.append(a, b); return li;
    }));

  for (const [id, actif] of [["#t-calme", e.modes.calme], ["#t-garde", e.modes.garde]]) $(id).setAttribute("aria-checked", String(actif));

  const fin = e.journal.length ? e.journal[e.journal.length - 1].t : 0;
  $("#journal").replaceChildren(...e.journal.slice().reverse().map((x) => {
    const li = document.createElement("li");
    const a = document.createElement("span"); const s = Math.round(fin - x.t);
    a.textContent = s < 60 ? `il y a ${s} s` : s < 3600 ? `il y a ${Math.round(s / 60)} min` : `il y a ${Math.round(s / 3600)} h`;
    const b = document.createElement("span"); b.textContent = ETATS[x.etat] || x.etat;
    li.append(a, b); return li;
  }));
}

// Le Microduck de l'accueil : familles d'etats -> expression (signes par-dessus) ; image d'apres posture et tete.
const FAMILLES = {
  dort: ["nap"],
  marche: ["wander", "va_au_coin", "va_chargeur", "va_observer", "va_repas", "va_compagnie", "va_social", "pas_guide",
    "zoomies", "cherche_attention", "jeu_solitaire"],
  "joue-jeu": ["balle", "soleil", "cache_cache", "danse", "zoomies", "bravo", "salut", "toupie", "fier", "celebre"],
  alerte: ["alarme", "alerte", "startle", "sonnette", "meteo_orage", "retrait"],
  content: ["caresse", "cajole", "accueil", "compris", "celebre", "jour_special", "compagnie", "bonjour"],
  penaud: ["penaud", "timide", "gene", "hesite"],
};
const IMAGES = ["debout", "debout-tete-basse", "debout-tete-haute", "debout-gauche", "debout-droite", "debout-penche",
  "marche", "assis", "assis-dort", "tombe"];
IMAGES.forEach((n) => { new Image().src = `/microduck/${n}.webp`; });     // prechargees : pas de clignotement
let pasMarche = null;

function image(e, famille) {
  if (e.tombe) return "tombe";
  const [cou, tangage, lacet, roulis] = e.tete || [0, 0, 0, 0];
  if (e.assis) return famille.includes("dort") || tangage + cou > 0.35 ? "assis-dort" : "assis";
  if (Math.abs(lacet) > 0.25) return lacet > 0 ? "debout-gauche" : "debout-droite";
  if (tangage + cou > 0.25) return "debout-tete-basse";
  if (tangage + cou < -0.15) return "debout-tete-haute";
  if (Math.abs(roulis) > 0.15) return "debout-penche";
  return "debout";
}

function dessiner(e) {
  const boite = $("#microduck"), img = $("#microduck-img");
  const familles = Object.entries(FAMILLES).filter(([, etats]) => etats.includes(e.etat)).map(([f]) => f);
  if (e.tombe) familles.push("tombe");
  if (e.porte) familles.push("porte");
  boite.className = ["microduck", ...familles].join(" ");
  const choix = image(e, familles);
  clearInterval(pasMarche);
  if (familles.includes("marche") && !e.assis && !e.tombe) {
    let n = 0;                                  // il marche : deux images en alternance
    img.src = "/microduck/marche.webp";
    pasMarche = setInterval(() => { img.src = `/microduck/${n++ % 2 ? "marche" : choix}.webp`; }, 380);
  } else if (!img.src.endsWith(`/${choix}.webp`)) {
    img.src = `/microduck/${choix}.webp`;
  }
  boite.setAttribute("aria-label", "Microduck : " + (ETATS[e.etat] || e.etat));
}

function liaison(ok) { $("#liaison").className = "pastille " + (ok ? "ok" : "ko"); }

function ecouter() {
  if (flux) flux.close();
  flux = new EventSource("/api/flux?code=" + encodeURIComponent(code));
  flux.onmessage = (m) => { liaison(true); try { const e = JSON.parse(m.data); if (e.etat) afficher(e); } catch (x) { /* trame partielle */ } };
  flux.onerror = () => liaison(false);
}

async function entrer(c) {
  code = c;
  try {
    const e = await api("/api/etat");
    memoire("microduck-code", c);
    $("#appairage").hidden = true; $("#appli").hidden = false;
    if (e.etat) afficher(e);
    ecouter();
  } catch (x) {
    $("#appli").hidden = true; $("#appairage").hidden = false;
    texte("#erreur-code", x.message === "code" ? "Code refusé." : "Le canard ne répond pas (même Wi-Fi ?).");
  }
}

document.addEventListener("click", (ev) => {
  const b = ev.target.closest("button");
  if (!b) return;
  if (b.dataset.cmd) commande(b.dataset.cmd, b.dataset.cmd === "diagnostic" ? "Diagnostic demandé" : null);
  if (b.dataset.onglet) {
    document.querySelectorAll(".onglets button").forEach((o) => o.removeAttribute("aria-current"));
    b.setAttribute("aria-current", "page");
    document.querySelectorAll(".page").forEach((p) => { p.hidden = p.dataset.page !== b.dataset.onglet; });
    window.scrollTo(0, 0);
  }
});
$("#t-calme").addEventListener("click", () => commande(dernier && dernier.modes.calme ? "calme_off" : "calme_on"));
$("#t-garde").addEventListener("click", () => commande(dernier && dernier.modes.garde ? "garde_off" : "garde_on"));
$("#oublier").addEventListener("click", () => { memoire("microduck-code", null); location.reload(); });
$("#form-code").addEventListener("submit", (ev) => { ev.preventDefault(); entrer($("#code").value.trim()); });

const enregistre = memoire("microduck-code");
if (enregistre) entrer(enregistre); else $("#appairage").hidden = false;
