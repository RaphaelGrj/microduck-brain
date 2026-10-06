// Application Microduck pour ordinateur (Windows, Linux, macOS) : la meme coquille que l'APK Android. Elle trouve le
// canard sur le reseau local et ouvre l'interface qu'il sert lui-meme (appli.py) ; le mode demo sert une copie de
// l'interface embarquee. Aucune logique ici : une mise a jour du cerveau met l'appli a jour.
"use strict";

const { app, BrowserWindow, Menu, Notification, dialog, ipcMain, net, protocol, shell } = require("electron");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const PORT = 8090;
const DEPOT = "https://github.com/RaphaelGrj/microduck-brain/releases";
const INTERFACE = app.isPackaged ? path.join(process.resourcesPath, "interface") : path.join(__dirname, "..", "interface");
const ACCUEIL = path.join(__dirname, "accueil", "accueil.html");

// mode demo : microduck://demo/... = l'interface embarquee (demo.js s'active avec ?demo)
protocol.registerSchemesAsPrivileged([{ scheme: "microduck", privileges: { standard: true, secure: true, supportFetchAPI: true } }]);

let fenetre = null;
const fichierCanards = () => path.join(app.getPath("userData"), "canards.json");

function lireCanards() {
  try { const l = JSON.parse(fs.readFileSync(fichierCanards(), "utf8")); return Array.isArray(l) ? l : []; } catch (e) { return []; }
}
function retenirCanard(adresse, nom) {
  const l = lireCanards().filter((c) => c.adresse !== adresse);
  l.unshift({ adresse, nom: nom || "Microduck" });
  fs.mkdirSync(app.getPath("userData"), { recursive: true });
  fs.writeFileSync(fichierCanards(), JSON.stringify(l.slice(0, 10)));
}

// adresses privees seulement : l'appli ne parle qu'aux canards du reseau local
function adressePrivee(hote) {
  const m = /^(\d+)\.(\d+)\.(\d+)\.(\d+)$/.exec(hote || "");
  if (!m) return /\.local$/i.test(hote || "") || hote === "localhost";
  const [a, b] = [+m[1], +m[2]];
  return a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 169 && b === 254);
}
function urlCanard(u) {
  try { const x = new URL(u); return x.protocol === "http:" && adressePrivee(x.hostname); } catch (e) { return false; }
}

// -- recherche du canard : /api/sante sur le sous-reseau (/24) de chaque carte reseau -------------------------------
function sante(ip, delai = 900) {
  return new Promise((ok) => {
    const req = http.get({ host: ip, port: PORT, path: "/api/sante", timeout: delai }, (r) => {
      let d = "";
      r.on("data", (c) => { d += c; if (d.length > 4096) req.destroy(); });
      r.on("end", () => { try { const j = JSON.parse(d); ok(j.appli === "microduck" ? { adresse: `${ip}:${PORT}`, nom: j.nom || "Microduck" } : null); } catch (e) { ok(null); } });
    });
    req.on("timeout", () => req.destroy());
    req.on("error", () => ok(null));
  });
}
async function chercher() {
  const prefixes = new Set();
  for (const liste of Object.values(os.networkInterfaces())) {
    for (const a of liste || []) {
      if (a.family === "IPv4" && !a.internal && adressePrivee(a.address)) prefixes.add(a.address.split(".").slice(0, 3).join("."));
    }
  }
  const ips = [...prefixes].flatMap((p) => Array.from({ length: 254 }, (_, i) => `${p}.${i + 1}`));
  const trouves = [];
  for (let i = 0; i < ips.length; i += 64) {
    (await Promise.all(ips.slice(i, i + 64).map((ip) => sante(ip)))).forEach((r) => { if (r) trouves.push(r); });
  }
  return trouves;
}

// -- pont avec l'interface (meme nom que celui de l'APK : l'interface ne fait pas la difference) --------------------
ipcMain.handle("canards", () => lireCanards());
ipcMain.handle("oublier", (_e, adresse) => {
  fs.writeFileSync(fichierCanards(), JSON.stringify(lireCanards().filter((c) => c.adresse !== adresse)));
  return lireCanards();
});
ipcMain.handle("chercher", () => chercher());
ipcMain.handle("ouvrir", async (_e, adresse) => {
  const a = String(adresse || "").trim().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
  const hote = a.split(":")[0];
  if (!adressePrivee(hote)) return { ok: false, message: "Adresse du réseau local attendue (ex. 192.168.1.42)" };
  const r = await sante(hote, 2500);
  if (!r) return { ok: false, message: "Microduck ne répond pas à cette adresse (même Wi-Fi ?)" };
  retenirCanard(r.adresse, r.nom);
  fenetre.loadURL(`http://${r.adresse}/`);
  return { ok: true };
});
ipcMain.handle("demo", () => { fenetre.loadURL("microduck://demo/index.html?demo"); return true; });
ipcMain.on("accueil", () => fenetre.loadFile(ACCUEIL));
ipcMain.on("retenir", (e, origine) => {
  try { const u = new URL(origine); if (urlCanard(origine)) retenirCanard(u.host, (lireCanards().find((c) => c.adresse === u.host) || {}).nom); } catch (x) { /* rien */ }
});
// notifications : l'interface renvoie aussi les alertes des dernieres 24 h a l'ouverture -> un curseur (instant de la
// derniere alerte notifiee, garde entre deux lancements) evite de les ressortir
const fichierCurseur = () => path.join(app.getPath("userData"), "alertes-vues.json");
ipcMain.on("alertes", (_e, json) => {
  let liste = [];
  try { liste = JSON.parse(json).filter((a) => typeof a.t === "number"); } catch (x) { return; }
  let curseur = null;
  try { curseur = JSON.parse(fs.readFileSync(fichierCurseur(), "utf8")).t; } catch (x) { /* premier lancement */ }
  const max = Math.max(curseur || 0, ...liste.map((a) => a.t));
  fs.mkdirSync(app.getPath("userData"), { recursive: true });
  fs.writeFileSync(fichierCurseur(), JSON.stringify({ t: max }));
  if (curseur === null) return;                          // premier lancement : rien d'ancien en notification
  for (const a of liste.filter((x) => x.t > curseur).slice(-5)) {
    if (Notification.isSupported()) new Notification({ title: String(a.titre || "Microduck"), body: String(a.texte || ""), silent: !a.importante }).show();
  }
});
ipcMain.on("enregistrer", async (_e, nom, type, base64) => {
  const r = await dialog.showSaveDialog(fenetre, { defaultPath: path.basename(String(nom || "microduck")) });
  if (!r.canceled && r.filePath) fs.writeFileSync(r.filePath, Buffer.from(String(base64), "base64"));
});

// -- version : une plus recente sur GitHub ? (version.json de la derniere release « ordinateur ») ------------------
ipcMain.handle("version", async () => {
  const moi = app.getVersion();
  try {
    const r = await net.fetch("https://api.github.com/repos/RaphaelGrj/microduck-brain/releases?per_page=20");
    const derniere = (await r.json()).find((x) => /^ordinateur-v/.test(x.tag_name || "") && !x.draft);
    const v = derniere ? derniere.tag_name.replace("ordinateur-v", "") : null;
    const plus = (a, b) => { const x = a.split(".").map(Number), y = b.split(".").map(Number);
      for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); return false; };
    return { moi, nouvelle: v && plus(v, moi) ? v : null, lien: derniere ? derniere.html_url : DEPOT };
  } catch (e) { return { moi, nouvelle: null }; }
});
ipcMain.on("lien", (_e, u) => { if (/^https:\/\//.test(u)) shell.openExternal(u); });

function creerFenetre() {
  fenetre = new BrowserWindow({
    width: 460, height: 900, minWidth: 360, minHeight: 560, title: "Microduck", backgroundColor: "#ffffff",
    icon: path.join(INTERFACE, "icone.png"),
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  const wc = fenetre.webContents;
  // le canard (ou la demo) reste dans la fenetre ; Printables, Cults, GitHub... s'ouvrent dans le navigateur
  wc.setWindowOpenHandler(({ url }) => { if (/^https?:\/\//.test(url)) shell.openExternal(url); return { action: "deny" }; });
  wc.on("will-navigate", (e, url) => {
    if (url.startsWith("file:") || url.startsWith("microduck:") || urlCanard(url)) return;
    e.preventDefault();
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
  });
  wc.on("did-fail-load", (_e, code, _desc, url, principal) => {
    if (!principal || code === -3) return;                   // (-3 : chargement remplace par un autre)
    fenetre.loadFile(ACCUEIL, { query: { erreur: "Microduck ne répond pas : " + url } });
  });
  wc.session.setPermissionRequestHandler((_wc, permission, rappel) => rappel(permission === "notifications" || permission === "clipboard-sanitized-write"));
  fenetre.loadFile(ACCUEIL);
}

Menu.setApplicationMenu(Menu.buildFromTemplate([
  ...(process.platform === "darwin" ? [{ role: "appMenu" }] : []),
  { label: "Microduck", submenu: [
    { label: "Changer de canard", accelerator: "CmdOrCtrl+Shift+H", click: () => fenetre && fenetre.loadFile(ACCUEIL) },
    { label: "Recharger", role: "reload" },
    { type: "separator" },
    { label: "Plein écran", role: "togglefullscreen" },
    { label: "Zoom +", role: "zoomIn" }, { label: "Zoom −", role: "zoomOut" }, { label: "Taille normale", role: "resetZoom" },
    { type: "separator" },
    { label: "Quitter", role: "quit" },
  ] },
  { role: "editMenu", label: "Édition" },
]));

app.whenReady().then(() => {
  protocol.handle("microduck", (req) => {
    const u = new URL(req.url);
    const chemin = path.normalize(decodeURIComponent(u.pathname === "/" ? "/index.html" : u.pathname));
    const fichier = path.join(INTERFACE, chemin);
    if (!fichier.startsWith(INTERFACE + path.sep)) return new Response("Absent", { status: 404 });
    return net.fetch(require("url").pathToFileURL(fichier).toString());
  });
  creerFenetre();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) creerFenetre(); });
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
