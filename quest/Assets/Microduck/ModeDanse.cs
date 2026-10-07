// Microduck - mode « Danse » : lui apprendre une choregraphie avec ta tete.
//   Gachette : debut / fin de l'enregistrement (tes mouvements de tete, par rapport a ta position de depart, toutes
//   les 0,4 s, 16 s au plus). A la fin, la danse est ajoutee a son studio de choregraphies (/api/choregraphies).
//   A : la lui faire jouer. Joystick gauche / droite : moins / plus ample.
// Ses angles sont bornes par l'appli du canard (choregraphies.BORNES) ; les sens (gauche/droite, haut/bas) sont a
// verifier sur le vrai canard.
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;

public class ModeDanse : ModeMicroduck
{
    public override string Nom => "Danse (avec ta tete)";
    const float PAS_S = 0.4f;
    const int MAX_ETAPES = 40;

    bool enregistre;
    Quaternion depart;
    float tPas, amplitude = 1f, tStick;
    readonly List<Vector3> poses = new List<Vector3>();      // (lacet, tangage, roulis) en rad
    string derniere;

    public override string Consigne =>
        (enregistre ? "ENREGISTREMENT - bouge la tete ! (" + poses.Count + "/" + MAX_ETAPES + ")   gachette : fin\n"
                    : "Gachette : enregistrer une danse avec ta tete\n")
        + "Amplitude x" + amplitude.ToString("0.0") + " (joystick)   A : la lui faire jouer"
        + (derniere != null ? " (« " + derniere + " »)" : "") + "\n" + message;

    void Update()
    {
        var tete = Camera.main != null ? Camera.main.transform : null;
        if (tete == null) return;
        var s = Outils.Stick();
        if (Mathf.Abs(s.x) > 0.7f && Time.time - tStick > 0.3f)
        {
            tStick = Time.time;
            amplitude = Mathf.Clamp(amplitude + (s.x > 0 ? 0.25f : -0.25f), 0.5f, 3f);
        }
        if (Outils.Gachette())
        {
            if (!enregistre) { enregistre = true; poses.Clear(); depart = tete.rotation; tPas = 0f; message = ""; }
            else { enregistre = false; StartCoroutine(Ajouter()); }
        }
        if (enregistre && Time.time - tPas >= PAS_S)
        {
            tPas = Time.time;
            var r = (Quaternion.Inverse(depart) * tete.rotation).eulerAngles;
            float Angle(float a) => Mathf.DeltaAngle(0f, a) * Mathf.Deg2Rad * amplitude;
            // Unity : y = lacet (vers la droite), x = tangage (vers le bas), z = roulis ; canard : lacet + = gauche
            poses.Add(new Vector3(-Angle(r.y), Angle(r.x), -Angle(r.z)));
            if (poses.Count >= MAX_ETAPES) { enregistre = false; StartCoroutine(Ajouter()); }
        }
        if (Outils.A() && derniere != null)
            StartCoroutine(Canard.Ici.Envoyer("/api/choregraphies", "{\"jouer\":" + MiniJson.Texte(derniere) + "}"));
    }

    IEnumerator Ajouter()
    {
        if (poses.Count < 3) { message = "Trop court"; yield break; }
        string texte = null, err = null;
        yield return Canard.Ici.Lire("/api/choregraphies", (t, e) => { texte = t; err = e; });
        if (texte == null) { message = "Le canard ne repond pas : " + err; yield break; }
        var liste = MiniJson.Liste(MiniJson.Champ(MiniJson.Lire(texte), "liste"));
        var noms = new HashSet<string>();
        foreach (var c in liste) noms.Add(MiniJson.Champ(c, "nom") as string ?? "");
        int n = 1;
        while (noms.Contains("Danse du casque " + n)) n++;
        string nom = "Danse du casque " + n;
        // la liste existante, telle quelle (on la renvoie entiere), plus la nouvelle danse
        var sb = new StringBuilder("{\"liste\":[");
        int k = 0;
        foreach (var c in liste) { sb.Append(k++ > 0 ? "," : "").Append(Ecrire(c)); }
        sb.Append(k > 0 ? "," : "").Append("{\"nom\":").Append(MiniJson.Texte(nom)).Append(",\"etapes\":[");
        for (int i = 0; i < poses.Count; i++)
            sb.Append(i > 0 ? "," : "").Append("{\"type\":\"tete\",\"cou\":0,\"lacet\":").Append(MiniJson.N(poses[i].x))
              .Append(",\"tangage\":").Append(MiniJson.N(poses[i].y)).Append(",\"roulis\":").Append(MiniJson.N(poses[i].z))
              .Append(",\"duree\":").Append(MiniJson.N(PAS_S)).Append('}');
        sb.Append("]}]}");
        string rep = null;
        yield return Canard.Ici.Envoyer("/api/choregraphies", sb.ToString(), (t, e) => { rep = t; err = e; });
        if (rep != null) { derniere = nom; message = "« " + nom + " » ajoutee a son studio"; }
        else message = "Pas enregistree : " + err;
    }

    /// Re-ecrit un objet JSON lu (la liste existante est renvoyee telle quelle).
    static string Ecrire(object o)
    {
        switch (o)
        {
            case null: return "null";
            case bool b: return b ? "true" : "false";
            case double d: return MiniJson.N((float)d);
            case string s: return MiniJson.Texte(s);
            case List<object> l:
                var sl = new StringBuilder("[");
                for (int i = 0; i < l.Count; i++) sl.Append(i > 0 ? "," : "").Append(Ecrire(l[i]));
                return sl.Append(']').ToString();
            case Dictionary<string, object> m:
                var sm = new StringBuilder("{");
                int k = 0;
                foreach (var kv in m) sm.Append(k++ > 0 ? "," : "").Append(MiniJson.Texte(kv.Key)).Append(':').Append(Ecrire(kv.Value));
                return sm.Append('}').ToString();
            default: return "null";
        }
    }
}
