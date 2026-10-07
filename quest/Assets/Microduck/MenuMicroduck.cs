// Microduck - le menu de l'appli du casque : un seul mode actif ; X / Y (manette gauche) : mode suivant / precedent.
// Appairage avec le canard, sans rien taper : au premier lancement, puis a tout moment en cliquant le joystick GAUCHE,
// le casque cherche le canard sur le Wi-Fi (port 8090) et lui demande l'acces ; un parent accepte dans l'appli du
// telephone (Reglages -> Casque) et le casque recoit son adresse et son code, qu'il garde.
// A mettre sur le meme objet que les modes (ExportPlan, ModeAtelier, ModeVerite, ModeDessin, ModeDanse, ModeCanard)
// et que Canard (adresse et code de l'appli du canard).
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class MenuMicroduck : MonoBehaviour
{
    public static MenuMicroduck Ici;
    [Tooltip("Main droite (RightControllerAnchor du Camera Rig) - trouvee seule si vide")]
    public Transform mainDroite;
    [HideInInspector] public Transform pointe;

    ModeMicroduck[] modes;
    int actif;
    TextMesh texte;

    // -- appairage ----------------------------------------------------------------------------------------------------
    bool appairage;
    string messageAppairage = "";

    public string ModeActif => modes != null && modes.Length > 0 ? modes[actif].Nom : "casque";

    void Awake() { Ici = this; }

    void Start()
    {
        var cam = Camera.main != null ? Camera.main.transform : transform;
        texte = Outils.Etiquette3D("", cam, 0.006f);
        texte.transform.localPosition = new Vector3(0f, -0.12f, 0.9f);
        texte.color = Color.white;
        if (mainDroite == null)
        {
            var rig = FindFirstObjectByType<OVRCameraRig>();
            if (rig != null) mainDroite = rig.rightControllerAnchor;
        }
        var b = Outils.Boule(new Color(0.95f, 0.42f, 0.1f), 0.015f, mainDroite);
        b.transform.localPosition = new Vector3(0f, 0f, 0.07f);  // 7 cm devant la manette
        pointe = b.transform;
        modes = GetComponents<ModeMicroduck>();
        for (int i = 0; i < modes.Length; i++) modes[i].enabled = i == 0;
        if (Canard.Ici != null && Canard.Ici.Configure) StartCoroutine(ReperePlan.Charger());
        else Appairer();
    }

    void Appairer()
    {
        if (!appairage) StartCoroutine(Appairage());
    }

    IEnumerator Appairage()
    {
        appairage = true;
        // 1. le canard deja connu repond-il ?
        if (Canard.Ici.Configure)
        {
            string ok = null;
            yield return Canard.Ici.Lire("/api/casque", (t, e) => ok = t);
            if (ok != null) { messageAppairage = "Appaire avec " + Canard.Ici.adresse; appairage = false; yield break; }
        }
        // 2. le chercher sur le Wi-Fi : chaque adresse du reseau local, port 8090, /api/sante (sans code)
        var trouves = new List<string>();
        var noms = new Dictionary<string, string>();
        foreach (var prefixe in Prefixes())
        {
            messageAppairage = "Recherche du canard sur le Wi-Fi (" + prefixe + "x)...";
            int enCours = 0;
            for (int h = 1; h < 255 && trouves.Count == 0; h++)
            {
                string base_ = "http://" + prefixe + h + ":8090";
                enCours++;
                StartCoroutine(Canard.Brut(base_ + "/api/sante", null, 2, (t, c) =>
                {
                    enCours--;
                    var j = t != null ? MiniJson.Lire(t) : null;
                    if (MiniJson.Champ(j, "appli") as string == "microduck")
                    {
                        trouves.Add(base_);
                        noms[base_] = MiniJson.Champ(j, "nom") as string ?? "Microduck";
                    }
                }));
                while (enCours >= 32) yield return null;      // 32 a la fois : ~15 s pour tout le reseau
            }
            while (enCours > 0) yield return null;
            if (trouves.Count > 0) break;
        }
        if (trouves.Count == 0)
        {
            messageAppairage = "Canard introuvable sur le Wi-Fi (son cerveau tourne ? meme reseau ?). Joystick gauche : reessayer";
            appairage = false;
            yield break;
        }
        // 3. demander l'acces ; un parent accepte dans l'appli du telephone
        string adresse = trouves[0], id = null;
        long statut = 0;
        yield return Canard.Brut(adresse + "/api/casque-demande", "{}", 5, (t, c) =>
        {
            statut = c;
            id = t != null ? MiniJson.Champ(MiniJson.Lire(t), "id") as string : null;
        });
        if (id == null)
        {
            messageAppairage = "Demande refusee par " + noms[adresse] + " (" + statut + "). Joystick gauche : reessayer";
            appairage = false;
            yield break;
        }
        float fin = Time.time + 300f;
        while (Time.time < fin)
        {
            messageAppairage = noms[adresse] + " trouve (" + adresse + ").\nAccepte le casque dans son appli : Reglages -> Casque";
            string etat = null, code = null;
            yield return Canard.Brut(adresse + "/api/casque-demande?id=" + id, null, 5, (t, c) =>
            {
                var j = t != null ? MiniJson.Lire(t) : null;
                etat = MiniJson.Champ(j, "etat") as string;
                code = MiniJson.Champ(j, "code") as string;
            });
            if (etat == "accepte" && code != null)
            {
                Canard.Ici.Retenir(adresse, code);
                messageAppairage = "Appaire avec " + noms[adresse] + " !";
                appairage = false;
                StartCoroutine(ReperePlan.Charger());
                yield break;
            }
            if (etat == "refuse" || etat == "inconnue")
            {
                messageAppairage = "Demande " + (etat == "refuse" ? "refusee" : "expiree") + ". Joystick gauche : reessayer";
                appairage = false;
                yield break;
            }
            yield return new WaitForSeconds(2f);
        }
        messageAppairage = "Pas de reponse dans l'appli. Joystick gauche : reessayer";
        appairage = false;
    }

    /// Les debuts d'adresse du reseau local du casque (« 192.168.1. »), puis les plus courants.
    static List<string> Prefixes()
    {
        var out_ = new List<string>();
        try
        {
            foreach (var ni in System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces())
            {
                if (ni.OperationalStatus != System.Net.NetworkInformation.OperationalStatus.Up) continue;
                foreach (var ua in ni.GetIPProperties().UnicastAddresses)
                {
                    var a = ua.Address;
                    if (a.AddressFamily != System.Net.Sockets.AddressFamily.InterNetwork || System.Net.IPAddress.IsLoopback(a)) continue;
                    var b = a.GetAddressBytes();
                    string p = b[0] + "." + b[1] + "." + b[2] + ".";
                    if (!out_.Contains(p)) out_.Add(p);
                }
            }
        }
        catch (System.Exception) { /* pas d'acces aux interfaces : les reseaux courants */ }
        foreach (var p in new[] { "192.168.1.", "192.168.0.", "192.168.2.", "10.0.0." })
            if (!out_.Contains(p)) out_.Add(p);
        return out_;
    }

    void Update()
    {
        if (modes.Length == 0) return;
        if (OVRInput.GetDown(OVRInput.Button.PrimaryThumbstick, OVRInput.Controller.LTouch)) Appairer();
        if (Outils.X() || Outils.Y())
        {
            modes[actif].enabled = false;
            actif = (actif + (Outils.X() ? 1 : modes.Length - 1)) % modes.Length;
            modes[actif].enabled = true;
            if (!ReperePlan.Pret && Canard.Ici != null && Canard.Ici.Configure) StartCoroutine(ReperePlan.Charger());
        }
        texte.text = "Microduck - " + modes[actif].Nom + "  (" + (actif + 1) + "/" + modes.Length + ", X / Y : changer)\n"
                     + (messageAppairage.Length > 0 ? messageAppairage + "\n" : "") + "\n" + modes[actif].Consigne;
    }
}
