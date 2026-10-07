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


def version_du_cerveau():
    """Le commit du cerveau (affiche dans l'application, section Maintenance) : git, sinon le fichier VERSION ecrit
    par deploy/robot/mettre_a_jour.sh."""
    import subprocess
    try:
        v = subprocess.run(["git", "-C", str(Path(__file__).parent), "log", "-1", "--format=%h %cs"],
                           capture_output=True, text=True, timeout=3).stdout.strip()
        if v:
            return v
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        return (Path(__file__).parent / "VERSION").read_text().strip() or None
    except OSError:
        return None


def robotd_neuf():
    """Une connexion robotd a part (page Comportements de l'appli) : la boucle du cerveau garde la sienne."""
    from poc_robotd_client import SOCK_PATH, RobotdClient
    return RobotdClient(SOCK_PATH)


def assembler(client, args, log=print, cfg=None, cerveau=None, appli_cfg=None, brut=None):
    """-> dict(extras, sources, crochets, options, pont, fils) ; `cfg` = config HA deja lue (ou None), `cerveau` =
    section [cerveau] du fichier de config (lue meme sans Home Assistant : le canard vit sans lui)."""
    cerveau = cerveau if cerveau is not None else ((cfg or {}).get("cerveau") or {})
    import appli as appli_mod
    import lieux as lieux_tmp
    import reglages
    # une sauvegarde restauree depuis l'application s'applique ici, avant que la memoire soit lue
    appli_mod.appliquer_restaurations([memoire.CHEMIN_DEFAUT, lieux_tmp.CHEMIN_DEFAUT, reglages.CHEMIN_DEFAUT,
                                       appli_mod.Appli.fichier_design_defaut()], log=log)
    cerveau = {**cerveau, **reglages.lire()}           # reglages changes dans l'appli : prennent le dessus sur ha.toml
    extras, sources, crochets, fils = {"memoire": memoire.Memoire(ecriture_differee=True)}, [], [], []
    import choregraphies
    extras["choregraphies"] = {c["nom"]: c["etapes"] for c in choregraphies.lire()}
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
        import personnage
        extras["soleil"] = lambda: personnage.tache_soleil(vision.grab_frame(timeout=2.0))  # bain de soleil
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
            import lieux as lieux_lus
            import plan_vie
            noms_lieux = plan_vie.noms(lieux_lus.Lieux(log=lambda m: None).plan())   # (lus au demarrage)
            commandes = cmd.Commandes(cmd.fabrique_vosk(Path(modele).expanduser()), nom=cerveau.get("nom", "canard"),
                                      maison=maison, lieux=noms_lieux)
            log(f"commandes vocales locales : '{cerveau.get('nom', 'canard')} ...' (modele {modele}, hors ligne)")
        elif modele:
            log(f"commandes vocales : modele absent ({modele})")
        voix = audio.VoixPropre()
        extras["voix"] = voix                   # le cerveau signale ses propres sons : le micro ne les analyse pas
        micro = audio.MicroAlsa(peripherique=os.environ.get("MICRODUCK_MICRO"), commandes=commandes, voix=voix)
        fils.append(micro)
        sources.append(micro.source)
        log(f"micro : {os.environ.get('MICRODUCK_MICRO') or 'peripherique ALSA par defaut'} (reflexes sonores)")
    appli = None
    appli_cfg = appli_cfg if appli_cfg is not None else ((cfg or {}).get("appli") or {})
    if appli_cfg.get("actif", True) is not False:
        # sans code : l'appli s'ouvre en « installation » (quelques minutes, reseau local) pour le choisir depuis le
        # telephone, avec le nom du canard et les habitants - sans jamais editer ha.toml
        import appli as appli_mod
        code = None if pont_ha.est_vide(appli_cfg.get("code")) else appli_cfg.get("code")
        try:
            appli = appli_mod.Appli(code, port=int(appli_cfg.get("port", appli_mod.PORT_DEFAUT)), log=log,
                                    version=version_du_cerveau(), code_enfant=appli_cfg.get("code_enfant"))
            sources.append(appli.source)
            crochets.append(appli.photographier)
            appli.cerveau = dict(cerveau)
            appli._reglages_a_appliquer = dict(cerveau)     # routines programmees : actives des le demarrage
            appli.brut = brut if brut is not None else {}
            appli.choregraphies = extras["choregraphies"]       # le meme dict : une choregraphie gardee se joue aussitot
            appli.robotd = robotd_neuf
            if "--sans-camera" not in args:
                import photos                           # journal photo (opt-in) et mode photo : gardes sur le canard
                appli.photos = photos.Photos(log=log)
        except ValueError as e:
            log(f"application Microduck desactivee : {e}")
    lieux = None
    if cerveau.get("lieux", True):
        import lieux as lieux_mod                          # lieux reconnus par le Wi-Fi (maison, chez les parents...)
        lieux = lieux_mod.Lieux(log=log)
        extras["lieu"] = lieux.nom_actuel()
        sources.append(lieux.source)
        if appli is not None:
            appli.lieux = lieux
            lieux.carte_actuelle = lambda: appli.carte
        # ou il est sur le plan du lieu (scan du Quest) : un fil a part ; rien tant que le lieu n'a pas de plan
        import position as position_mod
        grab = None
        if "--sans-camera" not in args:
            import vision
            grab = lambda: vision.grab_frame(timeout=2.0)          # noqa: E731 - marqueurs (recalage)
        pos = position_mod.PositionPlan(lieux, tof=extras.get("tof"), grab=grab, log=log)
        extras["position"] = pos
        fils.append(pos)
        crochets.append(pos.etat_robot_hook)
        if appli is not None:
            appli.position, appli.grab = pos, grab
    heure_ronde = lire_heure(cerveau.get("ronde")) if cerveau.get("ronde") else None
    if heure_ronde is not None:
        extras["ronde"] = heure_ronde                     # ronde du soir (avec le mode garde), sur le plan
    imprimantes = None
    if (brut or {}).get("imprimante_directe"):
        import imprimantes as imprimantes_mod              # Prusa / Elegoo suivies en direct, sans Home Assistant
        imprimantes = imprimantes_mod.Imprimantes(brut["imprimante_directe"], log=log)
        sources.append(imprimantes.source)
        if appli is not None:
            appli.imprimantes = imprimantes
    pont, options = None, pont_ha.options_cerveau({"cerveau": cerveau})
    if cfg is not None:
        pont = pont_ha.PontHA(cfg, pont_ha.lire_jeton(cfg), log=log)
        sources.append(pont.source)
        crochets.append(pont.photographier)
        log("Home Assistant : " + cfg["url"])
    if options:
        log(f"routines : {options}")
    return {"extras": extras, "sources": sources, "crochets": crochets, "options": options, "pont": pont, "fils": fils,
            "appli": appli, "lieux": lieux, "imprimantes": imprimantes}


def main():
    from poc_robotd_client import RobotdClient, SOCK_PATH
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    chemin = Path(args[0]) if args else Path(__file__).parent / "ha.toml"
    duree = float(args[1]) if len(args) > 1 else 10 * 365 * 86400.0
    import tomllib
    import configuration
    brut = {}
    if chemin.exists():                                # ha.toml est facultatif : l'appli sait tout configurer
        pont_ha.avertir_si_non_ignore(chemin)
        with open(chemin, "rb") as f:
            brut = tomllib.load(f)
    brut = configuration.fusion(brut, configuration.lire())
    cfg = pont_ha.normaliser(brut)
    cerveau, appli_cfg = cfg.get("cerveau") or {}, cfg.get("appli") or {}
    if "--sans-ha" in sys.argv:
        cfg = None
    elif cfg["url"] is None:
        print("pas d'adresse Home Assistant : le canard vit sans (a activer dans l'appli, page Connexions)", flush=True)
        cfg = None
    elif not (cfg.get("token") or cfg.get("token_file") or os.environ.get("HA_TOKEN")):
        print("Home Assistant sans jeton : pont desactive (a renseigner dans l'appli, page Connexions)", flush=True)
        cfg = None
    c = RobotdClient(SOCK_PATH)
    hz = ((cfg or {}).get("reseau") or {}).get("etat_hz")
    c.request("robot.subscribe", {"hz": int(hz)} if isinstance(hz, int) and 10 <= hz <= 50 else {})
    a = assembler(c, sys.argv[1:], log=lambda m: print(m, flush=True), cfg=cfg, cerveau=cerveau, appli_cfg=appli_cfg,
                  brut=brut)
    for f in a["fils"]:
        f.start()
    if a["pont"] is not None:
        a["pont"].demarrer()
    if a["appli"] is not None:
        a["appli"].demarrer()
    arret_lieux = a["lieux"].demarrer() if a["lieux"] is not None else None
    arret_imprimantes = a["imprimantes"].demarrer() if a["imprimantes"] is not None else None

    def source():
        return [e for s in a["sources"] for e in s()]

    # systemctl stop / redemarrage : SIGTERM -> sortie normale (le canard se releve, la memoire est sauvee) au lieu
    # d'une mort brutale qui perdrait ce qui a change depuis la derniere sauvegarde
    import signal
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    def crochet(b, state):
        for f in a["crochets"]:
            f(b, state)
        if a["appli"] is not None and a["appli"].redemarrage_demande:
            # depuis l'appli (nouvelle configuration) : sortie propre, systemd le relance (Restart=always)
            print("redemarrage demande par l'application", flush=True)
            raise SystemExit(0)
    try:
        brain.run(c, duree, source=source, a_chaque_tick=crochet, extras=a["extras"], **a["options"])
    finally:
        for f in a["fils"]:
            f.actif = False
        if a["pont"] is not None:
            a["pont"].stop()
        if a["appli"] is not None:
            a["appli"].arreter()
        if arret_lieux is not None:
            arret_lieux.set()
        if arret_imprimantes is not None:
            arret_imprimantes.set()
        mem = a["extras"].get("memoire")
        if mem is not None and hasattr(mem, "fermer"):
            mem.fermer()


if __name__ == "__main__":
    main()
