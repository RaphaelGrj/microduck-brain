package fr.microduck.appli;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Verification en arriere-plan (toutes les 15 min environ, le minimum d'Android) : les alertes du canard deviennent des
 * notifications, et le widget est mis a jour. Ne parle qu'au canard, sur le reseau local, avec le code d'appairage.
 */
public class Veille extends JobService {
    static final int JOB_PERIODIQUE = 1, JOB_IMMEDIAT = 2;
    static final String CANAL = "alertes";
    static final int FLAG_IMMUTABLE = 0x04000000;     // PendingIntent.FLAG_IMMUTABLE (API 23+, exige des Android 12)

    static SharedPreferences prefs(Context c) { return c.getSharedPreferences("microduck", Context.MODE_PRIVATE); }

    /** Programme la verification periodique (et une tout de suite si `maintenant`). Rien tant que le canard est inconnu. */
    static void planifier(Context c, boolean maintenant) {
        try {
            planifierOuEchouer(c, maintenant);
        } catch (Throwable e) {
            // jamais un plantage de l'appli pour la veille (permission refusee, quota de taches...) : sans elle, l'appli
            // marche, il n'y a juste pas de notifications en arriere-plan
        }
    }

    private static void planifierOuEchouer(Context c, boolean maintenant) {
        if (prefs(c).getString("url", null) == null) return;
        JobScheduler js = (JobScheduler) c.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        ComponentName cn = new ComponentName(c, Veille.class);
        boolean deja = false;                              // (getPendingJob n'existe qu'a partir d'Android 7)
        for (JobInfo j : js.getAllPendingJobs()) deja |= j.getId() == JOB_PERIODIQUE;
        if (!deja) {
            js.schedule(new JobInfo.Builder(JOB_PERIODIQUE, cn).setPeriodic(15 * 60 * 1000L)
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPersisted(true).build());
        }
        if (maintenant) {
            js.schedule(new JobInfo.Builder(JOB_IMMEDIAT, cn).setOverrideDeadline(0)
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).build());
        }
    }

    @Override
    public boolean onStartJob(final JobParameters p) {
        new Thread(new Runnable() {
            public void run() {
                // Tourne aussi appli FERMEE : rien ici ne doit jamais la faire planter (Throwable, pas seulement Exception)
                try { verifier(Veille.this); } catch (Throwable e) { /* canard injoignable, ou autre : la prochaine fois */ }
                finally {
                    try { jobFinished(p, false); } catch (Throwable e) { /* tache deja annulee par Android */ }
                }
            }
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters p) { return true; }

    static void verifier(Context c) throws Exception {
        SharedPreferences pr = prefs(c);
        String url = pr.getString("url", null), code = pr.getString("code", null);
        if (url == null || code == null) return;
        JSONObject etat;
        try {
            etat = new JSONObject(lire(url + "/api/etat", code));
        } catch (Exception e) {
            pr.edit().putBoolean("joignable", false).apply();   // hors de la maison (ou canard eteint)
            throw e;
        }
        // presence par ce telephone : il etait injoignable, le voila sur le Wi-Fi de la maison -> « je suis la »
        String prenom = pr.getString("prenom", "");
        if (!pr.getBoolean("joignable", false) && prenom.length() > 0) {
            try {
                ecrire(url + "/api/presence", code, new JSONObject().put("nom", prenom).toString());
            } catch (Exception e) { /* la prochaine fois */ }
        }
        pr.edit().putBoolean("joignable", true).apply();
        majWidget(c, etat);
        sauvegarder(c, url, code);
        double depuis = Double.longBitsToDouble(pr.getLong("depuis", Double.doubleToLongBits(System.currentTimeMillis() / 1000.0 - 3600)));
        alertes(c, new JSONObject(lire(url + "/api/alertes?depuis=" + depuis, code)).getJSONArray("alertes"));
    }

    static final long SEMAINE_MS = 7L * 24 * 3600 * 1000;
    static final int SAUVEGARDES_GARDEES = 4;

    static java.io.File dossierSauvegardes(Context c) {
        java.io.File d = c.getExternalFilesDir("sauvegardes");             // Android/data/fr.microduck.appli/files/...
        return d != null ? d : new java.io.File(c.getFilesDir(), "sauvegardes");
    }

    /** Une fois par semaine, sa sauvegarde (memoire, lieux, design, reglages...) dans le telephone : les 4 dernieres. */
    static void sauvegarder(Context c, String url, String code) {
        SharedPreferences pr = prefs(c);
        long maintenant = System.currentTimeMillis();
        if (!pr.getBoolean("sauvegarde_auto", true) || maintenant - pr.getLong("derniere_sauvegarde", 0L) < SEMAINE_MS) return;
        try {
            String json = lire(url + "/api/sauvegarde", code);            // (code enfant : refuse, rien n'est fait)
            java.io.File d = dossierSauvegardes(c);
            d.mkdirs();
            String nom = "microduck-sauvegarde-" + new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.FRANCE)
                    .format(new java.util.Date(maintenant)) + ".json";
            java.io.FileOutputStream out = new java.io.FileOutputStream(new java.io.File(d, nom));
            out.write(json.getBytes("UTF-8"));
            out.close();
            java.io.File[] f = d.listFiles();
            if (f != null && f.length > SAUVEGARDES_GARDEES) {
                java.util.Arrays.sort(f);
                for (int i = 0; i < f.length - SAUVEGARDES_GARDEES; i++) f[i].delete();
            }
            pr.edit().putLong("derniere_sauvegarde", maintenant).apply();
        } catch (Exception e) { /* la semaine prochaine (ou au prochain passage) */ }
    }

    /** Une notification par alerte plus recente que la derniere vue (curseur partage avec l'appli ouverte). */
    static synchronized void alertes(Context c, JSONArray liste) throws Exception {
        SharedPreferences pr = prefs(c);
        double depuis = Double.longBitsToDouble(pr.getLong("depuis", 0L));
        double max = depuis;
        for (int i = 0; i < liste.length(); i++) {
            JSONObject a = liste.getJSONObject(i);
            double t = a.getDouble("t");
            if (t <= depuis) continue;
            notifier(c, a.optString("titre", "Microduck"), a.optString("texte", ""), a.optBoolean("importante"), (int) (t * 10 % 100000));
            max = Math.max(max, t);
        }
        if (max > depuis) pr.edit().putLong("depuis", Double.doubleToLongBits(max)).apply();
    }

    @SuppressWarnings("deprecation")
    static void notifier(Context c, String titre, String texte, boolean importante, int id) {
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= 26) {
            try {                                      // NotificationChannel (Android 8+), par reflexion : compile en API 23
                Class<?> canal = Class.forName("android.app.NotificationChannel");
                Object ch = canal.getConstructor(String.class, CharSequence.class, int.class)
                        .newInstance(CANAL, Accueil.L("Alertes du canard", "Duck alerts"), 4 /* IMPORTANCE_HIGH */);
                NotificationManager.class.getMethod("createNotificationChannel", canal).invoke(nm, ch);
                b = Notification.Builder.class.getConstructor(Context.class, String.class).newInstance(c, CANAL);
            } catch (Exception e) {
                b = new Notification.Builder(c);
            }
        } else {
            b = new Notification.Builder(c).setPriority(importante ? Notification.PRIORITY_HIGH : Notification.PRIORITY_DEFAULT);
        }
        Intent ouvrir = new Intent(c, Accueil.class).putExtra("reprendre", true)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        b.setSmallIcon(R.drawable.notif).setColor(Accueil.ORANGE).setContentTitle(titre).setContentText(texte)
                .setStyle(new Notification.BigTextStyle().bigText(texte)).setAutoCancel(true)
                .setContentIntent(PendingIntent.getActivity(c, 0, ouvrir, PendingIntent.FLAG_UPDATE_CURRENT | FLAG_IMMUTABLE));
        if (importante) b.setDefaults(Notification.DEFAULT_ALL);
        try {
            nm.notify(id, b.build());
        } catch (SecurityException e) { /* notifications refusees par l'utilisateur */ }
    }

    static void majWidget(Context c, JSONObject e) {
        AppWidgetManager awm = AppWidgetManager.getInstance(c);
        int[] ids = awm.getAppWidgetIds(new ComponentName(c, WidgetCanard.class));
        if (ids.length == 0) return;
        String etat = e.optBoolean("tombe") ? Accueil.L("Il est tombé", "He fell") : e.optBoolean("porte") ? Accueil.L("Dans les bras", "In someone's arms") : Etats.libelle(e.optString("etat"));
        JSONObject batt = e.optJSONObject("batterie");
        String detail = (batt != null && !batt.isNull("pourcent") ? Accueil.L("Batterie ", "Battery ") + Math.round(batt.optDouble("pourcent")) + " %" : Accueil.L("Batterie —", "Battery —"))
                + " · " + new java.text.SimpleDateFormat("HH:mm", java.util.Locale.FRANCE).format(new java.util.Date());
        RemoteViews v = WidgetCanard.vue(c);
        v.setTextViewText(R.id.w_etat, etat);
        v.setTextViewText(R.id.w_detail, detail);
        awm.updateAppWidget(ids, v);
    }

    static void ecrire(String adresse, String code, String json) throws Exception {
        HttpURLConnection h = (HttpURLConnection) new URL(adresse).openConnection();
        h.setConnectTimeout(4000);
        h.setReadTimeout(6000);
        h.setRequestMethod("POST");
        h.setDoOutput(true);
        h.setRequestProperty("X-Microduck-Code", code);
        h.setRequestProperty("Content-Type", "application/json");
        try {
            h.getOutputStream().write(json.getBytes("UTF-8"));
            if (h.getResponseCode() != 200) throw new Exception("HTTP " + h.getResponseCode());
        } finally {
            h.disconnect();
        }
    }

    static String lire(String adresse, String code) throws Exception {
        HttpURLConnection h = (HttpURLConnection) new URL(adresse).openConnection();
        h.setConnectTimeout(4000);
        h.setReadTimeout(6000);
        h.setRequestProperty("X-Microduck-Code", code);
        try {
            if (h.getResponseCode() != 200) throw new Exception("HTTP " + h.getResponseCode());
            InputStream in = h.getInputStream();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] t = new byte[4096];
            int n;
            while ((n = in.read(t)) > 0) out.write(t, 0, n);
            return out.toString("UTF-8");
        } finally {
            h.disconnect();
        }
    }
}
