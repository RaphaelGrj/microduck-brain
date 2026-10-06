// Jouer avec lui : statistiques et defi du jeu de balle, ses tours (choregraphies.py) et leur studio, comportements
// (politiques de robotd), curseurs de caractere, regard au pave tactile.
"use strict";

(function () {
  const $ = (s) => document.querySelector(s);
  const SONS = { greet: "Bonjour", chirp: "Pépiement", coo: "Roucoulement", inquire: "Question", peck: "Petit coup",
    wheee: "Youpi", alarm: "Alarme" };
  const GESTES = { content: "Content", non: "Non", oui: "Oui", curieux: "Curieux", surpris: "Surpris", fatigue: "Fatigué",
    etirement: "Étirement", ebouriffe: "S'ébouriffe", lissage: "Se lisse", eternuement: "Éternuement", fier: "Fier",
    baillement: "Bâillement", gene: "Gêné" };
  const DUREES = { son: 0.4, assis: 2.5, geste: 2 };
  const el = (tag, props, ...enfants) => { const e = Object.assign(document.createElement(tag), props || {}); e.append(...enfants.filter((x) => x != null)); return e; };

  // ---------- jeu de balle : statistiques et defi ----------
  let derniereBalle = null, defi = { joueurs: [], tour: 0, attente: null };
  try { defi = JSON.parse(localStorage.getItem("microduck-defi")) || defi; } catch (e) { /* vide */ }
  const garderDefi = () => { try { localStorage.setItem("microduck-defi", JSON.stringify(defi)); } catch (e) { /* prive */ } };
  function dessinerDefi() {
    $("#defi-joueurs").replaceChildren(...defi.joueurs.map((j, k) => {
      const li = el("li", { className: k === defi.tour ? "tour" : "" }, el("span", { className: "nom", textContent: j.nom }),
        el("b", { textContent: j.points + " pt" + (j.points > 1 ? "s" : "") }));
      return li;
    }));
    const j = defi.joueurs[defi.tour];
    $("#defi-tour").hidden = !j;
    $("#defi-tour").textContent = defi.attente ? `${defi.attente} : il tire…` : j ? `Au tour de ${j.nom} : lancer !` : "";
    $("#defi-tour").disabled = !!defi.attente;
  }
  window.majJouer = (e) => {
    const b = e.balle || {};
    const pct = b.tirs ? Math.round((100 * (b.reussies || 0)) / b.parties) : null;
    const dl = $("#stats-balle");
    dl.replaceChildren(...[["Parties", b.parties || 0], ["Réussies", b.parties ? `${b.reussies} (${pct} %)` : "—"],
      ["Tirs", b.tirs || 0], ["Meilleure série", b.record || 0]].flatMap(([k, v]) => [el("dt", { textContent: k }), el("dd", { textContent: v })]));
    // defi : la partie lancee pour un joueur se termine -> un point s'il l'a reussie
    if (defi.attente && derniereBalle && (b.parties || 0) > (derniereBalle.parties || 0)) {
      const j = defi.joueurs.find((x) => x.nom === defi.attente);
      if (j && b.derniere === "reussi") { j.points += 1; window.toast(`But pour ${j.nom} !`); } else window.toast("Raté…");
      defi.attente = null;
      defi.tour = (defi.tour + 1) % Math.max(1, defi.joueurs.length);
      garderDefi(); dessinerDefi();
    }
    derniereBalle = b;
  };
  $("#defi-ajout").addEventListener("click", () => {
    const nom = $("#defi-nom").value.trim();
    if (!nom) return;
    defi.joueurs.push({ nom, points: 0 }); $("#defi-nom").value = "";
    garderDefi(); dessinerDefi();
  });
  $("#defi-tour").addEventListener("click", async () => {
    const j = defi.joueurs[defi.tour];
    if (!j) return;
    defi.attente = j.nom; garderDefi(); dessinerDefi();
    await window.commande("jouer_balle", `À ${j.nom} de jouer !`);
  });
  $("#defi-raz").addEventListener("click", () => {
    defi.joueurs.forEach((j) => { j.points = 0; }); defi.tour = 0; defi.attente = null; garderDefi(); dessinerDefi();
  });
  dessinerDefi();

  // ---------- ses tours (liste, page Jouer) ----------
  let tours = [], studio = null;
  window.chargerTours = async () => {
    try { const r = await window.api("/api/choregraphies"); tours = r.liste; studio = studio || r; } catch (x) { return; }
    $("#liste-tours").replaceChildren(...(tours.length ? tours.map((t) => el("li", {}, el("span", { className: "nom", textContent: t.nom }),
      el("button", { textContent: "▶", ariaLabel: "Jouer " + t.nom, onclick: () => jouer(t.nom) })))
      : [el("li", { textContent: "Pas encore de tour : crée-le dans le studio." })]));
  };
  async function jouer(nom) {
    try { await window.api("/api/choregraphies", { jouer: nom }); window.toast(`« ${nom} »`); } catch (x) { window.toast(x.message); }
  }

  // ---------- studio ----------
  let courant = null;
  function curseur(etape, cle, bas, haut) {
    const v = el("output", { textContent: (+etape[cle]).toFixed(2) });
    const i = el("input", { type: "range", min: bas, max: haut, step: 0.05, value: etape[cle] });
    i.addEventListener("input", () => { etape[cle] = +i.value; v.textContent = (+i.value).toFixed(2); dureeTotale(); });
    return el("label", {}, el("span", { textContent: { cou: "Cou", tangage: "Haut/bas", lacet: "Gauche/droite", roulis: "Penché", duree: "Durée (s)" }[cle] }), i, v);
  }
  function choix(etape, cle, options) {
    const s = el("select", { ariaLabel: cle });
    for (const [k, v] of Object.entries(options)) s.add(new Option(v, k, false, k === etape[cle]));
    s.addEventListener("change", () => { etape[cle] = s.value; dureeTotale(); });
    return s;
  }
  function dureeTotale() {
    const t = courant ? courant.etapes.reduce((a, e) => a + (e.duree != null && ["tete", "pause"].includes(e.type) ? +e.duree : DUREES[e.type] || 0.4), 0) : 0;
    $("#studio-duree").textContent = `${courant ? courant.etapes.length : 0} étape(s) · ${t.toFixed(1)} s (60 s au plus)`;
  }
  function dessinerEtapes() {
    const ol = $("#studio-etapes");
    ol.replaceChildren(...courant.etapes.map((e, k) => {
      const outils = el("header", {}, el("b", { textContent: { tete: "Tête", son: "Son", geste: "Geste", assis: "S'asseoir / se relever", pause: "Pause" }[e.type] }),
        el("button", { textContent: "↑", ariaLabel: "Monter", onclick: () => { if (k) { courant.etapes.splice(k - 1, 0, courant.etapes.splice(k, 1)[0]); dessinerEtapes(); } } }),
        el("button", { textContent: "↓", ariaLabel: "Descendre", onclick: () => { if (k < courant.etapes.length - 1) { courant.etapes.splice(k + 1, 0, courant.etapes.splice(k, 1)[0]); dessinerEtapes(); } } }),
        el("button", { textContent: "✕", ariaLabel: "Retirer", onclick: () => { courant.etapes.splice(k, 1); dessinerEtapes(); } }));
      const li = el("li", {}, outils);
      const B = (studio && studio.bornes) || { cou: [-0.3, 0.4], tangage: [-0.5, 0.6], lacet: [-0.9, 0.9], roulis: [-0.4, 0.4] };
      if (e.type === "tete") li.append(...["lacet", "tangage", "roulis", "cou"].map((c) => curseur(e, c, B[c][0], B[c][1])), curseur(e, "duree", 0.2, 5));
      if (e.type === "son") li.append(choix(e, "son", SONS));
      if (e.type === "geste") li.append(choix(e, "geste", GESTES));
      if (e.type === "pause") li.append(curseur(e, "duree", 0.2, 10));
      return li;
    }));
    dureeTotale();
  }
  function choisir(nom) {
    const t = tours.find((x) => x.nom === nom);
    courant = t ? JSON.parse(JSON.stringify(t)) : { nom: "Mon tour", etapes: [] };
    $("#studio-nom").value = courant.nom;
    const s = $("#studio-choix");
    s.replaceChildren(...tours.map((x) => new Option(x.nom, x.nom, false, x.nom === courant.nom)), new Option("— nouvelle —", "", false, !t));
    dessinerEtapes();
  }
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-etape]");
    if (!b || !courant) return;
    const type = b.dataset.etape;
    courant.etapes.push({ tete: { type, cou: 0, tangage: 0, lacet: 0, roulis: 0, duree: 1 }, son: { type, son: "greet" },
      geste: { type, geste: "oui" }, assis: { type }, pause: { type, duree: 1 } }[type]);
    dessinerEtapes();
  });
  async function enregistrer() {
    courant.nom = $("#studio-nom").value.trim() || "Mon tour";
    const liste = tours.filter((t) => t.nom !== $("#studio-choix").value && t.nom !== courant.nom).concat([courant]);
    const r = await window.api("/api/choregraphies", { liste });
    tours = r.liste;
    choisir(courant.nom);
    window.chargerTours();
  }
  $("#studio-enregistrer").addEventListener("click", async () => {
    try { await enregistrer(); window.toast("Tour enregistré"); } catch (x) { window.toast(x.message); }
  });
  $("#studio-jouer").addEventListener("click", async () => {
    try { await enregistrer(); await jouer(courant.nom); } catch (x) { window.toast(x.message); }
  });
  $("#studio-choix").addEventListener("change", (e) => choisir(e.target.value));
  $("#studio-nouveau").addEventListener("click", () => choisir(""));
  $("#studio-supprimer").addEventListener("click", async () => {
    if (!confirm(`Supprimer « ${courant.nom} » ?`)) return;
    try {
      const r = await window.api("/api/choregraphies", { liste: tours.filter((t) => t.nom !== courant.nom) });
      tours = r.liste; choisir(tours[0] ? tours[0].nom : ""); window.chargerTours();
    } catch (x) { window.toast(x.message); }
  });
  $("#ouvrir-studio").addEventListener("click", async () => {
    $("#studio").hidden = false; history.pushState({ ecran: "studio" }, "");
    await window.chargerTours();
    choisir(tours[0] ? tours[0].nom : "");
  });

  // ---------- comportements ----------
  function liste(sel, items, bouton) {
    $(sel).replaceChildren(...(items.length ? items.map((x) => el("li", {}, el("span", { className: "nom", textContent: x }), bouton(x)))
      : [el("li", { className: "discret", textContent: "Rien ici." })]));
  }
  const nomDe = (x) => (typeof x === "string" ? x : x.name || x.nom || x.repo || x.id || JSON.stringify(x));
  $("#ouvrir-comportements").addEventListener("click", async () => {
    $("#comportements").hidden = false; history.pushState({ ecran: "comportements" }, "");
    $("#comp-etat").textContent = "…";
    try {
      const r = await window.api("/api/comportements");
      if (!r.ok) { $("#comp-etat").textContent = r.message; return; }
      $("#comp-etat").textContent = "";
      const skills = Array.isArray(r.skills) ? r.skills.map(nomDe) : [];
      const pol = Array.isArray(r.politiques) ? r.politiques.map(nomDe) : [];
      liste("#comp-installes", [...new Set([...skills, ...pol])], (x) => el("button", { textContent: "Essayer",
        disabled: !skills.includes(x), onclick: async () => { await window.api("/api/comportement", { action: "essayer", nom: x }); window.toast(`${x} : s'il est debout et au calme`); } }));
    } catch (x) { $("#comp-etat").textContent = x.message; }
  });
  $("#comp-chercher").addEventListener("click", async () => {
    const texte = $("#comp-texte").value.trim();
    try {
      const r = await window.api("/api/comportement", { action: "chercher", texte });
      const items = Array.isArray(r.resultat) ? r.resultat.map(nomDe) : r.ok ? [] : [r.message || "Recherche impossible"];
      liste("#comp-resultats", items, (x) => el("button", { textContent: "Installer", onclick: async () => {
        if (!confirm(`Installer ${x} sur le canard ?`)) return;
        const i = await window.api("/api/comportement", { action: "installer", texte: x });
        window.toast(i.ok ? "Installé" : "Échec : " + (i.message || JSON.stringify(i.resultat)));
      } }));
    } catch (x) { window.toast(x.message); }
  });

  // ---------- curseurs de caractere ----------
  window.chargerCurseurs = async () => {
    try {
      const r = await window.api("/api/reglages");
      const c = r.caractere || {};
      for (const k of ["joueur", "bavard", "taquin"]) $("#k-" + k).value = c[k] != null ? c[k] : 0.5;
    } catch (x) { /* profil enfant ou canard injoignable */ }
  };
  $("#k-enregistrer").addEventListener("click", async () => {
    try {
      await window.api("/api/reglages", { caractere: { joueur: +$("#k-joueur").value, bavard: +$("#k-bavard").value, taquin: +$("#k-taquin").value } });
      window.toast("Caractère enregistré");
    } catch (x) { window.toast(x.message); }
  });

  // ---------- regard au pave tactile (4 envois par seconde au plus) ----------
  const pave = $("#pave-regard"), point = pave.querySelector("i");
  let dernierEnvoi = 0, enAttente = null;
  function viser(ev) {
    const r = pave.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)), y = Math.max(0, Math.min(1, (ev.clientY - r.top) / r.height));
    point.style.left = x * 100 + "%"; point.style.top = y * 100 + "%";
    enAttente = { lacet: +(0.8 - 1.6 * x).toFixed(3), tangage: +(-0.4 + 0.9 * y).toFixed(3) };   // gauche = lacet positif
    const t = Date.now();
    if (t - dernierEnvoi > 250) { dernierEnvoi = t; window.api("/api/regard", enAttente).catch(() => {}); enAttente = null; }
  }
  pave.addEventListener("pointerdown", (ev) => { pave.setPointerCapture(ev.pointerId); viser(ev); });
  pave.addEventListener("pointermove", (ev) => { if (ev.buttons || ev.pointerType === "touch") viser(ev); });
  pave.addEventListener("pointerup", () => { if (enAttente) window.api("/api/regard", enAttente).catch(() => {}); });
})();
