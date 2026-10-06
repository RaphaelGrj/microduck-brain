package fr.microduck.appli;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.InputStream;

/** L'interface du canard en plein ecran. En demo, elle est servie depuis l'APK (assets/interface) avec un canard imaginaire. */
public class Canard extends Activity {
    static final String DEMO = "http://demo.microduck.local/index.html";
    private WebView vue;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setStatusBarColor(Accueil.ORANGE_FONCE);
        final String url = getIntent().getStringExtra("url");
        vue = new WebView(this);
        vue.setBackgroundColor(Color.WHITE);
        WebSettings s = vue.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);           // le code d'appairage reste memorise (localStorage)
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        vue.setWebViewClient(new WebViewClient() {     // (un WebViewClient garde tous les liens dans l'appli)
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if (!"demo.microduck.local".equals(u.getHost())) return null;
                String chemin = u.getPath() == null || u.getPath().equals("/") ? "/index.html" : u.getPath();
                if (chemin.contains("..")) return null;
                try {
                    InputStream in = getAssets().open("interface" + chemin);
                    return new WebResourceResponse(type(chemin), "utf-8", in);
                } catch (Exception e) {
                    return new WebResourceResponse("text/plain", "utf-8", 404, "Absent", null, null);
                }
            }

            @Override
            @SuppressWarnings("deprecation")
            public void onReceivedError(WebView v, int code, String description, String echec) {
                String retour = url.replace("\"", "");
                v.loadDataWithBaseURL(null, "<!doctype html><meta name=viewport content='width=device-width'>"
                        + "<body style='font-family:sans-serif;text-align:center;padding:48px 24px;color:#333'>"
                        + "<h2 style='color:#f26a1b'>Microduck ne répond pas</h2>"
                        + "<p>Le canard est-il allumé, et le téléphone sur le même Wi-Fi ?</p>"
                        + "<p><a href=\"" + retour + "\" style='display:inline-block;padding:14px 22px;"
                        + "background:#c24a08;color:#fff;border-radius:14px;text-decoration:none'>Réessayer</a></p>",
                        "text/html", "utf-8", null);
            }
        });
        setContentView(vue);
        vue.loadUrl(url);
    }

    static String type(String chemin) {
        if (chemin.endsWith(".html")) return "text/html";
        if (chemin.endsWith(".js")) return "text/javascript";
        if (chemin.endsWith(".css")) return "text/css";
        if (chemin.endsWith(".webp")) return "image/webp";
        if (chemin.endsWith(".png")) return "image/png";
        if (chemin.endsWith(".svg")) return "image/svg+xml";
        if (chemin.endsWith(".webmanifest")) return "application/manifest+json";
        return "application/octet-stream";
    }

    @Override
    protected void onDestroy() {
        if (vue != null) vue.destroy();
        super.onDestroy();
    }
}
