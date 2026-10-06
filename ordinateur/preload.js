// Pont entre les pages et l'application : l'accueil (fichier local) cherche et ouvre les canards ; l'interface du
// canard (ou la demo) recoit le meme pont « MicroduckAndroid » que dans l'APK (notifications, fichiers), sans la
// presence par le Wi-Fi propre au telephone.
"use strict";
const { contextBridge, ipcRenderer } = require("electron");

if (location.protocol === "file:") {
  contextBridge.exposeInMainWorld("MicroduckOrdinateur", {
    canards: () => ipcRenderer.invoke("canards"),
    oublier: (adresse) => ipcRenderer.invoke("oublier", adresse),
    chercher: () => ipcRenderer.invoke("chercher"),
    ouvrir: (adresse) => ipcRenderer.invoke("ouvrir", adresse),
    demo: () => ipcRenderer.invoke("demo"),
    version: () => ipcRenderer.invoke("version"),
    lien: (u) => ipcRenderer.send("lien", u),
  });
} else {
  contextBridge.exposeInMainWorld("MicroduckAndroid", {
    retenir: (origine) => ipcRenderer.send("retenir", String(origine)),
    alertes: (json) => ipcRenderer.send("alertes", String(json)),
    enregistrer: (nom, type, base64) => ipcRenderer.send("enregistrer", String(nom), String(type), String(base64)),
  });
  contextBridge.exposeInMainWorld("MicroduckOrdinateur", { accueil: () => ipcRenderer.send("accueil") });
}
