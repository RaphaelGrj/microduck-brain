#!/usr/bin/env python3
"""Fabrique une scene de test avec une AFFICHE de ton chat (photo) debout dans l'arene, pour tester en simulation la
chaine camera -> detection -> cerveau (le simulateur n'a pas de chat).

La photo est recadree (bandes noires de capture d'ecran retirees) et copiee dans ~/.cache/duck-sim/cat/ ; la scene
`scene_arena_cat.xml` est ecrite dans le dossier du modele du fork (indispensable : les chemins des maillages y sont
relatifs) mais est ignoree par git, comme la photo (donnees personnelles, depot public).

Usage : bash ~/run-brain.sh make_cat_scene.py photos_chat/chat_2.jpg [distance=1.2] [hauteur_m=0.30]
Puis  : bash ~/run-scene.sh arena_chat
"""
import sys
from pathlib import Path

import cv2

MODELE = Path.home() / "microduck_rl/src/mjlab_microduck/robot/microduck"
CACHE = Path.home() / ".cache/duck-sim/cat"


def main():
    photo = Path(sys.argv[1])
    distance = float(sys.argv[2]) if len(sys.argv) > 2 else 1.2
    hauteur = float(sys.argv[3]) if len(sys.argv) > 3 else 0.30
    img = cv2.imread(str(photo))
    if img is None:
        raise SystemExit(f"photo illisible : {photo}")
    lignes = [i for i in range(img.shape[0]) if img[i].mean() > 8]       # bandes noires de la capture d'ecran
    img = img[lignes[0]:lignes[-1] + 1]
    if img.shape[0] > 512:                                      # texture raisonnable : l'affiche couvre ~100 px de l'image
        e = 512 / img.shape[0]
        img = cv2.resize(img, (round(img.shape[1] * e), 512), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    CACHE.mkdir(parents=True, exist_ok=True)
    png = CACHE / "cat_poster.png"
    cv2.imwrite(str(png), img)
    largeur = hauteur * w / h
    xml = f"""<mujoco model="scene_arena_cat">
    <!-- GENERE par make_cat_scene.py (ne pas versionner) : arene + affiche de la photo du chat a {distance} m devant le
         canard, face a lui. Affiche de {largeur:.2f} x {hauteur:.2f} m (un vrai chat assis : ~0,25-0,30 m). -->
    <include file="scene_arena_testball.xml" />
    <asset>
        <texture type="2d" name="chat_affiche" file="{png}" />
        <material name="chat_affiche" texture="chat_affiche" texuniform="false" />
    </asset>
    <worldbody>
        <!-- plan vertical (une boite etire la texture : stries) ; axe local x -> -y monde (vers la droite vu du canard),
             axe local y -> haut, donc la normale pointe vers le canard (-x). -->
        <geom name="chat_affiche" type="plane" size="{largeur / 2:.4f} {hauteur / 2:.4f} 0.01" xyaxes="0 -1 0 0 0 1"
              pos="{distance} 0 {hauteur / 2}" material="chat_affiche" contype="0" conaffinity="0" />
    </worldbody>
</mujoco>
"""
    sortie = MODELE / "scene_arena_cat.xml"
    sortie.write_text(xml)
    print(f"affiche {largeur:.2f} x {hauteur:.2f} m ({w}x{h} px) -> {png}\nscene -> {sortie}")


if __name__ == "__main__":
    main()
