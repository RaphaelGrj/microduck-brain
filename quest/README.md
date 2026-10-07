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
     *Permission Requests On Startup*, cocher **Scene**.
6. Copier le dossier `quest/Assets/Microduck/` de ce dépôt dans le dossier `Assets/` du projet.
   `ExportPlan.cs` apparaît dans Unity.
7. *GameObject → Create Empty*, le nommer `Microduck`, puis glisser `ExportPlan.cs` dessus. Dans l'inspecteur :
   - **Nom Du Lieu** : `Maison` (ou le nom du lieu) ;
   - **Adresse Canard** et **Code Appli** : laisser **vides** pour l'instant (pas encore de canard). Plus tard :
     `http://<adresse du canard>:8090` et le code de l'appli, et le scan arrivera directement dans le canard ;
   - **Main Droite** : laisser vide, il la trouve seul.
8. *Edit → Project Settings → Player → Android* : *Company Name* = ton nom ; vérifier que le *Package Name* vaut par
   exemple `com.raphaelgrj.microduckscan`. Pour l'envoi au canard plus tard, mettre aussi *Allow downloads over
   HTTP* = **Always allowed** (le canard parle en http sur le réseau local).
9. Brancher le Quest en USB-C et accepter « Autoriser le débogage USB » dans le casque. Puis *File → Build Profiles*
   → **Build And Run**. L'appli se lance dans le casque ; plus tard, on la retrouve dans *Bibliothèque → Sources
   inconnues*.

Le kit Meta change souvent de version. Si Unity affiche une erreur rouge sur `ExportPlan.cs`, envoie-moi le texte
exact et je corrige le script. Il lit le relevé de façon tolérante, mais je n'ai pas pu le compiler ici.

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
