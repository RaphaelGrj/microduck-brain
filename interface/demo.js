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
      journal: journal.slice(),
      temperatures: { moteurs: 41, cpu: 52 },
      maintenance: {
        diagnostic: {
          ok: diag.ok, le: diag.le, demande: diag.demande,
          detail: diag.demande ? {} : { robotd: "OK", boucle: "OK 50 Hz", bus: "OK", imu: "OK", tof: "OK",
            camera: "OK", tete_lacet: "OK", tete_tangage: "OK", batterie: "OK 82 %" },
        },
        batterie: { autonomie_h: 1.6, sante_pct: 97, a_remplacer: false, cycles: 12 },
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
    else if (nom === "garde_on" || nom === "garde_off") garde = nom === "garde_on";
    else if (nom === "diagnostic") {
      diag = { ok: null, le: diag.le, demande: true, finDemande: Date.now() / 1000 + 5 };
      changer("autotest", 5); force = "autotest";
    }
    return { ok: true, commande: nom };
  }

  window.MicroduckDemo = { instantane, commande };
})();
