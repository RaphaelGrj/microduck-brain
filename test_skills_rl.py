#!/usr/bin/env python3
"""Gestes du corps appris par RL branches dans le cerveau (skills_rl.py) : opt-in, repli sur le geste scripte."""
from brain import Brain, Humeur
from etats_base import Geste
from pont_ha import options_cerveau
from skills_rl import SkillsRL, noms_skills


class Client:
    def __init__(self, skills=("startle", "frisson"), refuse=False):
        self.appels, self.skills, self.refuse = [], list(skills), refuse

    def notify(self, method, params=None):
        self.appels.append((method, params))

    def request(self, method, params=None, **kw):
        self.appels.append((method, params))
        if method == "robot.skills":
            return {"result": self.skills}
        if method == "robot.do" and self.refuse == "poli":
            return {"result": {"accepted": False, "reason": "no skill"}}
        if method == "robot.do" and self.refuse:
            return {"error": {"message": "non"}}
        return {"result": {"accepted": True}}

    def do(self):
        return [p["skill"] for m, p in self.appels if m == "robot.do"]


def test_noms_skills_formats():
    assert noms_skills({"result": ["a", "b"]}) == {"a", "b"}
    assert noms_skills({"result": [{"name": "a"}]}) == {"a"}
    assert noms_skills({"result": {"skills": {"a": 1}}}) == {"a"}
    assert noms_skills({"error": "x"}) == set()


def test_desactive_par_defaut():
    c = Client()
    assert SkillsRL(c).joue("surpris") == 0.0
    assert c.do() == []


def test_lance_si_installe():
    c = Client()
    assert SkillsRL(c, actif=True).joue("surpris") == 1.2
    assert c.do() == ["startle"]


def test_repli_si_non_installe_chute_assis_porte_ou_refus():
    assert SkillsRL(Client(skills=()), actif=True).joue("surpris") == 0.0
    c = Client()
    s = SkillsRL(c, actif=True)
    assert s.joue("surpris", {"safety": {"fallen": True}}) == 0.0
    assert s.joue("surpris", {"safety": {"picked_up": True}}) == 0.0
    assert s.joue("surpris", assis=True) == 0.0
    assert s.joue("non") == 0.0                      # geste sans variante RL
    assert c.do() == []
    assert SkillsRL(Client(refuse=True), actif=True).joue("surpris") == 0.0
    assert SkillsRL(Client(refuse="poli"), actif=True).joue("surpris") == 0.0     # accepted: false, sans erreur


def test_geste_rl_ne_commande_pas_la_tete():
    c = Client()
    b = Brain(c, Humeur(), seed=1, skills_rl=True)
    g = Geste("startle", "surpris", recul=True)
    g.entre(b)
    assert c.do() == ["startle"] and g.duree(b) == 2.0
    avant = len(c.appels)
    g.pas(b, 0.2)
    assert len(c.appels) == avant                    # ni robot.head ni robot.move pendant le skill


def test_geste_scripte_sans_option():
    c = Client()
    b = Brain(c, Humeur(), seed=1)
    g = Geste("startle", "surpris", recul=True)
    g.entre(b)
    g.pas(b, 0.2)
    assert c.do() == [] and any(m == "robot.head" for m, _ in c.appels)


def test_option_config():
    assert options_cerveau({"cerveau": {"skills_rl": True}}) == {"skills_rl": True}
    assert "skills_rl" not in options_cerveau({"cerveau": {}})


def test_skill_par_etat_prioritaire():
    c = Client(skills=("pirouette", "trepigner", "startle"))
    s = SkillsRL(c, actif=True)
    assert s.joue("content", etat="celebre") == 3.1          # le geste "content" n a pas de skill, l etat oui
    assert s.joue("surpris", etat="alerte") == 2.0           # l etat l emporte sur le geste (trepigner, pas startle)
    assert s.joue("content", etat="autre") == 0.0
    assert c.do() == ["pirouette", "trepigner"]
