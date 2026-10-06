package fr.microduck.appli;

import android.content.Context;
import android.webkit.JavascriptInterface;

import org.json.JSONArray;

/** window.MicroduckAndroid dans l'interface du canard : retenir le canard (veille, widget) et notifier ses alertes. */
public class Pont {
    private final Context c;

    Pont(Context c) { this.c = c.getApplicationContext(); }

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
