// Microduck - lecteur JSON minimal (objets -> Dictionary<string, object>, tableaux -> List<object>, nombres -> double,
// chaines, booleens, null). JsonUtility d'Unity ne sait pas lire des objets libres comme ceux de l'API du canard.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

public static class MiniJson
{
    public static object Lire(string json)
    {
        if (string.IsNullOrEmpty(json)) return null;
        int i = 0;
        try { return Valeur(json, ref i); }
        catch (Exception) { return null; }
    }

    static void Blancs(string s, ref int i) { while (i < s.Length && char.IsWhiteSpace(s[i])) i++; }

    static object Valeur(string s, ref int i)
    {
        Blancs(s, ref i);
        char c = s[i];
        if (c == '{') return Objet(s, ref i);
        if (c == '[') return Tableau(s, ref i);
        if (c == '"') return Chaine(s, ref i);
        if (s.Substring(i).StartsWith("true")) { i += 4; return true; }
        if (s.Substring(i).StartsWith("false")) { i += 5; return false; }
        if (s.Substring(i).StartsWith("null")) { i += 4; return null; }
        int debut = i;
        while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
        return double.Parse(s.Substring(debut, i - debut), CultureInfo.InvariantCulture);
    }

    static Dictionary<string, object> Objet(string s, ref int i)
    {
        var d = new Dictionary<string, object>();
        i++;
        Blancs(s, ref i);
        if (s[i] == '}') { i++; return d; }
        while (true)
        {
            Blancs(s, ref i);
            string cle = Chaine(s, ref i);
            Blancs(s, ref i);
            i++;                                            // ':'
            d[cle] = Valeur(s, ref i);
            Blancs(s, ref i);
            if (s[i] == ',') { i++; continue; }
            i++;                                            // '}'
            return d;
        }
    }

    static List<object> Tableau(string s, ref int i)
    {
        var l = new List<object>();
        i++;
        Blancs(s, ref i);
        if (s[i] == ']') { i++; return l; }
        while (true)
        {
            l.Add(Valeur(s, ref i));
            Blancs(s, ref i);
            if (s[i] == ',') { i++; continue; }
            i++;                                            // ']'
            return l;
        }
    }

    static string Chaine(string s, ref int i)
    {
        var sb = new StringBuilder();
        i++;                                                // '"'
        while (s[i] != '"')
        {
            if (s[i] == '\\')
            {
                i++;
                char e = s[i];
                if (e == 'u') { sb.Append((char)Convert.ToInt32(s.Substring(i + 1, 4), 16)); i += 4; }
                else sb.Append(e == 'n' ? '\n' : e == 't' ? '\t' : e == 'r' ? '\r' : e == 'b' ? '\b' : e == 'f' ? '\f' : e);
            }
            else sb.Append(s[i]);
            i++;
        }
        i++;
        return sb.ToString();
    }

    // -- acces pratiques ---------------------------------------------------------------------------------------------
    public static object Champ(object o, string cle) =>
        o is Dictionary<string, object> d && d.TryGetValue(cle, out var v) ? v : null;

    public static float Nombre(object o, float defaut = 0f) => o is double x ? (float)x : defaut;

    public static List<object> Liste(object o) => o as List<object> ?? new List<object>();

    public static string Texte(string s)
    {
        var sb = new StringBuilder("\"");
        foreach (char c in s ?? "")
        {
            if (c == '"' || c == '\\') sb.Append('\\').Append(c);
            else if (c < ' ') sb.Append("\\u").Append(((int)c).ToString("x4"));
            else sb.Append(c);
        }
        return sb.Append('"').ToString();
    }

    public static string N(float v) => v.ToString("0.####", CultureInfo.InvariantCulture);
}
