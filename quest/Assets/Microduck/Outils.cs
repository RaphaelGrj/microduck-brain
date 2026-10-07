// Microduck - outils communs aux modes : lecture tolerante du MR Utility Kit, manettes, texte flottant, pointeur,
// petites formes (boules, lignes, etiquettes).
using System;
using System.Collections;
using System.Reflection;
using Meta.XR.MRUtilityKit;
using UnityEngine;

public static class Outils
{
    // -- lecture par reflexion (les noms changent selon les versions du MRUK) --------------------------------------
    public static object Lire(object o, string nom)
    {
        if (o == null) return null;
        var t = o.GetType();
        const BindingFlags F = BindingFlags.Public | BindingFlags.Instance;
        var p = t.GetProperty(nom, F);
        if (p != null) return p.GetValue(o);
        var f = t.GetField(nom, F);
        return f != null ? f.GetValue(o) : null;
    }

    public static object Appeler(object o, string nom)
    {
        var m = o?.GetType().GetMethod(nom, BindingFlags.Public | BindingFlags.Instance, null, Type.EmptyTypes, null);
        return m?.Invoke(o, null);
    }

    public static IEnumerable Liste(object o)
    {
        if (o is IEnumerable e) foreach (var x in e) yield return x;
    }

    /// FLOOR, WALL_FACE, TABLE... : « Label » (MRUK recent, enum) ou « AnchorLabels » (ancien).
    public static string Etiquette(MRUKAnchor ancre)
    {
        var v = Lire(ancre, "Label");
        if (v != null) return v.ToString().Split(',')[0].Trim();
        foreach (var o in Liste(Lire(ancre, "AnchorLabels"))) return o.ToString();
        return "OTHER";
    }

    /// Identifiant durable de l'ancre (le meme d'une seance a l'autre), ou null.
    public static string Uuid(MRUKAnchor ancre)
    {
        var a = Lire(ancre, "Anchor");
        var u = Lire(a, "Uuid");
        return u?.ToString();
    }

    // -- manettes (droite : action ; gauche : changer de mode) ------------------------------------------------------
    public static bool Gachette() => OVRInput.GetDown(OVRInput.Button.PrimaryIndexTrigger, OVRInput.Controller.RTouch);
    public static bool Grip() => OVRInput.GetDown(OVRInput.Button.PrimaryHandTrigger, OVRInput.Controller.RTouch);
    public static bool A() => OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.RTouch);
    public static bool B() => OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.RTouch);
    public static bool X() => OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.LTouch);
    public static bool Y() => OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.LTouch);
    public static Vector2 Stick() => OVRInput.Get(OVRInput.Axis2D.PrimaryThumbstick, OVRInput.Controller.RTouch);

    // -- formes ----------------------------------------------------------------------------------------------------
    public static GameObject Boule(Color couleur, float taille, Transform parent = null)
    {
        var b = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        UnityEngine.Object.Destroy(b.GetComponent<Collider>());
        b.transform.localScale = Vector3.one * taille;
        b.GetComponent<Renderer>().material.color = couleur;
        if (parent != null) b.transform.SetParent(parent, false);
        return b;
    }

    public static LineRenderer Ligne(Color couleur, float largeur, Transform parent)
    {
        var go = new GameObject("ligne");
        go.transform.SetParent(parent, false);
        var l = go.AddComponent<LineRenderer>();
        l.material = Materiau("Sprites/Default");
        l.startColor = l.endColor = couleur;
        l.startWidth = l.endWidth = largeur;
        l.positionCount = 0;
        return l;
    }

    /// Un materiau simple, quel que soit le pipeline de rendu du projet (integre ou URP).
    public static Material Materiau(string shader)
    {
        var s = Shader.Find(shader) ?? Shader.Find("Universal Render Pipeline/Unlit") ?? Shader.Find("Unlit/Color");
        return new Material(s);
    }

    public static TextMesh Etiquette3D(string texte, Transform parent, float taille = 0.004f)
    {
        var go = new GameObject("etiquette");
        go.transform.SetParent(parent, false);
        var t = go.AddComponent<TextMesh>();
        t.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        go.GetComponent<MeshRenderer>().material = t.font.material;
        t.characterSize = taille;
        t.fontSize = 60;
        t.anchor = TextAnchor.MiddleCenter;
        t.alignment = TextAlignment.Center;
        t.text = texte;
        return t;
    }

    /// Une etiquette tournee vers la personne qui porte le casque.
    public static void FaceALaCamera(Transform t)
    {
        if (Camera.main == null) return;
        t.rotation = Quaternion.LookRotation(t.position - Camera.main.transform.position);
    }
}
