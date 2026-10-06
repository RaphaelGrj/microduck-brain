"use strict";
const M = window.MicroduckOrdinateur;
const $ = (s) => document.querySelector(s);
const EN = !(navigator.language || "fr").toLowerCase().startsWith("fr");
const T = EN ? { "Trouve ton canard sur le Wi-Fi de la maison.": "Find your duck on the home Wi-Fi.", "Chercher mon canard": "Find my duck",
  "ou son adresse": "or his address", "Se connecter": "Connect", "Essayer en démo (sans le canard)": "Try the demo (without the duck)",
  "Rien ne sort de la maison : l'appli ne parle qu'au canard, sur le réseau local.": "Nothing leaves the house: the app only talks to the duck, on the local network.",
  "Recherche sur le Wi-Fi…": "Searching the Wi-Fi…", "Aucun canard trouvé. Est-il allumé, et sur le même Wi-Fi ?": "No duck found. Is he on, and on the same Wi-Fi?",
  "Oublier": "Forget", "Connexion…": "Connecting…" } : {};
const t = (s) => T[s] || s;
document.querySelectorAll("p, button, h1 + p").forEach((e) => { if (e.childElementCount === 0 && T[e.textContent.trim()]) e.textContent = T[e.textContent.trim()]; });

function message(m) { $("#message").textContent = m || ""; }
async function ouvrir(adresse) {
  message(t("Connexion…"));
  const r = await M.ouvrir(adresse);
  if (!r.ok) message(EN ? r.message.replace("Adresse du réseau local attendue (ex. 192.168.1.42)", "Local network address expected (e.g. 192.168.1.42)")
    .replace("Microduck ne répond pas à cette adresse (même Wi-Fi ?)", "Microduck is not answering at this address (same Wi-Fi?)") : r.message);
}
async function dessiner(liste) {
  liste = liste || await M.canards();
  $("#canards").replaceChildren(...liste.map((c) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    const n = document.createElement("b"); n.textContent = c.nom;
    const a = document.createElement("small"); a.textContent = c.adresse;
    b.append(n, a); b.onclick = () => ouvrir(c.adresse);
    const x = document.createElement("button"); x.textContent = "✕"; x.title = t("Oublier"); x.setAttribute("aria-label", t("Oublier") + " " + c.nom);
    x.onclick = async () => dessiner(await M.oublier(c.adresse));
    li.append(b, x); return li;
  }));
}
$("#chercher").onclick = async () => {
  const b = $("#chercher"); b.disabled = true; message(t("Recherche sur le Wi-Fi…"));
  try {
    const trouves = await M.chercher();
    if (!trouves.length) { message(t("Aucun canard trouvé. Est-il allumé, et sur le même Wi-Fi ?")); return; }
    if (trouves.length === 1) { await ouvrir(trouves[0].adresse); return; }
    message(""); dessiner(trouves);
  } finally { b.disabled = false; }
};
$("#form").onsubmit = (e) => { e.preventDefault(); if ($("#adresse").value.trim()) ouvrir($("#adresse").value.trim()); };
$("#demo").onclick = () => M.demo();
const erreur = new URLSearchParams(location.search).get("erreur");
if (erreur) message(EN ? erreur.replace("Microduck ne répond pas", "Microduck is not responding") : erreur);
dessiner();
M.version().then((v) => {
  if (!v.nouvelle) return;
  const p = $("#maj"); p.hidden = false;
  const a = document.createElement("a"); a.textContent = (EN ? "Version " : "Version ") + v.nouvelle + (EN ? " available" : " disponible");
  a.onclick = () => M.lien(v.lien);
  p.replaceChildren(a);
});
