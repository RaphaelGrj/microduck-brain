// Mode demo de l'application : un Microduck imaginaire, pour essayer l'appli sans le robot (appli Android « Essayer en
// demo », ou ?demo dans l'adresse). Tout est fabrique ici, dans le telephone : rien n'est envoye nulle part.
"use strict";

(function () {
  // demo : dans l'APK, avec ?demo, ou sur GitHub Pages (https://raphaelgrj.github.io/microduck-brain/, pour l'iPhone)
  if (location.hostname !== "demo.microduck.local" && !/[?&]demo\b/.test(location.search)
      && !location.hostname.endsWith(".github.io")) return;

  const debut = Date.now() / 1000;
  const VIE = [["chill", 14], ["look", 8], ["wander", 12], ["curious", 6], ["jeu_solitaire", 10], ["chill", 10],
    ["etirement", 5], ["regarde_chat", 8], ["nap", 18], ["bonjour", 5]];
  const JEUX = { jouer_balle: "balle", jouer_cache: "cache_cache", jouer_soleil: "soleil", danse: "danse",
    suis_moi: "suis_moi", je_te_suis: "mene",
    salut: "salut", toupie: "toupie", avance: "pas_guide", gauche: "pas_guide", droite: "pas_guide" };
  const REGARDS = { regard_gauche: [0, 0, 0.6, 0], regard_droite: [0, 0, -0.6, 0], regard_haut: [0, -0.3, 0, 0],
    regard_bas: [0, 0.4, 0, 0], regard_centre: [0, 0, 0, 0] };
  const TETES = { look: [0, 0, 0.5, 0], curious: [0, 0.1, 0, 0.25], regarde_chat: [0, 0.2, -0.45, 0],
    nap: [0.1, 0.5, 0, 0], jeu_solitaire: [0, 0.3, 0, 0] };

  let carteDepuis = -1e6;
  let batterieDedans = "2", batterieANommer = true;
  let choregraphiesDemo = [{ nom: "Coucou", etapes: [{ type: "son", son: "greet" }, { type: "tete", cou: 0, tangage: -0.2, lacet: 0.6, roulis: 0.2, duree: 1 },
    { type: "geste", geste: "oui" }, { type: "son", son: "wheee" }] }];
  const balle = { parties: 7, reussies: 5, tirs: 11, serie: 2, record: 3, derniere: "reussi" };
  const SEMAINE = [{ promenades: 4, siestes: 2, jeux: 1 }, { promenades: 2, siestes: 3, caresses: 3 },
    { promenades: 5, jeux: 3, danses: 1 }, { siestes: 2, caresses: 1 }, { promenades: 6, jeux: 2, accueils: 2 },
    { promenades: 3, siestes: 2, jeux: 4, danses: 2 }, null];
  // alertes imaginaires : une impression finie apres 25 s, puis une alerte de garde si on active le mode garde
  const alertes = [{ t: Date.now() / 1000 - 3600, type: "impression_finie", titre: "Impression finie", texte: "MK4S", importante: false }];
  setTimeout(() => alertes.push({ t: Date.now() / 1000, type: "impression_finie", titre: "Impression finie",
    texte: "Saturn 4 Ultra", importante: false }), 25000);
  let reglagesDemo = { heures_calmes: [23, 7], bonjour: "07:30", bonjour_weekend: "09:30", repas: ["12:30", "19:30"],
    autotest: true, circadien: true,
    routines: [{ heure: "18:30", jours: [0, 1, 2, 3, 4], action: "vient_me_voir" }, { heure: "10:00", jours: [6], action: "danse" }] };                      // « Effacer sa carte » : il repart de zero ici
  let i = 0, finEtat = 0, force = null, tete = null, assis = false, calme = false, garde = false, vacances = false;
  // lots 5 a 8 : messages, photos, parcours, carnet, invites (imaginaires, dans ce telephone)
  const H = Date.now() / 1000;
  const messagesDemo = [{ id: "m1", pour: "Clémence", texte: "Il reste des crêpes dans le frigo !", de: "Raphaël", t: H - 5400, transmis: H - 3000 }];
  const photosDemo = [
    { id: "d3", t: H - 1800, motif: "chat", src: "microduck/debout-gauche.webp" },
    { id: "d2", t: H - 7200, motif: "impression", src: "microduck/debout-tete-basse.webp" },
    { id: "d1", t: H - 86400, motif: "retour", src: "microduck/debout.webp" }];
  let photosActif = true;
  const jeuxDemo = { records: { 3: 38.6, 4: 51.2 }, historique: [{ t: H - 4000, issue: "reussi", duree: 38.6, atteints: 3, total: 3 }] };
  const carnetDemo = [{ id: "c1", type: "impression", texte: "Coque de tête noire, PLA Galaxy Black", date: "2026-10-02", piece: "coque-superieure-origine" },
    { id: "c2", type: "nettoyage", texte: "Semelles dépoussiérées", date: "2026-10-05" }];
  const invitesDemo = [{ code: "mamy-k7p2", nom: "Mamie", jusqua: H + 86400 }];
  // lot 9 : minuteurs, rappels, statistiques (60 jours d'activites, une semaine d'humeur)
  const planningDemo = { minuteurs: [], rappels: [{ id: "r1", texte: "Arroser les plantes", heure: "18:00", pour: "Clémence", quotidien: true, quand: H + 7200 }] };
  const ACT = ["promenades", "siestes", "jeux", "caresses", "danses", "accueils", "folles_courses", "blagues"];
  const statsDemo = { balle: { parties: 23, reussies: 15, tirs: 34, record: 5 },
    jours: Array.from({ length: 45 }, (_, k) => ({ date: new Date(Date.now() - (45 - k) * 86400000).toISOString().slice(0, 10),
      compte: Object.fromEntries(ACT.map((a, i) => [a, Math.max(0, Math.round(3 + 2.5 * Math.sin(k * 0.7 + i) - i * 0.4))])) })),
    humeur: Array.from({ length: 7 * 96 }, (_, k) => { const t = H - (7 * 96 - k) * 900, hr = new Date(t * 1000).getHours();
      const jour = hr >= 8 && hr < 23; return [t, +(0.35 + (jour ? 0.35 : 0) + 0.12 * Math.sin(k / 9)).toFixed(2), +(jour ? 0.55 + 0.25 * Math.sin(k / 5) : 0.12).toFixed(2)]; }) };
  function courbe(n, base, pente, bruit) { return Array.from({ length: n }, (_, k) => Math.round(base + pente * k + bruit * Math.sin(k * 1.7))); }
  const JOURS_USURE = Array.from({ length: 21 }, (_, k) => `2026-${String(259 + k).padStart(3, "0")}`);
  const usureDemo = { servos: { jours: JOURS_USURE, servos: Object.fromEntries(["left_hip_yaw", "left_hip_roll", "left_hip_pitch",
    "left_knee", "left_ankle", "neck_pitch", "head_pitch", "head_yaw", "head_roll", "right_hip_yaw", "right_hip_roll",
    "right_hip_pitch", "right_knee", "right_ankle"].map((n, k) => [n, { courant: courbe(21, 60 + 9 * k, n === "right_knee" ? 3.2 : 0.2, 4),
      ecart: [] }])), chaleur: courbe(21, 44, 0.1, 2), remplaces: {}, plus_chaud: { right_knee: 31 } },
  batteries: { 1: courbe(9, 104, -0.6, 2).map((m, k) => ({ t: H - (9 - k) * 86400, autonomie_h: m / 60 })),
    2: courbe(6, 98, -0.4, 2).map((m, k) => ({ t: H - (6 - k) * 86400, autonomie_h: m / 60 })),
    3: courbe(3, 92, -0.3, 1).map((m, k) => ({ t: H - (3 - k) * 86400, autonomie_h: m / 60 })) } };
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
    if (etat === "balle") {                     // fin d'une partie imaginaire : reussie 2 fois sur 3
      const ok = Math.random() < 0.67;
      Object.assign(balle, { parties: balle.parties + 1, reussies: balle.reussies + (ok ? 1 : 0), tirs: balle.tirs + 1 + (ok ? 0 : 1),
        serie: ok ? balle.serie + 1 : 0, derniere: ok ? "reussi" : "rate" });
      balle.record = Math.max(balle.record, balle.serie);
    }
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
      modes: { calme, garde, vacances, discret: false, vacarme: false, timidite: 0, taquineries_coupees: false },
      presents: garde ? [] : ["Raphaël"],
      du_jour: duJour, balle: { ...balle },
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
        blagues: 3, age_jours: 12, humeur_jour: "joueur",
        etres: [{ nom: "Raphaël", familiarite: 0.92, rencontres: 214 }, { nom: "le chat", familiarite: 0.61, rencontres: 87 }],
      },
    };
  }

  function commande(nom) {
    if (JEUX[nom]) { if (!calme) changer(JEUX[nom], nom.startsWith("jouer") ? 25 : 6); force = nom; }
    else if (REGARDS[nom]) { tete = REGARDS[nom]; changer("regard_guide", 6); }
    else if (nom === "ou_es_tu") changer("ou_es_tu", 4);
    else if (nom === "signal_stop") changer("chill", 10);
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
      ...(fait < CHEMIN.length / 2 ? { obstacles: [], chutes: [], coins: {}, chargeur: null, objets: [], vus: {} } : {
        obstacles, chutes: [[14, -5]],
        coins: { nap: [3.4, 0.6], chill: [1.2, 1.0], repas: [0.6, -1.4] }, chargeur: [0.3, 0.3], objets: [[2.9, -0.8]],
        vus: { chat: { t: Math.round(t - 900), x: 3.0, y: -1.1 }, balle: { t: Math.round(t - 240), x: 1.6, y: 1.3 } } }),
    };
  }

  // Ses lieux imaginaires : la maison, chez les parents, et un gite archive.
  const lieux = {
    actuel: "l1", reseau: "Freebox-Maison", suggestion: null, suivant: 4,
    lieux: {
      l1: { nom: "Maison", reseaux: ["Freebox-Maison", "Freebox-Maison-Etage"], archive: false, auto: true, vu: 3,
        plan: { nom: "Maison (exemple)", source: "scene", date: 1791590400, taille_m: [8.32, 6.32], objets: 3, chargeur: true } },
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
  // Plans definitifs (scan Quest) : celui de la maison est l'appartement du simulateur ; un plan sauvegarde s'importe
  // tel quel ; un scan brut du Quest, lui, ne se convertit que sur le canard.
  // (le plan de l'appartement du simulateur, genere par plan.depuis_mjcf - incorpore : la demo ne charge rien)
  const PLAN_MAISON = {"format":"microduck-plan-1","nom":"dock_s2","source":"scene","date":1791590400,"resolution":0.02,"origine":[-4.16,-3.16],"largeur":416,"hauteur":316,"rle":[2,2088,1,400,2,16,1,400,2,16,1,400,2,13,1,406,2,10,1,406,2,10,1,406,2,10,1,6,0,47,1,50,0,47,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,47,1,50,0,47,1,6,0,69,1,6,0,33,1,8,0,128,1,6,2,10,1,6,0,13,1,2,0,32,1,50,0,47,1,6,0,69,1,6,0,32,1,10,0,127,1,6,2,10,1,6,0,13,1,2,0,32,1,50,0,47,1,6,0,69,1,6,0,31,1,12,0,126,1,6,2,10,1,6,0,13,1,2,0,32,1,50,0,47,1,23,0,52,1,6,0,30,1,14,0,95,1,36,2,10,1,6,0,13,1,2,0,32,1,50,0,47,1,23,0,52,1,6,0,30,1,14,0,95,1,36,2,10,1,6,0,13,1,2,0,32,1,50,0,47,1,23,0,52,1,6,0,30,1,14,0,95,1,36,2,10,1,15,0,4,1,2,0,32,1,50,0,38,1,4,0,5,1,23,0,52,1,6,0,30,1,14,0,95,1,36,2,10,1,17,0,2,1,2,0,32,1,50,0,36,1,8,0,3,1,23,0,52,1,6,0,30,1,14,0,95,1,36,2,10,1,17,0,2,1,2,0,32,1,50,0,36,1,8,0,3,1,23,0,52,1,6,0,30,1,14,0,95,1,36,2,10,1,17,0,2,1,2,0,117,1,10,0,2,1,23,0,52,1,6,0,30,1,14,0,95,1,36,2,10,1,17,0,2,1,2,0,117,1,10,0,2,1,6,0,69,1,6,0,30,1,14,0,95,1,36,2,10,1,17,0,2,1,2,0,117,1,10,0,2,1,6,0,69,1,6,0,31,1,12,0,96,1,36,2,10,1,17,0,2,1,2,0,117,1,10,0,2,1,6,0,69,1,6,0,32,1,10,0,97,1,36,2,10,1,17,0,2,1,2,0,118,1,8,0,3,1,6,0,69,1,6,0,33,1,8,0,98,1,36,2,10,1,17,0,122,1,8,0,3,1,6,0,69,1,6,0,139,1,36,2,10,1,17,0,124,1,4,0,5,1,6,0,69,1,6,0,139,1,36,2,10,1,17,0,133,1,6,0,69,1,6,0,139,1,36,2,10,1,17,0,133,1,6,0,69,1,6,0,139,1,36,2,10,1,17,0,133,1,6,0,69,1,6,0,139,1,36,2,10,1,17,0,133,1,6,0,69,1,6,0,139,1,36,2,10,1,17,0,133,1,6,0,69,1,6,0,139,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,17,0,133,1,6,0,214,1,36,2,10,1,15,0,135,1,6,0,214,1,36,2,10,1,6,0,144,1,6,0,214,1,36,2,10,1,6,0,144,1,6,0,214,1,36,2,10,1,6,0,144,1,6,0,214,1,36,2,10,1,6,0,15,1,9,0,120,1,6,0,214,1,36,2,10,1,6,0,13,1,12,0,119,1,6,0,214,1,36,2,10,1,6,0,12,1,15,0,117,1,6,0,214,1,36,2,10,1,6,0,11,1,16,0,117,1,6,0,214,1,36,2,10,1,6,0,11,1,17,0,116,1,6,0,214,1,36,2,10,1,6,0,10,1,19,0,115,1,6,0,214,1,36,2,10,1,6,0,10,1,19,0,115,1,6,0,214,1,36,2,10,1,6,0,10,1,19,0,115,1,6,0,214,1,36,2,10,1,6,0,10,1,19,0,115,1,6,0,214,1,36,2,10,1,6,0,9,1,20,0,115,1,6,0,214,1,36,2,10,1,6,0,10,1,19,0,115,1,6,0,214,1,36,2,10,1,6,0,10,1,19,0,115,1,6,0,214,1,36,2,10,1,6,0,10,1,19,0,115,1,6,0,214,1,36,2,10,1,6,0,10,1,19,0,115,1,6,0,214,1,36,2,10,1,6,0,11,1,17,0,116,1,6,0,214,1,36,2,10,1,6,0,11,1,16,0,117,1,6,0,214,1,36,2,10,1,6,0,12,1,15,0,117,1,6,0,214,1,36,2,10,1,6,0,13,1,12,0,339,1,36,2,10,1,6,0,15,1,9,0,340,1,36,2,10,1,6,0,19,1,1,0,344,1,36,2,10,1,6,0,364,1,36,2,10,1,6,0,364,1,36,2,10,1,6,0,219,1,6,0,139,1,36,2,10,1,6,0,219,1,6,0,139,1,36,2,10,1,6,0,219,1,6,0,139,1,36,2,10,1,6,0,219,1,6,0,5,1,20,0,114,1,36,2,10,1,6,0,219,1,6,0,5,1,20,0,114,1,36,2,10,1,6,0,219,1,6,0,5,1,20,0,114,1,36,2,10,1,6,0,219,1,6,0,5,1,20,0,114,1,36,2,10,1,6,0,219,1,6,0,5,1,20,0,144,1,6,2,10,1,6,0,219,1,6,0,5,1,20,0,144,1,6,2,10,1,6,0,219,1,6,0,5,1,20,0,144,1,6,2,10,1,24,0,201,1,6,0,5,1,20,0,144,1,6,2,10,1,24,0,201,1,6,0,5,1,20,0,144,1,6,2,10,1,24,0,201,1,6,0,5,1,20,0,144,1,6,2,10,1,24,0,201,1,6,0,5,1,20,0,144,1,6,2,10,1,24,0,201,1,6,0,5,1,20,0,144,1,6,2,10,1,24,0,159,2,20,0,22,1,6,0,5,1,20,0,144,1,6,2,10,1,24,0,159,2,20,0,22,1,6,0,5,1,20,0,144,1,6,2,10,1,24,0,159,2,20,0,22,1,6,0,5,1,20,0,144,1,6,2,10,1,24,0,159,2,20,0,22,1,6,0,5,1,20,0,119,1,15,0,10,1,6,2,10,1,24,0,159,2,20,0,22,1,6,0,5,1,20,0,119,1,15,0,10,1,6,2,10,1,24,0,159,2,20,0,22,1,6,0,5,1,20,0,119,1,15,0,10,1,6,2,10,1,24,0,159,2,20,0,22,1,6,0,5,1,20,0,119,1,15,0,10,1,6,2,10,1,24,0,159,2,20,0,22,1,6,0,5,1,20,0,119,1,15,0,10,1,6,2,10,1,24,0,159,2,20,0,22,1,6,0,5,1,20,0,119,1,15,0,10,1,6,2,10,1,24,0,159,2,20,0,22,1,6,0,5,1,20,0,119,1,15,0,10,1,6,2,10,1,24,0,24,1,30,0,105,2,20,0,22,1,6,0,5,1,20,0,119,1,15,0,10,1,6,2,10,1,24,0,24,1,30,0,105,2,20,0,22,1,6,0,5,1,20,0,119,1,15,0,10,1,6,2,10,1,24,0,24,1,30,0,105,2,20,0,22,1,6,0,5,1,20,0,144,1,6,2,10,1,24,0,24,1,30,0,105,2,20,0,22,1,6,0,169,1,6,2,10,1,24,0,24,1,30,0,105,2,20,0,22,1,6,0,169,1,6,2,10,1,24,0,24,1,30,0,105,2,20,0,22,1,6,0,169,1,6,2,10,1,24,0,24,1,30,0,105,2,20,0,22,1,6,0,169,1,6,2,10,1,24,0,24,1,30,0,105,2,20,0,22,1,181,2,10,1,24,0,24,1,30,0,105,2,20,0,22,1,181,2,10,1,24,0,24,1,30,0,105,2,20,0,22,1,181,2,10,1,24,0,24,1,30,0,72,1,6,0,27,2,20,0,22,1,181,2,10,1,24,0,24,1,30,0,72,1,6,0,27,2,20,0,22,1,181,2,10,1,24,0,24,1,30,0,72,1,6,0,27,2,20,0,22,1,181,2,10,1,24,0,24,1,30,0,72,1,6,0,27,2,20,0,22,1,6,0,169,1,6,2,10,1,24,0,24,1,30,0,72,1,6,0,27,2,20,0,22,1,6,0,169,1,6,2,10,1,24,0,24,1,30,0,72,1,6,0,27,2,20,0,22,1,6,0,169,1,6,2,10,1,24,0,24,1,30,0,72,1,6,0,27,2,20,0,22,1,6,0,30,1,4,0,135,1,6,2,10,1,24,0,24,1,30,0,72,1,6,0,27,2,20,0,22,1,6,0,28,1,8,0,133,1,6,2,10,1,24,0,24,1,30,0,72,1,6,0,27,2,20,0,22,1,6,0,28,1,8,0,133,1,6,2,10,1,24,0,24,1,30,0,72,1,6,0,27,2,20,0,22,1,6,0,27,1,10,0,132,1,6,2,10,1,24,0,126,1,6,0,27,2,20,0,22,1,6,0,27,1,10,0,132,1,6,2,10,1,24,0,126,1,6,0,27,2,20,0,22,1,6,0,27,1,10,0,132,1,6,2,10,1,24,0,126,1,6,0,27,2,20,0,22,1,6,0,27,1,10,0,132,1,6,2,10,1,24,0,126,1,6,0,27,2,20,0,22,1,6,0,28,1,8,0,133,1,6,2,10,1,24,0,126,1,6,0,27,2,20,0,22,1,6,0,28,1,8,0,133,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,19,1,1,0,10,1,4,0,135,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,17,1,5,0,147,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,16,1,7,0,146,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,15,1,9,0,145,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,15,1,9,0,145,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,15,1,9,0,145,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,15,1,9,0,145,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,16,1,7,0,146,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,17,1,5,0,147,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,19,1,1,0,149,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,169,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,169,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,169,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,169,1,6,2,10,1,24,0,126,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,141,1,2,0,24,1,8,2,10,1,6,0,144,1,6,0,69,1,6,0,141,1,2,0,24,1,8,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,6,1,2,0,136,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,6,1,2,0,136,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,244,1,6,2,10,1,6,0,144,1,6,0,80,1,18,0,101,1,6,0,39,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,80,1,18,0,99,1,10,0,37,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,80,1,18,0,98,1,12,0,36,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,80,1,18,0,97,1,14,0,35,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,80,1,18,0,96,1,16,0,34,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,80,1,18,0,96,1,16,0,34,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,1,1,6,0,73,1,18,0,95,1,18,0,33,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,1,1,6,0,73,1,18,0,95,1,18,0,33,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,1,1,6,0,73,1,18,0,95,1,18,0,33,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,1,1,6,0,73,1,18,0,95,1,18,0,33,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,1,1,6,0,73,1,18,0,95,1,18,0,33,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,1,1,6,0,73,1,18,0,95,1,18,0,33,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,80,1,18,0,96,1,16,0,34,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,80,1,18,0,96,1,16,0,34,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,80,1,18,0,97,1,14,0,35,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,80,1,18,0,98,1,12,0,36,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,80,1,18,0,99,1,10,0,37,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,80,1,18,0,101,1,6,0,39,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,244,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,244,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,244,1,6,2,10,1,6,0,82,1,20,0,42,1,6,0,244,1,6,2,10,1,6,0,144,1,6,0,244,1,6,2,10,1,6,0,144,1,6,0,244,1,6,2,10,1,6,0,144,1,6,0,244,1,6,2,10,1,6,0,144,1,6,0,244,1,6,2,10,1,6,0,144,1,6,0,216,1,2,0,24,1,8,2,10,1,6,0,144,1,6,0,216,1,2,0,24,1,8,2,10,1,6,0,144,1,6,0,244,1,6,2,10,1,6,0,144,1,6,0,244,1,6,2,10,1,6,0,144,1,6,0,244,1,6,2,10,1,53,0,40,1,63,0,244,1,6,2,10,1,53,0,40,1,63,0,244,1,6,2,10,1,53,0,40,1,63,0,244,1,6,2,10,1,53,0,40,1,63,0,244,1,6,2,10,1,53,0,40,1,63,0,244,1,6,2,10,1,53,0,40,1,63,0,244,1,6,2,10,1,6,0,144,1,6,0,244,1,6,2,10,1,6,0,144,1,6,0,244,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,24,0,51,1,6,0,169,1,6,2,10,1,6,0,144,1,24,0,51,1,6,0,2,1,40,0,127,1,6,2,10,1,6,0,144,1,24,0,51,1,6,0,2,1,40,0,127,1,6,2,10,1,6,0,144,1,24,0,51,1,6,0,2,1,40,0,127,1,6,2,10,1,6,0,144,1,24,0,51,1,6,0,2,1,40,0,127,1,6,2,10,1,6,0,144,1,24,0,51,1,6,0,2,1,40,0,127,1,6,2,10,1,6,0,59,1,6,0,44,1,6,0,29,1,6,0,69,1,6,0,2,1,40,0,127,1,6,2,10,1,6,0,58,1,8,0,42,1,8,0,28,1,6,0,69,1,6,0,2,1,40,0,127,1,6,2,10,1,6,0,57,1,10,0,40,1,10,0,27,1,6,0,69,1,6,0,2,1,40,0,127,1,6,2,10,1,6,0,57,1,10,0,40,1,10,0,27,1,6,0,69,1,6,0,2,1,40,0,127,1,6,2,10,1,6,0,57,1,10,0,40,1,10,0,27,1,6,0,69,1,181,2,10,1,6,0,57,1,10,0,40,1,10,0,27,1,6,0,69,1,181,2,10,1,6,0,57,1,10,0,40,1,10,0,27,1,6,0,69,1,181,2,10,1,6,0,58,1,8,0,42,1,8,0,28,1,6,0,69,1,181,2,10,1,6,0,59,1,6,0,44,1,6,0,29,1,6,0,69,1,181,2,10,1,6,0,144,1,6,0,69,1,181,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,144,1,6,0,69,1,6,0,169,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,59,1,45,0,65,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,59,1,45,0,65,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,69,1,6,0,54,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,129,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,129,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,129,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,129,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,129,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,129,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,129,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,129,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,129,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,37,1,6,0,129,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,172,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,172,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,172,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,172,1,55,0,60,1,6,2,10,1,6,0,67,1,40,0,172,1,55,0,60,1,6,2,10,1,6,0,267,1,80,0,47,1,6,2,10,1,6,0,267,1,80,0,47,1,6,2,10,1,6,0,267,1,80,0,47,1,6,2,10,1,6,0,267,1,80,0,47,1,6,2,10,1,6,0,267,1,80,0,47,1,6,2,10,1,6,0,267,1,80,0,27,1,26,2,10,1,6,0,267,1,80,0,27,1,26,2,10,1,6,0,267,1,80,0,27,1,26,2,10,1,6,0,267,1,80,0,27,1,26,2,10,1,6,0,267,1,80,0,27,1,26,2,10,1,6,0,267,1,80,0,27,1,26,2,10,1,6,0,267,1,80,0,27,1,26,2,10,1,6,0,267,1,15,0,50,1,15,0,27,1,26,2,10,1,6,0,267,1,15,0,50,1,15,0,27,1,26,2,10,1,6,0,267,1,15,0,50,1,15,0,27,1,26,2,10,1,6,0,374,1,26,2,10,1,6,0,374,1,26,2,10,1,6,0,374,1,26,2,10,1,6,0,374,1,26,2,10,1,6,0,374,1,26,2,10,1,6,0,374,1,26,2,10,1,6,0,374,1,26,2,10,1,6,0,374,1,26,2,10,1,6,0,374,1,26,2,10,1,6,0,374,1,26,2,10,1,6,0,219,1,6,0,149,1,26,2,10,1,6,0,219,1,6,0,149,1,26,2,10,1,6,0,219,1,6,0,149,1,26,2,10,1,6,0,219,1,6,0,149,1,26,2,10,1,6,0,219,1,6,0,149,1,26,2,10,1,6,0,219,1,6,0,149,1,26,2,10,1,6,0,219,1,6,0,149,1,26,2,10,1,6,0,219,1,6,0,149,1,26,2,10,1,6,0,219,1,6,0,149,1,26,2,10,1,6,0,219,1,6,0,149,1,26,2,10,1,6,0,2,1,25,0,117,1,6,0,69,1,6,0,149,1,26,2,10,1,6,0,2,1,25,0,117,1,6,0,69,1,6,0,149,1,26,2,10,1,6,0,2,1,25,0,117,1,6,0,69,1,6,0,149,1,26,2,10,1,6,0,2,1,25,0,95,1,5,0,17,1,6,0,69,1,6,0,31,1,7,0,111,1,26,2,10,1,6,0,2,1,25,0,94,1,7,0,16,1,6,0,69,1,6,0,29,1,11,0,109,1,26,2,10,1,6,0,2,1,25,0,93,1,9,0,15,1,6,0,69,1,6,0,28,1,13,0,108,1,26,2,10,1,6,0,2,1,25,0,93,1,9,0,15,1,6,0,69,1,6,0,27,1,15,0,107,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,26,1,17,0,106,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,26,1,17,0,106,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,26,1,17,0,106,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,26,1,17,0,106,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,26,1,17,0,106,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,26,1,17,0,106,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,27,1,15,0,107,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,28,1,13,0,108,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,29,1,11,0,109,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,31,1,7,0,111,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,149,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,6,1,2,0,61,1,6,0,12,1,30,0,107,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,5,1,4,0,60,1,6,0,12,1,30,0,107,1,26,2,10,1,6,0,2,1,135,0,7,1,6,0,5,1,4,0,60,1,6,0,12,1,30,0,127,1,6,2,10,1,6,0,2,1,135,0,7,1,6,0,6,1,2,0,61,1,6,0,12,1,30,0,127,1,6,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,12,1,30,0,127,1,6,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,12,1,30,0,127,1,6,2,10,1,6,0,2,1,135,0,7,1,6,0,69,1,6,0,12,1,30,0,127,1,6,2,10,1,6,0,7,1,130,0,7,1,6,0,69,1,6,0,12,1,30,0,127,1,6,2,10,1,6,0,7,1,130,0,7,1,6,0,69,1,6,0,12,1,30,0,127,1,6,2,10,1,406,2,10,1,406,2,10,1,406,2,13,1,400,2,16,1,400,2,16,1,400,2,2088],"objets":[{"type":"couch","nom":"canapé","centre":[-3.55,-0.15],"contour":[],"hauteur":0.38,"dessous_libre":false},{"type":"bed","nom":"lit","centre":[1.6,2.45],"contour":[],"hauteur":0.2,"dessous_libre":false},{"type":"table","nom":"table","centre":[-2.6,0.0],"contour":[],"hauteur":0.4,"dessous_libre":true}],"pieces":[],"reperes":{"chargeur":[-3.8,-2.78,0.0],"marqueurs":{"0":[-2.0,-3.0,1.5708],"1":[1.0,3.0,-1.5708]}}};
  const plans = {};
  function planDe(lid) {
    if (plans[lid]) return plans[lid];
    if (!(lieux.lieux[lid] || {}).plan) throw new Error("pas de plan");
    return PLAN_MAISON;
  }
  function importerPlanDemo({ id, contenu }) {
    const l = lieux.lieux[id];
    if (!l) throw new Error("lieu inconnu");
    if (!contenu || contenu.format !== "microduck-plan-1") {
      throw new Error(contenu && contenu.format === "microduck-quest-1" ? "en démo, le scan se convertit sur le vrai canard" : "ce n'est pas un plan");
    }
    plans[id] = contenu;
    l.plan = { nom: contenu.nom, source: contenu.source, date: contenu.date,
      taille_m: [+(contenu.largeur * contenu.resolution).toFixed(2), +(contenu.hauteur * contenu.resolution).toFixed(2)],
      objets: (contenu.objets || []).length, chargeur: !!(contenu.reperes || {}).chargeur };
    return { ok: true, plan: l.plan, avertissements: [] };
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
    actif: "Noir et orange",
  };

  const configDemo = {
    cerveau: { nom: "Microduck", garde: false }, appli: { code: "••••••", code_enfant: null },
    home_assistant: { actif: true, url: "http://homeassistant.local:8123", token: "••••••" },
    habitant: [{ nom: "Raphaël", entite: "person.raphael" }],
    imprimante_directe: [{ nom: "MK4S", type: "prusalink", adresse: "192.168.1.30", cle_api: "••••••" },
      { nom: "Saturn 4 Ultra", type: "sdcp", adresse: "192.168.1.31", cle_api: null }],
    appareil: [{ nom: "Sonnette", type: "sonnette", entite: "binary_sensor.sonnette" }],
  };

  function api(chemin, corps) {
    if (chemin === "/api/commande") return commande(corps.commande);
    if (chemin === "/api/lieu") return actionLieu(corps);
    if (chemin === "/api/plan") return importerPlanDemo(corps);
    if (chemin === "/api/plan-supprimer") { const l = lieux.lieux[corps.id]; if (l) { delete l.plan; delete plans[corps.id]; } return { ok: true }; }
    if (chemin.startsWith("/api/plan?")) return planDe(new URLSearchParams(chemin.split("?")[1]).get("id"));
    if (chemin === "/api/carte") return carte();
    if (chemin.startsWith("/api/alertes")) {
      const depuis = +new URLSearchParams(chemin.split("?")[1]).get("depuis") || 0;
      return { maintenant: Date.now() / 1000, alertes: alertes.filter((a) => a.t > depuis) };
    }
    if (chemin === "/api/role") return { role: "parent" };
    if (chemin === "/api/choregraphies") {
      if (corps && corps.jouer) { changer("choregraphie", 6); return { ok: true }; }
      if (corps && corps.liste) { choregraphiesDemo = corps.liste.filter((c) => c.nom && c.etapes.length); return { ok: true, liste: choregraphiesDemo }; }
      return { liste: choregraphiesDemo, gestes: [], bornes: { cou: [-0.3, 0.4], tangage: [-0.5, 0.6], lacet: [-0.9, 0.9], roulis: [-0.4, 0.4] } };
    }
    if (chemin === "/api/comportements") return { ok: true, politiques: ["walk", "stand", "sit"], skills: ["roulade", "kick_left", "ground_pick", "sit_toggle"] };
    if (chemin === "/api/comportement") return corps.action === "chercher"
      ? { ok: true, resultat: [{ repo: "pollen-robotics/microduck-salto" }, { repo: "communaute/microduck-moonwalk" }] } : { ok: true };
    if (chemin === "/api/regard") { tete = [0, corps.tangage, corps.lacet, 0]; changer("regard_guide", 6); return { ok: true }; }
    if (chemin === "/api/imprimantes") {
      const t = (Date.now() / 1000 - debut) / 600;
      return [{ nom: "MK4S", type: "prusalink", etat: "en_cours", joignable: true, progression: Math.min(99, 64 + t * 10), reste_s: 2700 },
        { nom: "Saturn 4 Ultra", type: "sdcp", etat: "finie", joignable: true, progression: 100 }];
    }
    if (chemin === "/api/configuration") {
      if (corps) configDemo[corps.section] = corps.valeur;
      return corps ? { ok: true, redemarrer: corps.section !== "appli", configuration: configDemo } : configDemo;
    }
    if (chemin === "/api/tester-ha") return { ok: false, message: "démo : pas de Home Assistant ici" };
    if (chemin === "/api/tester-imprimante") return { ok: true, etat: "en_cours", progression: 64 };
    if (chemin === "/api/redemarrer" || chemin === "/api/mise-a-jour") return { ok: true };
    if (chemin === "/api/rapport") return { format: "microduck-rapport", version: 1, cerveau: "démo", etat, batterie: { pourcent: 82 } };
    if (chemin === "/api/sauvegarde") return { format: "microduck-sauvegarde", version: 1, date: Date.now() / 1000,
      cerveau: "démo", fichiers: { "design.json": DESIGN, "reglages.json": reglagesDemo } };
    if (chemin === "/api/restauration") return { ok: true, redemarrer: true };
    if (chemin === "/api/presence") return { ok: true };
    if (chemin === "/api/messages") return { liste: messagesDemo.slice().reverse() };
    if (chemin === "/api/message") {
      if (corps.action === "annuler") { messagesDemo.splice(messagesDemo.findIndex((m) => m.id === corps.id), 1); return { ok: true }; }
      const m = { id: "m" + Date.now(), pour: corps.pour, texte: corps.texte, de: corps.de || null, t: Date.now() / 1000, transmis: null };
      messagesDemo.push(m);
      setTimeout(() => { m.transmis = Date.now() / 1000; alertes.push({ t: Date.now() / 1000, type: "message", titre: "Message transmis",
        texte: `${m.pour} est là : il le lui a signalé.`, importante: false }); changer("messager", 4); }, 12000);
      return { ok: true, message: m };
    }
    if (chemin === "/api/photos") return { actif: photosActif, liste: photosDemo };
    if (chemin === "/api/photo") {
      if (corps.action === "tout_supprimer") photosDemo.length = 0;
      else if (corps.action === "supprimer") photosDemo.splice(photosDemo.findIndex((p) => p.id === corps.id), 1);
      else {
        if (corps.pose) { changer("pose_photo", 4); tete = { fier: [0, -0.25, 0, 0], curieux: [0, 0.1, 0, 0.3], content: [0, -0.1, 0.2, 0.1] }[corps.pose] || [0, 0, 0, 0]; }
        const p = { id: "d" + Date.now(), t: Date.now() / 1000, motif: corps.pose ? "pose" : "photo",
          src: corps.pose === "curieux" ? "microduck/debout-penche.webp" : corps.pose ? "microduck/debout-tete-haute.webp" : "microduck/debout.webp" };
        photosDemo.unshift(p);
        return { ok: true, ...p };
      }
      return { ok: true };
    }
    if (chemin === "/api/parcours") {
      if (!corps) return jeuxDemo;
      const n = corps.points.length;
      changer(corps.genre === "balle" ? "parcours" : "parcours", corps.genre === "balle" ? 6 : 6 + 3 * n);
      if (corps.genre === "balle") setTimeout(() => changer("balle", 20), 6000);
      else setTimeout(() => {
        const d = +(8 + 9 * n + Math.random() * 4).toFixed(1), rec = !jeuxDemo.records[n] || d < jeuxDemo.records[n];
        if (rec) jeuxDemo.records[n] = d;
        jeuxDemo.historique.push({ t: Date.now() / 1000, issue: "reussi", duree: d, atteints: n, total: n });
        alertes.push({ t: Date.now() / 1000, type: "parcours", titre: "Parcours réussi", texte: `${String(d).replace(".", ",")} s` + (rec ? " : record !" : ""), importante: false });
      }, (6 + 3 * n) * 1000);
      return { ok: true };
    }
    if (chemin === "/api/usure") return usureDemo;
    if (chemin === "/api/stats") return statsDemo;
    if (chemin === "/api/planning") return { maintenant: Date.now() / 1000, ...planningDemo };
    if (chemin === "/api/minuteur" || chemin === "/api/rappel") {
      const liste = chemin === "/api/minuteur" ? planningDemo.minuteurs : planningDemo.rappels;
      if (corps.action === "annuler") { liste.splice(liste.findIndex((x) => x.id === corps.id), 1); return { ok: true }; }
      if (chemin === "/api/minuteur") {
        const m = { id: "m" + Date.now(), nom: corps.nom || "Minuteur", duree: corps.secondes, fin: Date.now() / 1000 + corps.secondes };
        liste.push(m);
        setTimeout(() => { liste.splice(liste.indexOf(m), 1); changer("signal", 8);
          alertes.push({ t: Date.now() / 1000, type: "minuteur", titre: `Minuteur : ${m.nom}`, texte: "C'est l'heure !", importante: true }); },
          Math.min(corps.secondes, 20) * 1000);           // (en demo : 20 s au plus, pour voir la fin)
        return { ok: true, element: m };
      }
      const r = { id: "r" + Date.now(), texte: corps.texte, heure: corps.heure, pour: corps.pour || null, quotidien: !!corps.quotidien, quand: Date.now() / 1000 + 3600 };
      liste.push(r);
      return { ok: true, element: r };
    }
    if (chemin === "/api/carnet") {
      if (!corps) return { liste: carnetDemo, types: [] };
      if (corps.action === "supprimer") { carnetDemo.splice(carnetDemo.findIndex((e) => e.id === corps.id), 1); return { ok: true }; }
      const e = { ...corps, id: "c" + Date.now() }; delete e.action;
      if (e.type === "servo") usureDemo.servos.remplaces[e.servo] = `2026-${String(new Date().getDate() + 273).padStart(3, "0")}`;
      carnetDemo.push(e); carnetDemo.sort((a, b) => a.date.localeCompare(b.date));
      return { ok: true, entree: e };
    }
    if (chemin === "/api/invites") {
      if (!corps) return { liste: invitesDemo };
      if (corps.action === "revoquer") { invitesDemo.splice(invitesDemo.findIndex((i) => i.code === corps.code), 1); return { ok: true }; }
      const c = { code: Math.random().toString(36).slice(2, 6) + "-" + Math.random().toString(36).slice(2, 6), nom: corps.nom || "Invité",
        jusqua: Date.now() / 1000 + corps.heures * 3600 };
      invitesDemo.push(c);
      return { ok: true, ...c };
    }
    if (chemin === "/api/reglages") {
      if (corps && "vacances" in corps) { vacances = !!corps.vacances; calme = vacances; garde = vacances; finEtat = 0; }
      if (corps && "photos" in corps) photosActif = !!corps.photos;
      if (corps) reglagesDemo = { ...reglagesDemo, ...corps };
      return reglagesDemo;
    }
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
        licence: "CC BY-NC 4.0", photos: ["microduck/debout-gauche.webp", "microduck/debout.webp"],
        remplace_nom: "Dessus de la tête" },
      { id: "ex2", nom: "Semelles antidérapantes", exemple: true, categorie: "pieds", bientot: true, liens: {},
        description: "Exemple : semelles en TPU pour le carrelage.", impression: { materiau: "TPU 95A", temps: "1 h" },
        photos: ["microduck/marche.webp"] },
    ];
  }

  window.MicroduckDemo = { instantane, commande, carte, api, exemplesBoutique };
})();
