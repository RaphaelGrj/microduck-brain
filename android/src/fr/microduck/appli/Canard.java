package fr.microduck.appli;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.webkit.ValueCallback;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.InputStream;

/** L'interface du canard en plein ecran. En demo, elle est servie depuis l'APK (assets/interface) avec un canard imaginaire. */
public class Canard extends Activity {
    static final String DEMO = "http://demo.microduck.local/index.html";
    private static final int CHOIX_FICHIER = 1, CREER_FICHIER = 2;
    private byte[] aEnregistrer;
    private WebView vue;
    private String hote;
    private ValueCallback<Uri[]> fichierRappel;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setStatusBarColor(Accueil.ORANGE_FONCE);
        final String url = getIntent().getStringExtra("url");
        hote = Uri.parse(url).getHost();
        vue = new WebView(this);
        vue.setBackgroundColor(Color.WHITE);
        WebSettings s = vue.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);           // le code d'appairage reste memorise (localStorage)
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        vue.addJavascriptInterface(new Pont(this), "MicroduckAndroid");   // seules les pages du canard sont chargees ici
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
            public boolean shouldOverrideUrlLoading(WebView v, String lien) {
                // le canard (ou la demo) reste dans l'appli ; Printables, Cults... s'ouvrent dans le navigateur
                Uri u = Uri.parse(lien);
                if (hote != null && hote.equals(u.getHost())) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (ActivityNotFoundException e) { /* aucun navigateur */ }
                return true;
            }

            @Override
            @SuppressWarnings("deprecation")
            public void onReceivedError(WebView v, int code, String description, String echec) {
                String retour = url.replace("\"", "");
                v.loadDataWithBaseURL(null, "<!doctype html><meta name=viewport content='width=device-width'>"
                        + "<body style='font-family:sans-serif;text-align:center;padding:48px 24px;color:#333'>"
                        + "<h2 style='color:#f26a1b'>" + Accueil.L("Microduck ne répond pas", "Microduck is not responding") + "</h2>"
                        + "<p>" + Accueil.L("Le canard est-il allumé, et le téléphone sur le même Wi-Fi ?", "Is the duck on, and the phone on the same Wi-Fi?") + "</p>"
                        + "<p><a href=\"" + retour + "\" style='display:inline-block;padding:14px 22px;"
                        + "background:#c24a08;color:#fff;border-radius:14px;text-decoration:none'>" + Accueil.L("Réessayer", "Try again") + "</a></p>",
                        "text/html", "utf-8", null);
            }
        });
        vue.setWebChromeClient(new WebChromeClient() {  // sans lui, confirm() repond toujours « non »
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> rappel, FileChooserParams params) {
                if (fichierRappel != null) fichierRappel.onReceiveValue(null);
                fichierRappel = rappel;                 // « Ma piece (STL) » du design : choisir un fichier du telephone
                try {
                    Intent choix = new Intent(Intent.ACTION_GET_CONTENT);
                    choix.addCategory(Intent.CATEGORY_OPENABLE);
                    choix.setType("*/*");               // les STL n'ont pas de type fiable sur Android
                    startActivityForResult(Intent.createChooser(choix, Accueil.L("Ta pièce (STL)", "Your part (STL)")), CHOIX_FICHIER);
                } catch (ActivityNotFoundException e) {
                    fichierRappel = null;
                    return false;
                }
                return true;
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
        if (chemin.endsWith(".json")) return "application/json";
        if (chemin.endsWith(".webmanifest")) return "application/manifest+json";
        return "application/octet-stream";
    }

    /** Pont.enregistrer : le selecteur de fichiers d'Android (aucune permission de stockage necessaire). */
    void enregistrer(String nom, String type, byte[] octets) {
        aEnregistrer = octets;
        Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                .setType(type == null ? "application/octet-stream" : type).putExtra(Intent.EXTRA_TITLE, nom);
        try {
            startActivityForResult(i, CREER_FICHIER);
        } catch (ActivityNotFoundException e) {
            aEnregistrer = null;
        }
    }

    @Override
    protected void onActivityResult(int code, int resultat, Intent donnees) {
        if (code == CREER_FICHIER) {
            if (resultat == RESULT_OK && donnees != null && donnees.getData() != null && aEnregistrer != null) {
                try {
                    java.io.OutputStream out = getContentResolver().openOutputStream(donnees.getData());
                    out.write(aEnregistrer);
                    out.close();
                    android.widget.Toast.makeText(this, Accueil.L("Enregistré", "Saved"), android.widget.Toast.LENGTH_SHORT).show();
                } catch (Exception e) {
                    android.widget.Toast.makeText(this, Accueil.L("Enregistrement impossible", "Could not save"), android.widget.Toast.LENGTH_SHORT).show();
                }
            }
            aEnregistrer = null;
            return;
        }
        if (code == CHOIX_FICHIER && fichierRappel != null) {
            fichierRappel.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultat, donnees));
            fichierRappel = null;
            return;
        }
        super.onActivityResult(code, resultat, donnees);
    }

    @Override
    protected void onDestroy() {
        if (vue != null) vue.destroy();
        super.onDestroy();
    }
}
