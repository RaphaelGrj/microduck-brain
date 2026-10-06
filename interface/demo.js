// Mode demo de l'application : un Microduck imaginaire, pour essayer l'appli sans le robot (appli Android « Essayer en
// demo », ou ?demo dans l'adresse). Tout est fabrique ici, dans le telephone : rien n'est envoye nulle part.
"use strict";

(function () {
  if (location.hostname !== "demo.microduck.local" && !/[?&]demo\b/.test(location.search)) return;

  const debut = Date.now() / 1000;
  const VIE = [["chill", 14], ["look", 8], ["wander", 12], ["curious", 6], ["jeu_solitaire", 10], ["chill", 10],
    ["etirement", 5], ["regarde_chat", 8], ["nap", 18], ["bonjour", 5]];
  const JEUX = { jouer_balle: "balle", jouer_cache: "cache_cache", jouer_soleil: "soleil", danse: "danse",
    salut: "salut", toupie: "toupie", avance: "pas_guide", gauche: "pas_guide", droite: "pas_guide" };
  const REGARDS = { regard_gauche: [0, 0, 0.6, 0], regard_droite: [0, 0, -0.6, 0], regard_haut: [0, -0.3, 0, 0],
    regard_bas: [0, 0.4, 0, 0], regard_centre: [0, 0, 0, 0] };
  const TETES = { look: [0, 0, 0.5, 0], curious: [0, 0.1, 0, 0.25], regarde_chat: [0, 0.2, -0.45, 0],
    nap: [0.1, 0.5, 0, 0], jeu_solitaire: [0, 0.3, 0, 0] };

  let carteDepuis = -1e6;
  let batterieDedans = "2", batterieANommer = true;
  const SEMAINE = [{ promenades: 4, siestes: 2, jeux: 1 }, { promenades: 2, siestes: 3, caresses: 3 },
    { promenades: 5, jeux: 3, danses: 1 }, { siestes: 2, caresses: 1 }, { promenades: 6, jeux: 2, accueils: 2 },
    { promenades: 3, siestes: 2, jeux: 4, danses: 2 }, null];
  // alertes imaginaires : une impression finie apres 25 s, puis une alerte de garde si on active le mode garde
  const alertes = [{ t: Date.now() / 1000 - 3600, type: "impression_finie", titre: "Impression finie", texte: "MK4S", importante: false }];
  setTimeout(() => alertes.push({ t: Date.now() / 1000, type: "impression_finie", titre: "Impression finie",
    texte: "Saturn 4 Ultra", importante: false }), 25000);
  let reglagesDemo = { heures_calmes: [23, 7], bonjour: "07:30", bonjour_weekend: "09:30", repas: ["12:30", "19:30"],
    autotest: true, circadien: true };                      // « Effacer sa carte » : il repart de zero ici
  let i = 0, finEtat = 0, force = null, tete = null, assis = false, calme = false, garde = false;
  let diag = { ok: true, le: "ce matin, 7 h 42", demande: false, finDemande: 0 };
  const journal = [], duJour = { promenades: 3, siestes: 1, jeux: 2, caresses: 4, accueils: 1 };
  let etat = "chill";

  function changer(nouvel, duree) {
    etat = nouvel; finEtat = Date.now() / 1000 + duree;
    journal.push({ t: Math.round(Date.now() / 1000), etat });
    if (journal.length > 40) journal.shift();
  }
  for (const [e] of VIE.slice(0, 6)) journal.push({ t: Math.round(debut - 600 + journal.length * 90), etat: e });

  function avancer() {
    const t = Date.now() / 1000;
    if (diag.demande && t > diag.finDemande) {
      diag = { ok: true, le: "à l'instant", demande: false, finDemande: 0 };
      if (force === "autotest") force = null;
    }
    if (t < finEtat) return;
    tete = null;
    if (force) { force = null; }
    if (calme) { changer("nap", 30); return; }
    const [e, d] = VIE[i++ % VIE.length];
    changer(e, d);
  }

  function instantane() {
    avancer();
    const t = Date.now() / 1000, energie = 0.55 + 0.25 * Math.sin((t - debut) / 90);
    return {
      t, version: "démo",
      etat, energie: +energie.toFixed(2), eveil: etat === "nap" ? 0.15 : 0.7,
      batterie: { pourcent: Math.max(20, Math.round(82 - (t - debut) / 60)), volts: 7.9 },
      tombe: false, porte: false, assis: assis || etat === "nap",
      tete: tete || TETES[etat] || [0, 0, 0, 0],
      modes: { calme, garde, discret: false, vacarme: false, timidite: 0, taquineries_coupees: false },
      presents: garde ? [] : ["Raphaël"],
      du_jour: duJour,
      semaine: SEMAINE.map((compte, k) => ({ date: new Date(Date.now() - (6 - k) * 86400000).toISOString().slice(0, 10),
        compte: k === 6 ? duJour : compte })),
      journal: journal.slice(),
      temperatures: { moteurs: 41, cpu: 52 },
      maintenance: {
        diagnostic: {
          ok: diag.ok, le: diag.le, demande: diag.demande,
          detail: diag.demande ? {} : { robotd: "OK", boucle: "OK 50 Hz", bus: "OK", imu: "OK", tof: "OK",
            camera: "OK", tete_lacet: "OK", tete_tangage: "OK", batterie: "OK 82 %" },
        },
        batterie: { autonomie_h: 1.6, sante_pct: 97, a_remplacer: false, cycles: 12, actuelle: batterieDedans,
          a_nommer: batterieANommer, batteries: {
            1: { cycles: 6, autonomie_h: 1.7, sante_pct: null, a_remplacer: false },
            2: { cycles: 4, autonomie_h: 1.6, sante_pct: null, a_remplacer: false },
            3: { cycles: 2, autonomie_h: 1.5, sante_pct: null, a_remplacer: false } } },
        servos: { derives: [], plus_chaud_habituel: "genou droit", jours_mesures: 9 },
        chutes: { sept_jours: 1, activite_risquee: "wander", lieux_a_risque: 0, dernieres: [] },
      },
      caractere: {
        traits: { curiosite: 0.72, sociabilite: 0.64, espieglerie: 0.58, prudence: 0.41 },
        sons: { greet: 3, chirp: 5, coo: 4, inquire: 2, peck: 1, wheee: 2, alarm: 0.2 },
        blagues: 3,
        etres: [{ nom: "Raphaël", familiarite: 0.92, rencontres: 214 }, { nom: "le chat", familiarite: 0.61, rencontres: 87 }],
      },
    };
  }

  function commande(nom) {
    if (JEUX[nom]) { if (!calme) changer(JEUX[nom], nom.startsWith("jouer") ? 25 : 6); force = nom; }
    else if (REGARDS[nom]) { tete = REGARDS[nom]; changer("regard_guide", 6); }
    else if (nom === "assis") { assis = !assis; changer("assis_demande", 3); }
    else if (nom === "stop" || nom === "fin_jeu") { assis = false; changer("chill", 10); }
    else if (nom === "calme_on" || nom === "calme_off") { calme = nom === "calme_on"; finEtat = 0; }
    else if (nom === "garde_on" || nom === "garde_off") {
      garde = nom === "garde_on";
      if (garde) setTimeout(() => alertes.push({ t: Date.now() / 1000, type: "garde", titre: "Alerte de garde",
        texte: "Il a entendu une voix, alors que personne n'est à la maison.", importante: true }), 8000);
    }
    else if (nom.startsWith("batterie_")) { batterieDedans = nom.slice(9); batterieANommer = false; }
    else if (nom === "oublier_carte") carteDepuis = Math.floor((Date.now() / 1000 - debut) * 2);
    else if (nom === "diagnostic") {
      diag = { ok: null, le: diag.le, demande: true, finDemande: Date.now() / 1000 + 5 };
      changer("autotest", 5); force = "autotest";
    }
    return { ok: true, commande: nom };
  }

  // Sa carte imaginaire : un salon (5 x 4 m) et un couloir, parcourus en boucle ; un canape, une chute, ses coins.
  const CHEMIN = [];
  for (let a = 0; a < 2 * Math.PI; a += 0.05) CHEMIN.push([2.2 + 1.6 * Math.cos(a), 1.6 * Math.sin(a) * (1 + 0.3 * Math.cos(2 * a))]);
  for (let x = 0.6; x > -2.4; x -= 0.15) CHEMIN.push([x, 0.1]);             // le couloir, aller...
  for (let x = -2.4; x < 0.6; x += 0.15) CHEMIN.push([x, -0.1]);            // ...et retour
  function carte() {
    const t = Date.now() / 1000, cases = new Map(), k = 0.25;
    const n = Math.floor((t - debut) * 2) % CHEMIN.length;
    const fait = Math.floor((t - debut) * 2) - carteDepuis;               // pas faits depuis le dernier effacement
    CHEMIN.forEach(([x, y], m) => {
      const age = (n - m + CHEMIN.length) % CHEMIN.length;
      if (age > fait) return;
      cases.set(`${Math.floor(x / k)},${Math.floor(y / k)}`, 1 - age / CHEMIN.length * 0.8);
    });
    const [x, y] = CHEMIN[n], [xs, ys] = CHEMIN[(n + 1) % CHEMIN.length];
    const obstacles = [];
    for (let i = 7; i <= 10; i++) obstacles.push([i, 1], [i, 2]);              // le canape, au milieu du salon
    return {
      case: k, canard: { x, y, cap: Math.atan2(ys - y, xs - x) },
      cases: [...cases].map(([c, f]) => [...c.split(",").map(Number), +f.toFixed(2)]),
      ...(fait < CHEMIN.length / 2 ? { obstacles: [], chutes: [], coins: {}, chargeur: null, objets: [] } : {
        obstacles, chutes: [[14, -5]],
        coins: { nap: [3.4, 0.6], chill: [1.2, 1.0], repas: [0.6, -1.4] }, chargeur: [0.3, 0.3], objets: [[2.9, -0.8]] }),
    };
  }

  // Ses lieux imaginaires : la maison, chez les parents, et un gite archive.
  const lieux = {
    actuel: "l1", reseau: "Freebox-Maison", suggestion: null, suivant: 4,
    lieux: {
      l1: { nom: "Maison", reseaux: ["Freebox-Maison", "Freebox-Maison-Etage"], archive: false, auto: true, vu: 3 },
      l2: { nom: "Chez les parents", reseaux: ["Livebox-Parents"], archive: false, auto: true, vu: 2 },
      l3: { nom: "Gîte en Bretagne", reseaux: ["Gite-Wifi"], archive: true, auto: true, vu: 1 },
    },
  };
  const cartes = {};
  function carteDe(lid) {
    if (lid === lieux.actuel) return carte();
    if (cartes[lid]) return cartes[lid];
    if (lid === "l2") {                                 // un grand sejour en L
      const cases = [];
      for (let i = 0; i < 18; i++) cases.push([i, 0, 0.4], [i, 1, 0.3]);
      for (let j = 2; j < 12; j++) cases.push([16, j, 0.35], [17, j, 0.25]);
      return { case: 0.25, canard: null, cases, obstacles: [[8, 3], [9, 3]], chutes: [], coins: { nap: [4.3, 2.6] },
        chargeur: null, objets: [] };
    }
    return {};
  }
  function resumeLieux() {
    return { actuel: lieux.actuel, reseau: lieux.reseau, suggestion: lieux.suggestion,
      lieux: Object.entries(lieux.lieux).sort((a, b) => b[1].vu - a[1].vu).map(([id, l]) => ({ id, ...l, carte: true })) };
  }
  function actionLieu({ action, id, nom }) {
    const l = lieux.lieux[id];
    if (action === "nouveau") { id = "l" + lieux.suivant++; lieux.lieux[id] = { nom, reseaux: [], archive: false, auto: true, vu: 0 }; }
    else if (!l) throw new Error("lieu inconnu");
    if (action === "nouveau" || action === "basculer") {
      cartes[lieux.actuel] = carte();
      lieux.actuel = id; lieux.lieux[id].archive = false; lieux.lieux[id].vu = Date.now();
      carteDepuis = Math.floor((Date.now() / 1000 - debut) * 2); changer(action === "nouveau" ? "curious" : "chill", 6);
    }
    else if ((action === "archiver" || action === "supprimer") && id === lieux.actuel) throw new Error("c'est le lieu actuel");
    else if (action === "archiver") l.archive = true;
    else if (action === "restaurer") l.archive = false;
    else if (action === "supprimer") delete lieux.lieux[id];
    else if (action === "renommer") l.nom = nom;
    else if (action === "lier") {
      for (const autre of Object.values(lieux.lieux)) autre.reseaux = autre.reseaux.filter((r) => r !== lieux.reseau);
      l.reseaux.push(lieux.reseau);
    }
    else if (action === "auto_on" || action === "auto_off") l.auto = action === "auto_on";
    return { ok: true };
  }

  const DESIGN = {
    filaments: [{ nom: "PLA Prusament Orange", couleur: "#f26a1b" }, { nom: "PLA Galaxy Black", couleur: "#2b2a30" },
      { nom: "PETG Blanc", couleur: "#f2f1ec" }],
    schemas: [{ nom: "Noir et orange", couleurs: { dessus_tete: "#2b2a30", coques: "#2b2a30", cuisses: "#2b2a30",
      face: "#f2f1ec", bec: "#f26a1b", pieds: "#f26a1b", dessous_tete: "#f26a1b" } }],
    actif: null,
  };

  function api(chemin, corps) {
    if (chemin === "/api/commande") return commande(corps.commande);
    if (chemin === "/api/lieu") return actionLieu(corps);
    if (chemin === "/api/carte") return carte();
    if (chemin.startsWith("/api/alertes")) {
      const depuis = +new URLSearchParams(chemin.split("?")[1]).get("depuis") || 0;
      return { maintenant: Date.now() / 1000, alertes: alertes.filter((a) => a.t > depuis) };
    }
    if (chemin === "/api/reglages") { if (corps) reglagesDemo = { ...reglagesDemo, ...corps }; return reglagesDemo; }
    if (chemin === "/api/design") {                   // schemas et filaments : dans ce telephone, en demo
      if (corps) { try { localStorage.setItem("microduck-demo-design", JSON.stringify(corps)); } catch (e) { /* prive */ } return { ok: true }; }
      try { return JSON.parse(localStorage.getItem("microduck-demo-design")) || DESIGN; } catch (e) { return DESIGN; }
    }
    if (chemin === "/api/lieux") return resumeLieux();
    if (chemin.startsWith("/api/lieu-carte")) return carteDe(new URLSearchParams(chemin.split("?")[1]).get("id"));
    return instantane();
  }

  // Marketplace en demo, quand le vrai catalogue est vide ou injoignable : deux pieces imaginaires, sans lien.
  function exemplesBoutique() {
    return [
      { id: "ex1", nom: "Coque de tête « Casque »", exemple: true, categorie: "tête", bientot: true, liens: {},
        description: "Exemple : ta pièce apparaîtra ainsi, avec ses photos et ses liens Printables et Cults.",
        impression: { materiau: "PLA", temps: "3 h 20", filament_g: 45, supports: false }, auteur: "RaphaelGrj",
        licence: "CC BY-NC 4.0", photos: ["/microduck/debout-gauche.webp", "/microduck/debout.webp"],
        remplace_nom: "Dessus de la tête" },
      { id: "ex2", nom: "Semelles antidérapantes", exemple: true, categorie: "pieds", bientot: true, liens: {},
        description: "Exemple : semelles en TPU pour le carrelage.", impression: { materiau: "TPU 95A", temps: "1 h" },
        photos: ["/microduck/marche.webp"] },
    ];
  }

  window.MicroduckDemo = { instantane, commande, carte, api, exemplesBoutique };
})();
