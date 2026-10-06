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
  const demo = window.MicroduckDemo;                 // mode demo (demo.js) : un canard imaginaire, dans le telephone
  if (demo) return demo.api(chemin, corps);
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
    toast(e.message === "code" ? "Code refusé" : "Microduck ne répond pas");
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
  batteries(bt);
  semaine(e.semaine || []);
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

// Ses batteries (diagnostic.py) : laquelle est dans le canard, et la sante de chacune
function batteries(bt) {
  const liste = Object.entries(bt.batteries || {});
  $("#carte-batteries").hidden = !liste.length;
  if (!liste.length) return;
  const q = $("#batterie-question");
  q.hidden = !bt.a_nommer;
  q.replaceChildren(Object.assign(document.createElement("span"), { textContent: "Batterie changée : laquelle viens-tu de mettre ?" }),
    ...liste.map(([nom]) => Object.assign(document.createElement("button"), { className: "principal", textContent: nom,
      onclick: () => commande("batterie_" + nom, `Batterie ${nom} notée`) })));
  $("#batteries").replaceChildren(...liste.map(([nom, b]) => {
    const li = document.createElement("li");
    const n = document.createElement("div"); n.className = "nom";
    const titre = document.createElement("b"); titre.textContent = `Batterie ${nom}` + (bt.actuelle === nom ? " · dans le canard" : "");
    if (bt.actuelle === nom) titre.className = "actif";
    const d = document.createElement("div"); d.className = "discret petit";
    d.textContent = [b.cycles + " cycle" + (b.cycles > 1 ? "s" : ""), b.autonomie_h ? b.autonomie_h.toFixed(1) + " h" : null,
      b.sante_pct != null ? "santé " + Math.round(b.sante_pct) + " %" : null, b.a_remplacer ? "à remplacer" : null].filter(Boolean).join(" · ");
    n.append(titre, d);
    li.append(n);
    if (bt.actuelle !== nom) {
      const x = document.createElement("button"); x.textContent = "Elle est dedans";
      x.addEventListener("click", () => commande("batterie_" + nom, `Batterie ${nom} notée`));
      li.append(x);
    }
    return li;
  }));
}

// Sa semaine : une barre par jour (toutes activites), puis les totaux
const JOURS = ["dim", "lun", "mar", "mer", "jeu", "ven", "sam"];
function semaine(jours) {
  const totaux = {};
  const sommes = jours.map((j) => Object.entries(j.compte || {}).reduce((a, [k, v]) => { totaux[k] = (totaux[k] || 0) + v; return a + v; }, 0));
  const max = Math.max(1, ...sommes);
  $("#semaine").replaceChildren(...jours.map((j, i) => {
    const d = document.createElement("div");
    if (i === jours.length - 1) d.className = "aujourdhui";
    const b = document.createElement("b"); b.textContent = sommes[i];
    const barre = document.createElement("i"); barre.style.height = Math.round((sommes[i] / max) * 100) + "px";
    const l = document.createElement("span");
    l.textContent = i === jours.length - 1 ? "auj." : j.date ? JOURS[new Date(j.date + "T12:00").getDay()] : "—";
    d.append(b, barre, l);
    return d;
  }));
  const t = Object.entries(totaux).sort((a, b) => b[1] - a[1]);
  $("#semaine-totaux").replaceChildren(...(t.length ? t : [["rien", 0]]).map(([k, v]) => {
    const li = document.createElement("li");
    if (k === "rien") { li.textContent = "Pas encore d'activité cette semaine"; return li; }
    const b = document.createElement("b"); b.textContent = v; li.append(b, JOUR[k] ? JOUR[k][v > 1 ? 1 : 0] : k); return li;
  }));
}

// Alertes : le canard les tient (appli.py) ; le telephone les affiche, et l'APK en fait des notifications
let alerteDepuis = null;
const alertesVues = [];
async function verifierAlertes() {
  if (!code) return;
  try {
    const premiere = alerteDepuis === null;
    const r = await api("/api/alertes?depuis=" + (premiere ? Date.now() / 1000 - 86400 : alerteDepuis));
    alerteDepuis = r.maintenant;
    for (const a of r.alertes) {
      alertesVues.push(a);
      if (!premiere) toast(a.titre);
    }
    // APK : notifications Android (curseur partage avec la verification en arriere-plan : pas de doublon)
    if (window.MicroduckAndroid && r.alertes.length) window.MicroduckAndroid.alertes(JSON.stringify(r.alertes));
    alertesVues.splice(0, Math.max(0, alertesVues.length - 8));
    $("#carte-alertes").hidden = !alertesVues.length;
    $("#alertes-liste").replaceChildren(...alertesVues.slice().reverse().map((a) => {
      const li = document.createElement("li"); if (a.importante) li.className = "importante";
      const b = document.createElement("b"); b.textContent = a.titre;
      const t = document.createElement("small");
      t.textContent = [a.texte, new Date(a.t * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })].filter(Boolean).join(" · ");
      li.append(b, t); return li;
    }));
  } catch (x) { /* la prochaine fois */ }
}
setInterval(verifierAlertes, 15000);

// Sa journee (reglages.py) : heures calmes, bonjour, repas, auto-test, rythme
const heureVersTexte = (v) => (v ? v.slice(0, 5) : null);
function ligneRepas(v) {
  const s = document.createElement("span");
  const i = document.createElement("input"); i.type = "time"; i.value = v || "12:30"; i.setAttribute("aria-label", "Heure du repas");
  const x = document.createElement("button"); x.textContent = "✕"; x.setAttribute("aria-label", "Retirer ce repas");
  x.addEventListener("click", () => s.remove());
  s.append(i, x);
  return s;
}
async function chargerJournee() {
  let r;
  try { r = await api("/api/reglages"); } catch (x) { $("#carte-journee").hidden = true; return; }
  $("#carte-journee").hidden = false;
  for (const id of ["#r-calmes-debut", "#r-calmes-fin"]) {
    if (!$(id).options.length) for (let h = 0; h < 24; h++) $(id).add(new Option(String(h), String(h)));
  }
  $("#r-calmes").checked = !!r.heures_calmes;
  $("#r-calmes-debut").value = String((r.heures_calmes || [23, 7])[0]);
  $("#r-calmes-fin").value = String((r.heures_calmes || [23, 7])[1]);
  $("#r-calmes-heures").hidden = !r.heures_calmes;
  $("#r-bonjour").value = r.bonjour || "";
  $("#r-bonjour-we").value = r.bonjour_weekend || "";
  $("#r-repas").replaceChildren(...(r.repas || []).map(ligneRepas));
  $("#r-autotest").checked = !!r.autotest;
  $("#r-circadien").checked = !!r.circadien;
}
$("#r-calmes").addEventListener("change", (e) => { $("#r-calmes-heures").hidden = !e.target.checked; });
$("#r-repas-ajout").addEventListener("click", () => $("#r-repas").append(ligneRepas()));
$("#r-enregistrer").addEventListener("click", async () => {
  const calmes = $("#r-calmes").checked ? [+$("#r-calmes-debut").value, +$("#r-calmes-fin").value] : null;
  if (calmes && calmes[0] === calmes[1]) { toast("Début et fin des heures calmes identiques"); return; }
  try {
    await api("/api/reglages", { heures_calmes: calmes, bonjour: heureVersTexte($("#r-bonjour").value),
      bonjour_weekend: heureVersTexte($("#r-bonjour-we").value),
      repas: [...document.querySelectorAll("#r-repas input")].map((i) => i.value).filter(Boolean),
      autotest: $("#r-autotest").checked, circadien: $("#r-circadien").checked });
    toast("Réglages enregistrés");
    chargerJournee();
  } catch (x) { toast(x.message === "code" ? "Code refusé" : "Microduck ne répond pas"); }
});

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

// Sa carte : ce qu'il a parcouru depuis son demarrage (repere de l'odometrie). Vue de dessus, son cap de depart vers le
// haut, sa gauche a gauche. Rafraichie toutes les 5 s, seulement quand l'accueil est affiche.
let derniereCarte = null;

function dessinerCarte(c, plan = $("#plan"), messageVide = $("#plan-vide")) {
  if (plan.id === "plan") derniereCarte = c;
  const vide = !c || !c.cases || !c.cases.length;
  plan.hidden = vide; messageVide.hidden = !vide;
  if (vide || plan.offsetParent === null) return;
  const css = getComputedStyle(document.documentElement), v = (n) => css.getPropertyValue(n).trim();
  const dpr = window.devicePixelRatio || 1, L = plan.clientWidth, H = plan.clientHeight;
  plan.width = L * dpr; plan.height = H * dpr;
  const g = plan.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, L, H);
  const k = c.case;                                   // odometrie (x devant, y gauche) -> ecran (u droite, w haut)
  const pts = [...c.cases, ...(c.obstacles || []), ...(c.chutes || [])].map(([i, j]) => [i * k, j * k]);
  if (c.canard) pts.push([c.canard.x, c.canard.y]);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs) - k, x1 = Math.max(...xs) + 2 * k, y0 = Math.min(...ys) - k, y1 = Math.max(...ys) + 2 * k;
  const e = Math.min((L - 16) / (y1 - y0), (H - 16) / (x1 - x0), 90);     // pixels par metre (zoom max : 90 px/m)
  const cu = L / 2 + ((y1 + y0) / 2) * e, cw = H / 2 + ((x1 + x0) / 2) * e;
  const ecran = (x, y) => [cu - y * e, cw - x * e];
  const caseEcran = (i, j) => { const [u, w] = ecran((i + 1) * k, (j + 1) * k); return [u, w, k * e, k * e]; };
  g.fillStyle = v("--orange");
  for (const [i, j, f] of c.cases) { g.globalAlpha = 0.15 + 0.5 * f; g.fillRect(...caseEcran(i, j)); }
  g.globalAlpha = 1;
  g.fillStyle = "#6b6f76"; for (const [i, j] of c.obstacles || []) g.fillRect(...caseEcran(i, j));
  g.fillStyle = v("--danger"); for (const [i, j] of c.chutes || []) g.fillRect(...caseEcran(i, j));
  g.font = "16px system-ui, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  const SIGNES = { nap: "💤", chill: "🛋️", social: "💬", repas: "🍽️" };
  for (const [a, p] of Object.entries(c.coins || {})) g.fillText(SIGNES[a] || "★", ...ecran(p[0], p[1]));
  if (c.chargeur) g.fillText("🔌", ...ecran(...c.chargeur));
  g.fillStyle = v("--texte"); for (const p of c.objets || []) { const [u, w] = ecran(...p); g.beginPath(); g.arc(u, w, 3, 0, 7); g.fill(); }
  if (c.canard) {                                     // lui : un triangle pointe vers son cap
    const [u, w] = ecran(c.canard.x, c.canard.y), a = -c.canard.cap - Math.PI / 2;
    g.save(); g.translate(u, w); g.rotate(a);
    g.beginPath(); g.moveTo(11, 0); g.lineTo(-7, 7); g.lineTo(-3, 0); g.lineTo(-7, -7); g.closePath();
    g.fillStyle = v("--orange-fonce"); g.strokeStyle = "#fff"; g.lineWidth = 2; g.stroke(); g.fill(); g.restore();
  }
}

async function rafraichirCarte() {
  if ($("#plan").closest(".page").hidden || !code) return;
  try { dessinerCarte(await api("/api/carte")); } catch (x) { /* la prochaine fois */ }
}
setInterval(rafraichirCarte, 5000);
window.addEventListener("resize", () => dessinerCarte(derniereCarte));

// Lieux (reglages) : reconnus par le Wi-Fi sur le canard (lieux.py) ; ici on les montre et on agit dessus.
async function lieu(action, id, nom) {
  try {
    await api("/api/lieu", { action, id, nom });
    toast({ basculer: "C'est noté", archiver: "Archivé", restaurer: "Restauré", supprimer: "Supprimé", lier: "Wi-Fi lié",
      nouveau: "Nouveau lieu", renommer: "Renommé" }[action] || "Fait");
  } catch (e) { toast(e.message === "code" ? "Code refusé" : String(e.message).startsWith("c'est le lieu") ? "C'est le lieu actuel" : e.message); }
  rafraichirLieux();
}

function ligneLieu(l, d) {
  const li = document.createElement("li"), det = document.createElement("details"), sum = document.createElement("summary");
  const a = document.createElement("span"); a.textContent = l.nom;
  if (l.id === d.actuel) { const t = document.createElement("span"); t.className = "etiquette ici"; t.textContent = "ici"; a.append(" ", t); }
  const b = document.createElement("span"); b.className = "discret";
  b.textContent = l.reseaux.length ? "📶 " + l.reseaux.join(", ") : "aucun Wi-Fi lié";
  sum.append(a, b);
  const actions = document.createElement("div"); actions.className = "actions";
  const bouton = (texte, f, classe) => {
    const x = document.createElement("button"); x.textContent = texte; if (classe) x.className = classe;
    x.addEventListener("click", f); actions.append(x);
  };
  if (l.id !== d.actuel && !l.archive) bouton("Y aller", () => lieu("basculer", l.id), "principal");
  bouton("Sa carte", () => voirLieu(l));
  if (!l.archive) {
    bouton("Renommer", () => { const n = prompt("Nom du lieu", l.nom); if (n && n.trim()) lieu("renommer", l.id, n.trim()); });
    if (d.reseau && !l.reseaux.includes(d.reseau)) bouton(`Lier « ${d.reseau} »`, () => lieu("lier", l.id));
    bouton(l.auto ? "Bascule auto : oui" : "Bascule auto : non", () => lieu(l.auto ? "auto_off" : "auto_on", l.id));
  }
  if (l.id !== d.actuel) {
    if (l.archive) bouton("Restaurer", () => lieu("restaurer", l.id));
    else bouton("Archiver", () => lieu("archiver", l.id));
    bouton("Supprimer", () => { if (confirm(`Supprimer « ${l.nom} » et sa carte ? (Archiver la garde.)`)) lieu("supprimer", l.id); }, "danger");
  }
  det.append(sum, actions); li.append(det);
  return li;
}

async function voirLieu(l) {
  const d = $("#vue-lieu");
  texte("#vue-lieu-titre", l.nom);
  d.showModal();
  try { dessinerCarte(await api("/api/lieu-carte?id=" + encodeURIComponent(l.id)), $("#plan-lieu"), $("#plan-lieu-vide")); }
  catch (x) { dessinerCarte(null, $("#plan-lieu"), $("#plan-lieu-vide")); }
}

async function rafraichirLieux() {
  let d;
  try { d = await api("/api/lieux"); } catch (x) { $("#carte-lieux").hidden = true; return; }
  $("#carte-lieux").hidden = false;
  const ici = d.lieux.find((l) => l.id === d.actuel);
  const b = document.createElement("b"); b.textContent = ici ? ici.nom : "—";
  $("#lieu-ici").replaceChildren("Ici : ", b, d.reseau ? ` · Wi-Fi « ${d.reseau} »` : " · pas de Wi-Fi");
  const sug = d.lieux.find((l) => l.id === d.suggestion);
  $("#lieu-suggestion").hidden = !sug;
  if (sug) {
    const t = document.createElement("span"); t.textContent = `Il pense être à « ${sug.nom} ».`;
    const x = document.createElement("button"); x.className = "principal"; x.textContent = "Y aller";
    x.addEventListener("click", () => lieu("basculer", sug.id));
    $("#lieu-suggestion").replaceChildren(t, x);
  }
  const actifs = d.lieux.filter((l) => !l.archive), archives = d.lieux.filter((l) => l.archive);
  $("#lieux").replaceChildren(...actifs.map((l) => ligneLieu(l, d)));
  $("#archives").hidden = !archives.length;
  $("#archives summary").textContent = `Archives (${archives.length})`;
  $("#lieux-archives").replaceChildren(...archives.map((l) => ligneLieu(l, d)));
}

function liaison(ok) { $("#liaison").className = "pastille " + (ok ? "ok" : "ko"); }

function ecouter() {
  if (window.MicroduckDemo) {
    setInterval(() => { liaison(true); afficher(window.MicroduckDemo.instantane()); }, 1000);
    return;
  }
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
    rafraichirCarte();
    verifierAlertes();
    // APK : il retient l'adresse et le code pour verifier les alertes en arriere-plan (notifications, widget)
    if (window.MicroduckAndroid && !window.MicroduckDemo) window.MicroduckAndroid.retenir(location.origin, c);
  } catch (x) {
    $("#appli").hidden = true; $("#appairage").hidden = false;
    texte("#erreur-code", x.message === "code" ? "Code refusé." : "Microduck ne répond pas (même Wi-Fi ?).");
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
    if (b.dataset.onglet === "accueil") rafraichirCarte();
    if (b.dataset.onglet === "reglages") { rafraichirLieux(); chargerJournee(); }
  }
});
$("#t-calme").addEventListener("click", () => commande(dernier && dernier.modes.calme ? "calme_off" : "calme_on"));
$("#t-garde").addEventListener("click", () => commande(dernier && dernier.modes.garde ? "garde_off" : "garde_on"));
$("#oublier-carte").addEventListener("click", async () => {
  if (!confirm("Effacer sa carte ? Il oubliera aussi ses coins favoris et son chargeur, jusqu'à les réapprendre.")) return;
  await commande("oublier_carte", "Carte effacée");
  rafraichirCarte();
});
$("#lieu-nouveau").addEventListener("click", () => {
  const n = prompt("Nom du nouveau lieu (il y recommence une carte)", "Nouveau lieu");
  if (n && n.trim()) lieu("nouveau", null, n.trim());
});
// Ecrans plein (design, marketplace) : ouverts par les icones en haut a droite, fermes par la fleche ou le bouton retour
async function ouvrirDesign() {
  try {
    if (!window.MicroduckDesign) await import("/design.js");
    await window.MicroduckDesign.ouvrir();
  } catch (e) { toast("Le design ne s'ouvre pas"); }
}
$("#ouvrir-design").addEventListener("click", ouvrirDesign);
document.addEventListener("click", (ev) => { if (ev.target.closest("[data-fermer]")) history.back(); });
window.addEventListener("popstate", () => { document.querySelectorAll(".ecran.plein").forEach((e) => { e.hidden = true; }); });

$("#oublier").addEventListener("click", () => { memoire("microduck-code", null); location.reload(); });
$("#form-code").addEventListener("submit", (ev) => { ev.preventDefault(); entrer($("#code").value.trim()); });

const enregistre = window.MicroduckDemo ? "demo" : memoire("microduck-code");
if (enregistre) entrer(enregistre); else $("#appairage").hidden = false;
