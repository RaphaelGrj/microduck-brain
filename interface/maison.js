// Lot 9 : minuteurs et rappels (planning.py), signal en cours (Arreter), graphique d'humeur, bilan du mois (image).
"use strict";

(function () {
  const $ = (s) => document.querySelector(s);
  const el = (tag, props, ...enfants) => { const e = Object.assign(document.createElement(tag), props || {}); e.append(...enfants.filter((x) => x != null)); return e; };
  const erreur = (x) => window.toast(x.message === "code" ? "Code refusé" : x.message === "Failed to fetch" ? "Microduck ne répond pas" : x.message);
  const enfant = () => document.body.classList.contains("enfant");

  // ---------- minuteurs et rappels ----------
  let planning = { minuteurs: [], rappels: [], maintenant: Date.now() / 1000 }, decalage = 0;
  const duree = (s) => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0"); };
  function dessinerPlanning() {
    const t = Date.now() / 1000 + decalage;
    const lignes = [
      ...planning.minuteurs.map((m) => el("li", {}, el("span", { className: "nom" }, el("b", { textContent: "⏲️ " + m.nom })),
        el("span", { className: "compte", textContent: duree(m.fin - t) }),
        el("button", { textContent: "✕", ariaLabel: "Annuler " + m.nom, onclick: () => annuler("/api/minuteur", m.id) }))),
      ...planning.rappels.map((r) => el("li", {}, el("span", { className: "nom" }, el("b", { textContent: "🔔 " + r.texte }),
        el("small", { textContent: `${r.heure}${r.quotidien ? " · chaque jour" : ""}${r.pour ? " · pour " + r.pour : " · pour tout le monde"}` })),
        enfant() ? null : el("button", { textContent: "✕", ariaLabel: "Annuler le rappel", onclick: () => annuler("/api/rappel", r.id) }))),
    ];
    $("#planning").replaceChildren(...lignes);
  }
  async function chargerPlanning() {
    try { planning = await window.api("/api/planning"); decalage = planning.maintenant - Date.now() / 1000; } catch (x) { return; }
    dessinerPlanning();
  }
  setInterval(() => { if (planning.minuteurs.length && !$("#planning").closest(".page").hidden) dessinerPlanning(); }, 1000);
  setInterval(() => { if (code && !$("#planning").closest(".page").hidden) chargerPlanning(); }, 15000);
  async function annuler(chemin, id) {
    try { await window.api(chemin, { action: "annuler", id }); chargerPlanning(); } catch (x) { erreur(x); }
  }
  async function lancer(minutes, nom) {
    try {
      await window.api("/api/minuteur", { secondes: Math.round(minutes * 60), nom: nom || "" });
      window.toast(`Minuteur : ${minutes} min`);
      chargerPlanning();
    } catch (x) { erreur(x); }
  }
  document.querySelectorAll("[data-minutes]").forEach((b) => b.addEventListener("click", () => lancer(+b.dataset.minutes)));
  $("#min-lancer").addEventListener("click", () => {
    const m = +$("#min-duree").value;
    if (!(m > 0)) { $("#min-duree").focus(); return; }
    lancer(m, $("#min-nom").value.trim()); $("#min-duree").value = ""; $("#min-nom").value = "";
  });
  $("#rap-ajouter").addEventListener("click", async () => {
    const texte = $("#rap-texte").value.trim();
    if (!texte) { $("#rap-texte").focus(); return; }
    try {
      await window.api("/api/rappel", { texte, heure: $("#rap-heure").value, pour: $("#rap-pour").value.trim(), quotidien: $("#rap-quotidien").checked });
      $("#rap-texte").value = ""; window.toast("Rappel programmé"); chargerPlanning();
    } catch (x) { erreur(x); }
  });
  $("#signal-stop").addEventListener("click", () => window.commande("signal_stop", "C'est noté"));

  // ---------- son humeur (7 jours) ----------
  let stats = null;
  async function chargerStats() {
    try { stats = await window.api("/api/stats"); } catch (x) { return; }
    const h = stats.humeur || [];
    $("#humeur-vide").hidden = h.length >= 3; $("#humeur-graphe").hidden = h.length < 3;
    if (h.length >= 3 && window.graphe) {
      const jour = (t) => new Date(t * 1000).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric" });
      window.graphe($("#humeur-graphe"), [{ points: h.map((x) => Math.round(x[1] * 100)), couleur: "#f26a1b" },
        { points: h.map((x) => Math.round(x[2] * 100)), couleur: "#2563eb" }],
        { etiquettes: [jour(h[0][0]), jour(h[h.length - 1][0])], format: (y) => Math.round(y) + " %" });
      const moy = (k) => Math.round((100 * h.reduce((a, x) => a + x[k], 0)) / h.length);
      $("#humeur-legende").replaceChildren(el("li", {}, el("i", { className: "ligne", style: "background:#f26a1b" }), `Énergie (moyenne ${moy(1)} %)`),
        el("li", {}, el("i", { className: "ligne", style: "background:#2563eb" }), `Éveil (moyenne ${moy(2)} %)`));
    }
    const mois = [...new Set((stats.jours || []).map((j) => (j.date || "").slice(0, 7)).filter(Boolean))].sort().reverse();
    const s = $("#bilan-mois"), avant = s.value;
    s.replaceChildren(...mois.map((m) => new Option(new Date(m + "-15").toLocaleDateString(LOC, { month: "long", year: "numeric" }), m)));
    if (mois.includes(avant)) s.value = avant;
    dessinerBilan();
  }

  // ---------- bilan du mois (une carte a partager) ----------
  const JOUR = { promenades: "promenades", siestes: "siestes", jeux: "jeux", danses: "danses", caresses: "caresses",
    accueils: "accueils", folles_courses: "folles courses", blagues: "blagues" };
  let nomCanard = "Microduck";
  const EN = window.MicroduckLangue === "en", LOC = EN ? "en-GB" : "fr-FR";
  const JOUR_EN = { promenades: "walks", siestes: "naps", jeux: "games", danses: "dances", caresses: "pats", accueils: "welcomes",
    folles_courses: "zoomies", blagues: "pranks" };
  async function dessinerBilan() {
    const c = $("#bilan-carte"), m = $("#bilan-mois").value;
    if (!stats || !m || !c.clientWidth) return;
    const jours = (stats.jours || []).filter((j) => (j.date || "").startsWith(m));
    const tot = {}; let meilleur = null;
    for (const j of jours) {
      const n = Object.values(j.compte || {}).reduce((a, b) => a + b, 0);
      for (const [k, v] of Object.entries(j.compte || {})) tot[k] = (tot[k] || 0) + v;
      if (!meilleur || n > meilleur.n) meilleur = { date: j.date, n };
    }
    const W = 800, H = 1000; c.width = W; c.height = H;
    const g = c.getContext("2d");
    const fond = g.createLinearGradient(0, 0, 0, H); fond.addColorStop(0, "#f26a1b"); fond.addColorStop(1, "#c24a08");
    g.fillStyle = fond; g.fillRect(0, 0, W, H);
    g.fillStyle = "#fff"; g.textAlign = "center";
    g.font = "700 30px system-ui, sans-serif";
    g.fillText(new Date(m + "-15").toLocaleDateString(LOC, { month: "long", year: "numeric" }).toUpperCase(), W / 2, 70);
    g.font = "800 64px system-ui, sans-serif"; g.fillText(nomCanard, W / 2, 145);
    const img = $("#microduck-img");
    if (img && img.complete && img.naturalWidth) { const h = 300, w = (img.naturalWidth / img.naturalHeight) * h; g.drawImage(img, (W - w) / 2, 175, w, h); }
    const lignes = Object.entries(tot).sort((a, b) => b[1] - a[1]).slice(0, 4);
    g.font = "600 34px system-ui, sans-serif";
    let y = 540;
    g.fillText(EN ? `${jours.length} day${jours.length > 1 ? "s" : ""} of life` : `${jours.length} jour${jours.length > 1 ? "s" : ""} de vie`, W / 2, y); y += 60;
    g.font = "500 32px system-ui, sans-serif";
    for (const [k, v] of lignes) { g.fillText(`${v} ${(EN ? JOUR_EN : JOUR)[k] || k}`, W / 2, y); y += 50; }
    if (!lignes.length) { g.fillText(EN ? "A very quiet month" : "Un mois tout calme", W / 2, y); y += 50; }
    const b = stats.balle || {};
    if (b.parties) { g.fillText(EN ? `⚽ ${b.reussies || 0} goals in ${b.parties} games` : `⚽ ${b.reussies || 0} buts sur ${b.parties} parties`, W / 2, y); y += 50; }
    if (meilleur && meilleur.n) {
      g.font = "italic 28px system-ui, sans-serif";
      const d = new Date(meilleur.date + "T12:00").toLocaleDateString(LOC, { weekday: "long", day: "numeric" });
      g.fillText(EN ? `His best day: ${d}` : `Sa plus belle journée : ${d}`, W / 2, y + 20);
    }
    g.font = "500 22px system-ui, sans-serif"; g.globalAlpha = 0.8; g.fillText("Microduck", W / 2, H - 40); g.globalAlpha = 1;
  }
  $("#bilan-mois").addEventListener("change", dessinerBilan);
  $("#bilan-exporter").addEventListener("click", () => {
    const m = $("#bilan-mois").value || "mois";
    window.enregistrerFichier(`microduck-bilan-${m}.png`, "image/png", $("#bilan-carte").toDataURL("image/png"));
  });

  // ---------- APK : sauvegarde automatique chaque semaine (dans le telephone) ----------
  function sauvegardeAuto() {
    const a = window.MicroduckAndroid;
    if (!a || !a.sauvegardesAuto || window.MicroduckDemo) return;
    let s = {};
    try { s = JSON.parse(a.sauvegardesAuto()); } catch (x) { return; }
    $("#sauvegarde-auto").hidden = false;
    $("#sauvegarde-auto-actif").checked = !!s.actif;
    const l = s.fichiers || [];
    $("#sauvegarde-auto-info").textContent = s.derniere
      ? `Dernière : ${new Date(s.derniere * 1000).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })} · ${l.length} gardée${l.length > 1 ? "s" : ""} dans le téléphone`
      : "Pas encore faite : au prochain passage du téléphone à la maison.";
    $("#sauvegarde-auto-recuperer").hidden = !l.length;
    $("#sauvegarde-auto-recuperer").onclick = () => a.exporterSauvegarde(l[0]);
  }
  $("#sauvegarde-auto-actif").addEventListener("change", (e) => {
    window.MicroduckAndroid.reglerSauvegardeAuto(e.target.checked); sauvegardeAuto();
  });

  // ---------- raccourcis de l'icone (APK) : #action=... a l'ouverture ----------
  const RACCOURCIS = ["ou_es_tu", "jouer_balle", "calme_on", "minuteur_10"];
  function actionRaccourci() {
    const a = (location.hash.match(/^#action=([a-z_0-9]+)$/) || [])[1];
    if (!a || !RACCOURCIS.includes(a)) return;
    history.replaceState(null, "", location.pathname + location.search);
    if (a === "minuteur_10") lancer(10, "");
    else window.commande(a, { ou_es_tu: "Écoute bien…", jouer_balle: "À toi de jouer !", calme_on: "Mode calme" }[a]);
  }

  // ---------- branchements ----------
  const ancien = window.majPlus;
  window.majPlus = (e) => {
    if (ancien) ancien(e);
    $("#signal-stop").hidden = e.etat !== "signal";
  };
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-onglet]");
    if (!b) return;
    if (b.dataset.onglet === "accueil") chargerPlanning();
    if (b.dataset.onglet === "journal") chargerStats();
    if (b.dataset.onglet === "reglages") sauvegardeAuto();
  });
  const premier = setInterval(() => {
    if (!code) return;
    clearInterval(premier); chargerPlanning(); actionRaccourci();
    if (!window.MicroduckDemo) fetch("api/sante").then((r) => r.json()).then((s) => { nomCanard = s.nom || nomCanard; }).catch(() => {});
  }, 500);
})();
