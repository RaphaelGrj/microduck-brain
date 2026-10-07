# Microduck XR : le Meta Quest 3 au service du canard

Une seule appli dans le casque, **sept modes**. La manette **gauche** change de mode : **X** pour le suivant, **Y** pour
le précédent.

| Mode | À quoi il sert |
| --- | --- |
| **Scan** | Relever la maison et en faire son plan (ci-dessous). |
| **Atelier** | Voir, posé sur ta vraie pièce, ce qu'il croit : où il pense être (flèche orange), ses hypothèses (boules jaunes), ce que voit son capteur (points rouges), son trajet (ligne bleue), ses zones interdites et ses points nommés. **Gâchette** : l'envoyer au point visé au sol. |
| **Vérité** | Mesurer l'erreur de sa localisation : gâchette au **centre de son dos**, puis au **bout de son bec**. L'erreur s'affiche en cm et en degrés. **A** le recale à cet endroit (« tu es ici »). |
| **Dessin** | **Zones interdites** : gâchette à chaque coin au sol, **A** pour fermer la zone. **Points nommés** (panier, gamelle…) : nom choisi au joystick, posé avec le **grip**. **B** annule. Tout est enregistré tout de suite dans son plan. |
| **Danse** | **Gâchette** : enregistrer une danse avec **ta tête** (16 s au plus). Elle s'ajoute à son studio de chorégraphies. **A** la lui fait jouer. Joystick : plus ou moins ample. |
| **Jumeau** | Le canard **simulé** (`duck-sim`, sur le PC) dessiné dans ta pièce, à sa taille, animé en direct et piloté par son vrai cerveau et sa vraie appli : tout s'essaie avant la livraison. **Gâchette** tenue puis relâchée : lancer la balle. **Grip** la main sur sa tête : le caresser. **A** : ses couleurs (ci-dessous). Détails : « Le canard jumeau », plus bas. |
| **Être le canard** | Sa tête suit la tienne, le joystick le fait marcher (pas guidés, avec les garde-fous de la télécommande). Tu vois ce qu'il voit, **seulement si les photos sont permises** dans ses réglages. |

**Appairage** (une fois, puis à chaque changement de canard), **sans rien taper** : au premier lancement, ou en
**cliquant le joystick gauche** à tout moment, le casque cherche le canard sur le Wi-Fi (port 8090 : le vrai canard,
ou ton PC qui fait tourner le canard jumeau) et lui demande l'accès. Dans l'appli du téléphone, *Réglages → Casque
(Meta Quest)* : **Accepter**. Le casque reçoit l'adresse et le code, et les garde.

**Sans câble** : *Build And Run* installe l'appli dans le casque une fois pour toutes (*Bibliothèque → Sources
inconnues → Microduck XR*). Ensuite, plus besoin du câble : elle parle au canard (ou au PC) par le Wi-Fi.

Les modes autres que Scan parlent au canard par son appli (réseau local, code parent). Ils ne reçoivent que des
positions, sauf le mode « Être le canard », qui reçoit une image **en opt-in**.

---

# Scanner la maison avec le Meta Quest 3 → le plan du canard

Le Quest 3 sait déjà relever une pièce : murs, sol, portes, fenêtres, meubles (« Configuration de l'espace »). Mais
il ne propose pas d'exporter ce relevé. On compile donc une petite appli, **Microduck Scan**, qui :

1. lit le relevé du Quest ;
2. te fait pointer, avec la manette, le **chargeur**, la direction **devant** le chargeur, l'**entrée** et
   éventuellement les **marqueurs** imprimés ;
3. écrit un fichier `microduck-scan-AAAAMMJJ-HHMM.json`, et l'envoie au canard si tu as renseigné son adresse.

Ensuite, sur le PC, `plan_quest.py` transforme ce fichier en plan et en image de contrôle. Tu vois ta maison telle
que le canard la verra, avant même de l'avoir. Le canard fera la même conversion lui-même quand tu importeras le
fichier dans l'appli.

Seuls les meubles et la position des murs sortent du casque, vers ton PC ou ton canard. Aucune image ne sort.

---

## Ce qu'il faut (une fois)

| Quoi | Où |
| --- | --- |
| Unity Hub + **Unity 6 LTS** (6000.0.x) avec le module **Android Build Support** (cocher aussi OpenJDK et Android SDK & NDK) | unity.com/download |
| Un compte **Meta developer** (gratuit) et une « organisation » à ton nom | developers.meta.com/horizon |
| Le **mode développeur** activé sur le Quest | appli Meta Horizon du téléphone → Appareils → ton Quest → Paramètres du casque → Mode développeur |
| **Meta Quest Developer Hub** (MQDH), pour récupérer le fichier | developers.meta.com/horizon/downloads |
| Un câble USB-C (celui du Quest) | |

## 1. Le projet Unity (≈ 30 min la première fois)

1. Unity Hub → **New project** → modèle **Universal 3D** (ou 3D) → nom `MicroduckScan`.
2. Ajouter le kit Meta. Sur l'Asset Store, prendre le paquet gratuit **« Meta XR All-in-One SDK »** (*Add to My
   Assets*), puis dans Unity : *Window → Package Manager → My Assets* → l'installer. Il contient le **MR Utility
   Kit** (MRUK). Accepter les redémarrages d'Unity.
3. *File → Build Profiles* (ou *Build Settings*) → **Android** → *Switch Platform*.
4. *Meta → Tools → Project Setup Tool* → **Fix All** (onglet Android), puis encore **Fix All** jusqu'à ce que
   tout soit vert.
5. *Meta → Tools → Building Blocks* : glisser dans la scène **Camera Rig**, **Passthrough**, puis
   **MR Utility Kit**.
   - Sur l'objet **MRUK** créé : *Scene Settings → Data Source* = **Device**, et cocher *Load Scene On Startup*.
   - Sur **OVRCameraRig → OVR Manager** : *Quest Features → General → Scene Support* = **Required**, et dans
     *Permission Requests On Startup*, cocher **Scene**. Toujours dans *Quest Features → General*, cocher
     **Requires System Keyboard** (inutile pour l'appairage, qui se fait sans clavier ; sans effet si décoché).
6. Copier le dossier `quest/Assets/Microduck/` de ce dépôt dans le dossier `Assets/` du projet.
   `ExportPlan.cs` apparaît dans Unity.
7. *GameObject → Create Empty*, le nommer `Microduck`. Glisser dessus, **dans cet ordre** (c'est l'ordre des
   modes) : `Canard`, `MenuMicroduck`, `ExportPlan`, `ModeAtelier`, `ModeVerite`, `ModeDessin`, `ModeDanse`,
   `ModeCanard`, `ModeJumeau`. Dans l'inspecteur :
   - **Canard → Adresse** et **Code** : laisser **vides**. On les tape **dans le casque** (appairage, ci-dessous) :
     changer de canard (le PC aujourd'hui, le vrai canard plus tard) ne demande pas de recompiler ;
   - **Export Plan → Nom Du Lieu** : `Maison` (ou le nom du lieu) ;
   - **Menu Microduck → Main Droite** : laisser vide, il la trouve seul.
8. *Edit → Project Settings → Player → Android* : *Company Name* = ton nom ; vérifier que le *Package Name* vaut par
   exemple `com.raphaelgrj.microduckscan`. Pour l'envoi au canard plus tard, mettre aussi *Allow downloads over
   HTTP* = **Always allowed** (le canard parle en http sur le réseau local).
   Toujours dans *Player → Android*, section **Icon** : glisser `Assets/Microduck/Icone/microduck.png` dans les
   cases d'icône (le même logo que l'appli du téléphone).
9. Brancher le Quest en USB-C et accepter « Autoriser le débogage USB » dans le casque. Puis *File → Build Profiles*
   → **Build And Run**. L'appli se lance dans le casque ; plus tard, on la retrouve dans *Bibliothèque → Sources
   inconnues*.

Le kit Meta change souvent de version. Si Unity affiche une erreur rouge sur un des scripts, envoie-moi le texte
exact et je corrige. Ils lisent le relevé de façon tolérante, mais je n'ai pas pu les compiler ici.

## 2. Le scan (dans le casque)

1. **Avant** : *Paramètres du Quest → Environnement physique → Configuration de l'espace* → **Configurer** la pièce.
   Fais le tour lentement, puis **ajoute les meubles** proposés et ceux qui manquent : canapé, table, lit,
   rangements… Ce sont eux qui deviennent les obstacles du canard. Recommence pour chaque pièce, à la suite, sans
   réinitialiser le suivi.
2. Si tu as imprimé des marqueurs (voir plus bas), colle-les **avant** cette étape.
3. Lance **Microduck Scan**. Tu vois la pièce (passthrough) et une petite **boule orange** au bout de la manette
   droite : c'est le pointeur.
4. Suis les consignes affichées. La **gâchette** note le point où se trouve la boule :
   1. **le chargeur** : pose la boule au sol, là où le canard s'assoit pour se recharger. Pas encore de canard ? Là
      où tu poseras sa station ;
   2. **devant** : un point au sol à ~50 cm devant le chargeur, là où le canard regarde quand il est dessus. C'est le
      « devant » de tout le plan ;
   3. **l'entrée** : au sol, au pas de la porte par laquelle on rentre (il s'en servira pour t'attendre) ;
   4. puis **chaque marqueur, dans l'ordre de leurs numéros** : la boule au centre du marqueur.
   - **B** annule le dernier point.
   - **A** exporte. Le message « Fichier écrit » confirme.
5. Tu peux relancer l'appli et réexporter à tout moment (marqueurs ajoutés plus tard…). Le relevé du Quest, lui, est
   gardé.

## 3. Récupérer le fichier sur le PC

- **MQDH** : *Device Manager → File Manager* →
  `Android/data/com.raphaelgrj.microduckscan/files/` → télécharger `microduck-scan-….json`.
- Ou en ligne de commande, dans un terminal où `adb` est disponible (il est fourni avec MQDH) :
  ```
  adb pull /sdcard/Android/data/com.raphaelgrj.microduckscan/files/ .
  ```

## 4. Voir le plan tout de suite (PC, sans canard)

```
cd ~/microduck-brain
bash ~/run-brain.sh plan_quest.py ~/microduck-scan-20261010-1530.json ~/plan-maison.json ~/plan-maison.png
```

- `plan-maison.png` montre ce que le canard verra :
  - en clair, le libre ;
  - en sombre, les obstacles entre 3 et 30 cm de haut ;
  - en orange, le chargeur ; en vert, l'entrée ; en bleu, les marqueurs.
  - Le devant du chargeur est en haut.
- Les avertissements éventuels s'affichent, par exemple « marqueur 2 : aucun mur à moins de 15 cm ».
- `plan-maison.json` s'importe déjà dans la **démo** de l'appli : *Réglages → Lieux → Maison → Remplacer le plan*.
  Tu vois ainsi ta maison dans l'appli.

## 5. Dans le canard (à la livraison)

*Réglages → Lieux →* le lieu → **Importer un plan (scan Quest)** → choisir le `microduck-scan-….json`. Le canard le
convertit lui-même. Si l'adresse et le code sont renseignés dans l'appli Quest, le bouton A l'envoie directement.

## Changer de carte, déménager

- **Un plan par lieu.** Les lieux (*Réglages → Lieux*) se reconnaissent au Wi-Fi. Dans un nouveau logement, le canard
  crée un nouveau lieu tout seul : on y importe le nouveau scan. L'ancien lieu garde son plan (*Archiver*) ou
  disparaît avec (*Supprimer*).
- **Meubles déplacés, pièce refaite** : refaire la Configuration de l'espace de la pièce, réexporter, puis *Remplacer
  le plan*.
- **Sauvegarde** : les plans font partie de la sauvegarde du canard. *Exporter le plan* garde aussi un fichier à part,
  réimportable tel quel.

## Les marqueurs (conseillés)

Le canard se situe sur le plan grâce à son capteur de distance. Mais au démarrage hors du chargeur, ou si on l'a
porté ailleurs, plusieurs endroits se ressemblent. Un **marqueur** vu par sa caméra lui donne sa position exacte.

- Imprimer la page : `bash ~/run-brain.sh marqueurs.py imprimer`, puis imprimer `marqueurs_a_imprimer.png` en
  **taille réelle** (100 %). Les carrés noirs doivent mesurer 10 cm.
- Coller chaque marqueur bien à plat, **en bas d'un mur**, le centre à ~10-12 cm du sol (la caméra du canard est
  basse) : au moins un par pièce, là où il passe souvent.
- Les noter dans l'appli Quest dans l'ordre de leurs numéros (étape 4 du scan).

---

# Le canard jumeau (sans le canard)

Le canard simulé par `duck-sim` sur le PC apparaît dans ta pièce, à l'échelle réelle. Ce sont **ses vrais logiciels**
qui le font vivre : les daemons de Pollen, son cerveau (`canard.py`) et son appli. Tu le pilotes depuis le téléphone
(télécommande, « va là », station, ronde, chasse au trésor...) et tu le vois faire, chez toi.

## Ce qu'il faut

1. **Sur le PC (WSL)** : mettre les scripts à jour, puis tout lancer d'une commande.
   ```
   cd ~/microduck-brain && git pull && cp scripts-wsl/*.sh ~/
   bash ~/jumeau.sh maison           # TA maison (plan du lieu actuel) ; ou : bash ~/jumeau.sh testball (appartement)
   ```
   `jumeau.sh` lance `duck-sim` puis le cerveau avec son appli, **sans Home Assistant** (un canard simulé ne doit pas
   allumer tes vraies lampes ; `--avec-ha` pour l'avoir). Depuis le téléphone, *Réglages → Casque* : lancer la balle,
   remettre le canard sur son chargeur, **changer de scène** (le simulateur et le cerveau redémarrent tout seuls).
   Ctrl+C arrête tout.
   La scène `maison` est générée depuis le plan importé (scan Quest) : murs et meubles deviennent des boîtes. Son
   capteur de distance simulé voit donc tes vrais meubles, et le canard les contourne sous tes yeux.
2. **Le Quest doit joindre l'appli du canard sur le PC**. WSL2 est derrière un réseau privé : il faut le rendre
   visible sur le Wi-Fi, une fois pour toutes.
   - Dans `C:\Users\<toi>\.wslconfig` (à créer s'il n'existe pas) :
     ```
     [wsl2]
     networkingMode=mirrored
     ```
     puis, dans PowerShell, `wsl --shutdown` et relancer Ubuntu. WSL prend alors l'adresse du PC.
   - Ouvrir le port 8090, dans PowerShell **administrateur** :
     ```
     New-NetFirewallRule -DisplayName "Microduck appli" -Direction Inbound -LocalPort 8090 -Protocol TCP -Action Allow
     Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -DefaultInboundAction Allow
     ```
     (la seconde ligne autorise les connexions entrantes vers WSL : c'est l'identifiant de WSL chez Microsoft).
   - Appairer le casque (joystick gauche) avec l'adresse et le code affichés dans *Réglages → Casque* de l'appli
     (l'adresse est celle du PC une fois WSL en mode « mirrored »).
3. **Le mode Jumeau** : X / Y sur la manette gauche jusqu'à « Jumeau ».
   - Scène `maison` + plan avec repère Quest : le canard est posé tout seul au bon endroit (le chargeur du scan).
   - Autre scène : il demande où il est né. Gâchette au sol à cet endroit, puis gâchette devant lui (sa direction).
     **B** recommence.

## Jouer avec lui

| Geste | Effet |
| --- | --- |
| Gâchette tenue, puis relâchée en lançant | La balle part de ta main avec ta vitesse. Il la voit avec sa caméra simulée et joue avec. |
| Grip tenu, la manette sur sa tête | Une caresse par seconde (ce que ses servos sentiraient sur le vrai). |
| L'appli du téléphone | Tout marche comme avec le vrai canard ; les autres modes du casque (Atelier, Vérité, Dessin...) aussi. |

Ses sons s'affichent en note flottante au-dessus de sa tête (« ♪ chirp »). Pour les entendre, mets les fichiers des
sons du canard dans `Assets/Resources/SonsCanard/` (`chirp.wav`, `coo.wav`...) : le casque les joue depuis sa tête.

## Ses couleurs, en direct

Le canard du casque porte le **schéma actif de son appli** (design space). Change de schéma sur le téléphone : le
canard change de couleurs dans ta pièce, en une seconde. Avec **👓 Voir dans le casque** (design space, carte
« Schémas de couleurs »), chaque retouche du téléphone apparaît aussitôt sur le canard du casque, avant même
d'enregistrer.

Et dans l'autre sens, **A** passe en mode Couleurs :

| Geste | Effet |
| --- | --- |
| Viser une pièce avec la manette | Son nom s'affiche (dessus de la tête, coques, pieds...). |
| Joystick gauche / droite | Choisir la couleur : tes bobines, tes couleurs gardées, puis la palette de l'appli. La pastille au bout de la manette la montre. |
| Gâchette | Peindre la pièce visée. Les pièces achetées (servos, électronique) ne se peignent pas. |
| Joystick haut / bas | Passer d'un schéma enregistré à l'autre (puis « couleurs d'origine »). |
| Grip | Enregistrer : un schéma « Casque 1 », « Casque 2 »... apparaît dans l'appli, prêt pour la fiche d'impression. |
| A | Retour au jeu. |

Sans simulateur, le canard reste debout, immobile : pratique pour choisir ses couleurs posé sur la table.

## Ce qui reste faux

- Sa **caméra voit le monde simulé** (des boîtes), pas ta pièce : il ne te reconnaît pas, ni le chat. Seule la balle
  virtuelle marche avec la vision.
- On ne le touche pas vraiment : la caresse est un bouton.
- Sa démarche est celle de la simulation (même politique que sur le robot, mais le transfert au réel n'est pas garanti).
