// Microduck - mode « Etre le canard » : sa tete suit la tienne, tu le fais marcher au joystick, et tu vois ce qu'il
// voit - SEULEMENT si les photos sont permises dans ses reglages (opt-in, code parent ; sinon pas d'image).
//   A : recentrer (ta position actuelle = sa tete droite). Joystick : avancer / tourner (pas guides, avec les
//   garde-fous de sa telecommande : vide, obstacle, zone interdite). B : stop.
using System.Collections;
using UnityEngine;

public class ModeCanard : ModeMicroduck
{
    public override string Nom => "Etre le canard";

    Quaternion repos;
    bool recentre;
    float tRegard, tPas, tImage;
    bool imageEnCours;
    Renderer ecran;
    Texture2D derniere;
    string etatImage = "";

    public override string Consigne =>
        "Sa tete suit la tienne   A : recentrer   Joystick : marcher   B : stop\n" + etatImage + "\n" + message;

    protected override void OnEnable()
    {
        recentre = false;
        if (ecran == null && Camera.main != null)
        {
            var q = GameObject.CreatePrimitive(PrimitiveType.Quad);
            Destroy(q.GetComponent<Collider>());
            q.transform.SetParent(Camera.main.transform, false);
            q.transform.localPosition = new Vector3(0f, 0.05f, 1.2f);
            q.transform.localScale = new Vector3(0.45f, 0.8f, 1f);     // image portrait 360 x 640
            ecran = q.GetComponent<Renderer>();
            ecran.material = Outils.Materiau("Unlit/Texture");
        }
        if (ecran != null) ecran.gameObject.SetActive(true);
    }

    protected override void OnDisable()
    {
        if (ecran != null) ecran.gameObject.SetActive(false);
        if (Canard.Ici != null && Canard.Ici.Configure)
            Canard.Ici.StartCoroutine(Canard.Ici.Envoyer("/api/regard", "{\"lacet\":0,\"tangage\":0}"));
    }

    void Update()
    {
        var tete = Camera.main != null ? Camera.main.transform : null;
        if (tete == null || Canard.Ici == null || !Canard.Ici.Configure) { message = "Adresse du canard a renseigner"; return; }
        if (!recentre || Outils.A()) { repos = tete.rotation; recentre = true; }
        if (Time.time - tRegard >= 0.1f)
        {
            tRegard = Time.time;
            var r = (Quaternion.Inverse(repos) * tete.rotation).eulerAngles;
            float lacet = Mathf.Clamp(-Mathf.DeltaAngle(0f, r.y) * Mathf.Deg2Rad, -0.9f, 0.9f);
            float tangage = Mathf.Clamp(Mathf.DeltaAngle(0f, r.x) * Mathf.Deg2Rad, -0.5f, 0.6f);
            StartCoroutine(Canard.Ici.Envoyer("/api/regard",
                "{\"lacet\":" + MiniJson.N(lacet) + ",\"tangage\":" + MiniJson.N(tangage) + "}"));
        }
        var s = Outils.Stick();
        if (Time.time - tPas >= 0.8f)
        {
            if (s.y > 0.6f) { Canard.Ici.Commande("avance"); tPas = Time.time; }
            else if (s.x < -0.6f) { Canard.Ici.Commande("gauche"); tPas = Time.time; }
            else if (s.x > 0.6f) { Canard.Ici.Commande("droite"); tPas = Time.time; }
        }
        if (Outils.B()) Canard.Ici.Commande("stop");
        if (!imageEnCours && Time.time - tImage >= 0.25f) StartCoroutine(Image());
    }

    IEnumerator Image()
    {
        imageEnCours = true;
        tImage = Time.time;
        Texture2D tex = null;
        string err = null;
        yield return Canard.Ici.Image("/api/vue", (t, e) => { tex = t; err = e; });
        imageEnCours = false;
        if (tex == null) { etatImage = "Pas d'image : " + err; tImage = Time.time + 2f; yield break; }
        if (derniere != null) Destroy(derniere);
        derniere = tex;
        ecran.material.mainTexture = tex;
        etatImage = "";
    }
}
