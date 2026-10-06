// Lots 5 a 8 de l'application : ou l'a-t-il vu, messages, vacances (app.js), jeux sur sa carte (balle guidee,
// parcours chronometre), mode photo et journal photo, usure des servos, comparaison des batteries, carnet d'entretien,
// codes invites (QR code), partage des choregraphies, envoi d'un G-code du catalogue a une Prusa.
"use strict";

(function () {
  const $ = (s) => document.querySelector(s);
  const el = (tag, props, ...enfants) => { const e = Object.assign(document.createElement(tag), props || {}); e.append(...enfants.filter((x) => x != null)); return e; };
  const demo = () => !!window.MicroduckDemo;
  const CATALOGUE = "https://raw.githubusercontent.com/RaphaelGrj/microduck-catalogue/main/catalogue.json";
  const erreur = (x) => window.toast(x.message === "code" ? "Code refusé" : x.message === "Failed to fetch" ? "Microduck ne répond pas" : x.message);

  function ilYa(t) {
    const s = Math.max(0, Math.round(Date.now() / 1000 - t));
    if (s < 60) return "à l'instant";
    if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
    if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
    return `il y a ${Math.round(s / 86400)} j`;
  }
  const dateCourte = (t) => new Date(t * 1000).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });

  // ---------- ou l'a-t-il vu ? (carte de l'accueil) ----------
  const VUS = { chat: "🐱 Le chat", balle: "⚽ La balle", objet: "📦 Un objet au sol" };
  window.majVus = (c) => {
    const vus = Object.entries((c && c.vus) || {}).sort((a, b) => b[1].t - a[1].t);
    $("#vus").replaceChildren(...(vus.length ? vus.map(([k, v]) => el("li", {}, el("span", { textContent: VUS[k] || k }),
      el("span", { className: "discret", textContent: ilYa(v.t) })))
      : [el("li", { className: "discret", textContent: "Rien de remarqué depuis son démarrage." })]));
  };

  // ---------- messages ----------
  async function chargerMessages() {
    let r;
    try { r = await window.api("/api/messages"); } catch (x) { return; }
    const liste = (r.liste || []).slice(0, 12);
    $("#messages").replaceChildren(...liste.map((m) => {
      const n = el("div", { className: "nom" }, el("b", { textContent: `Pour ${m.pour}` + (m.de ? ` · de ${m.de}` : "") }),
        el("small", { textContent: m.texte }),
        el("small", { textContent: m.transmis ? `✓ signalé ${ilYa(m.transmis)}` : `en attente · ${ilYa(m.t)}` }));
      const li = el("li", { className: m.transmis ? "transmis" : "" }, n);
      if (!m.transmis && !document.body.classList.contains("enfant")) {
        li.append(el("button", { textContent: "✕", ariaLabel: "Annuler ce message", onclick: async () => {
          try { await window.api("/api/message", { action: "annuler", id: m.id }); chargerMessages(); } catch (x) { erreur(x); }
        } }));
      }
      return li;
    }));
  }
  $("#msg-envoyer").addEventListener("click", async () => {
    const pour = $("#msg-pour").value.trim(), texte = $("#msg-texte").value.trim();
    if (!pour) { $("#msg-pour").focus(); return; }
    if (!texte) { $("#msg-texte").focus(); return; }
    let de = "";
    try { de = (window.MicroduckAndroid && window.MicroduckAndroid.prenom && window.MicroduckAndroid.prenom()) || ""; } catch (x) { /* navigateur */ }
    try {
      await window.api("/api/message", { pour, texte, de });
      $("#msg-texte").value = "";
      window.toast(`Il le dira à ${pour}`);
      chargerMessages();
    } catch (x) { erreur(x); }
  });

  // ---------- jeux sur sa carte : balle guidee, parcours ----------
  let modeJeu = null, points = [], carteJeu = null;
  const plan = $("#plan-jeu");
  function dessinerJeu() {
    window.dessinerCarte(carteJeu, plan, $("#plan-jeu-vide"), (g, ecran, v) => {
      g.strokeStyle = v("--orange-fonce"); g.lineWidth = 2; g.setLineDash([6, 5]);
      const depart = carteJeu && carteJeu.canard ? [carteJeu.canard.x, carteJeu.canard.y] : null;
      const chemin = (depart ? [depart] : []).concat(points);
      if (chemin.length > 1) { g.beginPath(); chemin.forEach((p, k) => g[k ? "lineTo" : "moveTo"](...ecran(...p))); g.stroke(); }
      g.setLineDash([]);
      points.forEach((p, k) => {
        const [u, w] = ecran(...p);
        if (modeJeu === "balle") { g.font = "20px system-ui"; g.fillText("⚽", u, w); return; }
        g.fillStyle = v("--orange-fonce"); g.beginPath(); g.arc(u, w, 11, 0, 7); g.fill();
        g.fillStyle = "#fff"; g.font = "bold 12px system-ui"; g.fillText(String(k + 1), u, w + 1);
      });
    });
    $("#jeu-partir").disabled = !points.length || !modeJeu;
  }
  async function rafraichirJeu() {
    if (plan.closest(".page").hidden) return;
    try { carteJeu = await window.api("/api/carte"); } catch (x) { return; }
    dessinerJeu();
  }
  setInterval(rafraichirJeu, 5000);
  function choisirJeu(m) {
    modeJeu = modeJeu === m ? null : m;
    points = [];
    $("#jeu-balle").setAttribute("aria-pressed", String(modeJeu === "balle"));
    $("#jeu-parcours").setAttribute("aria-pressed", String(modeJeu === "parcours"));
    $("#jeu-aide").textContent = modeJeu === "balle" ? "Touche sa carte là où tu as lancé la balle : il y va, puis la cherche."
      : modeJeu === "parcours" ? "Pose jusqu'à 6 points (4 m au plus entre deux) : il les enchaîne, chronométré."
        : "Choisis un jeu, puis touche sa carte.";
    dessinerJeu();
  }
  $("#jeu-balle").addEventListener("click", () => choisirJeu("balle"));
  $("#jeu-parcours").addEventListener("click", () => choisirJeu("parcours"));
  $("#jeu-effacer").addEventListener("click", () => { points = []; dessinerJeu(); });
  plan.addEventListener("pointerdown", (ev) => {
    if (!modeJeu || !plan._vers_odom) { if (!modeJeu) window.toast("Choisis d'abord un jeu"); return; }
    const r = plan.getBoundingClientRect();
    const p = plan._vers_odom(ev.clientX - r.left, ev.clientY - r.top).map((x) => +x.toFixed(2));
    const prec = points.length ? points[points.length - 1] : carteJeu && carteJeu.canard ? [carteJeu.canard.x, carteJeu.canard.y] : null;
    if (prec && Math.hypot(p[0] - prec[0], p[1] - prec[1]) > 4) { window.toast("Trop loin : 4 m au plus"); return; }
    if (modeJeu === "balle") points = [p];
    else if (points.length < 6) points.push(p);
    else { window.toast("6 points au plus"); return; }
    dessinerJeu();
  });
  $("#jeu-partir").addEventListener("click", async () => {
    try {
      await window.api("/api/parcours", { points, genre: modeJeu });
      window.toast(modeJeu === "balle" ? "Il va chercher la balle !" : "Partez !");
      points = []; dessinerJeu();
    } catch (x) { erreur(x); }
  });
  async function chargerRecords() {
    let d;
    try { d = await window.api("/api/parcours"); } catch (x) { return; }
    const lignes = Object.entries(d.records || {}).sort((a, b) => a[0] - b[0])
      .map(([n, s]) => [`Record, ${n} point${n > 1 ? "s" : ""}`, `${String(s).replace(".", ",")} s`]);
    const der = (d.historique || []).slice(-1)[0];
    if (der) lignes.push(["Dernier parcours", der.issue === "reussi" ? `${String(der.duree).replace(".", ",")} s`
      : `${der.atteints} point(s) sur ${der.total}`]);
    $("#records").replaceChildren(...lignes.flatMap(([k, v]) => [el("dt", { textContent: k }), el("dd", { textContent: v })]));
  }

  // ---------- photos (journal, mode photo) ----------
  const cachePhotos = new Map();
  async function urlPhoto(p) {
    if (p.src) return p.src;                                   // demo
    if (cachePhotos.has(p.id)) return cachePhotos.get(p.id);
    const r = await fetch("/api/photo?id=" + encodeURIComponent(p.id), { headers: { "X-Microduck-Code": code } });
    if (!r.ok) throw new Error(r.status);
    const url = URL.createObjectURL(await r.blob());
    cachePhotos.set(p.id, url);
    return url;
  }
  const MOTIFS = { chat: "Le chat", retour: "Un retour", jour_special: "Jour spécial", danse: "Il danse", fier: "Fier",
    balle: "La balle", objet: "Un objet", impression: "Impression", pose: "Pose", photo: "Photo" };
  let photosListe = [], photoVue = null;
  async function chargerPhotos() {
    let r;
    try { r = await window.api("/api/photos"); } catch (x) { $("#carte-photos").hidden = true; return; }
    $("#carte-photos").hidden = false;
    $("#t-photos").setAttribute("aria-checked", String(!!r.actif));
    photosListe = r.liste || [];
    $("#photos-vide").hidden = !!photosListe.length;
    $("#photos").replaceChildren(...photosListe.map((p) => {
      const img = el("img", { alt: MOTIFS[p.motif] || p.motif, loading: "lazy" });
      urlPhoto(p).then((u) => { img.src = u; }).catch(() => {});
      return el("button", { ariaLabel: (MOTIFS[p.motif] || p.motif) + ", " + dateCourte(p.t), onclick: () => voirPhoto(p) },
        img, el("small", { textContent: MOTIFS[p.motif] || p.motif }));
    }));
  }
  async function voirPhoto(p) {
    photoVue = p;
    $("#vue-photo-img").src = await urlPhoto(p).catch(() => "");
    $("#vue-photo-legende").textContent = `${MOTIFS[p.motif] || p.motif} · ${dateCourte(p.t)} · ${new Date(p.t * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`;
    $("#vue-photo").showModal();
  }
  async function enDataUrl(url) {
    const b = await (await fetch(url)).blob();
    return new Promise((ok) => { const f = new FileReader(); f.onload = () => ok(f.result); f.readAsDataURL(b); });
  }
  $("#vue-photo-garder").addEventListener("click", async () => {
    if (!photoVue) return;
    try {
      const d = await enDataUrl(await urlPhoto(photoVue));
      window.enregistrerFichier(`microduck-${photoVue.id || photoVue.t + ".webp"}`, d.slice(5, d.indexOf(";")), d);
    } catch (x) { window.toast("Enregistrement impossible"); }
  });
  $("#vue-photo-effacer").addEventListener("click", async () => {
    if (!photoVue) return;
    try { await window.api("/api/photo", { action: "supprimer", id: photoVue.id }); $("#vue-photo").close(); chargerPhotos(); } catch (x) { erreur(x); }
  });
  $("#t-photos").addEventListener("click", async () => {
    const on = $("#t-photos").getAttribute("aria-checked") !== "true";
    try { await window.api("/api/reglages", { photos: on }); window.toast(on ? "Journal photo activé" : "Journal photo coupé"); chargerPhotos(); } catch (x) { erreur(x); }
  });
  $("#photo-maintenant").addEventListener("click", async () => {
    try { await window.api("/api/photo", { action: "prendre" }); window.toast("Clic !"); chargerPhotos(); } catch (x) { erreur(x); }
  });
  $("#photos-effacer").addEventListener("click", async () => {
    if (!confirm("Effacer toutes ses photos ?")) return;
    try { await window.api("/api/photo", { action: "tout_supprimer" }); chargerPhotos(); } catch (x) { erreur(x); }
  });
  const POSES = { fier: "😤 Fier", content: "😊 Content", curieux: "🤔 Curieux", oui: "👍 Oui", surpris: "😮 Surpris",
    etirement: "🙆 Étirement", ebouriffe: "🪶 Ébouriffé", gene: "🙈 Gêné" };
  $("#poses").replaceChildren(...Object.entries(POSES).map(([k, v]) => el("button", { textContent: v, onclick: async (ev) => {
    const b = ev.currentTarget; b.disabled = true;
    try {
      window.toast("Il prend la pose…");
      const r = await window.api("/api/photo", { action: "prendre", pose: k });
      const p = r.src ? r : { id: r.id };
      $("#photo-posee").src = await urlPhoto(p); $("#photo-posee").hidden = false;
      window.toast("Clic ! (dans Journal → Ses photos)");
    } catch (x) { erreur(x); } finally { b.disabled = false; }
  } })));

  // ---------- usure des servos, comparaison des batteries ----------
  const SERVOS = { left_hip_yaw: "Hanche gauche (rotation)", left_hip_roll: "Hanche gauche (côté)", left_hip_pitch: "Hanche gauche (avant)",
    left_knee: "Genou gauche", left_ankle: "Cheville gauche", neck_pitch: "Cou", head_pitch: "Tête (haut-bas)",
    head_yaw: "Tête (gauche-droite)", head_roll: "Tête (penchée)", right_hip_yaw: "Hanche droite (rotation)",
    right_hip_roll: "Hanche droite (côté)", right_hip_pitch: "Hanche droite (avant)", right_knee: "Genou droit", right_ankle: "Cheville droite" };
  window.NOMS_SERVOS = SERVOS;
  const COULEURS = ["#f26a1b", "#2f855a", "#2563eb"];
  function graphe(canvas, series, opts = {}) {
    const dpr = window.devicePixelRatio || 1, L = canvas.clientWidth, H = canvas.clientHeight;
    if (!L) return;
    canvas.width = L * dpr; canvas.height = H * dpr;
    const g = canvas.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, L, H);
    const css = getComputedStyle(document.documentElement), v = (n) => css.getPropertyValue(n).trim();
    const vals = series.flatMap((s) => s.points.filter((x) => x != null));
    if (!vals.length) return;
    const n = Math.max(...series.map((s) => s.points.length));
    const mn = Math.min(0, ...vals), mx = Math.max(...vals) * 1.15 || 1;
    const X = (i) => 34 + (n > 1 ? (i / (n - 1)) * (L - 46) : (L - 46) / 2), Y = (y) => H - 22 - ((y - mn) / (mx - mn)) * (H - 34);
    g.strokeStyle = v("--bord"); g.fillStyle = v("--discret"); g.font = "11px system-ui"; g.lineWidth = 1;
    for (const y of [mn, (mn + mx) / 2, mx]) { g.beginPath(); g.moveTo(34, Y(y)); g.lineTo(L - 8, Y(y)); g.stroke(); g.fillText(opts.format ? opts.format(y) : Math.round(y), 2, Y(y) + 4); }
    if (opts.etiquettes) { g.fillText(opts.etiquettes[0], 34, H - 6); const d = opts.etiquettes[opts.etiquettes.length - 1]; g.fillText(d, L - 8 - g.measureText(d).width, H - 6); }
    for (const s of series) {
      g.strokeStyle = s.couleur; g.fillStyle = s.couleur; g.lineWidth = 2.5; g.setLineDash(s.tirets ? [5, 4] : []);
      g.beginPath(); let debut = true;
      s.points.forEach((y, i) => { if (y == null) { debut = true; return; } g[debut ? "moveTo" : "lineTo"](X(i), Y(y)); debut = false; });
      g.stroke(); g.setLineDash([]);
      s.points.forEach((y, i) => { if (y != null) { g.beginPath(); g.arc(X(i), Y(y), 3, 0, 7); g.fill(); } });
    }
  }
  let usure = null;
  const jourLisible = (j) => { const [a, d] = j.split("-").map(Number); const t = new Date(a, 0, d); return t.toLocaleDateString("fr-FR", { day: "numeric", month: "short" }); };
  function dessinerUsure() {
    const sv = usure && usure.servos;
    const nom = $("#usure-servo").value;
    const vide = !sv || !sv.jours || sv.jours.length < 2;
    $("#usure-vide").hidden = !vide; $("#usure-graphe").hidden = vide;
    if (!vide && sv.servos[nom]) {
      graphe($("#usure-graphe"), [{ points: sv.servos[nom].courant, couleur: COULEURS[0] }],
        { etiquettes: [jourLisible(sv.jours[0]), jourLisible(sv.jours[sv.jours.length - 1])], format: (y) => Math.round(y) + "" });
    }
    const b = usure && usure.batteries;
    const series = Object.entries(b || {}).map(([k, c], i) => ({ nom: k, points: c.map((x) => x.autonomie_h), couleur: COULEURS[i % 3] }));
    $("#carte-comparer").hidden = !series.some((s) => s.points.length);
    if (!$("#carte-comparer").hidden) {
      graphe($("#batteries-graphe"), series, { format: (y) => y.toFixed(1) + " h", etiquettes: ["1er cycle", "dernier"] });
      $("#batteries-legende").replaceChildren(...series.map((s) => el("li", {}, el("i", { className: "ligne", style: `background:${s.couleur}` }),
        `Batterie ${s.nom} : ${s.points.length ? s.points[s.points.length - 1].toFixed(1) + " h" : "pas encore de cycle"}`)));
    }
  }
  async function chargerUsure() {
    try { usure = await window.api("/api/usure"); } catch (x) { return; }
    const s = $("#usure-servo");
    if (!s.options.length) for (const [k, v] of Object.entries(SERVOS)) s.add(new Option(v, k));
    const remplaces = (usure.servos && usure.servos.remplaces) || {};
    $("#usure-alertes").replaceChildren(...Object.entries(remplaces).map(([k, j]) => el("li", {},
      el("span", { textContent: SERVOS[k] || k }), el("span", { className: "discret", textContent: `remplacé le ${jourLisible(j)}` }))));
    dessinerUsure();
  }
  $("#usure-servo").addEventListener("change", dessinerUsure);
  window.addEventListener("resize", () => { if (usure) dessinerUsure(); if (carteJeu) dessinerJeu(); });

  // ---------- carnet d'entretien ----------
  const TYPES = { piece: "Pièce changée", impression: "Pièce imprimée", servo: "Servo remplacé", batterie: "Batterie remplacée",
    nettoyage: "Nettoyage", autre: "Autre" };
  for (const [k, v] of Object.entries(SERVOS)) $("#cn-servo").add(new Option(v, k));
  $("#cn-date").value = new Date().toISOString().slice(0, 10);
  $("#cn-type").addEventListener("change", () => {
    $("#cn-servo").hidden = $("#cn-type").value !== "servo";
    $("#cn-batterie").hidden = $("#cn-type").value !== "batterie";
  });
  async function chargerCarnet() {
    let r;
    try { r = await window.api("/api/carnet"); } catch (x) { return; }
    const liste = (r.liste || []).slice().reverse();
    $("#carnet").replaceChildren(...(liste.length ? liste.map((e) => {
      const quoi = e.type === "servo" ? `${TYPES.servo} : ${SERVOS[e.servo] || e.servo}` : e.type === "batterie" ? `Batterie ${e.batterie} remplacée`
        : TYPES[e.type] || e.type;
      const li = el("li", {}, el("span", { textContent: new Date(e.date + "T12:00").toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }) }),
        el("span", {}, el("b", { textContent: quoi }), e.texte || e.piece ? el("small", { textContent: [e.texte, e.piece].filter(Boolean).join(" · ") }) : null));
      li.append(el("button", { textContent: "✕", ariaLabel: "Retirer", onclick: async () => {
        if (!confirm("Retirer cette ligne du carnet ?")) return;
        try { await window.api("/api/carnet", { action: "supprimer", id: e.id }); chargerCarnet(); } catch (x) { erreur(x); }
      } }));
      return li;
    }) : [el("li", { className: "discret", textContent: "Rien de noté pour l'instant." })]));
  }
  $("#cn-ajouter").addEventListener("click", async () => {
    const type = $("#cn-type").value;
    const e = { action: "ajouter", type, texte: $("#cn-texte").value.trim(), date: $("#cn-date").value };
    if (type === "servo") e.servo = $("#cn-servo").value;
    if (type === "batterie") e.batterie = $("#cn-batterie").value;
    if ((type === "servo" || type === "batterie") && !confirm("Il repartira d'une mesure neuve pour cette pièce. C'est bien un remplacement ?")) return;
    try { await window.api("/api/carnet", e); $("#cn-texte").value = ""; window.toast("Noté"); chargerCarnet(); chargerUsure(); }
    catch (x) { window.toast(x.message === "entree incomplete" ? "Ajoute un détail" : x.message); }
  });

  // ---------- QR code ----------
  function qrSvg(texte) {
    const q = window.qrcode(0, "M");
    q.addData(texte, "Byte");
    q.make();
    return q.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  }
  function montrerQR(titre, texte, aide) {
    let svg;
    try { svg = qrSvg(texte); } catch (x) { window.toast("Trop long pour un QR code : exporte le fichier"); return; }
    $("#vue-qr-titre").textContent = titre;
    $("#vue-qr-image").innerHTML = svg;             // (SVG fabrique ici, sans donnee exterieure)
    $("#vue-qr-texte").textContent = aide || texte;
    $("#vue-qr-copier").onclick = async () => {
      try { await navigator.clipboard.writeText(texte); window.toast("Copié"); } catch (x) { window.prompt("Copie ce texte :", texte); }
    };
    $("#vue-qr-partager").hidden = !navigator.share;
    $("#vue-qr-partager").onclick = () => navigator.share({ title: titre, text: texte }).catch(() => {});
    $("#vue-qr").showModal();
  }

  window.montrerQR = montrerQR;
  // ---------- sur un autre appareil : iPhone (appli web installee par Safari), ordinateur ----------
  const RELEASES = "https://github.com/RaphaelGrj/microduck-brain/releases";
  $("#qr-iphone").addEventListener("click", () => {
    if (demo() || !/^https?:$/.test(location.protocol)) { window.toast("Depuis l'appli connectée au canard (pas en démo)"); return; }
    montrerQR("Sur un iPhone", location.origin + "/", "Appareil photo → ouvrir dans Safari → Partager → « Sur l'écran d'accueil ». Puis entre le code du canard.");
  });
  $("#lien-ordinateur").addEventListener("click", () => {
    const a = document.createElement("a"); a.href = RELEASES; a.target = "_blank"; a.rel = "noopener"; a.click();
  });                   // (design.js : partager un schema de couleurs)

  // ---------- invites ----------
  const lienInvite = (c) => `${location.origin}/#code=${c}`;
  async function chargerInvites() {
    let r;
    try { r = await window.api("/api/invites"); } catch (x) { return; }
    $("#invites").replaceChildren(...(r.liste || []).map((i) => el("li", {},
      el("div", { className: "nom" }, el("b", { textContent: i.nom }), el("small", { textContent: `${i.code} · jusqu'au ${dateCourte(i.jusqua)} ${new Date(i.jusqua * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}` })),
      el("button", { textContent: "QR", ariaLabel: "QR code de " + i.nom, onclick: () => montrerQR(`Invité : ${i.nom}`, lienInvite(i.code), `Scanne avec l'appareil photo (même Wi-Fi). Ou code : ${i.code}`) }),
      el("button", { textContent: "✕", ariaLabel: "Révoquer", onclick: async () => {
        try { await window.api("/api/invites", { action: "revoquer", code: i.code }); chargerInvites(); } catch (x) { erreur(x); }
      } }))));
  }
  $("#inv-creer").addEventListener("click", async () => {
    try {
      const r = await window.api("/api/invites", { heures: +$("#inv-duree").value, nom: $("#inv-nom").value.trim() });
      $("#inv-nom").value = "";
      chargerInvites();
      montrerQR(`Invité : ${r.nom}`, lienInvite(r.code), `Scanne avec l'appareil photo (même Wi-Fi). Ou code : ${r.code}`);
    } catch (x) { erreur(x); }
  });

  // ---------- partage des choregraphies ----------
  const PREFIXE = "MICRODUCK-CHOREGRAPHIE:";
  function lireChoregraphie(texte) {
    texte = String(texte || "").trim();
    if (texte.startsWith(PREFIXE)) texte = texte.slice(PREFIXE.length);
    const d = JSON.parse(texte);
    const c = d.choregraphie || d;
    if (!c || !Array.isArray(c.etapes) || !c.etapes.length) throw new Error("Ce n'est pas une chorégraphie");
    return { nom: c.nom || "Tour importé", etapes: c.etapes };
  }
  async function importer(c) {
    try { const nom = await window.studio.ajouter(c); window.toast(`« ${nom} » ajouté`); } catch (x) { erreur(x); }
  }
  const exportable = () => {
    const c = window.studio && window.studio.courant();
    if (!c || !c.etapes.length) { window.toast("Rien à exporter : ajoute des étapes"); return null; }
    return c;
  };
  $("#studio-exporter").addEventListener("click", () => {
    const c = exportable();
    if (!c) return;
    const nom = c.nom.normalize("NFD").replace(/[^\w-]+/g, "-").replace(/^-|-$/g, "").toLowerCase() || "choregraphie";
    window.enregistrerFichier(`${nom}.json`, "application/json",
      JSON.stringify({ format: "microduck-choregraphie", version: 1, choregraphie: c }, null, 1));
  });
  $("#studio-qr").addEventListener("click", () => {
    const c = exportable();
    if (c) montrerQR(c.nom, PREFIXE + JSON.stringify(c), "Scanne ce code avec l'appareil photo, copie le texte, puis « Coller un texte » dans le studio de l'autre téléphone.");
  });
  $("#studio-importer").addEventListener("change", async (e) => {
    const f = e.target.files[0]; e.target.value = "";
    if (!f) return;
    try { await importer(lireChoregraphie(await f.text())); } catch (x) { window.toast("Ce fichier n'est pas une chorégraphie"); }
  });
  $("#studio-coller").addEventListener("click", async () => {
    let texte = "";
    try { texte = await navigator.clipboard.readText(); } catch (x) { /* pas d'acces au presse-papiers */ }
    if (!texte || !texte.includes("etapes")) texte = window.prompt("Colle le texte de la chorégraphie :", "") || "";
    if (!texte) return;
    try { await importer(lireChoregraphie(texte)); } catch (x) { window.toast("Ce texte n'est pas une chorégraphie"); }
  });
  let catalogueTours = null;
  window.chargerCatalogueTours = async () => {
    try {
      if (!catalogueTours) catalogueTours = demo() ? [{ id: "coucou", nom: "Coucou", auteur: "RaphaelGrj",
        description: "Il dit bonjour, tourne la tête vers toi, acquiesce et lance un « youpi ».",
        etapes: [{ type: "son", son: "greet" }, { type: "tete", cou: 0, tangage: -0.2, lacet: 0.6, roulis: 0.2, duree: 1 },
          { type: "geste", geste: "oui" }, { type: "son", son: "wheee" }] }]
        : ((await (await fetch(CATALOGUE, { cache: "no-cache" })).json()).choregraphies || []);
    } catch (x) { $("#studio-catalogue").replaceChildren(el("li", { className: "discret", textContent: "Catalogue injoignable (Internet ?)" })); return; }
    $("#studio-catalogue").replaceChildren(...(catalogueTours.length ? catalogueTours.map((c) => el("li", {},
      el("div", { className: "nom" }, el("b", { textContent: c.nom }), el("small", { textContent: [c.description, c.auteur].filter(Boolean).join(" · ") })),
      el("button", { textContent: "Ajouter", onclick: () => importer(c) })))
      : [el("li", { className: "discret", textContent: "Pas encore de chorégraphie partagée." })]));
  };

  // ---------- envoyer un G-code du catalogue a une Prusa ----------
  let dialogueImpression = null;
  window.envoyerImpression = async (p) => {
    let imprimantes = [];
    try { imprimantes = (await window.api("/api/imprimantes")).filter((i) => i.type === "prusalink"); } catch (x) { /* aucune */ }
    if (!imprimantes.length) { window.toast("Ajoute d'abord ta Prusa dans Réglages → Connexions"); return; }
    if (!dialogueImpression) { dialogueImpression = el("dialog", { className: "vue-qr" }); document.body.append(dialogueImpression); }
    const fichier = el("select", { ariaLabel: "Fichier" }, ...p.fichiers.map((f, k) => new Option(`${f.imprimante} · ${f.materiau || ""} · ${(f.octets / 1e6).toFixed(1)} Mo`, k)));
    const cible = el("select", { ariaLabel: "Imprimante" }, ...imprimantes.map((i) => new Option(i.nom + (i.etat === "en_cours" ? " (occupée)" : ""), i.nom)));
    const lancer = el("input", { type: "checkbox", className: "case" });
    const etat = el("p", { className: "discret petit", textContent: "Vérifie que le plateau est libre et le bon filament chargé." });
    const envoyer = el("button", { className: "principal large", textContent: "Envoyer" });
    envoyer.onclick = async () => {
      const f = p.fichiers[+fichier.value];
      envoyer.disabled = true;
      try {
        if (demo()) { await new Promise((ok) => setTimeout(ok, 800)); throw new Error("démo : rien n'est envoyé"); }
        etat.textContent = "Téléchargement depuis le catalogue…";
        const r = await fetch(f.url);
        if (!r.ok) throw new Error("fichier introuvable dans le catalogue");
        const octets = await r.arrayBuffer();
        etat.textContent = "Envoi à l'imprimante (par le canard)…";
        const e = await fetch("/api/imprimer", { method: "POST", body: octets, headers: { "X-Microduck-Code": code,
          "X-Imprimante": cible.value, "X-Fichier": f.nom, "X-Lancer": lancer.checked ? "1" : "0", "Content-Type": "application/octet-stream" } });
        const j = await e.json().catch(() => ({}));
        if (!e.ok) throw new Error(j.erreur || e.status);
        window.toast(lancer.checked ? "Impression lancée !" : "Fichier posé sur l'imprimante");
        dialogueImpression.close();
      } catch (x) { etat.textContent = "Échec : " + x.message; } finally { envoyer.disabled = false; }
    };
    dialogueImpression.replaceChildren(el("h2", { textContent: p.nom }),
      el("label", { className: "champ" }, "Fichier", fichier), el("label", { className: "champ" }, "Imprimante", cible),
      el("div", { className: "reglage" }, el("div", {}, el("b", { textContent: "Lancer l'impression" })), lancer),
      etat, envoyer, el("form", { method: "dialog" }, el("button", { className: "large", textContent: "Annuler" })));
    dialogueImpression.showModal();
  };

  // ---------- chargements par onglet ----------
  window.majPlus = (e) => {
    const noms = new Set([...(e.presents || []), ...((e.caractere && e.caractere.etres) || []).map((x) => x.nom)]);
    noms.delete("le chat"); noms.delete("aspirateur");
    const dl = $("#msg-noms");
    if (dl.childElementCount !== noms.size) dl.replaceChildren(...[...noms].map((n) => el("option", { value: n })));
  };
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-onglet]");
    if (!b) return;
    const o = b.dataset.onglet;
    if (o === "accueil") chargerMessages();
    if (o === "jouer") { rafraichirJeu(); chargerRecords(); }
    if (o === "journal") chargerPhotos();
    if (o === "sante") { chargerUsure(); chargerCarnet(); }
    if (o === "reglages") chargerInvites();
  });
  // alertes « Message transmis » / « Parcours » : rafraichir la liste concernee
  setInterval(() => {
    if (!code) return;
    if (!$("#messages").closest(".page").hidden) chargerMessages();
    if (!plan.closest(".page").hidden) chargerRecords();
  }, 15000);
  const premier = setInterval(() => { if (code) { clearInterval(premier); chargerMessages(); } }, 500);
})();
