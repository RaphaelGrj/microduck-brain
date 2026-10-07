// English version of the Microduck app. The interface is written in French; this file translates what is displayed
// (text, placeholders, labels, dialogs), including content added later (MutationObserver). Language: Settings →
// This phone, or the phone's language by default. Strings not found here stay in French.
"use strict";

(function () {
  let choix = null;
  try { choix = localStorage.getItem("microduck-langue"); } catch (e) { /* private browsing */ }
  const langue = choix || ((navigator.language || "fr").toLowerCase().startsWith("fr") ? "fr" : "en");
  window.MicroduckLangue = langue;
  if (langue === "fr") return;
  document.documentElement.lang = "en";

  const EN = {
    // --- navigation, headers ---
    "Accueil": "Home", "Jouer": "Play", "Commander": "Control", "Santé": "Health", "Caractère": "Character",
    "Réglages": "Settings", "Journal": "Log", "Sections": "Sections", "Retour": "Back", "Debout": "Standing",
    "Assis": "Sitting", "Connexion…": "Connecting…", "Liaison avec Microduck": "Link with Microduck",
    "Design : ses couleurs": "Design: his colours", "Marketplace : pièces à imprimer": "Marketplace: parts to print",
    // --- pairing, installation ---
    "Entre le code d'appairage de ton Microduck (choisi à son installation).": "Enter your Microduck's pairing code (chosen when you set it up).",
    "Code": "Code", "Code d'appairage": "Pairing code", "Se connecter": "Connect", "Bienvenue !": "Welcome!",
    "Ton Microduck est neuf. Trois choses et c'est parti.": "Your Microduck is brand new. Three things and you're off.",
    "Son nom": "His name", "Qui vit avec lui ?": "Who lives with him?", "(prénoms, séparés par des virgules)": "(first names, separated by commas)",
    "Code de l'appli": "App code", "(6 caractères au moins : la clé de ton canard)": "(at least 6 characters: your duck's key)",
    "Encore une fois": "Once more", "C'est parti": "Let's go",
    "Home Assistant, imprimantes, appareils : plus tard, dans Réglages → Connexions. Tout est facultatif.": "Home Assistant, printers, devices: later, in Settings → Connections. All optional.",
    // --- home ---
    "En ce moment": "Right now", "Énergie": "Energy", "Éveil": "Alertness", "Batterie": "Battery", "À la maison": "At home",
    "Personne": "Nobody", "Aujourd'hui": "Today", "Rien encore aujourd'hui": "Nothing yet today", "Sa carte": "His map",
    "Carte des endroits où il est passé depuis son démarrage": "Map of the places he has been since he started",
    "Il n'a pas encore exploré depuis son démarrage.": "He hasn't explored since he started.",
    "passé par là": "been here", "obstacle": "obstacle", "il y est tombé": "fell here", "Alertes": "Alerts",
    "Impressions": "Prints", "📍 Où es-tu ?": "📍 Where are you?", "Écoute bien…": "Listen…",
    "Il est tombé": "He fell", "Il est tombé…": "He fell…", "Dans les bras": "In someone's arms",
    "Mode calme": "Quiet mode", "Garde": "Watch", "Quelqu'un téléphone": "Someone is on the phone", "Trop de bruit": "Too noisy",
    "Visiteur": "Visitor", "Tombé": "Fallen", "Diagnostic en échec": "Diagnostic failed", "Batterie à remplacer": "Battery to replace",
    "promenade": "walk", "promenades": "walks", "sieste": "nap", "siestes": "naps", "jeu": "game", "jeux": "games",
    "danse": "dance", "danses": "dances", "caresse": "pat", "caresses": "pats", "accueil": "welcome", "accueils": "welcomes",
    "folle course": "zoomies", "folles courses": "zoomies", "blague": "prank", "blagues": "pranks",
    "Impression finie": "Print finished", "Impression ratée": "Print failed", "Alerte de garde": "Watch alert",
    "Alarme incendie !": "Fire alarm!", "Batterie faible": "Low battery", "Batterie changée": "Battery changed",
    "Machine terminée": "Machine finished", "Machine en panne": "Machine failure", "Diagnostic : problème détecté": "Diagnostic: problem found",
    "en cours": "printing", "terminée": "finished", "en échec": "failed", "au repos": "idle", "injoignable": "unreachable",
    // --- play ---
    "Jeu de balle": "Ball game", "Parties": "Games", "Réussies": "Successful", "Tirs": "Kicks", "Meilleure série": "Best streak",
    "Défi à plusieurs": "Multiplayer challenge",
    "Chacun son tour pose la balle devant lui et lance : un tir réussi rapporte un point.": "Take turns putting the ball in front of him and start: a good kick scores a point.",
    "Prénom du joueur": "Player's name", "Ajouter": "Add", "Nouvelle partie": "New game", "Raté…": "Missed…",
    "Jeux": "Games", "⚽ Balle": "⚽ Ball", "🙈 Cache-cache": "🙈 Hide and seek", "☀️ 1-2-3 soleil": "☀️ Red light, green light",
    "🎵 Danse": "🎵 Dance", "Fin du jeu": "End game", "Tours": "Tricks", "👋 Salut": "👋 Hello", "🌀 Toupie": "🌀 Spin",
    "🪑 Assis / debout": "🪑 Sit / stand", "Ses tours à lui": "His own tricks",
    "Compose des chorégraphies : positions de tête, sons de canard, gestes, s'asseoir.": "Compose choreographies: head positions, duck sounds, gestures, sitting.",
    "Pas encore de tour : crée-le dans le studio.": "No trick yet: create one in the studio.",
    "Studio de chorégraphies": "Choreography studio", "Comportements": "Behaviours",
    "Les politiques apprises (Pollen et communauté) : installées, à essayer, à ajouter.": "Learned policies (Pollen and community): installed, to try, to add.",
    "Ouvrir": "Open",
    // --- control ---
    "Marcher": "Walk", "Regarder": "Look",
    "Garde le doigt appuyé pour continuer. Petits pas guidés : il refuse d'avancer s'il y a un obstacle ou un vide. Pas de marche arrière (il ne voit pas derrière).": "Keep your finger pressed to continue. Small guided steps: he refuses to move towards an obstacle or a drop. No walking backwards (he can't see behind).",
    "Avancer": "Forward", "Tourner à gauche": "Turn left", "Tourner à droite": "Turn right", "Stop": "Stop",
    "Regarder en haut": "Look up", "Regarder à gauche": "Look left", "Regarder devant": "Look ahead", "Regarder à droite": "Look right",
    "Regarder en bas": "Look down", "Ou fais glisser ton doigt : il regarde où tu pointes.": "Or slide your finger: he looks where you point.",
    "Pavé du regard": "Gaze pad", "Envoyé": "Sent", "Microduck ne répond pas": "Microduck is not responding", "Code refusé": "Code refused",
    // --- health ---
    "Mise en route": "Getting started", "À la livraison, dans l'ordre. Les points marqués « auto » se cochent tout seuls.": "On delivery, in order. Items marked “auto” tick themselves.",
    "Appli connectée au canard": "App connected to the duck", "Wi-Fi de la maison lié au lieu actuel": "Home Wi-Fi linked to the current place",
    "Batteries numérotées 1, 2, 3 au feutre": "Batteries numbered 1, 2, 3 with a marker",
    "Premier diagnostic : tout va bien": "First diagnostic: all good", "Capteur de distance et caméra vus par le diagnostic": "Distance sensor and camera seen by the diagnostic",
    "Index du bec confirmé (scénario bec_index)": "Beak index confirmed (bec_index scenario)", "Validation groupée dans duck-sim": "Full validation in duck-sim",
    "Home Assistant le voit (entités microduck)": "Home Assistant sees him (microduck entities)", "Ses couleurs choisies dans le design": "His colours chosen in the design",
    "Diagnostic": "Diagnostic", "Lancer le diagnostic": "Run the diagnostic", "Diagnostic demandé": "Diagnostic requested",
    "Pas encore de diagnostic.": "No diagnostic yet.", "Tout va bien": "All good", "Problème détecté": "Problem found",
    "Demandé : il le fera dès qu'il sera au repos.": "Requested: he'll do it as soon as he is resting.",
    "Logiciel du robot": "Robot software", "Boucle de contrôle": "Control loop", "Bus des moteurs": "Motor bus",
    "Centrale inertielle": "IMU", "Capteur de distance": "Distance sensor", "Caméra": "Camera", "Tête (gauche-droite)": "Head (left-right)",
    "Tête (haut-bas)": "Head (up-down)", "Niveau": "Level", "Tension": "Voltage", "Autonomie": "Battery life", "Cycles mesurés": "Measured cycles",
    "À remplacer": "To replace", "oui": "yes", "non": "no", "Ses batteries": "His batteries",
    "Batterie changée : laquelle viens-tu de mettre ?": "Battery changed: which one did you put in?",
    "Écris 1, 2 et 3 au feutre sur tes batteries : il suit la santé de chacune.": "Write 1, 2 and 3 on your batteries with a marker: he tracks the health of each.",
    "Elle est dedans": "It's in", "Servos et températures": "Servos and temperatures", "Servo le plus chaud": "Hottest servo", "Carte": "Board",
    "Chauffe souvent": "Often hot", "À surveiller": "To watch", "aucun": "none", "Jours de mesure": "Days measured", "Chutes": "Falls",
    "Sur 7 jours": "Over 7 days", "Activité risquée": "Risky activity", "Endroits à risque": "Risky places",
    "Mises à jour et rapport": "Updates and report", "Cerveau": "Brain", "Chercher une mise à jour": "Check for updates", "Installer": "Install",
    "Revenir à la version précédente": "Go back to the previous version", "Exporter un rapport de diagnostic": "Export a diagnostic report",
    "Le rapport sert à demander de l'aide": "The report is for asking for help (Pollen, community): versions, health, alerts. No first name, place, network or household log. The robot software itself is updated by Pollen's official app.",
    "Il est à jour.": "He is up to date.", "GitHub ne répond pas.": "GitHub is not responding.", "Il redémarre (une à deux minutes)…": "He's restarting (one or two minutes)…",
    // --- character ---
    "Ses réglages": "His settings", "Au milieu : tel qu'il est. Sa personnalité continue d'évoluer avec ce qu'il vit.": "In the middle: as he is. His personality keeps evolving with what he experiences.",
    "Plutôt calme": "Calmer", "Plutôt joueur": "More playful", "Discret": "Quiet", "Bavard": "Chatty", "Sage": "Well-behaved", "Taquin": "Cheeky",
    "Enregistrer": "Save", "Caractère enregistré": "Character saved", "Personnalité": "Personality", "Curiosité": "Curiosity",
    "Sociabilité": "Sociability", "Espièglerie": "Mischief", "Prudence": "Caution", "Sa voix": "His voice",
    "Ses petits sons préférés : ceux qui font réagir la maison reviennent plus souvent.": "His favourite little sounds: the ones that get a reaction come back more often.",
    "Ceux qu'il connaît": "Those he knows", "Personne encore": "Nobody yet", "le chat": "the cat",
    // --- settings ---
    "Modes": "Modes", "Assis, silencieux, il ne bouge plus.": "Sitting, silent, he stops moving.", "Mode garde": "Watch mode",
    "Maison vide : il signale une voix, un choc, des coups à la porte.": "Empty house: he reports a voice, a bang, a knock at the door.",
    "Taquineries": "Pranks", "Les couper 30 minutes.": "Turn them off for 30 minutes.", "Couper": "Turn off",
    "L'effacer (meubles déplacés, nouvel endroit). Elle repart aussi de zéro à chaque démarrage.": "Clear it (furniture moved, new place). It also restarts from scratch at each start.",
    "Effacer": "Clear", "Carte effacée": "Map cleared", "Aide": "Help", "Questions fréquentes, et ce que veut dire chacun de ses états.": "Frequently asked questions, and what each of his states means.",
    "Ouvrir l'aide": "Open help", "Connexions et configuration": "Connections and setup",
    "Son nom, les habitants, les codes, Home Assistant (facultatif), tes imprimantes 3D, les appareils de la maison.": "His name, the household, codes, Home Assistant (optional), your 3D printers, home devices.",
    "Sa journée": "His day", "Heures calmes": "Quiet hours", "Assis et silencieux la nuit.": "Sitting and silent at night.", "de": "from",
    "Bonjour du matin": "Morning hello", "Il s'étire et dit bonjour.": "He stretches and says hello.", "Bonjour le week-end": "Weekend hello",
    "Vide : comme en semaine.": "Empty: same as weekdays.", "Repas": "Meals", "Il apprend où l'on mange et vient voir.": "He learns where you eat and comes to see.",
    "Auto-test du matin": "Morning self-test", "Un diagnostic rapide au premier réveil.": "A quick diagnostic when he first wakes up.",
    "Rythme de la journée": "Daily rhythm", "Plus vif le matin, plus calme le soir.": "Livelier in the morning, calmer in the evening.",
    "Routines": "Routines", "À heure fixe, les jours choisis.": "At a set time, on chosen days.", "Réglages enregistrés": "Settings saved",
    "Heure": "Time", "Action": "Action", "Il vient me voir": "He comes to see me", "Salut": "Hello", "Danse": "Dance", "Toupie": "Spin",
"1-2-3 soleil": "Red light, green light", "Cache-cache": "Hide and seek", "Il se signale": "He signals",
    "Mode calme : oui": "Quiet mode: on", "Mode calme : non": "Quiet mode: off", "Ajouter un repas": "Add a meal", "Ajouter une routine": "Add a routine",
    "Retirer ce repas": "Remove this meal", "Retirer la routine": "Remove the routine", "Heure du repas": "Meal time",
    "Heure du bonjour en semaine": "Weekday hello time", "Heure du bonjour le week-end": "Weekend hello time",
    "Lieux": "Places", "Il reconnaît où il est par le Wi-Fi : sur un réseau inconnu, il crée un nouveau lieu ; de retour sur un réseau connu, il y rebascule tout seul.": "He recognises where he is by the Wi-Fi: on an unknown network he creates a new place; back on a known one, he switches back by himself.",
    "Ici :": "Here:", "Nouveau lieu": "New place", "Archives": "Archive", "Y aller": "Go there", "Renommer": "Rename", "Archiver": "Archive",
    "Restaurer": "Restore", "Supprimer": "Delete", "aucun Wi-Fi lié": "no Wi-Fi linked", "ici": "here", "Bascule auto : oui": "Auto switch: on",
    "Bascule auto : non": "Auto switch: off", "Pas de carte gardée pour ce lieu.": "No saved map for this place.", "Fermer": "Close",
    "Ce téléphone": "This phone", "Prévenir le canard quand j'arrive": "Tell the duck when I arrive",
    "Quand ce téléphone rejoint le Wi-Fi de la maison, il t'accueille (même sans Home Assistant).": "When this phone joins the home Wi-Fi, he welcomes you (even without Home Assistant).",
    "Ton prénom": "Your first name", "OK": "OK", "Oublier le code": "Forget the code", "Sauvegarde": "Backup",
    "Ce qu'il a appris (habitants, personnalité, lieux, batteries), tes schémas et ses réglages, dans un fichier sur ce téléphone. Jamais le jeton Home Assistant.": "What he has learned (household, personality, places, batteries), your colour schemes and his settings, in a file on this phone. Never the Home Assistant token.",
    "Restaurer…": "Restore…", "Langue": "Language",
    // --- journal ---
    "Sa semaine": "His week", "Activités des 7 derniers jours": "Activities over the last 7 days", "Pas encore d'activité cette semaine": "No activity yet this week",
    "Ce qu'il a fait": "What he did", "auj.": "today", "lun.": "Mon", "mar.": "Tue", "mer.": "Wed", "jeu.": "Thu", "ven.": "Fri", "sam.": "Sat", "dim.": "Sun",
    // --- design ---
    "Design": "Design", "Couleurs d'origine": "Original colours", "Comparer avec l'origine (maintenir)": "Compare with the original (hold)",
    "Chargement du Microduck…": "Loading Microduck…", "Touche une pièce": "Tap a part", "à imprimer": "to print", "pièce achetée": "bought part",
    "Couleurs": "Colours", "Autre couleur": "Other colour", "Couleur d'origine": "Original colour", "Ma pièce (STL)": "My part (STL)", "Pièce d'origine": "Original part",
    "Dessine ta pièce à partir du STL d'origine, dans le même repère : elle se pose alors exactement à sa place.": "Design your part from the original STL, in the same frame: it then sits exactly in place.",
    "Schémas de couleurs": "Colour schemes", "Aucun schéma enregistré pour l'instant.": "No scheme saved yet.", "Repartir de l'origine": "Start from the original",
    "Fiche d'impression": "Print sheet", "Photo": "Photo", "Voir": "View", "Mes filaments": "My filaments",
    "Tes bobines en stock : elles apparaissent en premier dans le nuancier.": "Your spools in stock: they come first in the palette.",
    "Ex. PLA orange Prusament": "E.g. PLA Prusament orange", "Nom du filament": "Filament name", "Couleur du filament": "Filament colour",
    "Copier": "Copy", "Fiche copiée": "Sheet copied", "Schéma enregistré": "Scheme saved", "Ta pièce est posée": "Your part is in place",
    "Nouveau schéma": "New scheme", "Schéma en cours": "Current scheme",
    "Blanc": "White", "Gris clair": "Light grey", "Gris": "Grey", "Noir": "Black", "Orange Microduck": "Microduck orange", "Jaune": "Yellow",
    "Rouge": "Red", "Rose": "Pink", "Violet": "Purple", "Bleu": "Blue", "Turquoise": "Turquoise", "Vert": "Green", "Beige": "Beige", "Bois": "Wood",
    "Dessus de la tête": "Top of the head", "Dessous de la tête": "Underside of the head", "Face": "Face", "Bec": "Beak", "Bec souple": "Soft beak",
    "Bec souple (haut)": "Soft beak (top)", "Tour de l'œil": "Eye ring", "Coques du corps": "Body shells", "Coque gauche": "Left shell",
    "Coque droite": "Right shell", "Châssis": "Chassis", "Cou": "Neck", "Cou (tangage)": "Neck (pitch)", "Hanches": "Hips", "Hanche": "Hip",
    "Cuisses": "Thighs", "Cuisse gauche": "Left thigh", "Cuisse droite": "Right thigh", "Jambes": "Legs", "Jambe": "Leg", "Pieds": "Feet",
    "Pied gauche": "Left foot", "Pied droit": "Right foot", "Cheville gauche": "Left ankle", "Cheville droite": "Right ankle", "Semelles": "Soles",
    "Semelle gauche": "Left sole", "Semelle droite": "Right sole", "Support de batterie": "Battery holder", "Support moteur": "Motor mount",
    "Pièce de hanche": "Hip part", "Pièce de hanche (rotation)": "Hip part (rotation)", "Roulement de hanche": "Hip bearing",
    "Plaque de cuisse": "Thigh plate", "Verrou de carte": "Board lock", "Servomoteurs": "Servos", "Électronique": "Electronics", "Roulements": "Bearings",
    // --- marketplace ---
    "Marketplace": "Marketplace", "Pièces à imprimer pour Microduck": "Parts to print for Microduck", "Chargement du catalogue…": "Loading the catalogue…",
    "Pas encore de pièce dans le catalogue.": "No part in the catalogue yet.", "Catégories": "Categories", "Tout": "All", "Tête": "Head", "Corps": "Body",
    "Accessoires": "Accessories", "Supports": "Stands", "Autres": "Other", "Essayer sur mon Microduck": "Try on my Microduck",
    "Bientôt en téléchargement.": "Download coming soon.", "Exemple (démo)": "Example (demo)",
    "Le téléchargement se fait sur Printables ou Cults. Le catalogue est lu par le téléphone ; le canard n'envoie rien.": "Downloads happen on Printables or Cults. The catalogue is read by the phone; the duck sends nothing.",
    "Catalogue injoignable : le téléphone a-t-il accès à Internet ?": "Catalogue unreachable: does the phone have Internet access?",
    // --- studio, behaviours ---
    "Studio": "Studio", "Chorégraphies": "Choreographies", "Chorégraphie": "Choreography", "Nouvelle": "New", "Nom": "Name", "Étapes": "Steps",
    "+ Tête": "+ Head", "+ Son": "+ Sound", "+ Geste": "+ Gesture", "+ Assis/debout": "+ Sit/stand", "+ Pause": "+ Pause", "▶ Essayer": "▶ Try",
    "Son": "Sound", "Geste": "Gesture", "S'asseoir / se relever": "Sit down / stand up", "Pause": "Pause", "Monter": "Up", "Descendre": "Down",
    "Retirer": "Remove", "Gauche/droite": "Left/right", "Haut/bas": "Up/down", "Penché": "Tilt", "Durée (s)": "Duration (s)", "— nouvelle —": "— new —",
    "Tour enregistré": "Trick saved", "Bonjour": "Hello", "Pépiement": "Chirp", "Roucoulement": "Coo", "Question": "Question", "Petit coup": "Peck",
    "Youpi": "Wheee", "Alarme": "Alarm", "Content": "Happy", "Non": "No", "Oui": "Yes", "Curieux": "Curious", "Surpris": "Surprised", "Fatigué": "Tired",
    "Étirement": "Stretch", "S'ébouriffe": "Ruffles", "Se lisse": "Preens", "Éternuement": "Sneeze", "Fier": "Proud", "Bâillement": "Yawn", "Gêné": "Embarrassed",
    "Ses politiques apprises": "His learned policies", "Installés": "Installed", "En trouver d'autres": "Find more", "Ex. salto, danse…": "E.g. flip, dance…",
    "Rechercher": "Search", "Chercher": "Search", "Essayer": "Try", "Rien ici.": "Nothing here.", "Installé": "Installed",
    "Le catalogue officiel (uduck-registry, Hugging Face) : c'est le robot qui le consulte, comme l'appli officielle de Pollen.": "The official catalogue (uduck-registry, Hugging Face): the robot looks it up, like Pollen's official app.",
    // --- connections ---
    "Connexions": "Connections", "Configuration du canard": "Duck setup", "Redémarre le cerveau pour appliquer.": "Restart the brain to apply.",
    "Redémarrer": "Restart", "Le canard": "The duck", "Mode garde au démarrage": "Watch mode at start", "Maison vide : il signale une voix, un choc.": "Empty house: he reports a voice, a bang.",
    "Habitants": "Household", "L'entité Home Assistant (person.…) est facultative : elle sert à savoir qui est à la maison.": "The Home Assistant entity (person.…) is optional: it tells who is at home.",
    "Prénom": "First name", "Entité Home Assistant": "Home Assistant entity", "Codes": "Codes", "(vide : inchangé)": "(empty: unchanged)",
    "Code enfant": "Child code", "(jouer, regarder, le retrouver ; ni réglages ni télécommande)": "(play, look, find him; no settings, no remote)",
    "(facultatif)": "(optional)", "Relier à Home Assistant": "Connect to Home Assistant", "États du canard, événements de la maison.": "Duck states, home events.",
    "Adresse": "Address", "Jeton d'accès longue durée": "Long-lived access token", "(profil HA → Sécurité)": "(HA profile → Security)", "Tester": "Test",
    "Imprimantes 3D": "3D printers", "Suivies en direct sur le Wi-Fi": "Followed live over Wi-Fi, without Home Assistant: he reacts when a print finishes or fails. Prusa: PrusaLink and its API key; Elegoo: SDCP protocol.",
    "Appareils": "Devices", "(Home Assistant)": "(Home Assistant)", "Sonnette, machines, détecteur de fumée, aspirateur, météo… par leur entité Home Assistant.": "Doorbell, machines, smoke detector, vacuum, weather… by their Home Assistant entity.",
    "Type": "Type", "Clé API": "API key", "Clé API PrusaLink": "PrusaLink API key", "Nom (ex. MK4S)": "Name (e.g. MK4S)", "Prusa (PrusaLink)": "Prusa (PrusaLink)",
    "Elegoo (SDCP)": "Elegoo (SDCP)", "Sonnette": "Doorbell", "Sonnette (événement)": "Doorbell (event)", "Détecteur de fumée": "Smoke detector",
    "Aspirateur": "Vacuum", "Calendrier": "Calendar", "Machine (lave-linge…)": "Machine (washer…)", "Prise (puissance)": "Plug (power)", "Météo": "Weather",
    "Température extérieure": "Outdoor temperature", "Enregistré": "Saved", "Il redémarre…": "He's restarting…",
    // --- help ---
    "Microduck au quotidien": "Microduck day to day", "Questions fréquentes": "Frequently asked questions",
    "Il ne marche pas, il reste sur place": "He doesn't walk, he stays put",
    "Il ne marche jamais sans son capteur de distance": "He never walks without his distance sensor, nor towards an obstacle or a drop. Tiny steps don't make him move: that's normal (walking only starts above a certain speed). Check the sensor in Health → Diagnostic.",
    "Il tombe souvent": "He falls often",
    "Santé → Chutes montre l'activité": "Health → Falls shows the activity and the risky places; he learns by himself to avoid where he fell. Slippery floors or rug edges are the usual causes. Run a diagnostic to check the servos.",
    "L'appli ne le trouve pas": "The app can't find him",
    "Le téléphone doit être sur le même Wi-Fi que lui.": "The phone must be on the same Wi-Fi as him. In the Android app, “Find the duck” scans the whole network; otherwise type his address. If he has just been switched on, give him a minute.",
    "Le mettre en silence": "Making him quiet",
    "Réglages → Mode calme (assis, silencieux)": "Settings → Quiet mode (sitting, silent), or quiet hours every night (Settings → His day).",
    "Les batteries": "The batteries",
    "Numérote-les 1, 2, 3 au feutre.": "Number them 1, 2, 3 with a marker. After a swap, he asks which one is in (Health → His batteries) and tracks each one's health.",
    "Home Assistant est-il obligatoire ?": "Is Home Assistant required?",
    "Non. Sans lui, il vit, joue": "No. Without it he lives, plays, watches his printers (Settings → Connections) and welcomes you thanks to your phone. Home Assistant adds the home: doorbell, machines, alarm, scenes.",
    "Les notifications arrivent en retard": "Notifications arrive late",
    "Appli fermée, Android ne laisse vérifier que toutes les 15 minutes environ. Appli ouverte, elles arrivent tout de suite.": "With the app closed, Android only allows a check about every 15 minutes. With the app open, they arrive immediately.",
    "Un enfant veut jouer avec": "A child wants to play with him",
    "Réglages → Connexions → Code enfant": "Settings → Connections → Child code: with this code the app only shows games, gaze and “Where are you?”.",
    "Où sont mes données ?": "Where is my data?",
    "Sur le canard, et nulle part ailleurs": "On the duck, and nowhere else: what he sees and hears is analysed by him alone. Home Assistant only receives states. A backup (Settings) is a file you keep on your phone.",
    "Ce qu'il peut être en train de faire": "What he might be doing", "Tout ce que l'accueil peut afficher dans « En ce moment ».": "Everything the home screen can show under “Right now”.",
    // --- his states (ETATS) ---
    "Il se repose": "He's resting", "Il regarde autour de lui": "He's looking around", "Il se tourne": "He's turning", "Il se promène": "He's walking around",
    "Il fait la sieste": "He's napping", "Surpris !": "Surprised!", "Il fait la fête": "He's celebrating", "Il donne l'alerte": "He's raising the alarm",
    "Il a quelque chose à dire": "He has something to say", "Il regarde le chat": "He's watching the cat", "Il accueille quelqu'un": "He's welcoming someone",
    "Au revoir": "Goodbye", "Il écoute": "He's listening", "Il s'étire": "He's stretching", "Il s'ébouriffe": "He's ruffling",
    "Il se lisse les plumes": "He's preening", "Atchoum": "Achoo", "Il joue tout seul": "He's playing by himself", "Il cherche de la compagnie": "He's looking for company",
    "Bonjour !": "Hello!", "On sonne !": "Someone's at the door!", "Il a un message": "He has a message", "Une main tendue": "A hand held out",
    "Il se fait caresser": "He's being petted", "Il va dans son coin": "He's going to his corner", "Il va se recharger": "He's going to charge",
    "Il va observer": "He's going to watch", "Il fait le malin": "He's showing off", "Il répond": "He's answering", "Bravo !": "Well done!",
    "Il danse": "He's dancing", "ALARME": "ALARM", "Assis !": "Sit!", "Salut !": "Hi!", "Il t'écoute": "He's listening to you",
    "Il n'a pas compris": "He didn't understand", "Il est fier": "He's proud", "Il a chaud": "He's hot", "Tiens, quelque chose de nouveau": "Oh, something new",
    "Folle course": "Zoomies", "Il picore": "He's pecking", "Il joue à la balle": "He's playing ball", "Diagnostic en cours": "Diagnostic in progress",
    "Il est timide": "He's shy", "Un coup d'œil": "A glance", "Il te tient compagnie": "He's keeping you company", "Il vient te voir": "He's coming to see you",
    "Penaud": "Sheepish", "Compris !": "Got it!", "Il marche (télécommande)": "He's walking (remote)", "Il regarde (télécommande)": "He's looking (remote)",
    "Trop de bruit, il s'éloigne": "Too noisy, he's moving away", "Jour spécial !": "Special day!", "Il bâille": "He's yawning", "Fausse chute !": "Fake fall!",
    "Je suis là !": "I'm here!", "Il fait son tour": "He's doing his trick",
    // --- map legend, misc ---
    "💤 sieste": "💤 nap", "🛋️ repos": "🛋️ rest", "🍽️ repas": "🍽️ meals", "🔌 chargeur": "🔌 charger", "• objet remarqué": "• noticed object",
    "Réglages → Lieux": "Settings → Places", "Santé → Lancer le diagnostic": "Health → Run the diagnostic",
    "Santé → Ses batteries": "Health → His batteries", "ha.toml rempli sur le canard": "ha.toml filled in on the duck",
    "valider_sim.py, en premier": "valider_sim.py, first", "Français": "Français", "son": "sound",
    "Mises à jour": "Updates", "Rapport": "Report", "démo": "demo", "auto": "auto", "C'est noté": "Noted", "Fait": "Done", "Wi-Fi lié": "Wi-Fi linked",
    "Archivé": "Archived", "Restauré": "Restored", "Supprimé": "Deleted", "Renommé": "Renamed",
    "Masquer cette section": "Hide this section", "Afficher la liste de la livraison dans les réglages.": "Show the delivery checklist in the settings.",
    "Masquée : Réglages → Ce téléphone pour la retrouver": "Hidden: Settings → This phone to bring it back",
    "Sur un autre appareil": "On another device", "iPhone, iPad": "iPhone, iPad",
    "Scanne le QR avec l'appareil photo (même Wi-Fi), ouvre dans Safari, puis Partager → « Sur l'écran d'accueil » : l'appli s'installe comme les autres.": "Scan the QR with the camera (same Wi-Fi), open in Safari, then Share → “Add to Home Screen”: the app installs like any other.",
    "Ordinateur": "Computer", "Windows, Mac, Linux : l'appli Microduck pour ordinateur trouve le canard toute seule.": "Windows, Mac, Linux: the Microduck desktop app finds the duck on its own.",
    "Télécharger": "Download", "Sur un iPhone": "On an iPhone", "Démo sur iPhone": "Demo on iPhone", "Appareil photo → ouvrir dans Safari → Partager → « Sur l'écran d'accueil ». Une démo, sans le canard.": "Camera → open in Safari → Share → “Add to Home Screen”. A demo, without the duck.",
    "Appareil photo → ouvrir dans Safari → Partager → « Sur l'écran d'accueil ». Puis entre le code du canard.": "Camera → open in Safari → Share → “Add to Home Screen”. Then enter the duck's code.",
    // design : code couleur, couleurs gardees, partage des schemas
    "Choisir une couleur": "Pick a colour", "Code couleur (#rrggbb)": "Colour code (#rrggbb)", "Garder": "Keep", "Garder cette couleur": "Keep this colour",
    "Mes couleurs": "My colours", "Les couleurs que tu as gardées (bouton « Garder »), avec leur code.": "The colours you kept (“Keep” button), with their code.",
    "Aucune couleur gardée pour l'instant.": "No colour kept yet.", "Couleur gardée": "Colour kept",
    "Exporter mes schémas": "Export my schemes", "Importer": "Import", "Coller un schéma (texte ou QR)": "Paste a scheme (text or QR)",
    "Schémas du catalogue": "Schemes from the catalogue",
    "Partagés par la communauté (dossier « schemas » de microduck-catalogue). « Voir » les essaie sans rien changer ; « Ajouter » les garde.": "Shared by the community (“schemas” folder of microduck-catalogue). “View” tries them without changing anything; “Add” keeps them.",
    "Pas encore de schéma partagé.": "No shared scheme yet.", "Aucun schéma à exporter": "No scheme to export", "Rien de nouveau": "Nothing new",
    "Ce fichier n'est pas un schéma de Microduck": "This file is not a Microduck scheme", "Ce texte n'est pas un schéma de Microduck": "This text is not a Microduck scheme",
    "Colle le texte du schéma :": "Paste the scheme text:", "Schéma illisible": "Unreadable scheme",
    "Scanne ce code, copie le texte, puis « Coller un schéma » dans le design de l'autre téléphone. « Exporter mes schémas » donne un fichier.": "Scan this code, copy the text, then “Paste a scheme” in the design of the other phone. “Export my schemes” gives a file.",
    "Chaque semaine, toute seule": "Every week, on its own", "Récupérer la dernière": "Get the latest",
    "Pas encore faite : au prochain passage du téléphone à la maison.": "Not done yet: next time the phone is home.",
    "À toi de jouer !": "Your turn!",
    "🐾 Suis-moi": "🐾 Follow me", "🦆 Je te suis": "🦆 I'll follow you", "Il boude": "He's sulking", "Réconciliés !": "Friends again!",
    "Il attend quelqu'un": "He's waiting for someone", "Il va à la porte": "He's going to the door", "Il te suit": "He's following you",
    "Il te montre le chemin": "He's showing the way", "Il te répond": "He's answering you", "Jaloux !": "Jealous!",
    "Il va flâner": "He's wandering off", "Un bon souvenir": "A good memory", "Méfiant": "Wary", "Lance-la !": "Throw it!",
    "Son plan": "Its floor plan", "Importer un plan (scan Quest)": "Import a floor plan (Quest scan)", "Remplacer le plan": "Replace the floor plan",
    "Exporter le plan": "Export the floor plan", "Retirer le plan": "Remove the floor plan", "Plan retiré": "Floor plan removed",
    "Plan indisponible": "Floor plan unavailable", "Conversion du scan sur le canard…": "Converting the scan on the duck…",
    "Ce fichier n'est pas un scan ni un plan": "This file is neither a scan nor a floor plan",
    "Un peu seul": "Some alone time", "Il rentre à sa station": "Heading to his dock", "Il se met sur sa station": "Getting on his dock",
    "Il fait sa ronde": "Doing his rounds", "Il vient te voir": "Coming to see you", "Il y va": "On his way",
    "Rentrer à sa station": "Go to his dock", "Faire la ronde": "Do the rounds", "Effacer zones et points": "Clear zones and points",
    "Il n'est pas dans ce lieu.": "He isn't at this place.", "Il cherche où il est (un marqueur vu par sa caméra l'aidera).": "He's working out where he is (a marker seen by his camera will help).",
    "L'envoyer ici ?": "Send him here?", "Il y va (s'il sait où il est)": "He's going (if he knows where he is)", "Effacé": "Cleared",
    "Touche le plan pour l'y envoyer. Zones interdites et points nommés : dessinés avec le casque (appli Quest), ou effacés ici.": "Tap the plan to send him there. No-go zones and named spots: drawn with the headset (Quest app), or cleared here.", "Il s'isole un peu": "Going off alone", "Joyeux anniversaire !": "Happy birthday!", "Le chat joue !": "The cat is playing!", "Sieste près du chat": "Napping near the cat",
    "Il a le hoquet": "He has hiccups", "Hoquet passé !": "Hiccups gone!", "Oups !": "Oops!", "Il fait son nid": "Making his nest", "Il inspecte": "Inspecting", "Il rejoue ton rythme": "Playing your rhythm back", "Il dit ton nom": "Saying your name", "Il se fait tout petit": "Making himself small", "Bain de soleil": "Sunbathing", "Avec son doudou": "With his favourite toy", "Il va voir son doudou": "Off to his favourite toy", "Il rit avec toi": "Laughing along", "Il fait le malin": "Showing off", "C'est l'heure du câlin": "Cuddle time",
    // lot 9 : minuteurs, rappels, reveil, humeur, bilan du mois
    "Minuteurs et rappels": "Timers and reminders", "🔕 Arrêter son signal": "🔕 Stop his signal", "Durée en minutes": "Duration in minutes",
    "Pour quoi ? (pâtes, lessive…)": "What for? (pasta, laundry…)", "Nom du minuteur": "Timer name", "Lancer": "Start",
    "Un rappel à heure fixe": "A reminder at a set time", "Arroser les plantes": "Water the plants", "Le rappel": "The reminder",
    "Heure": "Time", "Pour qui ? (vide : tout le monde)": "For whom? (empty: everyone)", "Chaque jour": "Every day", "Programmer": "Schedule",
    "À l'heure dite, il le signale en sons de canard, même en mode calme. Une caresse l'arrête. Le réveil doux se règle dans Réglages → Sa journée → Routines.": "At the set time, he signals it with duck sounds, even in quiet mode. A pat stops it. The gentle alarm is set in Settings → His day → Routines.",
    "Rappel programmé": "Reminder scheduled", "C'est noté": "Noted", "Réveil doux": "Gentle alarm", "Il te signale quelque chose": "He's signalling something",
    "Minuteur": "Timer", "Rappel": "Reminder", "C'est l'heure !": "Time's up!", "Annuler le rappel": "Cancel the reminder",
    "Son humeur": "His mood", "Énergie et éveil sur 7 jours": "Energy and alertness over 7 days",
    "Il faut quelques heures de vie pour tracer son humeur.": "It takes a few hours of life to chart his mood.",
    "Bilan du mois": "Monthly recap", "Mois": "Month", "Carte du bilan du mois": "Monthly recap card", "Enregistrer l'image": "Save the image",
    // --- lots 5 a 8 : messages, vus, jeux sur la carte, photos, usure, carnet, invites, partage ---
    "Où l'a-t-il vu ?": "Where did he see it?", "Rien de remarqué depuis son démarrage.": "Nothing noticed since he started.",
    "🐱 Le chat": "🐱 The cat", "⚽ La balle": "⚽ The ball", "📦 Un objet au sol": "📦 Something on the floor",
    "à l'instant": "just now", "Messages": "Messages", "Pour qui ?": "For whom?", "Ton message": "Your message", "Laisser": "Leave",
    "Laisse un message pour quelqu'un : quand il le verra (à son retour, ou tout de suite s'il est là), le canard le lui signalera en pépiant, et le texte s'affichera ici.": "Leave a message for someone: when he sees them (when they come home, or right away if they're here), the duck will chirp to let them know, and the text will show here.",
    "Annuler ce message": "Cancel this message", "Message transmis": "Message delivered",
    "Sur sa carte": "On his map", "Choisis un jeu, puis touche sa carte.": "Pick a game, then tap his map.",
    "⚽ La balle est là": "⚽ The ball is here", "🏁 Parcours": "🏁 Course", "Partir": "Go", "Effacer les points": "Clear the points",
    "Sa carte : touche pour poser un point": "His map: tap to place a point",
    "Il faut qu'il ait un peu exploré pour avoir une carte.": "He needs to explore a bit to have a map.",
    "Touche sa carte là où tu as lancé la balle : il y va, puis la cherche.": "Tap his map where you threw the ball: he goes there, then looks for it.",
    "Pose jusqu'à 6 points (4 m au plus entre deux) : il les enchaîne, chronométré.": "Place up to 6 points (4 m at most between two): he runs them in order, timed.",
    "Choisis d'abord un jeu": "Pick a game first", "Trop loin : 4 m au plus": "Too far: 4 m at most", "6 points au plus": "6 points at most",
    "Il va chercher la balle !": "He's going for the ball!", "Partez !": "Go!", "Dernier parcours": "Last course",
    "Parcours réussi": "Course completed", "Parcours : bloqué": "Course: blocked", "Parcours : trop long": "Course: too long",
    "Parcours interrompu": "Course interrupted", "Il ne peut pas faire ce parcours": "He can't do this course",
    "Il ne peut pas y aller": "He can't go there", "Debout, au calme, et pas trop loin (4 m).": "Standing, calm, and not too far (4 m).",
    "Debout, au calme, avec des étapes de 4 m au plus.": "Standing, calm, with legs of 4 m at most.",
    "Il fait son parcours": "He's running his course", "Il prend la pose": "He's posing",
    "Mode photo": "Photo mode", "Il prend la pose et la tient, sans un son, le temps de la photo (sa caméra).": "He strikes a pose and holds it, silently, while the photo is taken (his camera).",
    "😤 Fier": "😤 Proud", "😊 Content": "😊 Happy", "🤔 Curieux": "🤔 Curious", "👍 Oui": "👍 Yes", "😮 Surpris": "😮 Surprised",
    "🙆 Étirement": "🙆 Stretch", "🪶 Ébouriffé": "🪶 Ruffled", "🙈 Gêné": "🙈 Embarrassed",
    "Il prend la pose…": "Striking a pose…", "Clic ! (dans Journal → Ses photos)": "Click! (in Log → His photos)", "Clic !": "Click!",
    "La dernière photo": "The latest photo",
    "Ses photos": "His photos", "Journal photo": "Photo log",
    "Il garde quelques images de sa journée (le chat, un retour, une partie, une impression finie). Sur lui seulement, 7 jours, jamais ailleurs.": "He keeps a few pictures from his day (the cat, someone coming home, a game, a finished print). On him only, 7 days, never anywhere else.",
    "Pas de photo pour l'instant.": "No photos yet.", "📷 Une photo maintenant": "📷 A photo now", "Tout effacer": "Delete all",
    "Effacer toutes ses photos ?": "Delete all his photos?",
    "Journal photo activé": "Photo log on", "Journal photo coupé": "Photo log off",
    "Le chat": "The cat", "Un retour": "Someone came home", "Jour spécial": "Special day", "Il danse": "He's dancing", "Fier": "Proud",
    "La balle": "The ball", "Un objet": "An object", "Impression": "Print", "Pose": "Pose", "Photo": "Photo",
    "Usure des servos": "Servo wear",
    "Au repos debout, chaque jour : l'effort de chaque servo (courant) et la chaleur. Un servo qui force de plus en plus s'use : mieux vaut le savoir avant qu'il ne lâche.": "Standing at rest, every day: how hard each servo works (current) and the heat. A servo that strains more and more is wearing out: better to know before it gives up.",
    "Servo": "Servo", "Courant de repos du servo, jour par jour": "Servo resting current, day by day",
    "Pas encore assez de jours de mesure (il en faut quelques-uns au repos).": "Not enough days of measurements yet (it takes a few at rest).",
    "Comparer les batteries": "Compare the batteries", "Autonomie de chaque batterie, cycle après cycle": "Runtime of each battery, cycle after cycle",
    "1er cycle": "1st cycle", "dernier": "latest", "Servo à surveiller": "Servo to watch",
    "Hanche gauche (rotation)": "Left hip (rotation)", "Hanche gauche (côté)": "Left hip (side)", "Hanche gauche (avant)": "Left hip (forward)",
    "Genou gauche": "Left knee", "Cheville gauche": "Left ankle", "Cou": "Neck", "Tête (haut-bas)": "Head (up-down)",
    "Tête (gauche-droite)": "Head (left-right)", "Tête (penchée)": "Head (tilt)", "Hanche droite (rotation)": "Right hip (rotation)",
    "Hanche droite (côté)": "Right hip (side)", "Hanche droite (avant)": "Right hip (forward)", "Genou droit": "Right knee", "Cheville droite": "Right ankle",
    "Carnet d'entretien": "Maintenance log", "Type": "Type", "Pièce changée": "Part replaced", "Pièce imprimée": "Part printed",
    "Servo remplacé": "Servo replaced", "Batterie remplacée": "Battery replaced", "Nettoyage": "Cleaning", "Autre": "Other",
    "Quel servo ?": "Which servo?", "Quelle batterie ?": "Which battery?", "Batterie 1": "Battery 1", "Batterie 2": "Battery 2", "Batterie 3": "Battery 3",
    "Détail (pièce, couleur, remarque…)": "Detail (part, colour, note…)", "Détail": "Detail", "Date": "Date", "Noter": "Add",
    "Un servo ou une batterie notés « remplacés » repartent d'une mesure neuve.": "A servo or battery logged as “replaced” starts again from fresh measurements.",
    "Rien de noté pour l'instant.": "Nothing logged yet.", "Retirer cette ligne du carnet ?": "Remove this line from the log?", "Noté": "Logged",
    "Ajoute un détail": "Add a detail",
    "Il repartira d'une mesure neuve pour cette pièce. C'est bien un remplacement ?": "He'll start fresh measurements for this part. Is it really a replacement?",
    "Vacances": "Holidays", "Maison vide pour longtemps : calme et garde, et des nouvelles chaque soir à 20 h.": "House empty for a long time: quiet and watch, with news every evening at 8 pm.",
    "Bonnes vacances ! Des nouvelles chaque soir.": "Happy holidays! News every evening.", "Bon retour !": "Welcome back!",
    "Nouvelles du canard": "News from the duck",
    "Invités": "Guests", "Durée": "Duration", "Créer": "Create", "1 jour": "1 day", "3 jours": "3 days", "1 semaine": "1 week",
    "Un code pour quelques heures (un ami, les grands-parents) : jouer, regarder, laisser un message. Ni réglages, ni marche guidée, ni photos.": "A code for a few hours (a friend, the grandparents): play, watch, leave a message. No settings, no guided walking, no photos.",
    "Révoquer": "Revoke", "Invité": "Guest", "Copier": "Copy", "Partager": "Share", "Copié": "Copied",
    "Trop long pour un QR code : exporte le fichier": "Too long for a QR code: export the file",
    "Exporte ce tour (fichier, texte ou QR code) pour un autre Microduck, ou importe celui d'un ami. Pour le proposer à tous : le dossier « choregraphies » du catalogue.": "Export this trick (file, text or QR code) for another Microduck, or import a friend's. To offer it to everyone: the “choregraphies” folder of the catalogue.",
    "Exporter": "Export", "QR code": "QR code", "Importer un fichier": "Import a file", "Coller un texte": "Paste text",
    "Du catalogue": "From the catalogue", "Chargement…": "Loading…", "Ajouter": "Add", "Catalogue injoignable (Internet ?)": "Catalogue unreachable (Internet?)",
    "Pas encore de chorégraphie partagée.": "No shared choreography yet.", "Rien à exporter : ajoute des étapes": "Nothing to export: add steps",
    "Ce fichier n'est pas une chorégraphie": "This file is not a choreography", "Ce texte n'est pas une chorégraphie": "This text is not a choreography",
    "Rien de jouable dans ce tour": "Nothing playable in this trick", "Colle le texte de la chorégraphie :": "Paste the choreography text:",
    "Scanne ce code avec l'appareil photo, copie le texte, puis « Coller un texte » dans le studio de l'autre téléphone.": "Scan this code with the camera, copy the text, then “Paste text” in the studio of the other phone.",
    "Envoyer à l'imprimante": "Send to printer", "Ajoute d'abord ta Prusa dans Réglages → Connexions": "First add your Prusa in Settings → Connections",
    "Fichier": "File", "Imprimante": "Printer", "Lancer l'impression": "Start printing", "Envoyer": "Send", "Annuler": "Cancel",
    "Vérifie que le plateau est libre et le bon filament chargé.": "Check that the bed is clear and the right filament is loaded.",
    "Téléchargement depuis le catalogue…": "Downloading from the catalogue…", "Envoi à l'imprimante (par le canard)…": "Sending to the printer (via the duck)…",
    "Impression lancée !": "Print started!", "Fichier posé sur l'imprimante": "File placed on the printer", "Enregistrement impossible": "Could not save",
  };
  // libelles avec des chiffres ou des noms
  const REGLES = [
    [/^Il est (?:dans « (.+) »|sur le plan) \(à (\d+) cm près\)\.$/, (m) => `He is ${m[1] ? "in “" + m[1] + "”" : "on the plan"} (within ${m[2]} cm).`],
    [/^Plan importé : ([\d.]+) × ([\d.]+) m, (\d+) meubles$/, (m) => `Floor plan imported: ${m[1]} × ${m[2]} m, ${m[3]} pieces of furniture`],
    [/^Plan refusé : (.+)$/, (m) => `Floor plan rejected: ${m[1]}`],
    [/^il y a (\d+) s$/, (m) => `${m[1]} s ago`], [/^il y a (\d+) min$/, (m) => `${m[1]} min ago`], [/^il y a (\d+) h$/, (m) => `${m[1]} h ago`],
    [/^Batterie (\d)( · dans le canard)?$/, (m) => `Battery ${m[1]}${m[2] ? " · in the duck" : ""}`],
    [/^(.+) × (\d+)$/, (m) => `${t(m[1])} × ${m[2]}`], [/^Retirer (.+)$/, (m) => `Remove ${m[1]}`], [/^Supprimer (.+)$/, (m) => `Delete ${m[1]}`],
    [/^Jouer (.+)$/, (m) => `Play ${m[1]}`], [/^Microduck : (.+)$/, (m) => `Microduck: ${t(m[1])}`], [/^Archives \((\d+)\)$/, (m) => `Archive (${m[1]})`],
    [/^Lier « (.+) »$/, (m) => `Link “${m[1]}”`], [/^· Wi-Fi « (.+) »$/, (m) => `· Wi-Fi “${m[1]}”`], [/^ · Wi-Fi « (.+) »$/, (m) => ` · Wi-Fi “${m[1]}”`],
    [/^familiarité (\d+) % · (\d+) rencontres$/, (m) => `familiarity ${m[1]} % · ${m[2]} encounters`],
    [/^(\d+) cycles?((?: · .+)?)$/, (m) => `${m[1]} cycle${m[1] > 1 ? "s" : ""}${m[2].replace("santé", "health").replace("à remplacer", "to replace")}`],
    [/^Au tour de (.+) : lancer !$/, (m) => `${m[1]}'s turn: go!`], [/^(.+) : il tire…$/, (m) => `${m[1]}: he's kicking…`],
    [/^But pour (.+) !$/, (m) => `Point for ${m[1]}!`], [/^À (.+) de jouer !$/, (m) => `${m[1]}'s turn!`],
    [/^(\d+) étape\(s\) · ([\d.]+) s \(60 s au plus\)$/, (m) => `${m[1]} step(s) · ${m[2]} s (60 s max)`],
    [/^Tout va bien — (.+)$/, (m) => `All good — ${m[1]}`], [/^Problème détecté — (.+)$/, (m) => `Problem found — ${m[1]}`],
    [/^(.+) · (\d+) couleurs?$/, (m) => `${t(m[1])} · ${m[2]} colour${m[2] > 1 ? "s" : ""}`], [/^≈ (.+) \((#\w+)\)$/, (m) => `≈ ${t(m[1])} (${m[2]})`],
    [/^remplace : (.+)$/, (m) => `replaces: ${t(m[1])}`], [/^Il pense être à « (.+) »\.$/, (m) => `He thinks he's at “${m[1]}”.`],
    [/^Mise à jour (.+) disponible$/, (m) => `Update ${m[1]} available`], [/^Nouvelle version (\w+) du (.+?) : (.+)$/, (m) => `New version ${m[1]} of ${m[2]}: ${m[3]}`],
    [/^Batterie (\d) notée$/, (m) => `Battery ${m[1]} noted`], [/^« (.+) » posée sur le Microduck$/, (m) => `“${m[1]}” placed on the Microduck`],
    [/^(.+) : s'il est debout et au calme$/, (m) => `${m[1]}: if he's standing and calm`],
    [/^Il saura quand tu arrives, (.+)$/, (m) => `He'll know when you arrive, ${m[1]}`],
    [/^(.+) · auto$/, (m) => `${t(m[1])} · auto`], [/^Cerveau (.+)$/, (m) => `Brain ${m[1]}`],
    [/^il y a (\d+) (min|h|j)$/, (m) => `${m[1]} ${{ min: "min", h: "h", j: "d" }[m[2]]} ago`],
    [/^Pour (.+?)(?: · de (.+))?$/, (m) => `For ${m[1]}` + (m[2] ? ` · from ${m[2]}` : "")],
    [/^en attente · (.+)$/, (m) => `waiting · ${t(m[1])}`], [/^✓ signalé (.+)$/, (m) => `✓ delivered ${t(m[1])}`],
    [/^Il le dira à (.+)$/, (m) => `He'll tell ${m[1]}`], [/^(.+) est là : il le lui a signalé\.$/, (m) => `${m[1]} is here: he let them know.`],
    [/^Record, (\d+) points?$/, (m) => `Record, ${m[1]} point${m[1] > 1 ? "s" : ""}`],
    [/^([\d,]+) s : record !$/, (m) => `${m[1].replace(",", ".")} s: record!`], [/^([\d,]+) s$/, (m) => `${m[1].replace(",", ".")} s`],
    [/^(\d+) point\(s\) sur (\d+)$/, (m) => `${m[1]} point(s) out of ${m[2]}`],
    [/^Tout va bien : (.+)$/, (m) => `All good: ${m[1].replace("batterie", "battery").replace("rien d'anormal entendu", "nothing unusual heard")}`],
    [/^À voir : (.+)$/, (m) => `To check: ${m[1].replace("batterie", "battery").replace("alerte(s) de garde", "watch alert(s)").replace("chute(s)", "fall(s)")}`],
    [/^(.+) : détails dans Santé\.$/, (m) => `${m[1]}: details in Health.`],
    [/^Batterie (\d) : ([\d.]+) h$/, (m) => `Battery ${m[1]}: ${m[2]} h`], [/^Batterie (\d) : pas encore de cycle$/, (m) => `Battery ${m[1]}: no cycle yet`],
    [/^Batterie (\d) remplacée$/, (m) => `Battery ${m[1]} replaced`], [/^Servo remplacé : (.+)$/, (m) => `Servo replaced: ${t(m[1])}`],
    [/^remplacé le (.+)$/, (m) => `replaced on ${m[1]}`], [/^Invité : (.+)$/, (m) => `Guest: ${t(m[1])}`], [/^QR code de (.+)$/, (m) => `QR code for ${t(m[1])}`],
    [/^(.+) · jusqu'au (.+)$/, (m) => `${m[1]} · until ${m[2]}`],
    [/^Scanne avec l'appareil photo \(même Wi-Fi\)\. Ou code : (.+)$/, (m) => `Scan with the camera (same Wi-Fi). Or code: ${m[1]}`],
    [/^« (.+) » ajouté$/, (m) => `“${m[1]}” added`],
    [/^Minuteur : (.+?) min$/, (m) => `Timer: ${m[1]} min`], [/^Minuteur : (.+)$/, (m) => `Timer: ${m[1]}`],
    [/^Dernière : (.+) · (\d+) gardées? dans le téléphone$/, (m) => `Latest: ${m[1]} · ${m[2]} kept on the phone`],
    [/^(\d+) jours? de vie((?: · .+)?)$/, (m) => `${m[1]} day${m[1] > 1 ? "s" : ""} old${m[2].replace("encore un peu timide", "still a little shy").replace("de plus en plus sûr de lui", "more and more confident").replace("joueur aujourd'hui", "playful today").replace("paresseux aujourd'hui", "lazy today").replace("collant aujourd'hui", "clingy today").replace(/🎂 (\d+) ans? aujourd'hui !/, (_, n) => `🎂 ${n} today!`)}`],
    [/^Rappel pour (.+)$/, (m) => `Reminder for ${m[1]}`], [/^Annuler (.+)$/, (m) => `Cancel ${t(m[1])}`],
    [/^(\d\d:\d\d)( · chaque jour)? · pour (tout le monde|.+)$/, (m) => `${m[1]}${m[2] ? " · every day" : ""} · for ${m[3] === "tout le monde" ? "everyone" : m[3]}`],
    [/^Énergie \(moyenne (\d+) %\)$/, (m) => `Energy (average ${m[1]} %)`], [/^Éveil \(moyenne (\d+) %\)$/, (m) => `Alertness (average ${m[1]} %)`],
    [/^(\d+) schémas? ajoutés?$/, (m) => `${m[1]} scheme${m[1] > 1 ? "s" : ""} added`], [/^Aperçu : (.+)$/, (m) => `Preview: ${m[1]}`],
    [/^Nom de cette couleur \((#\w+)\)$/, (m) => `Name of this colour (${m[1]})`], [/^Partager (.+)$/, (m) => `Share ${m[1]}`], [/^Échec : (.+)$/, (m) => `Failed: ${m[1]}`],
    [/^(.+), (lun|mar|mer|jeu|ven|sam|dim)\. (.+)$/, (m) => `${t(m[1])}, ${m[2]}. ${m[3]}`],
    [/^(.+) · (lun|mar|mer|jeu|ven|sam|dim)\. (.+)$/, (m) => `${t(m[1])} · ${m[2]}. ${m[3]}`],
    [/^([✓▶+📍]\s*)(.+)$/u, (m) => m[1] + t(m[2])],
  ];

  function t(s) {
    if (!s) return s;
    const debut = s.match(/^\s*/)[0], fin = s.match(/\s*$/)[0], c = s.trim().replace(/\s+/g, " ");
    if (!c) return s;
    if (Object.prototype.hasOwnProperty.call(EN, c)) return debut + EN[c] + fin;
    for (const [re, f] of REGLES) { const m = c.match(re); if (m) { const r = f(m); if (r !== c) return debut + r + fin; } }
    for (const k in EN) if (k.length >= 25 && c.startsWith(k)) return debut + EN[k] + fin;   // longs paragraphes : par leur debut
    return s;
  }
  window.MicroduckT = t;

  const ATTRS = ["placeholder", "aria-label", "title"];
  const vus = new WeakMap();
  function traduireNoeud(n) {
    if (n.nodeType === 3) {
      if (vus.get(n) === n.nodeValue) return;
      const v = t(n.nodeValue);
      if (v !== n.nodeValue) n.nodeValue = v;
      vus.set(n, n.nodeValue);
      return;
    }
    if (n.nodeType !== 1 || n.tagName === "SCRIPT" || n.tagName === "STYLE") return;
    for (const a of ATTRS) if (n.hasAttribute(a)) { const v = n.getAttribute(a), r = t(v); if (r !== v) n.setAttribute(a, r); }
    if (n.tagName === "OPTION" || n.tagName === "TITLE") { /* texte enfant traite ci-dessous */ }
    for (const c of n.childNodes) traduireNoeud(c);
  }
  const obs = new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === "characterData") traduireNoeud(m.target);
      else if (m.type === "attributes") traduireNoeud(m.target);
      else m.addedNodes.forEach(traduireNoeud);
    }
  });
  function demarrer() {
    traduireNoeud(document.body);
    document.title = t(document.title);
    obs.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }
  if (document.body) demarrer(); else document.addEventListener("DOMContentLoaded", demarrer);
  for (const nom of ["confirm", "alert", "prompt"]) {
    const orig = window[nom].bind(window);
    window[nom] = (msg, ...rest) => orig(traduirePhrase(msg), ...rest);
  }
  function traduirePhrase(msg) {
    const r = t(String(msg || ""));
    if (r !== msg) return r;
    return String(msg).replace(/^Supprimer « (.+) » \?$/, "Delete “$1”?").replace(/^Supprimer le schéma « (.+) » \?$/, "Delete the scheme “$1”?")
      .replace(/^Nom du schéma$/, "Scheme name").replace(/^Nom du lieu$/, "Place name").replace(/^Installer (.+) sur le canard \?$/, "Install $1 on the duck?");
  }
})();
