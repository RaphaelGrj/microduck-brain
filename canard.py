#!/usr/bin/env python3
"""Lanceur du canard complet : le cerveau (brain.py) avec TOUT ce qui est disponible autour de lui.

  - robotd (obligatoire) : ROBOTD_SOCK, ou le socket de duck-sim ;
  - capteur de distance (tofd, TOFD_SOCK) : promenade sure, main tendue, jeu, coin de sieste - sans lui le canard ne
    marche jamais (prudence) ;
  - camera (MICRODUCK_FRAME_URL, route /frame de mediad) : detection de mouvement pour "1-2-3 soleil", analysee
    seulement pendant le jeu ; veille de la balle (taquineries : pousser, mime de vol), 2 images par seconde ;
  - veille du chat (YOLO, `--chat`) : seulement si le modele est present ET si la machine le supporte (CPU du RK3566 probablement trop lent : a porter sur son NPU) ;
  - micro (`--micro`, ALSA via arecord, MICRODUCK_MICRO) : reflexes sonores (audio.py) - NON TESTE sur le robot ;
  - Home Assistant (`ha.toml`) : evenements de la maison, etat du canard, routines [cerveau] (heures calmes, bonjour) ;
  - memoire persistante (memoire.py).

Tout est analyse SUR le canard (images, sons, distances) ; seul Home Assistant, s'il est configure, recoit des etats
(batterie, humeur, position...) et envoie les evenements de la maison. Aucune image ni aucun son ne sort du robot.

Usage : bash ~/run-brain.sh canard.py [ha.toml] [duree_s] [--sans-ha] [--sans-camera] [--chat] [--micro]
"""
import os
import sys
from pathlib import Path

import brain
import memoire
import pont_ha
import tof as tof_mod


def verifier_local(url_camera):
    """Regle du projet : tout tourne SUR le canard, aucune image ni aucun son ne part vers un autre appareil pour etre
    analyse. La camera doit donc etre lue en local (boucle locale), sinon on refuse de demarrer."""
    from urllib.parse import urlparse
    hote = urlparse(url_camera).hostname
    if hote not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit(f"camera lue sur {hote!r} : refuse. Le cerveau tourne SUR le canard et lit sa camera en local "
                         "(MICRODUCK_FRAME_URL=http://127.0.0.1:8080/frame) ; aucune image ne quitte le robot.")


def lire_heure(v):
    """12 ou "12:30" -> (12, 0) / (12, 30) ; None si illisible."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int) and 0 <= v < 24:
        return (v, 0)
    h, _, m = str(v).partition(":")
    if h.strip().isdigit() and (m.strip().isdigit() or not m) and 0 <= int(h) < 24 and 0 <= int(m or 0) < 60:
        return (int(h), int(m or 0))
    return None


def assembler(client, args, log=print, cfg=None, cerveau=None):
    """-> dict(extras, sources, crochets, options, pont, fils) ; `cfg` = config HA deja lue (ou None), `cerveau` =
    section [cerveau] du fichier de config (lue meme sans Home Assistant : le canard vit sans lui)."""
    cerveau = cerveau if cerveau is not None else ((cfg or {}).get("cerveau") or {})
    extras, sources, crochets, fils = {"memoire": memoire.Memoire(ecriture_differee=True)}, [], [], []
    extras["autotest"] = cerveau.get("autotest", True)     # auto-test au premier reveil de la journee (diagnostic.py)
    extras["circadien"] = cerveau.get("circadien", True)   # vivacite selon l'heure du jour (Brain.vivacite)
    extras["garde"] = bool(cerveau.get("garde", False))    # maison vide + voix/choc -> evenement HA (opt-in)
    repas = [h for h in (lire_heure(r) for r in cerveau.get("repas", [])) if h is not None]
    if repas:
        extras["repas"] = repas                             # heures des repas : il apprend ou l'on mange
    if tof_mod.SOCK_TOF.exists():
        capteur = tof_mod.Tof(tof_mod.beams_du_robot(client))
        extras["tof"], fils = capteur, fils + [capteur]
        log(f"capteur de distance : {tof_mod.SOCK_TOF}")
    else:
        log(f"capteur de distance ABSENT ({tof_mod.SOCK_TOF}) : le canard ne marchera pas (prudence)")
    if "--sans-camera" not in args:
        import mouvement
        import vision
        verifier_local(vision.FRAME_URL)
        import balle
        veille_mvt = mouvement.VeilleMouvement(vision.grab_frame)
        veille_balle = balle.VeilleBalle(vision.grab_frame)
        extras["mouvement"], extras["balle"] = veille_mvt, veille_balle
        extras["camera_test"] = lambda: vision.grab_frame(timeout=2.0) is not None    # auto-test : une image arrive
        extras["luminosite"] = lambda: vision.luminosite(vision.grab_frame(timeout=2.0))   # lumiere oubliee
        fils += [veille_mvt, veille_balle]
        crochets.append(veille_balle.etat_robot_hook)
        log(f"camera : {vision.FRAME_URL} (mouvement pendant les jeux ; balle 2 fois par seconde)")
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
    if "--micro" in args:
        import audio
        commandes = None
        modele = cerveau.get("modele_vosk")
        if modele and Path(modele).expanduser().exists():
            import commandes as cmd
            maison = {a["voix"]: a["voix_evt"] for a in (cfg or {}).get("actions", []) if a.get("voix")}
            commandes = cmd.Commandes(cmd.fabrique_vosk(Path(modele).expanduser()), nom=cerveau.get("nom", "canard"),
                                      maison=maison)
            log(f"commandes vocales locales : '{cerveau.get('nom', 'canard')} ...' (modele {modele}, hors ligne)")
        elif modele:
            log(f"commandes vocales : modele absent ({modele})")
        voix = audio.VoixPropre()
        extras["voix"] = voix                   # le cerveau signale ses propres sons : le micro ne les analyse pas
        micro = audio.MicroAlsa(peripherique=os.environ.get("MICRODUCK_MICRO"), commandes=commandes, voix=voix)
        fils.append(micro)
        sources.append(micro.source)
        log(f"micro : {os.environ.get('MICRODUCK_MICRO') or 'peripherique ALSA par defaut'} (reflexes sonores)")
    pont, options = None, pont_ha.options_cerveau({"cerveau": cerveau})
    if cfg is not None:
        pont = pont_ha.PontHA(cfg, pont_ha.lire_jeton(cfg), log=log)
        sources.append(pont.source)
        crochets.append(pont.photographier)
        log("Home Assistant : " + cfg["url"])
    if options:
        log(f"routines : {options}")
    return {"extras": extras, "sources": sources, "crochets": crochets, "options": options, "pont": pont, "fils": fils}


def main():
    from poc_robotd_client import RobotdClient, SOCK_PATH
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    chemin = Path(args[0]) if args else Path(__file__).parent / "ha.toml"
    duree = float(args[1]) if len(args) > 1 else 10 * 365 * 86400.0
    cfg, cerveau = None, {}
    if chemin.exists():
        pont_ha.avertir_si_non_ignore(chemin)
        cfg = pont_ha.lire_config(chemin)
        cerveau = cfg.get("cerveau") or {}
        if "--sans-ha" in sys.argv:
            cfg = None
        elif cfg["url"] is None:
            print(f"{chemin} : pas d'URL Home Assistant, pont desactive", flush=True)
            cfg = None
    c = RobotdClient(SOCK_PATH)
    hz = ((cfg or {}).get("reseau") or {}).get("etat_hz")
    c.request("robot.subscribe", {"hz": int(hz)} if isinstance(hz, int) and 10 <= hz <= 50 else {})
    a = assembler(c, sys.argv[1:], log=lambda m: print(m, flush=True), cfg=cfg, cerveau=cerveau)
    for f in a["fils"]:
        f.start()
    if a["pont"] is not None:
        a["pont"].demarrer()

    def source():
        return [e for s in a["sources"] for e in s()]

    # systemctl stop / redemarrage : SIGTERM -> sortie normale (le canard se releve, la memoire est sauvee) au lieu
    # d'une mort brutale qui perdrait ce qui a change depuis la derniere sauvegarde
    import signal
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

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
        mem = a["extras"].get("memoire")
        if mem is not None and hasattr(mem, "fermer"):
            mem.fermer()


if __name__ == "__main__":
    main()
