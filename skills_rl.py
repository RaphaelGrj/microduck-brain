#!/usr/bin/env python3
"""Gestes du corps appris par RL (politiques publiees : sursaut, frisson, accroupissement curieux...), joues depuis le
cerveau a la place du geste de tete scripte de meme nom - quand ils sont installes sur le robot et que l'option est
activee ([cerveau] skills_rl = true). Opt-in : valides en duck-sim uniquement, jamais sur le robot reel.

Installation sur le robot : `robotctl policy add <skill> RaphaelGrj/microduck-<nom>` (voir policies/*/manifest.json)."""
import time

# geste de gestures.GESTES -> skill robotd et duree du geste (s)
SKILLS_RL = {
    "surpris": {"skill": "startle", "duree_s": 1.2},
    "ebouriffe": {"skill": "frisson", "duree_s": 1.3},
    "curieux": {"skill": "curieux", "duree_s": 1.3},
}
# etat du cerveau -> skill, prioritaire sur le geste de l'etat (le pas de cote n'y est PAS : il deplace le canard de
# 12 a 30 cm de cote et le ToF ne regarde que devant, un vide a gauche passerait inapercu)
SKILLS_ETATS = {
    "celebre": {"skill": "pirouette", "duree_s": 3.1},      # impression terminee : tour sur place (2,1 s + 1,0 s de freinage)
    "alerte": {"skill": "trepigner", "duree_s": 2.0},       # impression ratee : il trepigne
}
RAFRAICHIT_S = 30.0         # la liste des skills installes est relue au plus toutes les 30 s


def noms_skills(reponse):
    """Reponse JSON-RPC de robot.skills -> ensemble de noms (liste de noms, de dicts {name}, ou dict nom -> ...)."""
    r = reponse.get("result") if isinstance(reponse, dict) else None
    if isinstance(r, dict):
        r = r.get("skills", r)
    if isinstance(r, dict):
        return {str(k) for k in r}
    noms = set()
    for e in r if isinstance(r, list) else []:
        if isinstance(e, str):
            noms.add(e)
        elif isinstance(e, dict) and e.get("name"):
            noms.add(str(e["name"]))
    return noms


class SkillsRL:
    def __init__(self, client, actif=False, horloge=time.monotonic):
        self.client, self.actif, self.horloge = client, actif, horloge
        self._noms, self._t = set(), None

    def installes(self):
        now = self.horloge()
        if self._t is None or now - self._t >= RAFRAICHIT_S:
            self._t = now
            try:
                self._noms = noms_skills(self.client.request("robot.skills"))
            except Exception as e:
                print(f"  (robot.skills impossible : {e})", flush=True)
                self._noms = set()
        return self._noms

    def joue(self, geste, state=None, assis=False, etat=None):
        """Lance le skill RL du geste. Renvoie sa duree (s), ou 0.0 si non lance (option off, non installe, assis, a
        terre, porte) : l'appelant joue alors le geste scripte."""
        choix = SKILLS_ETATS.get(etat) or SKILLS_RL.get(geste)
        if not self.actif or assis or choix is None:
            return 0.0
        skill, duree = choix["skill"], choix["duree_s"]
        s = (state or {}).get("safety") or {}
        if s.get("fallen") or s.get("limp") or s.get("picked_up") or skill not in self.installes():
            return 0.0
        try:
            r = self.client.request("robot.do", {"skill": skill})
        except Exception as e:
            print(f"  (skill {skill} impossible : {e})", flush=True)
            return 0.0
        if isinstance(r, dict) and "error" in r:
            print(f"  (skill {skill} refuse : {r['error']})", flush=True)
            return 0.0
        if isinstance(r, dict) and (r.get("result") or {}).get("accepted") is False:   # refus poli : pas d'erreur JSON-RPC
            print(f"  (skill {skill} non accepte : {r['result'].get('reason')})", flush=True)
            return 0.0
        return duree
