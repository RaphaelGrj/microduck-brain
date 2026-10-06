// Installation (premier demarrage), page Connexions (configuration du canard sans ha.toml), impressions en cours,
// profil enfant. Les secrets (jeton HA, codes, cles API) ne reviennent jamais du canard : « •••••• » = inchange.
"use strict";

(function () {
  const $ = (s) => document.querySelector(s);
  const SECRET = "••••••";
  const TYPES_APPAREIL = { sonnette: "Sonnette", sonnette_event: "Sonnette (événement)", fumee: "Détecteur de fumée",
    aspirateur: "Aspirateur", calendrier: "Calendrier", machine: "Machine (lave-linge…)", puissance: "Prise (puissance)",
    meteo: "Météo", temperature: "Température extérieure" };
  const TYPES_IMPRIMANTE = { prusalink: "Prusa (PrusaLink)", sdcp: "Elegoo (SDCP)" };
  let config = null;

  function champ(type, valeur, attrs) {
    const i = document.createElement(type === "select" ? "select" : "input");
    if (type !== "select") i.type = type;
    Object.assign(i, attrs || {});
    if (type !== "select") i.value = valeur || "";
    return i;
  }
  function retirer(ligne) {
    const x = document.createElement("button"); x.textContent = "✕"; x.setAttribute("aria-label", "Retirer");
    x.addEventListener("click", () => ligne.remove());
    return x;
  }

  // ---------- installation ----------
  $("#form-installation").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const code = $("#i-code").value;
    if (code !== $("#i-code2").value) { $("#erreur-installation").textContent = "Les deux codes sont différents."; return; }
    try {
      const r = await fetch("/api/installation", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, nom: $("#i-nom").value.trim(),
          habitants: $("#i-habitants").value.split(",").map((x) => x.trim()).filter(Boolean) }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.erreur || r.status);
      $("#installation").hidden = true;
      window.entrer(code);
    } catch (x) { $("#erreur-installation").textContent = "Installation refusée : " + x.message; }
  });

  // ---------- connexions ----------
  function ligneHabitant(h) {
    const d = document.createElement("div"); d.className = "ligne";
    d.append(champ("text", h && h.nom, { placeholder: "Prénom", maxLength: 40, ariaLabel: "Prénom" }),
      champ("text", h && h.entite, { placeholder: "person.… (facultatif)", ariaLabel: "Entité Home Assistant" }), retirer(d));
    return d;
  }
  function ligneImprimante(i) {
    i = i || { type: "prusalink" };
    const d = document.createElement("div"); d.className = "ligne";
    const type = champ("select"); type.setAttribute("aria-label", "Type");
    for (const [k, v] of Object.entries(TYPES_IMPRIMANTE)) type.add(new Option(v, k, false, k === i.type));
    const cle = champ("password", i.cle_api, { placeholder: "Clé API PrusaLink", ariaLabel: "Clé API", className: "large-ligne", autocomplete: "off" });
    const majCle = () => { cle.hidden = type.value !== "prusalink"; };
    type.addEventListener("change", majCle); majCle();
    const etat = document.createElement("div"); etat.className = "etat-ligne";
    const tester = document.createElement("button"); tester.textContent = "Tester";
    tester.addEventListener("click", async () => {
      etat.textContent = "…";
      try {
        const r = await window.api("/api/tester-imprimante", { type: type.value, adresse: d.children[1].value.trim(), cle_api: cle.value });
        etat.textContent = r.ok ? `Répond : ${r.etat}${r.progression != null ? " (" + Math.round(r.progression) + " %)" : ""}` : "Ne répond pas : " + (r.message || "");
      } catch (x) { etat.textContent = x.message; }
    });
    d.append(champ("text", i.nom, { placeholder: "Nom (ex. MK4S)", maxLength: 40, ariaLabel: "Nom" }),
      champ("text", i.adresse, { placeholder: "192.168.1.30", ariaLabel: "Adresse", inputMode: "url" }), retirer(d), type, tester, cle, etat);
    return d;
  }
  function ligneAppareil(a) {
    a = a || { type: "sonnette" };
    const d = document.createElement("div"); d.className = "ligne";
    const type = champ("select"); type.setAttribute("aria-label", "Type");
    for (const [k, v] of Object.entries(TYPES_APPAREIL)) type.add(new Option(v, k, false, k === a.type));
    type.className = "large-ligne";
    d.append(champ("text", a.nom, { placeholder: "Nom", maxLength: 40, ariaLabel: "Nom" }),
      champ("text", a.entite, { placeholder: "binary_sensor.…", ariaLabel: "Entité Home Assistant" }), retirer(d), type);
    return d;
  }

  function remplir(c) {
    config = c;
    $("#c-nom").value = c.cerveau.nom || "";
    $("#c-garde").checked = !!c.cerveau.garde;
    $("#c-habitants").replaceChildren(...c.habitant.map(ligneHabitant));
    $("#c-code").value = ""; $("#c-code-enfant").value = c.appli.code_enfant ? SECRET : "";
    $("#c-ha-actif").checked = !!c.home_assistant.actif;
    $("#c-ha-url").value = c.home_assistant.url || "";
    $("#c-ha-jeton").value = c.home_assistant.token ? SECRET : "";
    $("#c-imprimantes").replaceChildren(...c.imprimante_directe.map(ligneImprimante));
    $("#c-appareils").replaceChildren(...c.appareil.map(ligneAppareil));
  }

  const LECTEURS = {
    cerveau: () => ({ nom: $("#c-nom").value.trim(), garde: $("#c-garde").checked }),
    habitant: () => [...document.querySelectorAll("#c-habitants .ligne")].map((d) => ({ nom: d.children[0].value.trim(), entite: d.children[1].value.trim() })).filter((h) => h.nom),
    appli: () => ({ code: $("#c-code").value || SECRET, code_enfant: $("#c-code-enfant").value }),
    home_assistant: () => ({ actif: $("#c-ha-actif").checked, url: $("#c-ha-url").value.trim(), token: $("#c-ha-jeton").value }),
    imprimante_directe: () => [...document.querySelectorAll("#c-imprimantes .ligne")].map((d) => ({ nom: d.children[0].value.trim(),
      adresse: d.children[1].value.trim(), type: d.children[3].value, cle_api: d.children[5].value })).filter((i) => i.adresse),
    appareil: () => [...document.querySelectorAll("#c-appareils .ligne")].map((d) => ({ nom: d.children[0].value.trim(),
      entite: d.children[1].value.trim(), type: d.children[3].value })).filter((a) => a.entite),
  };

  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest("[data-sauver]");
    if (!b) return;
    const section = b.dataset.sauver;
    if (section === "appli" && $("#c-code").value && $("#c-code").value.length < 6) { window.toast("Code : 6 caractères au moins"); return; }
    try {
      const r = await window.api("/api/configuration", { section, valeur: LECTEURS[section]() });
      remplir(r.configuration);
      if (section === "appli" && $("#c-code").value) { /* nouveau code : on le retient */ }
      if (r.redemarrer) $("#redemarrer-bandeau").hidden = false;
      window.toast("Enregistré");
    } catch (x) { window.toast(x.message === "code" ? "Code refusé" : "Refusé : " + x.message); }
  });
  $("#c-habitant-ajout").addEventListener("click", () => $("#c-habitants").append(ligneHabitant()));
  $("#c-imprimante-ajout").addEventListener("click", () => $("#c-imprimantes").append(ligneImprimante()));
  $("#c-appareil-ajout").addEventListener("click", () => $("#c-appareils").append(ligneAppareil()));
  $("#c-ha-tester").addEventListener("click", async () => {
    $("#c-ha-test").textContent = "…";
    try {
      const r = await window.api("/api/tester-ha", { url: $("#c-ha-url").value.trim(), token: $("#c-ha-jeton").value });
      $("#c-ha-test").textContent = (r.ok ? "✓ " : "✗ ") + r.message;
    } catch (x) { $("#c-ha-test").textContent = x.message; }
  });
  $("#redemarrer").addEventListener("click", async () => {
    if (!confirm("Redémarrer le cerveau ? Il reprend dans une quinzaine de secondes.")) return;
    try { await window.api("/api/redemarrer", {}); window.toast("Il redémarre…"); $("#redemarrer-bandeau").hidden = true; }
    catch (x) { window.toast(x.message); }
  });
  $("#ouvrir-connexions").addEventListener("click", async () => {
    $("#connexions").hidden = false; $("#connexions").scrollTo(0, 0);
    history.pushState({ ecran: "connexions" }, "");
    try { remplir(await window.api("/api/configuration")); } catch (x) { window.toast("Microduck ne répond pas"); }
  });

  // ---------- impressions en cours (accueil) ----------
  const ETATS_IMPRESSION = { en_cours: "en cours", finie: "terminée", echec: "en échec", inactive: "au repos" };
  async function impressions() {
    let liste = [];
    try { liste = await window.api("/api/imprimantes"); } catch (x) { return; }
    $("#carte-impressions").hidden = !liste.length;
    $("#impressions").replaceChildren(...liste.map((i) => {
      const li = document.createElement("li");
      const n = document.createElement("div"); n.className = "nom";
      const b = document.createElement("b"); b.textContent = i.nom;
      const d = document.createElement("div"); d.className = "discret petit";
      d.textContent = !i.joignable ? "injoignable" : [ETATS_IMPRESSION[i.etat] || i.etat,
        i.progression != null ? Math.round(i.progression) + " %" : null,
        i.reste_s ? "reste " + Math.round(i.reste_s / 60) + " min" : null].filter(Boolean).join(" · ");
      n.append(b, d);
      if (i.etat === "en_cours" && i.progression != null) {
        const barre = document.createElement("div"); barre.className = "barre-impression";
        const r = document.createElement("i"); r.style.width = Math.round(i.progression) + "%"; barre.append(r); n.append(barre);
      }
      li.append(n); return li;
    }));
  }
  setInterval(impressions, 30000);

  // ---------- apres la connexion : profil, impressions ----------
  window.apresConnexion = async () => {
    try { const r = await window.api("/api/role"); document.body.classList.toggle("enfant", r.role === "enfant"); } catch (x) { /* parent */ }
    impressions();
  };
})();

// ---------- mises a jour du cerveau, rapport, aide ----------
(function () {
  const $ = (s) => document.querySelector(s);
  const BRANCHE = "ccr-4c5851c0-mdd2p8";                 // (a passer sur main une fois la branche fusionnee)
  const DEPOT = "RaphaelGrj/microduck-brain";
  $("#maj-chercher").addEventListener("click", async () => {
    $("#maj-etat").textContent = "…";
    try {
      // c'est le telephone qui regarde GitHub ; le canard ne telechargera que si tu choisis d'installer
      const r = await fetch(`https://api.github.com/repos/${DEPOT}/commits/${BRANCHE}`).then((x) => x.json());
      const sha = String(r.sha || "").slice(0, 7), date = (r.commit && r.commit.committer.date || "").slice(0, 10);
      const actuelle = String($("#maj-version").textContent).split(" ")[0];
      const nouvelle = sha && !sha.startsWith(actuelle) && actuelle !== sha;
      $("#maj-etat").textContent = !sha ? "GitHub ne répond pas." : nouvelle
        ? `Nouvelle version ${sha} du ${date} : ${(r.commit.message || "").split("\n")[0]}` : "Il est à jour.";
      $("#maj-installer").hidden = !nouvelle;
    } catch (x) { $("#maj-etat").textContent = "Pas d'accès à Internet depuis le téléphone."; }
  });
  async function majCanard(action, texte) {
    if (!confirm(texte)) return;
    try {
      await window.api("/api/mise-a-jour", { action, branche: BRANCHE });
      window.toast("Il redémarre (une à deux minutes)…");
    } catch (x) { window.toast(x.message); }
  }
  $("#maj-installer").addEventListener("click", () => majCanard("installer",
    "Installer la nouvelle version ? Il redémarre, et la version actuelle est gardée pour revenir en arrière."));
  $("#maj-revenir").addEventListener("click", () => majCanard("revenir", "Revenir à la version précédente ? Il redémarre."));
  $("#rapport").addEventListener("click", async () => {
    try {
      const r = await window.api("/api/rapport");
      window.enregistrerFichier(`microduck-rapport-${new Date().toISOString().slice(0, 10)}.json`, "application/json", JSON.stringify(r, null, 1));
    } catch (x) { window.toast(x.message); }
  });
  $("#ouvrir-aide").addEventListener("click", () => {
    $("#aide").hidden = false; $("#aide").scrollTo(0, 0); history.pushState({ ecran: "aide" }, "");
    const libelles = [...new Set(Object.values(window.ETATS_LIBELLES || {}))].sort((a, b) => a.localeCompare(b, "fr"));
    $("#glossaire").replaceChildren(...libelles.map((v) => Object.assign(document.createElement("li"), { textContent: v })));
  });
})();
