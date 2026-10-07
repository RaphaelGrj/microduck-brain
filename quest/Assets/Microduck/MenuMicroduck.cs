// Microduck - le menu de l'appli du casque : un seul mode actif ; X / Y (manette gauche) : mode suivant / precedent.
// Appairage avec le canard (son adresse et son code, au clavier du casque) : au premier lancement, puis a tout moment
// en cliquant le joystick GAUCHE. L'appli du canard (Reglages -> Casque) affiche l'adresse et le code a taper.
// A mettre sur le meme objet que les modes (ExportPlan, ModeAtelier, ModeVerite, ModeDessin, ModeDanse, ModeCanard)
// et que Canard (adresse et code de l'appli du canard).
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

    // -- appairage --------------------------------------------------------------------------------------------------
    TouchScreenKeyboard clavier;
    int etapeAppairage = -1;                   // -1 : rien ; 0 : adresse ; 1 : code ; 2 : verification
    string adresseSaisie = "", messageAppairage = "";

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
        etapeAppairage = 0;
        messageAppairage = "";
        string actuelle = Canard.Ici != null && Canard.Ici.Configure ? Canard.Ici.adresse : "http://192.168.1.";
        clavier = TouchScreenKeyboard.Open(actuelle, TouchScreenKeyboardType.URL, false, false, false);
    }

    void SuivreAppairage()
    {
        if (clavier == null) return;
        if (clavier.status == TouchScreenKeyboard.Status.Canceled || clavier.status == TouchScreenKeyboard.Status.LostFocus)
        {
            clavier = null;
            etapeAppairage = -1;
            messageAppairage = "Appairage annule (joystick gauche : recommencer)";
            return;
        }
        if (clavier.status != TouchScreenKeyboard.Status.Done) return;
        if (etapeAppairage == 0)
        {
            adresseSaisie = clavier.text;
            etapeAppairage = 1;
            clavier = TouchScreenKeyboard.Open("", TouchScreenKeyboardType.Default, false, false, true);
            return;
        }
        string code = clavier.text;
        clavier = null;
        etapeAppairage = 2;
        Canard.Ici.Retenir(adresseSaisie, code);
        StartCoroutine(Verifier());
    }

    System.Collections.IEnumerator Verifier()
    {
        messageAppairage = "Verification...";
        string rep = null, err = null;
        yield return Canard.Ici.Lire("/api/casque", (t, e) => { rep = t; err = e; });
        etapeAppairage = -1;
        messageAppairage = rep != null ? "Appaire avec " + Canard.Ici.adresse
                                       : "Pas de reponse (" + err + ") : verifier l'adresse et le code (joystick gauche)";
        if (rep != null) StartCoroutine(ReperePlan.Charger());
    }

    void Update()
    {
        if (modes.Length == 0) return;
        if (OVRInput.GetDown(OVRInput.Button.PrimaryThumbstick, OVRInput.Controller.LTouch)) Appairer();
        if (etapeAppairage >= 0)
        {
            SuivreAppairage();
            texte.text = "Microduck - appairage\n\n" + (etapeAppairage == 0 ? "Adresse du canard (Reglages -> Casque de son appli)"
                         : etapeAppairage == 1 ? "Code de son appli" : messageAppairage);
            return;
        }
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
