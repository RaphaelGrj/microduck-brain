package fr.microduck.appli;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

/** Widget d'ecran d'accueil : son etat et sa batterie. Toucher ouvre l'appli sur le canard. */
public class WidgetCanard extends AppWidgetProvider {
    static RemoteViews vue(Context c) {
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget);
        Intent ouvrir = new Intent(c, Accueil.class).putExtra("reprendre", true)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        v.setOnClickPendingIntent(R.id.widget, PendingIntent.getActivity(c, 1, ouvrir,
                PendingIntent.FLAG_UPDATE_CURRENT | Veille.FLAG_IMMUTABLE));
        return v;
    }

    @Override
    public void onUpdate(Context c, AppWidgetManager awm, int[] ids) {
        awm.updateAppWidget(ids, vue(c));
        Veille.planifier(c, true);             // les vraies valeurs arrivent par la verification du canard
    }
}
