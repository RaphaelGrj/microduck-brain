// Microduck - la liaison avec le canard (son appli, port 8090, reseau local) : adresse et code, requetes HTTP.
// Le casque ne recoit que ce que l'appli du telephone recoit : des positions, des etats ; une image de la camera
// seulement si les photos sont permises dans ses reglages (opt-in, code parent).
using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

public class Canard : MonoBehaviour
{
    [Tooltip("Adresse de l'appli du canard, ex. http://192.168.1.50:8090 (vide : pas de canard, scan seulement)")]
    public string adresse = "";
    [Tooltip("Code de l'appli du canard (code parent)")]
    public string code = "";

    public static Canard Ici;
    public bool Configure => !string.IsNullOrWhiteSpace(adresse);

    void Awake() { Ici = this; }

    UnityWebRequest Preparer(UnityWebRequest r)
    {
        r.SetRequestHeader("X-Microduck-Code", code);
        r.timeout = 5;
        return r;
    }

    /// GET -> texte (null si echec, avec le message d'erreur).
    public IEnumerator Lire(string chemin, Action<string, string> fini)
    {
        if (!Configure) { fini(null, "adresse du canard non renseignee"); yield break; }
        using (var r = Preparer(UnityWebRequest.Get(adresse.TrimEnd('/') + chemin)))
        {
            yield return r.SendWebRequest();
            if (r.result == UnityWebRequest.Result.Success) fini(r.downloadHandler.text, null);
            else fini(null, r.error + " " + r.downloadHandler?.text);
        }
    }

    /// POST JSON -> reponse (null si echec).
    public IEnumerator Envoyer(string chemin, string json, Action<string, string> fini = null)
    {
        if (!Configure) { fini?.Invoke(null, "adresse du canard non renseignee"); yield break; }
        using (var r = Preparer(new UnityWebRequest(adresse.TrimEnd('/') + chemin, "POST")))
        {
            r.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
            r.downloadHandler = new DownloadHandlerBuffer();
            r.SetRequestHeader("Content-Type", "application/json");
            yield return r.SendWebRequest();
            if (r.result == UnityWebRequest.Result.Success) fini?.Invoke(r.downloadHandler.text, null);
            else fini?.Invoke(null, r.error + " " + r.downloadHandler?.text);
        }
    }

    /// GET -> octets (fichier binaire : le modele 3D du canard).
    public IEnumerator LireOctets(string chemin, Action<byte[], string> fini)
    {
        if (!Configure) { fini(null, "adresse du canard non renseignee"); yield break; }
        using (var r = Preparer(UnityWebRequest.Get(adresse.TrimEnd('/') + chemin)))
        {
            r.timeout = 30;                                  // ~4 Mo sur le Wi-Fi
            yield return r.SendWebRequest();
            if (r.result == UnityWebRequest.Result.Success) fini(r.downloadHandler.data, null);
            else fini(null, r.error);
        }
    }

    /// GET image (JPEG) -> texture.
    public IEnumerator Image(string chemin, Action<Texture2D, string> fini)
    {
        if (!Configure) { fini(null, "adresse du canard non renseignee"); yield break; }
        using (var r = Preparer(UnityWebRequestTexture.GetTexture(adresse.TrimEnd('/') + chemin)))
        {
            yield return r.SendWebRequest();
            if (r.result == UnityWebRequest.Result.Success) fini(DownloadHandlerTexture.GetContent(r), null);
            else fini(null, r.responseCode == 403 ? "photos non permises (appli du canard : Reglages -> photos)" : r.error);
        }
    }

    /// Une commande de l'appli (avance, gauche, droite, stop, station, ronde...).
    public void Commande(string nom) =>
        StartCoroutine(Envoyer("/api/commande", "{\"commande\":" + MiniJson.Texte(nom) + "}"));
}
