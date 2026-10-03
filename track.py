#!/usr/bin/env python3
"""Suivi du regard : le canard tourne la tete pour garder une cible coloree au centre de l'image.

Boucle perception -> action en deux parties :
  - un thread de vision (HTTP /frame + detection), ~5-7 detections/s ;
  - la boucle principale, cadencee sur le flux robot.state (50 Hz), qui envoie robot.head.

Les signes et gains (pixel -> commande de tete) sont CALIBRES au demarrage en observant le
deplacement de la cible quand on bouge la tete : pas de convention a deviner.

Usage : bash ~/run-brain.sh track.py [couleur=orange] [duree_s=12]
"""
import math
import sys
import threading
import time

import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

CENTRE_X, CENTRE_Y = vision.WIDTH / 2, vision.HEIGHT / 2
YAW_MAX, PITCH_MIN, PITCH_MAX = 1.2, -0.5, 1.0


class Vision(threading.Thread):
    """Derniere detection de la couleur cible, mise a jour en continu."""

    def __init__(self, couleur):
        super().__init__(daemon=True)
        self.couleur = couleur
        self.lock = threading.Lock()
        self.last = None  # (t_monotonic, Detection | None)
        self.run_flag = True

    def run(self):
        while self.run_flag:
            try:
                t_debut = time.monotonic()           # l'image reflete l'etat de la tete A CET INSTANT
                img = vision.grab_frame()
                dets = vision.detect(img, couleurs=[self.couleur], aire_min=40)
                with self.lock:
                    self.last = (time.monotonic(), dets[0] if dets else None, t_debut)
            except Exception:
                time.sleep(0.2)

    def get(self, max_age=0.5):
        with self.lock:
            if self.last and time.monotonic() - self.last[0] <= max_age:
                return self.last[1]
        return None

    def get_apres(self, t_min):
        """Detection dont la capture a DEBUTE apres t_min (sinon None) -> pas d'image perimee."""
        with self.lock:
            if self.last and self.last[2] > t_min:
                return self.last
        return None

    def nouvelle_detection(self, apres):
        """Attend (max 1 s) une detection posterieure a `apres` ; renvoie Detection | None."""
        t_fin = time.monotonic() + 1.0
        while time.monotonic() < t_fin:
            with self.lock:
                if self.last and self.last[0] > apres:
                    return self.last[1]
            time.sleep(0.02)
        return None


class Tete:
    """Commande de tete, renvoyee a 50 Hz tant qu'on appelle pas()."""

    def __init__(self, client):
        self.c = client
        self.yaw = 0.0
        self.pitch = 0.0

    def pas(self):
        self.c.read_state_frame()  # cadence = flux d'etat
        self.c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": self.pitch,
                                     "head_yaw": self.yaw, "head_roll": 0.0})

    def tenir(self, secs):
        t0 = time.monotonic()
        while time.monotonic() - t0 < secs:
            self.pas()


def moyenne_detection(vis, tete, secs):
    """Tient la tete `secs` secondes puis moyenne les detections obtenues pendant la 2e moitie."""
    tete.tenir(secs / 2)
    t_ref = time.monotonic()
    pts = []
    while time.monotonic() - t_ref < secs / 2:
        tete.pas()
        d = vis.get(max_age=0.3)
        if d is not None:
            pts.append((d.cx, d.cy))
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def calibre(vis, tete, pas_rad=0.25):
    """Renvoie (px_par_rad_yaw, px_par_rad_pitch) signes : deplacement de la cible dans l'image
    par radian de commande. Essaie les deux sens si la cible sort du champ."""
    ref = moyenne_detection(vis, tete, 1.0)
    if ref is None:
        raise SystemExit("cible non visible au depart : impossible de calibrer")
    res = {}
    for axe, attr in (("yaw", "yaw"), ("pitch", "pitch")):
        for signe in (-1.0, +1.0):
            setattr(tete, attr, signe * pas_rad)
            m = moyenne_detection(vis, tete, 1.6)
            setattr(tete, attr, 0.0)
            tete.tenir(1.0)
            if m is not None:
                i = 0 if axe == "yaw" else 1
                res[axe] = (m[i] - ref[i]) / (signe * pas_rad)
                break
        else:
            raise SystemExit(f"calibration {axe} impossible : cible perdue dans les deux sens")
    return res["yaw"], res["pitch"]


def main():
    couleur = sys.argv[1] if len(sys.argv) > 1 else "orange"
    duree = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
    c = RobotdClient(SOCK_PATH)
    c.request("robot.subscribe", {})
    vis = Vision(couleur)
    vis.start()
    tete = Tete(c)
    tete.tenir(0.5)

    d0 = vis.nouvelle_detection(time.monotonic())
    if d0 is None:
        raise SystemExit(f"aucune {couleur} visible au depart")
    print(f"depart : {couleur} en ({d0.cx:.0f},{d0.cy:.0f}) rayon {d0.rayon:.0f}px", flush=True)

    k_yaw, k_pitch = calibre(vis, tete)
    print(f"calibration : cible bouge de {k_yaw:+.0f} px par rad de yaw, {k_pitch:+.0f} px par rad de pitch",
          flush=True)
    if abs(k_yaw) < 50 or abs(k_pitch) < 50:
        raise SystemExit("calibration suspecte (reponse trop faible)")

    # Controle proportionnel AVEC attente de stabilisation. Les images arrivent avec 0.15-0.25 s de
    # retard et la tete a sa propre inertie : corriger a chaque detection integre plusieurs fois la
    # meme erreur et fait osciller. Apres une correction on n'accepte donc que les images dont la
    # capture a DEBUTE apres `SETTLE` secondes (la tete a fini de bouger), et on corrige une
    # fraction `gain` de l'erreur.
    gain, SETTLE = 0.5, 0.55
    t0 = time.monotonic()
    t_pret = t0                       # aucune image avant ce moment n'est digne de confiance
    trace = []
    while time.monotonic() - t0 < duree:
        tete.pas()
        r = vis.get_apres(t_pret)
        if r is None or r[1] is None:
            continue
        d = r[1]
        t_pret = time.monotonic() + SETTLE
        err_x, err_y = d.cx - CENTRE_X, d.cy - CENTRE_Y
        tete.yaw = max(-YAW_MAX, min(YAW_MAX, tete.yaw - gain * err_x / k_yaw))
        tete.pitch = max(PITCH_MIN, min(PITCH_MAX, tete.pitch - gain * err_y / k_pitch))
        trace.append((time.monotonic() - t0, err_x, err_y, tete.yaw, tete.pitch))
        print(f"  t={trace[-1][0]:4.1f}s  erreur=({err_x:+5.0f},{err_y:+5.0f}) px  "
              f"-> tete yaw={tete.yaw:+.2f} pitch={tete.pitch:+.2f}", flush=True)

    vis.run_flag = False
    try:  # image finale annotee, prise tete encore orientee sur la cible
        import cv2
        img = vision.grab_frame()
        dets = vision.detect(img, couleurs=[couleur], aire_min=40)
        cv2.line(img, (int(CENTRE_X) - 12, int(CENTRE_Y)), (int(CENTRE_X) + 12, int(CENTRE_Y)), (0, 0, 255), 2)
        cv2.line(img, (int(CENTRE_X), int(CENTRE_Y) - 12), (int(CENTRE_X), int(CENTRE_Y) + 12), (0, 0, 255), 2)
        cv2.imwrite("/home/raphael/track_final.png", vision.annotate(img, dets))
        print("image finale : ~/track_final.png (croix rouge = centre de l'image)", flush=True)
    except Exception as e:
        print("pas d'image finale :", e, flush=True)
    fin = trace[-5:] if len(trace) >= 5 else trace
    if fin:
        ex = sum(abs(t[1]) for t in fin) / len(fin)
        ey = sum(abs(t[2]) for t in fin) / len(fin)
        print(f"--- erreur moyenne sur les {len(fin)} dernieres mesures : {ex:.0f} px en x, {ey:.0f} px en y "
              f"(image {vision.WIDTH}x{vision.HEIGHT}) ---", flush=True)
    tete.yaw = tete.pitch = 0.0
    tete.tenir(1.0)


if __name__ == "__main__":
    main()
