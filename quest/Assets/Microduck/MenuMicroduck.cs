// Microduck - le menu de l'appli du casque : un seul mode actif ; X / Y (manette gauche) : mode suivant / precedent.
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
    }

    void Update()
    {
        if (modes.Length == 0) return;
        if (Outils.X() || Outils.Y())
        {
            modes[actif].enabled = false;
            actif = (actif + (Outils.X() ? 1 : modes.Length - 1)) % modes.Length;
            modes[actif].enabled = true;
            if (!ReperePlan.Pret && Canard.Ici != null && Canard.Ici.Configure) StartCoroutine(ReperePlan.Charger());
        }
        texte.text = "Microduck - " + modes[actif].Nom + "  (" + (actif + 1) + "/" + modes.Length + ", X / Y : changer)\n\n"
                     + modes[actif].Consigne;
    }
}
