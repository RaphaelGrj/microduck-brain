// Microduck - mode « Jumeau » : le canard SIMULE (duck-sim, sur le PC) dessine en vrai dans ta piece, a sa taille, pilote
// par son vrai cerveau et sa vraie appli. Tout s'essaie avant la livraison : telecommande, « va la », ronde, jeux...
//
//   Jeu       Gachette tenue puis relachee : lancer la balle (il la voit et joue avec).
//             Grip tenu, la main sur sa tete : le caresser.        A : passer aux couleurs.   B : reposer son origine.
//   Couleurs  Vise une piece avec la manette. Joystick gauche / droite : choisir la couleur ; haut / bas : changer de
//             schema. Gachette : peindre la piece visee. Grip : enregistrer le schema dans son appli. A : retour au jeu.
//
// Ses couleurs sont celles du schema actif de son appli (design space) : un schema change sur le telephone change le
// canard du casque, en direct ; un schema peint dans le casque s'enregistre dans son appli.
// Sans simulateur, le canard reste debout, immobile, a son origine : pratique pour choisir ses couleurs.
// Ses sons : joues si les fichiers sont dans Assets/Resources/SonsCanard/<son> (chirp, coo...) ; sinon une note
// flottante au-dessus de sa tete.
using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class ModeJumeau : ModeMicroduck
{
    public override string Nom => "Jumeau";

    // la meme palette que le design space de l'appli (interface/design.js)
    static readonly string[][] PALETTE =
    {
        new[] { "Blanc", "#f4f4f2" }, new[] { "Gris clair", "#c9c9c4" }, new[] { "Gris", "#7d7f84" },
        new[] { "Noir", "#26272b" }, new[] { "Orange Microduck", "#f26a1b" }, new[] { "Jaune", "#f4b023" },
        new[] { "Rouge", "#d7322b" }, new[] { "Rose", "#e98bb5" }, new[] { "Violet", "#7a4fc4" },
        new[] { "Bleu", "#2f6fd6" }, new[] { "Turquoise", "#25a5a0" }, new[] { "Vert", "#4c9a3d" },
        new[] { "Beige", "#d9c7a7" }, new[] { "Bois", "#9b6b43" },
    };
    static readonly string[] TETE = { "yaw_roll_motion", "bearing_roll", "jaw_soft", "neck_pitch" };

    // -- le modele --------------------------------------------------------------------------------------------------
    Transform racine;
    readonly Dictionary<string, Transform> corps = new Dictionary<string, Transform>();
    readonly Dictionary<string, Vector3> ciblePos = new Dictionary<string, Vector3>();
    readonly Dictionary<string, Quaternion> cibleRot = new Dictionary<string, Quaternion>();
    readonly Dictionary<string, float[]> poseDebout = new Dictionary<string, float[]>();   // corps -> [x y z qw qx qy qz]
    readonly Dictionary<string, List<Renderer>> groupes = new Dictionary<string, List<Renderer>>();
    readonly Dictionary<string, Color> origine = new Dictionary<string, Color>();
    readonly Dictionary<string, string> nomGroupe = new Dictionary<string, string>();
    readonly HashSet<string> imprimables = new HashSet<string>();
    bool modeleCharge, chargement, collisions;
    string etatModele = "";

    // -- le simulateur -------------------------------------------------------------------------------------------------
    Transform balle, note;
    float tNote = -10f, tLecture, tCaresse, tDesign;
    bool lecture, simu, lectureDesign;
    double depuis;
    string repere = "libre";
    AudioSource voix;

    // -- l'origine (repere du simulateur dans la piece) -----------------------------------------------------------------
    bool ancre;
    int etapeAncre;
    Vector3 C, F = Vector3.forward, G = Vector3.left, depart;
    float sol;

    // -- lancer --------------------------------------------------------------------------------------------------------
    readonly Queue<KeyValuePair<float, Vector3>> trace = new Queue<KeyValuePair<float, Vector3>>();
    Transform tenue;

    // -- couleurs ------------------------------------------------------------------------------------------------------
    bool enCouleurs, modifie;
    object design;                           // /api/design tel que lu (filaments, couleurs, schemas, actif)
    string designTexte = "";
    readonly Dictionary<string, string> couleurs = new Dictionary<string, string>();   // groupe -> #rrggbb (en cours)
    readonly List<string[]> nuancier = new List<string[]>();
    int choix, schemaChoisi = -1;
    float tStick;
    string vise;
    Transform pastille;

    public override string Consigne
    {
        get
        {
            if (Canard.Ici == null || !Canard.Ici.Configure) return "Adresse du canard a renseigner (objet Microduck -> Canard)";
            if (!modeleCharge) return "Chargement du canard... " + etatModele;
            if (!ancre)
                return etapeAncre == 0 ? "Ou est-il ne ? Gachette : la pointe au sol, la ou le simulateur le fait naitre"
                                       : "Gachette : un point au sol DEVANT lui (sa direction de depart)";
            string etat = simu ? "Simulateur : en direct" + (repere == "plan" ? " (scene de ta maison)" : "")
                               : "Pas de simulateur : canard immobile (duck-sim lance ?)";
            if (enCouleurs)
            {
                string nom = vise != null && nomGroupe.ContainsKey(vise) ? nomGroupe[vise] : "(vise une piece)";
                string schema = MiniJson.Champ(design, "actif") as string ?? "Couleurs d'origine";
                return "COULEURS - " + schema + (modifie ? " (modifie)" : "") + "\nPiece : " + nom
                       + "\nCouleur : " + nuancier[choix][0]
                       + "\nJoystick : couleur / schema   Gachette : peindre   Grip : enregistrer   A : jeu\n" + message;
            }
            return etat + "\nGachette tenue puis relachee : lancer la balle   Grip sur sa tete : caresse\n"
                   + "A : couleurs   B : reposer son origine\n" + message;
        }
    }

    protected override void OnEnable()
    {
        if (racine == null) racine = new GameObject("Jumeau").transform;
        racine.gameObject.SetActive(true);
        if (!modeleCharge && !chargement && Canard.Ici != null && Canard.Ici.Configure) StartCoroutine(ChargerModele());
        AncreAutomatique();
    }

    protected override void OnDisable()
    {
        if (racine != null) racine.gameObject.SetActive(false);
        if (tenue != null) tenue.gameObject.SetActive(false);
    }

    // =================================================================================================================
    // Repere : simulateur (x devant, y gauche, z haut) -> piece
    // =================================================================================================================
    void AncreAutomatique()
    {
        // scene de la maison : le repere du simulateur EST celui du plan, pose par l'ancre du sol (ReperePlan)
        if (repere == "plan" && ReperePlan.Pret)
        {
            C = ReperePlan.Origine;
            F = ReperePlan.Devant;
            G = ReperePlan.Gauche;
            sol = ReperePlan.Sol;
            ancre = true;
        }
    }

    Vector3 Monde(float x, float y, float z) => new Vector3(C.x, sol, C.z) + x * F + y * G + z * Vector3.up;

    Vector3 Dir(float x, float y, float z) => x * F + y * G + z * Vector3.up;

    Quaternion Rot(float w, float x, float y, float z)
    {
        // colonnes x et z de la rotation (repere du simulateur), portees dans la piece
        var ex = Dir(1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y));
        var ez = Dir(2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y));
        return Quaternion.LookRotation(ex, ez);
    }

    Vector3 VersSimu(Vector3 p) { var v = p - new Vector3(C.x, sol, C.z); return new Vector3(Vector3.Dot(v, F), Vector3.Dot(v, G), v.y); }

    Vector3 VitesseSimu(Vector3 v) => new Vector3(Vector3.Dot(v, F), Vector3.Dot(v, G), v.y);

    // un point du repere du simulateur dans le repere du maillage Unity (x droite, y haut, z devant)
    static Vector3 M0(float x, float y, float z) => new Vector3(-y, z, x);

    static Quaternion RotationLocale(float[] l)
    {
        // l = [a00 a01 a02 b0, a10 a11 a12 b1, a20 a21 a22 b2] : colonnes x et z de A, dans le repere du maillage
        var fx = M0(l[0], l[4], l[8]);
        var fz = M0(l[2], l[6], l[10]);
        return Quaternion.LookRotation(fx, fz);
    }

    // =================================================================================================================
    // Modele : /design/microduck.json + .bin (le meme que le design space de l'appli)
    // =================================================================================================================
    IEnumerator ChargerModele()
    {
        chargement = true;
        etatModele = "description";
        string texte = null, err = null;
        yield return Canard.Ici.Lire("/design/microduck.json", (t, e) => { texte = t; err = e; });
        if (texte == null) { etatModele = "echec : " + err; chargement = false; yield break; }
        byte[] bin = null;
        etatModele = "maillages (4 Mo)";
        yield return Canard.Ici.LireOctets("/design/microduck.bin", (b, e) => { bin = b; err = e; });
        if (bin == null) { etatModele = "echec : " + err; chargement = false; yield break; }
        var m = MiniJson.Lire(texte);
        try { Construire(m, bin); }
        catch (Exception e) { etatModele = "modele illisible : " + e.Message; chargement = false; yield break; }
        modeleCharge = true;
        chargement = false;
        balle = Outils.Boule(new Color(1f, 0.55f, 0f), 0.07f, racine).transform;
        balle.gameObject.SetActive(false);
        tenue = Outils.Boule(new Color(1f, 0.55f, 0f), 0.07f, null).transform;
        tenue.gameObject.SetActive(false);
        var n = Outils.Etiquette3D("", racine, 0.003f);
        n.color = new Color(1f, 0.85f, 0.3f);
        note = n.transform;
        voix = racine.gameObject.AddComponent<AudioSource>();
        voix.spatialBlend = 1f;
        voix.minDistance = 0.3f;
        PoseDebout();
        yield return LireDesign(true);
    }

    void Construire(object m, byte[] bin)
    {
        int octetsPositions = (int)MiniJson.Nombre(MiniJson.Champ(m, "octets_positions"));
        int octetsNormales = (int)MiniJson.Nombre(MiniJson.Champ(m, "octets_normales"));
        int indices0 = octetsPositions + octetsNormales;
        foreach (var g in MiniJson.Liste(MiniJson.Champ(m, "groupes")))
        {
            string id = MiniJson.Champ(g, "id") as string;
            nomGroupe[id] = MiniJson.Champ(g, "nom") as string ?? id;
            origine[id] = Couleur(MiniJson.Champ(g, "origine") as string, Color.gray);
            if (MiniJson.Champ(g, "imprimable") is bool imp && imp) imprimables.Add(id);
            groupes[id] = new List<Renderer>();
        }
        var maillages = new Dictionary<string, Mesh>();
        var pieces = MiniJson.Champ(m, "pieces") as Dictionary<string, object>;
        foreach (var kv in pieces)
        {
            var v = MiniJson.Liste(MiniJson.Champ(kv.Value, "v"));
            var f = MiniJson.Liste(MiniJson.Champ(kv.Value, "f"));
            int v0 = (int)MiniJson.Nombre(v[0]), nv = (int)MiniJson.Nombre(v[1]) / 3;
            int n0 = (int)MiniJson.Nombre(MiniJson.Champ(kv.Value, "n"));
            int f0 = (int)MiniJson.Nombre(f[0]), nf = (int)MiniJson.Nombre(f[1]);
            var pos = new Vector3[nv];
            var nor = new Vector3[nv];
            for (int i = 0; i < nv; i++)
            {
                int o = (v0 + 3 * i) * 4;
                pos[i] = M0(BitConverter.ToSingle(bin, o), BitConverter.ToSingle(bin, o + 4), BitConverter.ToSingle(bin, o + 8));
                int p = octetsPositions + n0 + 3 * i;
                nor[i] = M0((sbyte)bin[p] / 127f, (sbyte)bin[p + 1] / 127f, (sbyte)bin[p + 2] / 127f).normalized;
            }
            var tri = new int[nf];
            for (int i = 0; i < nf; i++) tri[i] = BitConverter.ToUInt16(bin, indices0 + (f0 + i) * 2);
            // M0 retourne le repere (direct -> indirect) : on inverse l'ordre des sommets pour garder les faces dehors
            for (int i = 0; i + 2 < nf; i += 3) { int t = tri[i + 1]; tri[i + 1] = tri[i + 2]; tri[i + 2] = t; }
            var mesh = new Mesh { name = kv.Key };
            mesh.vertices = pos;
            mesh.normals = nor;
            mesh.triangles = tri;
            mesh.RecalculateBounds();
            maillages[kv.Key] = mesh;
        }
        foreach (var inst in MiniJson.Liste(MiniJson.Champ(m, "instances")))
        {
            string nomCorps = MiniJson.Champ(inst, "corps") as string ?? "trunk_base";
            string groupe = MiniJson.Champ(inst, "groupe") as string;
            var l = Nombres(MiniJson.Champ(inst, "l"));
            var w = Nombres(MiniJson.Champ(inst, "m"));
            if (l.Length != 12 || w.Length != 12) continue;
            if (!corps.TryGetValue(nomCorps, out var c))
            {
                c = new GameObject(nomCorps).transform;
                c.SetParent(racine, false);
                corps[nomCorps] = c;
                poseDebout[nomCorps] = PoseDuCorps(w, l);
            }
            var go = new GameObject(MiniJson.Champ(inst, "piece") as string);
            go.transform.SetParent(c, false);
            go.transform.localPosition = M0(l[3], l[7], l[11]);
            go.transform.localRotation = RotationLocale(l);
            go.AddComponent<MeshFilter>().sharedMesh = maillages[MiniJson.Champ(inst, "piece") as string];
            var r = go.AddComponent<MeshRenderer>();
            r.material = Outils.MateriauEclaire(origine.ContainsKey(groupe) ? origine[groupe] : Color.gray);
            if (groupe != null && groupes.ContainsKey(groupe)) groupes[groupe].Add(r);
            go.AddComponent<PieceJumeau>().groupe = groupe;
        }
        etatModele = "";
    }

    static float[] Nombres(object o)
    {
        var l = MiniJson.Liste(o);
        var t = new float[l.Count];
        for (int i = 0; i < l.Count; i++) t[i] = MiniJson.Nombre(l[i]);
        return t;
    }

    // pose du corps (debout) dans le repere du simulateur, d'apres une de ses pieces : monde = corps . local
    static float[] PoseDuCorps(float[] w, float[] l)
    {
        // R = Aw . Al^T ; p = bw - R . bl
        var R = new float[9];
        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++)
                R[3 * i + j] = w[4 * i] * l[4 * j] + w[4 * i + 1] * l[4 * j + 1] + w[4 * i + 2] * l[4 * j + 2];
        var p = new float[3];
        for (int i = 0; i < 3; i++) p[i] = w[4 * i + 3] - (R[3 * i] * l[3] + R[3 * i + 1] * l[7] + R[3 * i + 2] * l[11]);
        // matrice -> quaternion (w, x, y, z)
        float tr = R[0] + R[4] + R[8], qw, qx, qy, qz;
        if (tr > 0f)
        {
            float s = Mathf.Sqrt(tr + 1f) * 2f;
            qw = 0.25f * s; qx = (R[7] - R[5]) / s; qy = (R[2] - R[6]) / s; qz = (R[3] - R[1]) / s;
        }
        else if (R[0] > R[4] && R[0] > R[8])
        {
            float s = Mathf.Sqrt(1f + R[0] - R[4] - R[8]) * 2f;
            qw = (R[7] - R[5]) / s; qx = 0.25f * s; qy = (R[1] + R[3]) / s; qz = (R[2] + R[6]) / s;
        }
        else if (R[4] > R[8])
        {
            float s = Mathf.Sqrt(1f + R[4] - R[0] - R[8]) * 2f;
            qw = (R[2] - R[6]) / s; qx = (R[1] + R[3]) / s; qy = 0.25f * s; qz = (R[5] + R[7]) / s;
        }
        else
        {
            float s = Mathf.Sqrt(1f + R[8] - R[0] - R[4]) * 2f;
            qw = (R[3] - R[1]) / s; qx = (R[2] + R[6]) / s; qy = (R[5] + R[7]) / s; qz = 0.25f * s;
        }
        return new[] { p[0], p[1], p[2], qw, qx, qy, qz };
    }

    void PoseDebout()
    {
        foreach (var kv in poseDebout) Cible(kv.Key, kv.Value, true);
    }

    void Cible(string nom, float[] q, bool aussitot)
    {
        if (!corps.ContainsKey(nom) || q.Length < 7) return;
        ciblePos[nom] = Monde(q[0], q[1], q[2]);
        cibleRot[nom] = Rot(q[3], q[4], q[5], q[6]);
        if (aussitot) corps[nom].SetPositionAndRotation(ciblePos[nom], cibleRot[nom]);
    }

    // =================================================================================================================
    // Boucle
    // =================================================================================================================
    void Update()
    {
        if (!modeleCharge || Canard.Ici == null || !Canard.Ici.Configure) return;
        if (!ancre) { Ancrer(); return; }
        if (!lecture && Time.time - tLecture >= 1f / 30f) StartCoroutine(Lire());
        if (!lectureDesign && !modifie && Time.time - tDesign >= 2f) StartCoroutine(LireDesign(false));
        // mouvements adoucis : 30 poses par seconde, affichage a 72-90 images par seconde
        float k = 1f - Mathf.Exp(-Time.deltaTime * 25f);
        foreach (var kv in corps)
            if (ciblePos.ContainsKey(kv.Key))
                kv.Value.SetPositionAndRotation(Vector3.Lerp(kv.Value.position, ciblePos[kv.Key], k),
                                                Quaternion.Slerp(kv.Value.rotation, cibleRot[kv.Key], k));
        if (note != null)
        {
            note.gameObject.SetActive(Time.time - tNote < 1.4f);
            if (corps.TryGetValue("yaw_roll_motion", out var tete)) note.position = tete.position + Vector3.up * (0.12f + 0.05f * (Time.time - tNote));
            Outils.FaceALaCamera(note);
        }
        if (enCouleurs) Couleurs(); else Jeu();
    }

    void Ancrer()
    {
        AncreAutomatique();
        if (ancre || Pointe == null || !Outils.Gachette()) return;
        var p = Pointe.position;
        if (etapeAncre == 0) { depart = p; etapeAncre = 1; return; }
        var d = new Vector3(p.x - depart.x, 0f, p.z - depart.z);
        if (d.magnitude < 0.05f) return;
        C = depart;
        sol = depart.y;
        F = d.normalized;
        G = new Vector3(-F.z, 0f, F.x);
        ancre = true;
        etapeAncre = 0;
        if (!simu) PoseDebout();
    }

    void Jeu()
    {
        if (Outils.A()) { enCouleurs = true; message = ""; return; }
        if (Outils.B() && repere != "plan") { ancre = false; etapeAncre = 0; message = "Repose son origine"; return; }
        if (Pointe == null) return;
        // la balle dans la main, puis lancee avec la vitesse de la main
        trace.Enqueue(new KeyValuePair<float, Vector3>(Time.time, Pointe.position));
        while (trace.Count > 0 && Time.time - trace.Peek().Key > 0.12f) trace.Dequeue();
        if (Outils.GachetteTenue() && simu)
        {
            tenue.gameObject.SetActive(true);
            tenue.position = Pointe.position;
        }
        if (Outils.GachetteRelachee() && tenue.gameObject.activeSelf)
        {
            tenue.gameObject.SetActive(false);
            var premier = trace.Peek();
            float dt = Mathf.Max(0.02f, Time.time - premier.Key);
            var v = VitesseSimu((Pointe.position - premier.Value) / dt);
            var p = VersSimu(Pointe.position);
            StartCoroutine(Canard.Ici.Envoyer("/api/jumeau-balle",
                "{\"pos\":[" + MiniJson.N(p.x) + "," + MiniJson.N(p.y) + "," + MiniJson.N(p.z) + "],\"vel\":["
                + MiniJson.N(v.x) + "," + MiniJson.N(v.y) + "," + MiniJson.N(v.z) + "]}",
                (r, e) => message = r != null ? "Balle lancee" : "Lancer impossible : " + e));
        }
        // la main sur sa tete, grip tenu : une caresse par seconde
        if (Outils.GripTenu() && simu && Time.time - tCaresse > 1f)
        {
            foreach (var nom in TETE)
                if (corps.TryGetValue(nom, out var t) && Vector3.Distance(t.position, Pointe.position) < 0.12f)
                {
                    tCaresse = Time.time;
                    StartCoroutine(Canard.Ici.Envoyer("/api/jumeau-caresse", "{}"));
                    message = "Caresse";
                    break;
                }
        }
    }

    IEnumerator Lire()
    {
        lecture = true;
        tLecture = Time.time;
        string texte = null;
        yield return Canard.Ici.Lire("/api/jumeau?depuis=" + depuis.ToString(System.Globalization.CultureInfo.InvariantCulture),
                                     (t, e) => texte = t);
        lecture = false;
        if (texte == null)
        {
            if (simu) { simu = false; PoseDebout(); if (balle != null) balle.gameObject.SetActive(false); }
            tLecture = Time.time + 1f;          // pas de simulateur : on reessaie doucement
            yield break;
        }
        var e2 = MiniJson.Lire(texte);
        simu = true;
        string r = MiniJson.Champ(e2, "repere") as string ?? "libre";
        if (r != repere) { repere = r; if (repere == "plan") { ancre = false; AncreAutomatique(); } }
        if (MiniJson.Champ(e2, "corps") is Dictionary<string, object> cs)
            foreach (var kv in cs) Cible(kv.Key, Nombres(kv.Value), false);
        bool vue = false;
        if (MiniJson.Champ(e2, "balles") is Dictionary<string, object> bs)
            foreach (var kv in bs)
            {
                var b = Nombres(kv.Value);
                if (b.Length < 3) continue;
                balle.position = Monde(b[0], b[1], b[2]);
                vue = true;
                break;
            }
        balle.gameObject.SetActive(vue && !(tenue != null && tenue.gameObject.activeSelf));
        if (depuis == 0.0)
        {
            // premiere lecture : on ne rejoue pas les sons d'avant l'arrivee dans le mode
            depuis = MiniJson.Champ(e2, "maintenant") is double mt ? mt : 0.0;
            yield break;
        }
        foreach (var s in MiniJson.Liste(MiniJson.Champ(e2, "sons")))
        {
            var l = MiniJson.Liste(s);
            if (l.Count < 2) continue;
            depuis = Math.Max(depuis, l[0] is double d ? d : 0.0);
            Son(l[1] as string);
        }
    }

    void Son(string tag)
    {
        if (string.IsNullOrEmpty(tag)) return;
        var clip = Resources.Load<AudioClip>("SonsCanard/" + tag);
        if (clip != null && corps.TryGetValue("yaw_roll_motion", out var tete))
        {
            voix.transform.position = tete.position;
            voix.PlayOneShot(clip);
            return;
        }
        note.GetComponent<TextMesh>().text = "♪ " + tag;
        tNote = Time.time;
    }

    // =================================================================================================================
    // Couleurs : le schema actif de son appli, peint en direct dans le casque
    // =================================================================================================================
    IEnumerator LireDesign(bool premiere)
    {
        lectureDesign = true;
        tDesign = Time.time;
        string texte = null;
        yield return Canard.Ici.Lire("/api/design", (t, e) => texte = t);
        lectureDesign = false;
        if (texte == null || (!premiere && texte == designTexte) || modifie) yield break;
        designTexte = texte;
        design = MiniJson.Lire(texte);
        Nuancier();
        AppliquerSchema(MiniJson.Champ(design, "actif") as string);
    }

    List<object> Schemas() => MiniJson.Liste(MiniJson.Champ(design, "schemas"));

    void AppliquerSchema(string nom)
    {
        couleurs.Clear();
        schemaChoisi = -1;
        var sc = Schemas();
        for (int i = 0; i < sc.Count; i++)
            if (MiniJson.Champ(sc[i], "nom") as string == nom)
            {
                schemaChoisi = i;
                if (MiniJson.Champ(sc[i], "couleurs") is Dictionary<string, object> c)
                    foreach (var kv in c) if (kv.Value is string h) couleurs[kv.Key] = h;
            }
        foreach (var kv in groupes)
        {
            var col = couleurs.ContainsKey(kv.Key) ? Couleur(couleurs[kv.Key], origine[kv.Key]) : origine[kv.Key];
            foreach (var r in kv.Value) r.material.color = col;
        }
    }

    void Nuancier()
    {
        nuancier.Clear();
        foreach (var f in MiniJson.Liste(MiniJson.Champ(design, "filaments")))
            nuancier.Add(new[] { MiniJson.Champ(f, "nom") as string ?? "?", MiniJson.Champ(f, "couleur") as string ?? "#888888" });
        foreach (var f in MiniJson.Liste(MiniJson.Champ(design, "couleurs")))
            nuancier.Add(new[] { MiniJson.Champ(f, "nom") as string ?? "?", MiniJson.Champ(f, "couleur") as string ?? "#888888" });
        nuancier.AddRange(PALETTE);
        choix = Mathf.Clamp(choix, 0, nuancier.Count - 1);
    }

    void Couleurs()
    {
        if (Outils.A()) { enCouleurs = false; message = ""; if (pastille != null) pastille.gameObject.SetActive(false); return; }
        if (!collisions)
        {
            // pour viser une piece : une forme de collision par piece (une fois, a la premiere visite)
            foreach (var kv in groupes) foreach (var r in kv.Value) r.gameObject.AddComponent<MeshCollider>();
            collisions = true;
        }
        if (nuancier.Count == 0) Nuancier();
        var s = Outils.Stick();
        if (Time.time - tStick > 0.25f)
        {
            if (Mathf.Abs(s.x) > 0.6f) { choix = (choix + (s.x > 0 ? 1 : nuancier.Count - 1)) % nuancier.Count; tStick = Time.time; }
            else if (Mathf.Abs(s.y) > 0.6f && design != null)
            {
                // schemas enregistres, puis « couleurs d'origine »
                int n = Schemas().Count + 1;
                int i = ((schemaChoisi < 0 ? n - 1 : schemaChoisi) + (s.y > 0 ? 1 : n - 1)) % n;
                string nom = i < n - 1 ? MiniJson.Champ(Schemas()[i], "nom") as string : null;
                AppliquerSchema(nom);
                ((Dictionary<string, object>)design)["actif"] = nom;
                modifie = false;
                StartCoroutine(Enregistrer("Schema : " + (nom ?? "couleurs d'origine")));
                tStick = Time.time;
            }
        }
        vise = null;
        var main = MenuMicroduck.Ici != null ? MenuMicroduck.Ici.mainDroite : null;
        if (main != null && Physics.Raycast(main.position, main.forward, out var hit, 3f))
        {
            var p = hit.collider.GetComponent<PieceJumeau>();
            if (p != null) vise = p.groupe;
        }
        // (sur la main, pas sur la pointe : la pointe est une boule reduite, ses enfants le seraient aussi)
        if (pastille == null && main != null) pastille = Outils.Boule(Color.white, 0.025f, main).transform;
        if (pastille == null) return;
        pastille.gameObject.SetActive(true);
        pastille.localPosition = new Vector3(0f, 0.03f, 0.07f);
        pastille.GetComponent<Renderer>().material.color = Couleur(nuancier[choix][1], Color.white);
        if (Outils.Gachette() && vise != null)
        {
            if (!imprimables.Contains(vise)) { message = nomGroupe[vise] + " : piece achetee, pas a imprimer"; return; }
            couleurs[vise] = nuancier[choix][1].ToLowerInvariant();
            foreach (var r in groupes[vise]) r.material.color = Couleur(couleurs[vise], origine[vise]);
            modifie = true;
            message = nomGroupe[vise] + " : " + nuancier[choix][0];
        }
        if (Outils.Grip() && modifie && design != null) StartCoroutine(EnregistrerNouveau());
    }

    IEnumerator EnregistrerNouveau()
    {
        // un schema peint dans le casque : « Casque N » (on met a jour celui en cours s'il vient deja du casque)
        var d = (Dictionary<string, object>)design;
        var sc = Schemas();
        string actif = MiniJson.Champ(d, "actif") as string;
        string nom = actif != null && actif.StartsWith("Casque") ? actif : null;
        if (nom == null)
        {
            int k = 1;
            bool pris;
            do
            {
                nom = "Casque " + k++;
                pris = false;
                foreach (var s in sc) if (MiniJson.Champ(s, "nom") as string == nom) pris = true;
            } while (pris);
        }
        var c = new Dictionary<string, object>();
        foreach (var kv in couleurs) c[kv.Key] = kv.Value;
        var nouveau = new Dictionary<string, object> { { "nom", nom }, { "couleurs", c } };
        sc.RemoveAll(s => MiniJson.Champ(s, "nom") as string == nom);
        sc.Add(nouveau);
        d["schemas"] = sc;
        d["actif"] = nom;
        yield return Enregistrer("Enregistre : " + nom);
    }

    IEnumerator Enregistrer(string ok)
    {
        string json = MiniJson.Ecrire(design);
        string reponse = null, err = null;
        yield return Canard.Ici.Envoyer("/api/design", json, (r, e) => { reponse = r; err = e; });
        if (reponse != null)
        {
            modifie = false;
            designTexte = "";               // relu tel que le canard l'a garde
            message = ok + " (visible dans son appli)";
        }
        else message = "Enregistrement impossible : " + err + " (code parent ?)";
    }

    static Color Couleur(string hex, Color defaut) =>
        hex != null && ColorUtility.TryParseHtmlString(hex, out var c) ? c : defaut;
}

/// Le groupe de couleurs d'une piece du canard jumeau (pour la viser).
public class PieceJumeau : MonoBehaviour
{
    public string groupe;
}
