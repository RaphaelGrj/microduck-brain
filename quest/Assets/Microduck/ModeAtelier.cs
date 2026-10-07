// Microduck - mode « Atelier » : ce que le canard croit, pose sur la vraie piece.
//   - fleche orange : ou il croit etre (et son cap) ; petites boules jaunes : son nuage d'hypotheses ;
//   - points rouges : ce que voit son capteur de distance ; ligne bleue : le trajet qu'il suit ;
//   - zones interdites (contour rouge au sol) et points nommes (etiquettes) de son plan.
// Gachette : « va la » (le point vise au sol). A : recharger le plan. Rien n'est envoye d'autre.
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class ModeAtelier : ModeMicroduck
{
    public override string Nom => "Atelier";

    Transform racine;
    Transform canard;
    readonly List<Transform> nuage = new List<Transform>(), tof = new List<Transform>();
    LineRenderer trajet;
    readonly List<GameObject> decor = new List<GameObject>();
    object dernier;
    float tLecture;
    bool lecture;

    public override string Consigne
    {
        get
        {
            if (!ReperePlan.Pret) return ReperePlan.Erreur + "\n\nA : recharger le plan";
            if (dernier == null) return "En attente du canard...";
            float ecart = MiniJson.Nombre(MiniJson.Champ(dernier, "ecart"), 9f);
            string piece = MiniJson.Champ(dernier, "piece") as string;
            return (MiniJson.Champ(dernier, "sur") is bool s && s ? "Il sait ou il est" : "Il cherche ou il est")
                   + " (dispersion " + Mathf.RoundToInt(ecart * 100) + " cm)" + (piece != null ? " - " + piece : "")
                   + "\n\nGachette : l'envoyer la   A : recharger le plan\n" + message;
        }
    }

    protected override void OnEnable()
    {
        if (racine == null)
        {
            racine = new GameObject("Atelier").transform;
            var fleche = GameObject.CreatePrimitive(PrimitiveType.Cube);
            Destroy(fleche.GetComponent<Collider>());
            fleche.transform.localScale = new Vector3(0.16f, 0.05f, 0.25f);  // la taille du canard, vu de dessus
            fleche.GetComponent<Renderer>().material.color = new Color(0.95f, 0.42f, 0.1f, 0.8f);
            canard = fleche.transform;
            canard.SetParent(racine, false);
            trajet = Outils.Ligne(new Color(0.2f, 0.5f, 1f), 0.02f, racine);
        }
        racine.gameObject.SetActive(true);
        Decor();
    }

    protected override void OnDisable()
    {
        if (racine != null) racine.gameObject.SetActive(false);
    }

    void Decor()
    {
        foreach (var g in decor) Destroy(g);
        decor.Clear();
        if (!ReperePlan.Pret) return;
        foreach (var z in MiniJson.Liste(MiniJson.Champ(ReperePlan.Plan, "zones")))
        {
            var l = Outils.Ligne(new Color(0.85f, 0.2f, 0.2f), 0.03f, racine);
            var pts = MiniJson.Liste(MiniJson.Champ(z, "contour"));
            l.loop = true;
            l.positionCount = pts.Count;
            for (int i = 0; i < pts.Count; i++)
            {
                var q = MiniJson.Liste(pts[i]);
                l.SetPosition(i, ReperePlan.VersMonde(MiniJson.Nombre(q[0]), MiniJson.Nombre(q[1]), 0.01f));
            }
            decor.Add(l.gameObject);
        }
        if (MiniJson.Champ(ReperePlan.Plan, "points") is Dictionary<string, object> points)
            foreach (var kv in points)
            {
                var q = MiniJson.Liste(kv.Value);
                var t = Outils.Etiquette3D(kv.Key, racine);
                t.transform.position = ReperePlan.VersMonde(MiniJson.Nombre(q[0]), MiniJson.Nombre(q[1]), 0.15f);
                decor.Add(t.gameObject);
            }
    }

    void Update()
    {
        if (Outils.A()) StartCoroutine(Recharger());
        if (Outils.Gachette() && ReperePlan.Pret && Pointe != null)
        {
            var p = ReperePlan.VersPlan(Pointe.position);
            StartCoroutine(Canard.Ici.Envoyer("/api/aller", "{\"x\":" + MiniJson.N(p.x) + ",\"y\":" + MiniJson.N(p.y) + "}"));
            message = "Envoye en " + p.x.ToString("0.00") + ", " + p.y.ToString("0.00");
        }
        if (!lecture && Time.time - tLecture > 0.2f && Canard.Ici != null && Canard.Ici.Configure)
            StartCoroutine(Lire());
        foreach (Transform t in racine) if (t.GetComponent<TextMesh>() != null) Outils.FaceALaCamera(t);
    }

    IEnumerator Recharger()
    {
        message = "Chargement du plan...";
        yield return ReperePlan.Charger();
        Decor();
        message = ReperePlan.Pret ? "Plan charge" : ReperePlan.Erreur;
    }

    IEnumerator Lire()
    {
        lecture = true;
        tLecture = Time.time;
        string texte = null;
        yield return Canard.Ici.Lire("/api/xr", (t, e) => texte = t);
        lecture = false;
        if (texte == null || !ReperePlan.Pret) yield break;
        dernier = MiniJson.Lire(texte);
        if (!(MiniJson.Champ(dernier, "plan") is bool a && a)) yield break;
        float x = MiniJson.Nombre(MiniJson.Champ(dernier, "x")), y = MiniJson.Nombre(MiniJson.Champ(dernier, "y"));
        float cap = MiniJson.Nombre(MiniJson.Champ(dernier, "cap"));
        canard.position = ReperePlan.VersMonde(x, y, 0.025f);
        canard.rotation = Quaternion.LookRotation(ReperePlan.DirectionMonde(cap), Vector3.up);
        Placer(nuage, MiniJson.Liste(MiniJson.Champ(dernier, "nuage")), new Color(1f, 0.85f, 0.2f), 0.012f, 0.01f);
        Placer(tof, MiniJson.Liste(MiniJson.Champ(dernier, "tof")), new Color(0.9f, 0.15f, 0.15f), 0.015f, 0.08f);
        var ch = MiniJson.Liste(MiniJson.Champ(dernier, "chemin"));
        trajet.positionCount = ch.Count > 0 ? ch.Count + 1 : 0;
        if (ch.Count > 0) trajet.SetPosition(0, canard.position);
        for (int i = 0; i < ch.Count; i++)
        {
            var q = MiniJson.Liste(ch[i]);
            trajet.SetPosition(i + 1, ReperePlan.VersMonde(MiniJson.Nombre(q[0]), MiniJson.Nombre(q[1]), 0.02f));
        }
    }

    void Placer(List<Transform> reserve, List<object> pts, Color couleur, float taille, float hauteur)
    {
        while (reserve.Count < pts.Count) reserve.Add(Outils.Boule(couleur, taille, racine).transform);
        for (int i = 0; i < reserve.Count; i++)
        {
            reserve[i].gameObject.SetActive(i < pts.Count);
            if (i >= pts.Count) continue;
            var q = MiniJson.Liste(pts[i]);
            reserve[i].position = ReperePlan.VersMonde(MiniJson.Nombre(q[0]), MiniJson.Nombre(q[1]), hauteur);
        }
    }
}
