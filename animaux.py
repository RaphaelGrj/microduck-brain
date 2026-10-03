#!/usr/bin/env python3
"""Detection d'objets COCO (chat, chien, personne...) par un petit YOLO exporte en ONNX, via cv2.dnn
(aucune dependance de plus que opencv). La couleur ne suffit pas pour un chat : il faut un reseau.

Le modele n'est PAS dans le depot (poids : ~12 Mo pour YOLOv8n). Il se place dans
`~/microduck-brain/modeles/yolov8n.onnx` (ou on passe un autre chemin). Formats de sortie geres :
YOLOv8 / YOLO11 (1, 84, N) et YOLOv5 / v7 (1, N, 85, avec "objectness").

Usage : bash ~/run-brain.sh animaux.py <image.png|jpg> [classe=cat] [modele.onnx] [--rogner]
        bash ~/run-brain.sh animaux.py --test          (decodage sur un tenseur synthetique, sans modele)
"""
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

MODELE_PAR_DEFAUT = Path(__file__).parent / "modeles" / "yolov8n.onnx"

COCO = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
        "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
        "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
        "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
        "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
        "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
        "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
        "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
        "scissors", "teddy bear", "hair drier", "toothbrush"]


@dataclass
class Objet:
    classe: str
    score: float
    x: float          # boite dans l'image d'origine, en pixels
    y: float
    w: float
    h: float

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def pied(self):
        """Point de contact probable avec le sol : milieu du bord bas de la boite."""
        return self.x + self.w / 2, self.y + self.h


def pretraiter(img, taille=640):
    """Letterbox carre (bandes grises, proportions conservees). Renvoie (blob, echelle, (dx, dy))."""
    h, w = img.shape[:2]
    e = taille / max(h, w)
    nw, nh = round(w * e), round(h * e)
    cadre = np.full((taille, taille, 3), 114, np.uint8)
    dx, dy = (taille - nw) // 2, (taille - nh) // 2
    cadre[dy:dy + nh, dx:dx + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    blob = cv2.dnn.blobFromImage(cadre, 1 / 255.0, (taille, taille), swapRB=True, crop=False)
    return blob, e, (dx, dy)


def decoder(sortie, echelle, decalage, taille_img, classes=None, seuil=0.35, seuil_nms=0.45):
    """Transforme la sortie brute du reseau en liste d'`Objet` (apres suppression des doublons).

    `classes` : noms COCO a garder (None = toutes). `taille_img` = (hauteur, largeur) de l'image d'origine."""
    sortie = np.asarray(sortie)
    if sortie.ndim == 3:
        sortie = sortie[0]
    if sortie.shape[0] < sortie.shape[1]:          # YOLOv8 : (84, N) -> (N, 84)
        sortie = sortie.T
        scores_classes = sortie[:, 4:]
    else:                                          # YOLOv5 / v7 : (N, 85), score = objectness * classe
        scores_classes = sortie[:, 5:] * sortie[:, 4:5]
    voulues = None if classes is None else {COCO.index(c) for c in classes}
    ids = scores_classes.argmax(axis=1)
    scores = scores_classes[np.arange(len(ids)), ids]
    garde = scores >= seuil
    if voulues is not None:
        garde &= np.isin(ids, list(voulues))
    if not garde.any():
        return []
    boites, scores, ids = sortie[garde, :4], scores[garde], ids[garde]
    h_img, w_img = taille_img
    dx, dy = decalage
    xywh = []
    for cx, cy, w, h in boites:                    # centre/taille dans le carre letterbox -> coin/taille image
        x0, y0 = (cx - w / 2 - dx) / echelle, (cy - h / 2 - dy) / echelle
        w0, h0 = w / echelle, h / echelle
        x0, y0 = max(0.0, x0), max(0.0, y0)
        xywh.append([x0, y0, min(w0, w_img - x0), min(h0, h_img - y0)])
    garde_nms = cv2.dnn.NMSBoxes(xywh, scores.tolist(), seuil, seuil_nms)
    return [Objet(COCO[int(ids[i])], float(scores[i]), *xywh[int(i)]) for i in np.array(garde_nms).flatten()]


class DetecteurCoco:
    def __init__(self, modele=MODELE_PAR_DEFAUT, taille=640):
        modele = Path(modele)
        if not modele.exists():
            raise FileNotFoundError(f"modele absent : {modele} (voir l'en-tete de animaux.py)")
        self.net = cv2.dnn.readNetFromONNX(str(modele))
        self.taille = taille

    def detect(self, img, classes=("cat",), seuil=0.35, rogner_noir=False):
        """`rogner_noir` : retire les bandes noires haut/bas (captures d'ecran de telephone) avant la detection ;
        les boites sont renvoyees dans les coordonnees de l'image d'origine."""
        y0 = 0
        if rogner_noir:
            lignes = np.where(img.mean(axis=(1, 2)) > 8)[0]
            if len(lignes):
                y0 = int(lignes[0])
                img_utile = img[y0:int(lignes[-1]) + 1]
            else:
                img_utile = img
        else:
            img_utile = img
        blob, e, dec = pretraiter(img_utile, self.taille)
        self.net.setInput(blob)
        sortie = self.net.forward()
        objets = decoder(sortie, e, dec, img_utile.shape[:2], classes, seuil)
        for o in objets:
            o.y += y0
        return objets


def _test_synthetique():
    """Un faux tenseur YOLOv8 : un chat net, un doublon du meme chat, un chien et du bruit faible."""
    taille = 640
    n = 8400
    sortie = np.zeros((1, 84, n), np.float32)
    def poser(i, cx, cy, w, h, classe, score):
        sortie[0, 0:4, i] = (cx, cy, w, h)
        sortie[0, 4 + COCO.index(classe), i] = score
    poser(10, 320, 400, 100, 140, "cat", 0.9)
    poser(11, 322, 402, 104, 144, "cat", 0.7)      # doublon : doit disparaitre au NMS
    poser(12, 100, 100, 50, 50, "dog", 0.8)
    poser(13, 500, 500, 40, 40, "cat", 0.1)        # sous le seuil
    # image d'origine portrait 360x640 : echelle 1.0, bandes laterales de (640-360)/2 = 140 px
    obj = decoder(sortie, 1.0, (140, 0), (640, 360), classes=("cat",))
    assert len(obj) == 1, obj
    o = obj[0]
    assert o.classe == "cat" and abs(o.score - 0.9) < 1e-4
    assert abs(o.cx - (320 - 140)) < 1e-3 and abs(o.y - 330) < 1e-3 and abs(o.h - 140) < 1e-3, o
    tout = decoder(sortie, 1.0, (140, 0), (640, 360), classes=None)
    assert {x.classe for x in tout} == {"cat", "dog"}, tout
    print("decodage OK : 1 chat apres NMS, doublon et bruit elimines, chien vu avec classes=None ;"
          f" pied de la boite = ({o.pied[0]:.0f},{o.pied[1]:.0f}) px")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _test_synthetique()
        return
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    img = cv2.imread(sys.argv[1])
    if img is None:
        raise SystemExit(f"image illisible : {sys.argv[1]}")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    classe = args[1] if len(args) > 1 else "cat"
    modele = args[2] if len(args) > 2 else MODELE_PAR_DEFAUT
    objets = DetecteurCoco(modele).detect(img, classes=(classe,), rogner_noir="--rogner" in sys.argv)
    print(f"{len(objets)} {classe} detecte(s)")
    for o in objets:
        print(f"  score {o.score:.2f}  boite x={o.x:.0f} y={o.y:.0f} w={o.w:.0f} h={o.h:.0f}  pied=({o.pied[0]:.0f},{o.pied[1]:.0f})")
        cv2.rectangle(img, (int(o.x), int(o.y)), (int(o.x + o.w), int(o.y + o.h)), (0, 255, 0), 2)
    sortie = Path(sys.argv[1]).with_suffix(".detecte.png")
    cv2.imwrite(str(sortie), img)
    print("image annotee :", sortie)


if __name__ == "__main__":
    main()
