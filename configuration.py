#!/usr/bin/env python3
"""La configuration du canard modifiable depuis l'application (sans editer ha.toml) : son nom, le code de l'appli,
les habitants, Home Assistant (facultatif), les imprimantes 3D suivies en direct, les appareils de la maison.

Gardee dans configuration.json (a cote de la memoire, MICRODUCK_CONFIGURATION pour un autre chemin), au meme format
que ha.toml. Chaque section ecrite par l'appli REMPLACE celle de ha.toml ; ha.toml devient facultatif. Le jeton Home
Assistant et les cles des imprimantes restent sur le canard : l'appli ne les relit jamais (seulement « defini »).
"""
import ipaddress
import json
import os
import re
from pathlib import Path

import memoire

CHEMIN_DEFAUT = Path(os.environ.get("MICRODUCK_CONFIGURATION", memoire.CHEMIN_DEFAUT.parent / "configuration.json"))
NOM_MAX = 40
TYPES_IMPRIMANTE = ("prusalink", "sdcp")            # Prusa (PrusaLink, MK3S/MK4S...), Elegoo (SDCP, Saturn 4 Ultra...)
TYPES_APPAREIL = ("sonnette", "sonnette_event", "fumee", "aspirateur", "calendrier", "machine", "puissance", "meteo",
                  "temperature")
SECRET = "••••••"


def texte(v, n=NOM_MAX):
    v = "".join(c for c in v if c.isprintable()).strip()[:n] if isinstance(v, str) else ""
    return v or None


def adresse_locale(adresse):
    """Une imprimante doit etre sur le reseau local : IP privee ou nom .local / sans point (jamais Internet)."""
    hote = str(adresse or "").strip().split("://")[-1].split("/")[0].split(":")[0]
    if not hote:
        return False
    try:
        ip = ipaddress.ip_address(hote)
        return ip.is_private or ip.is_link_local
    except ValueError:
        return hote.endswith(".local") or ("." not in hote and re.fullmatch(r"[A-Za-z0-9-]+", hote) is not None)


def entite(v):
    v = texte(v, 120)
    return v if v and re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", v) else None


def valider(section, valeur, ancienne=None):
    """Une section envoyee par l'appli -> forme propre (celle de ha.toml), ou None si elle est fausse.
    `ancienne` : la section actuelle, pour garder un secret que l'appli n'a pas renvoye (SECRET ou vide)."""
    ancienne = ancienne if ancienne is not None else {}
    if section == "cerveau" and isinstance(valeur, dict):
        out = {"nom": texte(valeur.get("nom")) or "canard", "garde": bool(valeur.get("garde", False))}
        ronde = texte(valeur.get("ronde"), 5)
        if ronde and re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", ronde):
            out["ronde"] = ronde                # ronde du soir sur le plan, avec le mode garde
        return out
    if section == "appli" and isinstance(valeur, dict):
        code = valeur.get("code")
        if code in (None, "", SECRET):
            code = (ancienne or {}).get("code")
        out = {"code": code if isinstance(code, str) and len(code) >= 6 else None}
        enfant = valeur.get("code_enfant")
        if enfant == SECRET:
            enfant = (ancienne or {}).get("code_enfant")
        out["code_enfant"] = enfant if isinstance(enfant, str) and len(enfant) >= 6 and enfant != out["code"] else None
        return out if out["code"] else None
    if section == "home_assistant" and isinstance(valeur, dict):
        url = texte(valeur.get("url"), 200)
        if url and not url.startswith(("http://", "https://")):
            return None
        jeton = valeur.get("token")
        if jeton in (None, "", SECRET):
            jeton = (ancienne or {}).get("token")
        return {"actif": bool(valeur.get("actif", True)) and bool(url), "url": url,
                "token": jeton if isinstance(jeton, str) and jeton.strip() else None}
    if section == "habitant" and isinstance(valeur, list):
        out, vus = [], set()
        for h in valeur[:20]:
            nom = texte((h or {}).get("nom")) if isinstance(h, dict) else None
            if nom and nom.lower() not in vus:
                vus.add(nom.lower())
                out.append({"nom": nom, **({"entite": entite(h.get("entite"))} if entite(h.get("entite")) else {})})
        return out
    if section == "imprimante_directe" and isinstance(valeur, list):
        out = []
        anciennes = {i.get("adresse"): i for i in (ancienne or []) if isinstance(i, dict)}
        for i in valeur[:10]:
            if not isinstance(i, dict) or i.get("type") not in TYPES_IMPRIMANTE or not adresse_locale(i.get("adresse")):
                continue
            adresse = str(i["adresse"]).strip()
            cle = i.get("cle_api")
            if cle in (None, "", SECRET):
                cle = anciennes.get(adresse, {}).get("cle_api")
            out.append({"nom": texte(i.get("nom")) or adresse, "type": i["type"], "adresse": adresse,
                        **({"cle_api": cle} if isinstance(cle, str) and cle else {})})
        return out
    if section == "piece" and isinstance(valeur, list):
        # presence par piece (capteurs HA) : nom tel que sur le plan du lieu (scan Quest), entite binary_sensor
        return [{"nom": texte(p.get("nom")), "entite": entite(p.get("entite"))} for p in valeur[:20]
                if isinstance(p, dict) and texte(p.get("nom")) and entite(p.get("entite"))]
    if section == "appareil" and isinstance(valeur, list):
        out = []
        for a in valeur[:30]:
            if isinstance(a, dict) and a.get("type") in TYPES_APPAREIL and entite(a.get("entite")):
                out.append({"nom": texte(a.get("nom")) or a["entite"], "type": a["type"], "entite": entite(a["entite"])})
        return out
    return None


SECTIONS = ("cerveau", "appli", "home_assistant", "habitant", "imprimante_directe", "appareil", "piece")


def lire(chemin=None):
    chemin = chemin or CHEMIN_DEFAUT
    try:
        d = json.loads(Path(chemin).read_text())
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in d.items() if k in SECTIONS} if isinstance(d, dict) else {}


def ecrire(section, valeur, chemin=None):
    """Valide et garde une section. -> la section propre, ou None si refusee."""
    chemin = chemin or CHEMIN_DEFAUT
    d = lire(chemin)
    propre = valider(section, valeur, d.get(section))
    if propre is None:
        return None
    d[section] = propre
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False))
    os.chmod(tmp, 0o600)                               # le jeton Home Assistant y est
    os.replace(tmp, chemin)
    return propre


def fusion(brut_toml, app):
    """ha.toml (peut etre vide) + ce que l'appli a ecrit : les sections de l'appli remplacent celles de ha.toml.
    La section [cerveau] est fusionnee cle par cle (les reglages de reglages.py y vivent aussi)."""
    brut = dict(brut_toml or {})
    for section, valeur in (app or {}).items():
        if section == "home_assistant":
            ha = dict(brut.get("home_assistant") or {})
            ha.update({"url": valeur.get("url") if valeur.get("actif") else None, "token": valeur.get("token")})
            brut["home_assistant"] = ha
            brut.pop("url", None)                      # (ancien format plat)
        elif section in ("cerveau", "appli"):
            brut[section] = {**(brut.get(section) or {}), **{k: v for k, v in valeur.items() if v is not None}}
        else:
            brut[section] = valeur
    return brut


def pour_appli(brut):
    """Ce que l'appli affiche : sans aucun secret (jeton, codes, cles API remplaces par SECRET)."""
    ha = brut.get("home_assistant") or {}
    url = ha.get("url") or brut.get("url")
    appli = brut.get("appli") or {}
    return {
        "cerveau": {"nom": (brut.get("cerveau") or {}).get("nom", "canard"), "garde": bool((brut.get("cerveau") or {}).get("garde"))},
        "appli": {"code": SECRET if appli.get("code") else None, "code_enfant": SECRET if appli.get("code_enfant") else None},
        "home_assistant": {"actif": bool(url), "url": url, "token": SECRET if (ha.get("token") or ha.get("token_file")) else None},
        "habitant": [{"nom": h.get("nom"), **({"entite": h["entite"]} if h.get("entite") else {})}
                     for h in brut.get("habitant", []) if isinstance(h, dict) and h.get("nom")],
        "imprimante_directe": [{**{k: v for k, v in i.items() if k != "cle_api"}, "cle_api": SECRET if i.get("cle_api") else None}
                               for i in brut.get("imprimante_directe", []) if isinstance(i, dict)],
        "appareil": [a for a in brut.get("appareil", []) if isinstance(a, dict)],
    }
