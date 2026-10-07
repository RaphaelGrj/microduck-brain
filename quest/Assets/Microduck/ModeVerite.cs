// Microduck - mode « Verite » : le casque connait sa position au centimetre ; il sert de regle pour mesurer
// l'erreur de localisation du canard dans la vraie maison (l'equivalent reel de la verite terrain du simulateur).
//   Gachette 1 : la boule au CENTRE du dos du canard ; gachette 2 : la boule au bout de son BEC (son cap).
//   -> erreur en cm et en degres. A : le recaler a cet endroit (« tu es ici »). B : recommencer.
using System.Collections;
using UnityEngine;

public class ModeVerite : ModeMicroduck
{
    public override string Nom => "Verite terrain";

    Vector3? centre, bec;
    string mesure = "";
    readonly System.Collections.Generic.List<string> journal = new System.Collections.Generic.List<string>();

    public override string Consigne =>
        (!ReperePlan.Pret ? ReperePlan.Erreur + "\n\n"
         : centre == null ? "Pose la boule au CENTRE du dos du canard, gachette\n"
         : bec == null ? "Puis au bout de son BEC, gachette\n"
         : "A : le recaler ici   B : recommencer\n")
        + mesure + "\n" + string.Join("\n", journal) + "\n" + message;

    void Update()
    {
        if (Outils.B()) { centre = bec = null; mesure = ""; }
        if (!ReperePlan.Pret || Pointe == null) return;
        if (Outils.Gachette())
        {
            if (centre == null) centre = Pointe.position;
            else if (bec == null) { bec = Pointe.position; StartCoroutine(Envoyer(false)); }
        }
        if (Outils.A() && centre != null && bec != null) StartCoroutine(Envoyer(true));
    }

    IEnumerator Envoyer(bool recaler)
    {
        var p = ReperePlan.VersPlan(centre.Value);
        float cap = ReperePlan.Cap(bec.Value - centre.Value);
        string corps = "{\"x\":" + MiniJson.N(p.x) + ",\"y\":" + MiniJson.N(p.y) + ",\"cap\":" + MiniJson.N(cap)
                       + (recaler ? ",\"recaler\":true" : "") + "}";
        string rep = null, err = null;
        yield return Canard.Ici.Envoyer("/api/verite", corps, (t, e) => { rep = t; err = e; });
        if (rep == null) { message = "Le canard ne repond pas : " + err; yield break; }
        var r = MiniJson.Lire(rep);
        float e_m = MiniJson.Nombre(MiniJson.Champ(r, "erreur_m"), -1f);
        float e_deg = MiniJson.Nombre(MiniJson.Champ(r, "erreur_cap_deg"), -1f);
        mesure = "Erreur : " + Mathf.RoundToInt(e_m * 100) + " cm, " + Mathf.RoundToInt(e_deg) + " degres"
                 + (recaler ? " - recale (" + MiniJson.Champ(r, "recale") + ")" : "");
        if (!recaler)
        {
            journal.Insert(0, System.DateTime.Now.ToString("HH:mm:ss") + "  " + Mathf.RoundToInt(e_m * 100) + " cm");
            if (journal.Count > 5) journal.RemoveAt(5);
        }
    }
}
