package fr.microduck.appli;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.URL;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/** Premier ecran : trouver le canard sur le Wi-Fi (ou taper son adresse), ou essayer en demo. */
public class Accueil extends Activity {
    static final int ORANGE = 0xFFF26A1B;
    static final int ORANGE_FONCE = 0xFFC24A08;
    static final int PORT = 8090;

    private EditText adresse;
    private TextView message;
    private Button chercher;
    private SharedPreferences prefs;
    private Button majBouton;
    private LinearLayout mesCanards;

    // derniere version publiee de l'APK (android/version.json, ecrit par construire.sh) et l'APK lui-meme
    static final String DEPOT = "https://raw.githubusercontent.com/RaphaelGrj/microduck-brain/ccr-4c5851c0-mdd2p8/android/";

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = getSharedPreferences("microduck", MODE_PRIVATE);
        getWindow().setStatusBarColor(ORANGE_FONCE);
        if (android.os.Build.VERSION.SDK_INT >= 33) {      // Android 13+ : les notifications se demandent
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
        }
        Veille.planifier(this, false);
        String connu = prefs.getString("url", null);
        if (getIntent().getBooleanExtra("reprendre", false) && connu != null) {
            startActivity(new Intent(this, Canard.class).putExtra("url", connu + "/"));   // notification ou widget
        }

        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setGravity(Gravity.CENTER_HORIZONTAL);
        col.setPadding(dp(24), dp(40), dp(24), dp(24));
        col.setBackgroundColor(Color.WHITE);

        ImageView icone = new ImageView(this);
        icone.setImageResource(R.drawable.icone);
        col.addView(icone, new LinearLayout.LayoutParams(dp(112), dp(112)));

        TextView titre = new TextView(this);
        titre.setText("Microduck");
        titre.setTextSize(30);
        titre.setTypeface(Typeface.DEFAULT_BOLD);
        titre.setTextColor(ORANGE);
        titre.setGravity(Gravity.CENTER);
        titre.setPadding(0, dp(12), 0, dp(4));
        col.addView(titre);

        TextView intro = texte("Le téléphone doit être sur le même Wi-Fi que le canard.", 15, 0xFF555555);
        intro.setGravity(Gravity.CENTER);
        col.addView(intro);

        mesCanards = new LinearLayout(this);             // les canards deja connus (plusieurs canards : un bouton chacun)
        mesCanards.setOrientation(LinearLayout.VERTICAL);
        col.addView(mesCanards, largeur(dp(8)));
        majBouton = bouton("", true);                       // « Mise a jour x.y disponible » (cache tant qu'il n'y en a pas)
        majBouton.setVisibility(View.GONE);
        col.addView(majBouton, largeur(dp(16)));
        verifierMiseAJour();

        chercher = bouton("Chercher le canard sur le Wi-Fi", true);
        chercher.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { chercher(); }
        });
        col.addView(chercher, largeur(dp(28)));

        TextView ou = texte("ou son adresse", 13, 0xFF888888);
        ou.setGravity(Gravity.CENTER);
        ou.setPadding(0, dp(18), 0, dp(6));
        col.addView(ou);

        adresse = new EditText(this);
        adresse.setHint("192.168.1.42");
        adresse.setText(prefs.getString("adresse", ""));
        adresse.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        adresse.setImeOptions(EditorInfo.IME_ACTION_GO);
        adresse.setSingleLine(true);
        adresse.setGravity(Gravity.CENTER);
        adresse.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            public boolean onEditorAction(TextView v, int action, android.view.KeyEvent e) { ouvrir(); return true; }
        });
        col.addView(adresse, largeur(0));

        Button connecter = bouton("Se connecter", false);
        connecter.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { ouvrir(); }
        });
        col.addView(connecter, largeur(dp(10)));

        message = texte("", 14, ORANGE_FONCE);
        message.setGravity(Gravity.CENTER);
        message.setPadding(0, dp(14), 0, 0);
        col.addView(message);

        Button demo = bouton("Essayer en démo (sans le canard)", false);
        demo.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                startActivity(new Intent(Accueil.this, Canard.class).putExtra("url", Canard.DEMO));
            }
        });
        col.addView(demo, largeur(dp(36)));

        TextView note = texte("Rien ne sort de la maison : l'appli ne parle qu'au canard, sur le réseau local.",
                12, 0xFF888888);
        note.setGravity(Gravity.CENTER);
        note.setPadding(0, dp(20), 0, 0);
        col.addView(note);

        ScrollView defile = new ScrollView(this);
        defile.setBackgroundColor(Color.WHITE);
        defile.addView(col);
        setContentView(defile);
    }

    /** Une version plus recente sur GitHub ? Le bouton ouvre son telechargement dans le navigateur (installation par Android). */
    private void verifierMiseAJour() {
        new Thread(new Runnable() {
            public void run() {
                try {
                    HttpURLConnection c = (HttpURLConnection) new URL(DEPOT + "version.json").openConnection();
                    c.setConnectTimeout(5000);
                    c.setReadTimeout(5000);
                    c.setUseCaches(false);
                    if (c.getResponseCode() != 200) return;
                    InputStream in = c.getInputStream();
                    ByteArrayOutputStream out = new ByteArrayOutputStream();
                    byte[] t = new byte[1024];
                    int n;
                    while ((n = in.read(t)) > 0 && out.size() < 8192) out.write(t, 0, n);
                    final org.json.JSONObject v = new org.json.JSONObject(out.toString("UTF-8"));
                    int moi = getPackageManager().getPackageInfo(getPackageName(), 0).versionCode;
                    if (v.getInt("versionCode") <= moi) return;
                    final String apk = v.optString("apk", DEPOT + "microduck.apk");
                    if (!apk.startsWith("https://")) return;
                    runOnUiThread(new Runnable() {
                        public void run() {
                            majBouton.setText("Mise à jour " + v.optString("versionName") + " disponible");
                            majBouton.setVisibility(View.VISIBLE);
                            majBouton.setOnClickListener(new View.OnClickListener() {
                                public void onClick(View b) {
                                    try {
                                        startActivity(new Intent(Intent.ACTION_VIEW, android.net.Uri.parse(apk)));
                                    } catch (Exception e) { message.setText("Ouvre " + apk); }
                                }
                            });
                        }
                    });
                } catch (Exception e) { /* pas d'Internet : on verra au prochain lancement */ }
            }
        }).start();
    }

    @Override
    protected void onResume() {
        super.onResume();
        dessinerCanards();
    }

    /** Les canards connus : [{"adresse", "nom"}] dans les preferences ; le dernier ouvert en premier. */
    private org.json.JSONArray canards() {
        try { return new org.json.JSONArray(prefs.getString("canards", "[]")); } catch (Exception e) { return new org.json.JSONArray(); }
    }

    private void retenirCanard(String adresse, String nom) {
        org.json.JSONArray avant = canards(), apres = new org.json.JSONArray();
        String ancienNom = null;
        for (int i = 0; i < avant.length(); i++) {
            org.json.JSONObject c = avant.optJSONObject(i);
            if (c == null) continue;
            if (adresse.equals(c.optString("adresse"))) ancienNom = c.optString("nom", null);
            else apres.put(c);
        }
        try {
            org.json.JSONObject c = new org.json.JSONObject().put("adresse", adresse)
                    .put("nom", nom != null ? nom : ancienNom != null ? ancienNom : adresse);
            org.json.JSONArray tout = new org.json.JSONArray().put(c);
            for (int i = 0; i < apres.length() && i < 9; i++) tout.put(apres.get(i));
            prefs.edit().putString("canards", tout.toString()).apply();
        } catch (Exception e) { /* rien */ }
    }

    private void dessinerCanards() {
        if (mesCanards == null) return;
        mesCanards.removeAllViews();
        final org.json.JSONArray liste = canards();
        for (int i = 0; i < liste.length(); i++) {
            final org.json.JSONObject c = liste.optJSONObject(i);
            if (c == null) continue;
            LinearLayout ligne = new LinearLayout(this);
            ligne.setOrientation(LinearLayout.HORIZONTAL);
            Button b = bouton("🦆 " + c.optString("nom") + "  ·  " + c.optString("adresse"), i == 0);
            b.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) { adresse.setText(c.optString("adresse")); ouvrir(); }
            });
            Button x = bouton("✕", false);
            x.setContentDescription("Oublier ce canard");
            x.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) {
                    org.json.JSONArray garde = new org.json.JSONArray();
                    org.json.JSONArray tout = canards();
                    for (int k = 0; k < tout.length(); k++)
                        if (!c.optString("adresse").equals(tout.optJSONObject(k).optString("adresse"))) garde.put(tout.optJSONObject(k));
                    prefs.edit().putString("canards", garde.toString()).apply();
                    dessinerCanards();
                }
            });
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
            ligne.addView(b, p);
            LinearLayout.LayoutParams px = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            px.leftMargin = dp(6);
            ligne.addView(x, px);
            mesCanards.addView(ligne, largeur(dp(8)));
        }
    }

    /** Ouvre l'interface du canard a l'adresse tapee (ip, ip:port ou http://...). */
    private void ouvrir() {
        String a = adresse.getText().toString().trim();
        if (a.isEmpty()) { message.setText("Tape l'adresse du canard, ou cherche-le."); return; }
        if (!a.startsWith("http://") && !a.startsWith("https://")) a = "http://" + a;
        try {
            URL u = new URL(a);
            if (u.getHost().isEmpty()) throw new Exception();
            String url = u.getProtocol() + "://" + u.getHost() + ":" + (u.getPort() > 0 ? u.getPort() : PORT) + "/";
            prefs.edit().putString("adresse", adresse.getText().toString().trim()).apply();
            retenirCanard(u.getHost() + (u.getPort() > 0 && u.getPort() != PORT ? ":" + u.getPort() : ""), null);
            message.setText("");
            startActivity(new Intent(this, Canard.class).putExtra("url", url));
        } catch (Exception e) {
            message.setText("Adresse invalide.");
        }
    }

    /** Interroge /api/sante sur tout le sous-reseau du telephone (/24), port 8090 : le premier qui repond « microduck ». */
    private void chercher() {
        final List<String> bases = sousReseaux();
        if (bases.isEmpty()) { message.setText("Pas de Wi-Fi : connecte le téléphone au réseau de la maison."); return; }
        chercher.setEnabled(false);
        message.setText("Recherche…");
        new Thread(new Runnable() {
            public void run() {
                final java.util.concurrent.ConcurrentHashMap<String, String> trouves = new java.util.concurrent.ConcurrentHashMap<String, String>();
                ExecutorService pool = Executors.newFixedThreadPool(48);
                for (String base : bases) {
                    for (int i = 1; i < 255; i++) {
                        final String ip = base + i;
                        pool.execute(new Runnable() {
                            public void run() {
                                String nom = nomDuCanard(ip);
                                if (nom != null) trouves.put(ip, nom);
                            }
                        });
                    }
                }
                pool.shutdown();
                try { pool.awaitTermination(30, TimeUnit.SECONDS); } catch (InterruptedException e) { /* fin */ }
                runOnUiThread(new Runnable() {
                    public void run() {
                        chercher.setEnabled(true);
                        if (trouves.isEmpty()) {
                            message.setText("Aucun canard trouvé. Est-il allumé, et sur ce Wi-Fi ?");
                            return;
                        }
                        for (java.util.Map.Entry<String, String> t : trouves.entrySet()) retenirCanard(t.getKey(), t.getValue());
                        if (trouves.size() == 1) {
                            adresse.setText(trouves.keySet().iterator().next());
                            ouvrir();
                        } else {
                            message.setText(trouves.size() + " canards trouvés : choisis.");
                            dessinerCanards();
                        }
                    }
                });
            }
        }).start();
    }

    /** Le nom du canard qui repond a cette adresse (/api/sante), ou null si ce n'est pas un Microduck. */
    static String nomDuCanard(String ip) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL("http://" + ip + ":" + PORT + "/api/sante").openConnection();
            c.setConnectTimeout(700);
            c.setReadTimeout(1000);
            if (c.getResponseCode() != 200) return null;
            InputStream in = c.getInputStream();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] tampon = new byte[512];
            int n;
            while ((n = in.read(tampon)) > 0 && out.size() < 4096) out.write(tampon, 0, n);
            org.json.JSONObject s = new org.json.JSONObject(out.toString("UTF-8"));
            if (!"microduck".equals(s.optString("appli"))) return null;
            return s.optString("nom", "Microduck");
        } catch (Exception e) {
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    /** Prefixes « a.b.c. » des adresses IPv4 privees du telephone (Wi-Fi en general). */
    static List<String> sousReseaux() {
        List<String> r = new ArrayList<String>();
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (!(a instanceof Inet4Address) || !a.isSiteLocalAddress()) continue;
                    String ip = a.getHostAddress();
                    String base = ip.substring(0, ip.lastIndexOf('.') + 1);
                    if (!r.contains(base)) r.add(base);
                }
            }
        } catch (Exception e) { /* pas de reseau */ }
        return r;
    }

    private TextView texte(String t, int taille, int couleur) {
        TextView v = new TextView(this);
        v.setText(t);
        v.setTextSize(taille);
        v.setTextColor(couleur);
        return v;
    }

    private Button bouton(String t, boolean principal) {
        Button b = new Button(this);
        b.setText(t);
        b.setAllCaps(false);
        b.setTextSize(16);
        GradientDrawable fond = new GradientDrawable();
        fond.setCornerRadius(dp(14));
        if (principal) {
            fond.setColor(ORANGE_FONCE);
            b.setTextColor(Color.WHITE);
        } else {
            fond.setColor(Color.WHITE);
            fond.setStroke(dp(2), ORANGE);
            b.setTextColor(ORANGE_FONCE);
        }
        b.setBackground(fond);
        b.setPadding(dp(16), dp(14), dp(16), dp(14));
        return b;
    }

    private LinearLayout.LayoutParams largeur(int haut) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        p.topMargin = haut;
        return p;
    }

    private int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }
}
