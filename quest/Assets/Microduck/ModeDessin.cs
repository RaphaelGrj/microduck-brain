// Microduck - mode « Dessin » : dessiner dans la vraie piece ce que le canard doit savoir.
//   - zone interdite : gachette a chaque coin au sol (la boule touche le sol), A pour fermer la zone ;
//   - point nomme : choisir le nom au joystick (gauche / droite), GRIP pour le poser a la boule ;
//   - B : annule le dernier coin (ou la derniere zone / le dernier point si aucun coin en cours).
// Chaque zone ou point est enregistre tout de suite dans le plan du canard (/api/plan-annoter).
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;

public class ModeDessin : ModeMicroduck
{
    public override string Nom => "Dessin";

    [Tooltip("Noms proposes pour les points (joystick gauche / droite)")]
    public string[] nomsDePoints = { "panier", "gamelle du chat", "canape", "bureau", "porte d'entree", "jouets", "cuisine" };

    readonly List<Vector2> coins = new List<Vector2>();
    readonly List<List<Vector2>> zones = new List<List<Vector2>>();
    readonly List<string> nomsZones = new List<string>();
    readonly Dictionary<string, Vector2> points = new Dictionary<string, Vector2>();
    readonly List<string> ordre = new List<string>();      // annuler : le dernier ajout
    int choix;
    float tStick;
    LineRenderer enCours;
    bool charge;

    public override string Consigne =>
        (!ReperePlan.Pret ? ReperePlan.Erreur + "\n\n" : "")
        + "Zone interdite : gachette a chaque coin, A pour fermer (" + coins.Count + " coins)\n"
        + "Point « " + nomsDePoints[choix] + " » (joystick pour changer) : GRIP pour le poser\n"
        + "B : annuler   -   " + zones.Count + " zones, " + points.Count + " points\n" + message;

    protected override void OnEnable()
    {
        if (enCours == null) enCours = Outils.Ligne(new Color(0.85f, 0.2f, 0.2f), 0.02f, transform);
        enCours.gameObject.SetActive(true);
        if (!charge && ReperePlan.Pret) Charger();
    }

    protected override void OnDisable() { if (enCours != null) enCours.gameObject.SetActive(false); }

    void Charger()
    {
        charge = true;
        zones.Clear(); nomsZones.Clear(); points.Clear(); ordre.Clear();
        foreach (var z in MiniJson.Liste(MiniJson.Champ(ReperePlan.Plan, "zones")))
        {
            var l = new List<Vector2>();
            foreach (var q in MiniJson.Liste(MiniJson.Champ(z, "contour")))
                l.Add(new Vector2(MiniJson.Nombre(MiniJson.Liste(q)[0]), MiniJson.Nombre(MiniJson.Liste(q)[1])));
            zones.Add(l);
            nomsZones.Add(MiniJson.Champ(z, "nom") as string ?? "zone interdite");
        }
        if (MiniJson.Champ(ReperePlan.Plan, "points") is Dictionary<string, object> pts)
            foreach (var kv in pts)
            {
                var q = MiniJson.Liste(kv.Value);
                points[kv.Key] = new Vector2(MiniJson.Nombre(q[0]), MiniJson.Nombre(q[1]));
            }
    }

    void Update()
    {
        if (!ReperePlan.Pret || Pointe == null) return;
        if (!charge) Charger();
        var s = Outils.Stick();
        if (Mathf.Abs(s.x) > 0.7f && Time.time - tStick > 0.4f)
        {
            tStick = Time.time;
            choix = (choix + (s.x > 0 ? 1 : nomsDePoints.Length - 1)) % nomsDePoints.Length;
        }
        if (Outils.Gachette())
        {
            coins.Add(ReperePlan.VersPlan(Pointe.position));
            Dessiner();
        }
        if (Outils.A() && coins.Count >= 3)
        {
            zones.Add(new List<Vector2>(coins));
            nomsZones.Add("zone interdite " + zones.Count);
            ordre.Add("zone");
            coins.Clear();
            Dessiner();
            StartCoroutine(Enregistrer());
        }
        if (Outils.Grip())
        {
            string nom = nomsDePoints[choix];
            points[nom] = ReperePlan.VersPlan(Pointe.position);
            ordre.Remove("point:" + nom);
            ordre.Add("point:" + nom);
            StartCoroutine(Enregistrer());
        }
        if (Outils.B())
        {
            if (coins.Count > 0) { coins.RemoveAt(coins.Count - 1); Dessiner(); }
            else if (ordre.Count > 0)
            {
                string d = ordre[ordre.Count - 1];
                ordre.RemoveAt(ordre.Count - 1);
                if (d == "zone") { zones.RemoveAt(zones.Count - 1); nomsZones.RemoveAt(nomsZones.Count - 1); }
                else points.Remove(d.Substring(6));
                StartCoroutine(Enregistrer());
            }
        }
    }

    void Dessiner()
    {
        enCours.positionCount = coins.Count;
        for (int i = 0; i < coins.Count; i++) enCours.SetPosition(i, ReperePlan.VersMonde(coins[i].x, coins[i].y, 0.01f));
    }

    IEnumerator Enregistrer()
    {
        var sb = new StringBuilder("{\"zones\":[");
        for (int k = 0; k < zones.Count; k++)
        {
            sb.Append(k > 0 ? "," : "").Append("{\"nom\":").Append(MiniJson.Texte(nomsZones[k])).Append(",\"contour\":[");
            for (int i = 0; i < zones[k].Count; i++)
                sb.Append(i > 0 ? "," : "").Append('[').Append(MiniJson.N(zones[k][i].x)).Append(',')
                  .Append(MiniJson.N(zones[k][i].y)).Append(']');
            sb.Append("]}");
        }
        sb.Append("],\"points\":{");
        int n = 0;
        foreach (var kv in points)
            sb.Append(n++ > 0 ? "," : "").Append(MiniJson.Texte(kv.Key)).Append(":[").Append(MiniJson.N(kv.Value.x))
              .Append(',').Append(MiniJson.N(kv.Value.y)).Append(']');
        sb.Append("}}");
        string rep = null, err = null;
        yield return Canard.Ici.Envoyer("/api/plan-annoter", sb.ToString(), (t, e) => { rep = t; err = e; });
        message = rep != null ? "Enregistre dans son plan" : "Pas enregistre : " + err;
        if (rep != null) yield return ReperePlan.Charger();       // l'atelier verra les nouvelles zones
    }
}
