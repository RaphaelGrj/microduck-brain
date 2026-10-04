#!/usr/bin/env python3
"""Tests de la logique de veille du chat (horloge simulee, aucune camera). Usage : bash ~/run-brain.sh test_chat.py"""
from animaux import Objet
from chat import SuiviChat

CHAT = [Objet("cat", 0.9, 100, 100, 60, 100)]


class Horloge:
    t = 0.0

    def __call__(self):
        return self.t


def test():
    h = Horloge()
    s = SuiviChat(confirmations=2, absence_s=20, delai_grace_s=120, horloge=h)
    assert s.mise_a_jour(CHAT) == [], "une detection isolee ne doit pas declencher"
    h.t = 0.5
    assert s.mise_a_jour(CHAT) == ["chat"], "deux images consecutives : apparition"
    for i in range(1, 30):                       # le chat reste la 15 s : pas de nouvel evenement
        h.t = 0.5 + 0.5 * i
        assert s.mise_a_jour(CHAT) == []
    assert s.derniere_vue[1].score == 0.9
    h.t = 20.0
    assert s.mise_a_jour([]) == []
    h.t = 45.0                                    # absent > 20 s : parti
    assert s.mise_a_jour([]) == [] and not s.visible
    h.t = 50.0
    s.mise_a_jour(CHAT)
    h.t = 50.5
    assert s.mise_a_jour(CHAT) == [], "revue 50 s apres la 1re reaction : delai de grace de 120 s (ne jamais insister)"
    assert s.nb_apparitions == 2, "mais l'apparition est memorisee"
    h.t = 80.0
    s.mise_a_jour([])
    h.t = 130.0                                   # absent un moment, puis revient apres le delai de grace
    s.mise_a_jour([])
    h.t = 140.0
    s.mise_a_jour(CHAT)
    h.t = 140.5
    assert s.mise_a_jour(CHAT) == ["chat"], "nouvelle apparition apres le delai de grace : reaction"
    assert s.nb_apparitions == 3
    s2 = SuiviChat(confirmations=2, horloge=h)    # une detection puis rien : serie remise a zero
    s2.mise_a_jour(CHAT)
    s2.mise_a_jour([])
    assert s2.mise_a_jour(CHAT) == [], "detections non consecutives : pas de confirmation"
    print("veille du chat : OK (confirmation, nouvelle apparition seulement, delai de grace, memoire des apparitions)")


def test_memoire():
    import json
    import tempfile
    from pathlib import Path
    from memoire import Memoire
    h = Horloge()
    h.t = 1_700_000_000.0
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "m.json"
        m = Memoire(chemin, horloge=h)
        assert m.familiarite("chat") == 0.0 and m.heure_habituelle("chat") is None
        for _ in range(3):
            m.rencontre("chat")
        f3 = m.familiarite("chat")
        assert 0.35 < f3 < 0.40, f3                     # 1 - 0.85**3 = 0.386
        h.t += 14 * 86400                               # deux semaines sans le voir : moitie
        assert abs(m.familiarite("chat") - f3 / 2) < 1e-6
        m2 = Memoire(chemin, horloge=h)                 # relue depuis le disque
        assert m2.donnees["etres"]["chat"]["rencontres"] == 3 and m2.heure_habituelle("chat") is not None
        assert json.loads(chemin.read_text())["etres"]["chat"]["rencontres"] == 3
        s = SuiviChat(confirmations=1, horloge=h)
        s.sur_apparition = lambda t: m2.rencontre("chat")
        s.mise_a_jour(CHAT)
        assert m2.donnees["etres"]["chat"]["rencontres"] == 4, "une apparition est memorisee"
    print("memoire : OK (rencontres, familiarite qui monte puis s'oublie en 2 semaines, relecture du disque)")


if __name__ == "__main__":
    test()
    test_memoire()
