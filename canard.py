#!/usr/bin/env python3
"""Lanceur du canard complet : le cerveau (brain.py) avec TOUT ce qui est disponible autour de lui.

  - robotd (obligatoire) : ROBOTD_SOCK, ou le socket de duck-sim ;
  - capteur de distance (tofd, TOFD_SOCK) : promenade sure, main tendue, jeu, coin de sieste - sans lui le canard ne
    marche jamais (prudence) ;
  - camera (MICRODUCK_FRAME_URL, route /frame de mediad) : detection de mouvement pour "1-2-3 soleil", analysee
    seulement pendant le jeu ;
  - veille du chat (YOLO, `--chat`) : seulement si le modele est present ET si la machine le supporte (pas un Pi 3B+) ;
  - Home Assistant (`ha.toml`) : evenements de la maison, etat du canard, routines [cerveau] (heures calmes, bonjour) ;
  - memoire persistante (memoire.py).

Usage : bash ~/run-brain.sh canard.py [ha.toml] [duree_s] [--sans-ha] [--sans-camera] [--chat]
"""
import os
import sys
from pathlib import Path

import brain
import memoire
import pont_ha
import tof as tof_mod


def assembler(client, args, log=print, cfg=None):
    """-> dict(extras, sources, crochets, options, pont, fils) ; `cfg` = config HA deja lue (ou None)."""
    extras, sources, crochets, fils = {"memoire": memoire.Memoire()}, [], [], []
    if tof_mod.SOCK_TOF.exists():
        capteur = tof_mod.Tof(tof_mod.beams_du_robot(client))
        extras["tof"], fils = capteur, fils + [capteur]
        log(f"capteur de distance : {tof_mod.SOCK_TOF}")
    else:
        log(f"capteur de distance ABSENT ({tof_mod.SOCK_TOF}) : le canard ne marchera pas (prudence)")
    if "--sans-camera" not in args:
        import mouvement
        import vision
        veille_mvt = mouvement.VeilleMouvement(vision.grab_frame)
        extras["mouvement"], fils = veille_mvt, fils + [veille_mvt]
        log(f"camera : {vision.FRAME_URL} (analysee seulement pendant les jeux)")
    if "--chat" in args:
        import animaux
        if animaux.MODELE_PAR_DEFAUT.exists():
            import chat
            import vision
            veille_chat = chat.VeilleChat(animaux.DetecteurCoco(), vision.grab_frame, memoire=extras["memoire"])
            extras["chat"], fils = veille_chat, fils + [veille_chat]
            sources.append(veille_chat.source)
            crochets.append(veille_chat.etat_robot_hook)
            log("veille du chat : active")
        else:
            log(f"veille du chat : modele absent ({animaux.MODELE_PAR_DEFAUT})")
    pont, options = None, {}
    if cfg is not None:
        options = pont_ha.options_cerveau(cfg)
        pont = pont_ha.PontHA(cfg, pont_ha.lire_jeton(cfg), log=log)
        sources.append(pont.source)
        crochets.append(pont.photographier)
        log("Home Assistant : " + cfg["url"] + (f" ; routines {options}" if options else ""))
    return {"extras": extras, "sources": sources, "crochets": crochets, "options": options, "pont": pont, "fils": fils}


def main():
    from poc_robotd_client import RobotdClient, SOCK_PATH
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    chemin = Path(args[0]) if args else Path(__file__).parent / "ha.toml"
    duree = float(args[1]) if len(args) > 1 else 10 * 365 * 86400.0
    cfg = None
    if "--sans-ha" not in sys.argv and chemin.exists():
        pont_ha.avertir_si_non_ignore(chemin)
        cfg = pont_ha.lire_config(chemin)
        if cfg["url"] is None:
            print(f"{chemin} : pas d'URL Home Assistant, pont desactive", flush=True)
            cfg = None
    c = RobotdClient(SOCK_PATH)
    hz = ((cfg or {}).get("reseau") or {}).get("etat_hz")
    c.request("robot.subscribe", {"hz": int(hz)} if isinstance(hz, int) and 10 <= hz <= 50 else {})
    a = assembler(c, sys.argv[1:], log=lambda m: print(m, flush=True), cfg=cfg)
    for f in a["fils"]:
        f.start()
    if a["pont"] is not None:
        a["pont"].demarrer()

    def source():
        return [e for s in a["sources"] for e in s()]

    def crochet(b, state):
        for f in a["crochets"]:
            f(b, state)
    try:
        brain.run(c, duree, source=source, a_chaque_tick=crochet, extras=a["extras"], **a["options"])
    finally:
        for f in a["fils"]:
            f.actif = False
        if a["pont"] is not None:
            a["pont"].stop()


if __name__ == "__main__":
    main()
