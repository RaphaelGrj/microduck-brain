// Microduck - le plan du canard pose sur la vraie piece.
//
// Le repere « monde » du Quest change a chaque demarrage ; l'ancre du SOL (Configuration de l'espace), elle, est
// retrouvee. Le plan du canard (plan_quest.py) garde le chargeur et le point « devant » dans le repere de cette ancre
// (reperes.quest) : on les replace dans le monde du moment, et on en deduit le repere du plan.
//   plan -> monde : P = C + x.F + y.G (+ hauteur au-dessus du sol)      F = devant (horizontal), G = sa gauche
//   monde -> plan : x = (P - C).F, y = (P - C).G
using System.Collections;
using System.Collections.Generic;
using Meta.XR.MRUtilityKit;
using UnityEngine;

public static class ReperePlan
{
    public static bool Pret { get; private set; }
    public static string Erreur = "plan pas encore charge";
    public static object Plan;                             // le plan du canard (JSON lu), pour zones, points, objets
    static Vector3 C, F, G;
    static float sol;

    public static IEnumerator Charger()
    {
        Pret = false;
        string texte = null, err = null;
        yield return Canard.Ici.Lire("/api/plan", (t, e) => { texte = t; err = e; });
        if (texte == null) { Erreur = "plan du canard : " + err; yield break; }
        Plan = MiniJson.Lire(texte);
        var q = MiniJson.Champ(MiniJson.Champ(Plan, "reperes"), "quest");
        if (q == null) { Erreur = "ce plan n'a pas de repere Quest (refaire l'export avec cette version)"; yield break; }
        while (MRUK.Instance == null) yield return null;
        MRUKAnchor sol0 = null;
        string uuid = MiniJson.Champ(q, "ancre") as string;
        foreach (var objet in Outils.Liste(Outils.Lire(MRUK.Instance, "Rooms") ?? Outils.Appeler(MRUK.Instance, "GetRooms")))
            foreach (var a in Outils.Liste(Outils.Lire(objet, "Anchors")))
            {
                if (!(a is MRUKAnchor ancre) || Outils.Etiquette(ancre) != "FLOOR") continue;
                if (sol0 == null || (uuid != null && Outils.Uuid(ancre) == uuid)) sol0 = ancre;
            }
        if (sol0 == null) { Erreur = "sol introuvable (Configuration de l'espace faite ?)"; yield break; }
        var m = sol0.transform.localToWorldMatrix;
        C = m.MultiplyPoint3x4(Vec(MiniJson.Champ(q, "chargeur")));
        var d = m.MultiplyPoint3x4(Vec(MiniJson.Champ(q, "devant")));
        sol = sol0.transform.position.y;
        F = new Vector3(d.x - C.x, 0f, d.z - C.z).normalized;
        G = new Vector3(-F.z, 0f, F.x);
        Pret = true;
        Erreur = null;
    }

    static Vector3 Vec(object o)
    {
        var l = MiniJson.Liste(o);
        return new Vector3(MiniJson.Nombre(l[0]), MiniJson.Nombre(l[1]), MiniJson.Nombre(l[2]));
    }

    public static Vector3 VersMonde(float x, float y, float hauteur = 0f)
    {
        var p = C + x * F + y * G;
        p.y = sol + hauteur;
        return p;
    }

    public static Vector2 VersPlan(Vector3 p)
    {
        var v = p - C;
        return new Vector2(Vector3.Dot(v, F), Vector3.Dot(v, G));
    }

    /// Cap (rad, repere du plan) d'une direction du monde.
    public static float Cap(Vector3 direction) => Mathf.Atan2(Vector3.Dot(direction, G), Vector3.Dot(direction, F));

    public static Vector3 DirectionMonde(float cap) => Mathf.Cos(cap) * F + Mathf.Sin(cap) * G;

    public static float Sol => sol;
    public static Vector3 Origine => C;                    // le chargeur, au sol
    public static Vector3 Devant => F;
    public static Vector3 Gauche => G;
}
