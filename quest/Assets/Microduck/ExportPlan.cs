// Microduck - export du scan du Meta Quest 3 pour le plan du canard (format « microduck-quest-1 », lu par plan_quest.py).
//
// Dans le casque (passthrough : on voit la piece) :
//   - une petite boule orange au bout de la manette DROITE : c'est elle qui « pointe » ;
//   - GACHETTE : enregistre le point vise, dans l'ordre : 1) le chargeur (la ou le canard se pose pour se recharger),
//     2) « devant » (un point a ~50 cm devant le chargeur, dans la direction ou regarde le canard sur son chargeur),
//     3) l'entree (la porte par laquelle on rentre), puis 4...) chaque marqueur imprime, dans l'ordre de leurs numeros ;
//   - B : annule le dernier point ;
//   - A : exporte (fichier dans le casque, et envoi au canard si son adresse est renseignee).
// Rien d'autre ne sort du casque. Le scan lui-meme vient de la « Configuration de l'espace » du Quest (Space Setup),
// lu par le Mixed Reality Utility Kit (MRUK) de Meta.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using Meta.XR.MRUtilityKit;
using UnityEngine;
using UnityEngine.Networking;

public class ExportPlan : MonoBehaviour
{
    [Tooltip("Adresse de l'appli du canard, ex. http://192.168.1.50:8090 - vide : fichier seulement")]
    public string adresseCanard = "";
    [Tooltip("Code de l'appli du canard (le code parent)")]
    public string codeAppli = "";
    [Tooltip("Nom du lieu, tel qu'il apparaitra dans l'appli")]
    public string nomDuLieu = "Maison";
    [Tooltip("Main droite (RightControllerAnchor du Camera Rig) - trouvee seule si vide")]
    public Transform mainDroite;

    struct Repere { public string nom; public int id; public Vector3 pos; }

    readonly List<Repere> reperes = new List<Repere>();
    TextMesh texte;
    Transform pointe;
    bool sceneChargee;
    string message = "";

    static readonly string[] ETAPES = { "chargeur", "devant", "entree" };
    static readonly string[] CONSIGNES = {
        "Pose la boule sur le CHARGEUR (la ou le canard se recharge)",
        "Vise un point a ~50 cm DEVANT le chargeur (la ou le canard regarde)",
        "Vise l'ENTREE (la porte par laquelle on rentre)",
    };

    void Start()
    {
        var cam = Camera.main != null ? Camera.main.transform : transform;
        var go = new GameObject("Consignes Microduck");
        go.transform.SetParent(cam, false);
        go.transform.localPosition = new Vector3(0f, -0.12f, 0.9f);
        texte = go.AddComponent<TextMesh>();
        texte.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        go.GetComponent<MeshRenderer>().material = texte.font.material;
        texte.characterSize = 0.006f;
        texte.fontSize = 60;
        texte.anchor = TextAnchor.MiddleCenter;
        texte.alignment = TextAlignment.Center;
        texte.color = Color.white;

        if (mainDroite == null)
        {
            var rig = FindFirstObjectByType<OVRCameraRig>();
            if (rig != null) mainDroite = rig.rightControllerAnchor;
        }
        var boule = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        Destroy(boule.GetComponent<Collider>());
        boule.transform.localScale = Vector3.one * 0.015f;
        boule.GetComponent<Renderer>().material.color = new Color(0.95f, 0.42f, 0.1f);
        pointe = boule.transform;
        if (mainDroite != null)
        {
            pointe.SetParent(mainDroite, false);
            pointe.localPosition = new Vector3(0f, 0f, 0.07f);   // 7 cm devant la manette
        }
        MRUK.Instance.RegisterSceneLoadedCallback(() => { sceneChargee = true; });
    }

    void Update()
    {
        if (OVRInput.GetDown(OVRInput.Button.PrimaryIndexTrigger, OVRInput.Controller.RTouch) && pointe != null)
        {
            int n = reperes.Count;
            var r = new Repere { pos = pointe.position, id = -1 };
            if (n < ETAPES.Length) r.nom = ETAPES[n];
            else { r.nom = "marqueur"; r.id = n - ETAPES.Length; }
            reperes.Add(r);
            message = "Note : " + (r.id >= 0 ? "marqueur n" + r.id : r.nom);
        }
        if (OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.RTouch) && reperes.Count > 0)
        {
            reperes.RemoveAt(reperes.Count - 1);
            message = "Dernier point annule";
        }
        if (OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.RTouch))
        {
            if (!sceneChargee) message = "Le scan n'est pas encore charge (Configuration de l'espace faite ?)";
            else if (reperes.Count < 2) message = "Il faut au moins le chargeur et « devant »";
            else StartCoroutine(Exporter());
        }
        int k = reperes.Count;
        string consigne = !sceneChargee ? "Chargement du scan du Quest..."
            : k < ETAPES.Length ? (k + 1) + ") " + CONSIGNES[k] + (k == 2 ? "\n(ou A pour exporter sans)" : "")
            : "Marqueur n" + (k - ETAPES.Length) + " : pose la boule au CENTRE du marqueur\n(ou A pour exporter)";
        texte.text = "Microduck - scan du lieu « " + nomDuLieu + " »\n\n" + consigne
            + "\n\nGachette : noter   B : annuler   A : exporter\n" + message;
    }

    IEnumerator Exporter()
    {
        string json;
        try { json = Construire(); }
        catch (Exception e) { message = "Export impossible : " + e.Message; yield break; }
        string nomFichier = "microduck-scan-" + DateTime.Now.ToString("yyyyMMdd-HHmm") + ".json";
        string chemin = Path.Combine(Application.persistentDataPath, nomFichier);
        File.WriteAllText(chemin, json, new UTF8Encoding(false));
        message = "Fichier ecrit : " + nomFichier;
        Debug.Log("[Microduck] scan ecrit : " + chemin);
        if (string.IsNullOrWhiteSpace(adresseCanard)) yield break;
        string corps = "{\"nom\":" + Chaine(nomDuLieu) + ",\"contenu\":" + json + "}";
        using (var req = new UnityWebRequest(adresseCanard.TrimEnd('/') + "/api/plan", "POST"))
        {
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(corps));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            req.SetRequestHeader("X-Microduck-Code", codeAppli);
            yield return req.SendWebRequest();
            message = req.result == UnityWebRequest.Result.Success
                ? "Envoye au canard ! (" + nomFichier + ")"
                : "Fichier ecrit, mais envoi au canard rate : " + req.error + " " + req.downloadHandler.text;
        }
    }

    // -- le fichier « microduck-quest-1 » -------------------------------------------------------------------------------
    string Construire()
    {
        var sb = new StringBuilder();
        sb.Append("{\"format\":\"microduck-quest-1\",\"date\":").Append(Chaine(DateTime.Now.ToString("s")));
        sb.Append(",\"appareil\":").Append(Chaine(SystemInfo.deviceModel)).Append(",\"reperes\":[");
        for (int i = 0; i < reperes.Count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append("{\"nom\":").Append(Chaine(reperes[i].nom));
            if (reperes[i].id >= 0) sb.Append(",\"id\":").Append(reperes[i].id);
            sb.Append(",\"pos\":").Append(Vec(reperes[i].pos)).Append('}');
        }
        sb.Append("],\"pieces\":[");
        int p = 0;
        foreach (var piece in Liste(Lire(MRUK.Instance, "Rooms") ?? Appeler(MRUK.Instance, "GetRooms")))
        {
            if (p > 0) sb.Append(',');
            sb.Append("{\"nom\":").Append(Chaine("Piece " + (p + 1))).Append(",\"ancres\":[");
            int a = 0;
            foreach (var objet in Liste(Lire(piece, "Anchors")))
            {
                if (!(objet is MRUKAnchor ancre)) continue;
                if (a > 0) sb.Append(',');
                Ancre(sb, ancre);
                a++;
            }
            sb.Append("]}");
            p++;
        }
        if (p == 0) throw new Exception("aucune piece : faire la Configuration de l'espace du Quest");
        sb.Append("]}");
        return sb.ToString();
    }

    static void Ancre(StringBuilder sb, MRUKAnchor ancre)
    {
        sb.Append("{\"label\":").Append(Chaine(Etiquette(ancre)));
        var m = ancre.transform.localToWorldMatrix;
        sb.Append(",\"matrice\":[");
        for (int r = 0; r < 4; r++)
            for (int c = 0; c < 4; c++)
                sb.Append(r + c > 0 ? "," : "").Append(Nombre(m[r, c]));
        sb.Append("],\"plan\":");
        if (Lire(ancre, "PlaneRect") is Rect rect)
            sb.Append('[').Append(Nombre(rect.xMin)).Append(',').Append(Nombre(rect.yMin)).Append(',')
              .Append(Nombre(rect.width)).Append(',').Append(Nombre(rect.height)).Append(']');
        else sb.Append("null");
        sb.Append(",\"volume\":");
        if (Lire(ancre, "VolumeBounds") is Bounds b)
            sb.Append('[').Append(Nombre(b.min.x)).Append(',').Append(Nombre(b.min.y)).Append(',').Append(Nombre(b.min.z))
              .Append(',').Append(Nombre(b.max.x)).Append(',').Append(Nombre(b.max.y)).Append(',').Append(Nombre(b.max.z)).Append(']');
        else sb.Append("null");
        sb.Append(",\"contour\":[");
        int i = 0;
        foreach (var o in Liste(Lire(ancre, "PlaneBoundary2D")))
        {
            if (!(o is Vector2 v)) continue;
            sb.Append(i++ > 0 ? "," : "").Append('[').Append(Nombre(v.x)).Append(',').Append(Nombre(v.y)).Append(']');
        }
        sb.Append("]}");
    }

    /// Etiquette de l'ancre (FLOOR, WALL_FACE, TABLE...) : « Label » (MRUK recent, enum) ou « AnchorLabels » (ancien).
    static string Etiquette(MRUKAnchor ancre)
    {
        var v = Lire(ancre, "Label");
        if (v != null) return v.ToString().Split(',')[0].Trim();
        foreach (var o in Liste(Lire(ancre, "AnchorLabels"))) return o.ToString();
        return "OTHER";
    }

    // -- outils (lecture par reflexion : tolere les differences entre versions du MRUK) ---------------------------------
    static object Lire(object o, string nom)
    {
        if (o == null) return null;
        var t = o.GetType();
        const BindingFlags F = BindingFlags.Public | BindingFlags.Instance;
        var p = t.GetProperty(nom, F);
        if (p != null) return p.GetValue(o);
        var f = t.GetField(nom, F);
        return f != null ? f.GetValue(o) : null;
    }

    static object Appeler(object o, string nom)
    {
        var m = o?.GetType().GetMethod(nom, BindingFlags.Public | BindingFlags.Instance, null, Type.EmptyTypes, null);
        return m?.Invoke(o, null);
    }

    static IEnumerable Liste(object o)
    {
        if (o is IEnumerable e) foreach (var x in e) yield return x;
    }

    static string Nombre(float v) => v.ToString("0.#####", CultureInfo.InvariantCulture);
    static string Vec(Vector3 v) => "[" + Nombre(v.x) + "," + Nombre(v.y) + "," + Nombre(v.z) + "]";

    static string Chaine(string s)
    {
        var sb = new StringBuilder("\"");
        foreach (char c in s ?? "")
        {
            if (c == '"' || c == '\\') sb.Append('\\').Append(c);
            else if (c < ' ') sb.Append("\\u").Append(((int)c).ToString("x4"));
            else sb.Append(c);
        }
        return sb.Append('"').ToString();
    }
}
