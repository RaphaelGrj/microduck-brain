// Microduck - un mode de l'appli du casque (Scan, Atelier, Verite, Dessin, Danse, Canard). Le menu
// (MenuMicroduck) n'en active qu'un a la fois ; chaque mode lit les manettes et donne sa consigne a afficher.
using UnityEngine;

public abstract class ModeMicroduck : MonoBehaviour
{
    public abstract string Nom { get; }

    /// Ce qui s'affiche devant les yeux (en plus du nom du mode).
    public virtual string Consigne => "";

    /// Appele a l'activation (enabled = true) et a la desactivation.
    protected virtual void OnEnable() { }
    protected virtual void OnDisable() { }

    /// La pointe orange au bout de la manette droite.
    protected Transform Pointe => MenuMicroduck.Ici != null ? MenuMicroduck.Ici.pointe : null;

    protected string message = "";
}
