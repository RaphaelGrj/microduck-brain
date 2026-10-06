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
  };
  // libelles avec des chiffres ou des noms
  const REGLES = [
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
