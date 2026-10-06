package fr.microduck.appli;

import android.content.Context;
import android.webkit.JavascriptInterface;

import org.json.JSONArray;

/** window.MicroduckAndroid dans l'interface du canard : retenir le canard (veille, widget) et notifier ses alertes. */
public class Pont {
    private final Context c;
    private final Canard ecran;

    Pont(Canard ecran) { this.c = ecran.getApplicationContext(); this.ecran = ecran; }

    /** Enregistrer un fichier (sauvegarde, photo, fiche d'impression) : Android demande ou le mettre. */
    @JavascriptInterface
    public void enregistrer(final String nom, final String type, final String base64) {
        final byte[] octets;
        try {
            octets = android.util.Base64.decode(base64, android.util.Base64.DEFAULT);
        } catch (IllegalArgumentException e) {
            return;
        }
        ecran.runOnUiThread(new Runnable() {
            public void run() { ecran.enregistrer(nom, type, octets); }
        });
    }

    /** Presence : le prenom a annoncer quand ce telephone rejoint le Wi-Fi de la maison ("" = desactive). */
    @JavascriptInterface
    public void presence(String prenom) {
        String p = prenom == null ? "" : prenom.trim();
        Veille.prefs(c).edit().putString("prenom", p.length() > 40 ? p.substring(0, 40) : p)
                .putBoolean("joignable", true).apply();      // on est deja a la maison : pas d'accueil tout de suite
    }

    @JavascriptInterface
    public String prenom() { return Veille.prefs(c).getString("prenom", ""); }

    @JavascriptInterface
    public void retenir(String url, String code) {
        if (url == null || code == null || !url.startsWith("http")) return;
        android.content.SharedPreferences.Editor e = Veille.prefs(c).edit().putString("url", url).putString("code", code);
        if (!Veille.prefs(c).contains("depuis")) {
            e.putLong("depuis", Double.doubleToLongBits(System.currentTimeMillis() / 1000.0));   // pas l'historique
        }
        e.apply();
        Veille.planifier(c, true);
    }

    @JavascriptInterface
    public void alertes(String json) {
        try {
            Veille.alertes(c, new JSONArray(json));
        } catch (Exception e) { /* alerte illisible : ignoree */ }
    }
}
