// Carte Microduck pour le tableau de bord de Home Assistant (Lovelace). Elle n'utilise que les entites que le canard
// publie deja (pont_ha.py : sensor.microduck_*, binary_sensor.microduck_*, switch.microduck_calme, button.microduck_*).
// Installation : homeassistant/README.md. Aucun appel ailleurs qu'a Home Assistant.
const ETATS = {
  chill: "Il se repose", look: "Il regarde autour de lui", wander: "Il se promène", nap: "Il fait la sieste",
  curious: "Curieux", balle: "Il joue à la balle", accueil: "Il accueille quelqu'un", danse: "Il danse",
  caresse: "Il se fait caresser", regarde_chat: "Il regarde le chat", jeu_solitaire: "Il joue tout seul",
  cherche_attention: "Il cherche de la compagnie", alarme: "ALARME", porte: "Dans les bras", signal: "Il te signale quelque chose",
  ou_es_tu: "Je suis là !", parcours: "Il fait son parcours", soleil: "1-2-3 soleil", cache_cache: "Cache-cache",
};
const BOUTONS = [["ou_es_tu", "📍", "Où es-tu ?"], ["jouer_balle", "⚽", "Balle"], ["jouer_cache", "🙈", "Cache-cache"],
  ["tour_salut", "👋", "Salut"], ["signal_stop", "🔕", "Arrêter le signal"], ["diagnostic", "🩺", "Diagnostic"]];

class MicroduckCard extends HTMLElement {
  setConfig(config) {
    this.config = { prefixe: "microduck", titre: "Microduck", ...(config || {}) };
    if (!/^[a-z0-9_]+$/.test(this.config.prefixe)) throw new Error("prefixe : lettres minuscules, chiffres, _");
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  static getStubConfig() { return { prefixe: "microduck" }; }
  getCardSize() { return 4; }

  set hass(hass) {
    this._hass = hass;
    this.dessiner();
  }

  etat(domaine, objet) { return this._hass && this._hass.states[`${domaine}.${this.config.prefixe}_${objet}`]; }

  dessiner() {
    if (!this._hass || !this.shadowRoot) return;
    const v = (d, o) => { const s = this.etat(d, o); return s && !["unknown", "unavailable"].includes(s.state) ? s.state : null; };
    const pct = (x) => (x == null || isNaN(+x) ? null : Math.round(+x <= 1 ? +x * 100 : +x));
    const etat = v("sensor", "etat"), batt = pct(v("sensor", "batterie")), energie = pct(v("sensor", "energie")), eveil = pct(v("sensor", "eveil"));
    const tombe = v("binary_sensor", "tombe") === "on", calme = this.etat("switch", "calme");
    const dispo = this.etat("sensor", "etat") && this.etat("sensor", "etat").state !== "unavailable";
    const barre = (nom, x, coul) => `<div class="jauge"><span>${nom}</span><div class="b"><i style="width:${x || 0}%;background:${coul}"></i></div><b>${x == null ? "—" : x + " %"}</b></div>`;
    const boutons = BOUTONS.filter(([o]) => this.etat("button", o)).map(([o, e, t]) => `<button data-b="${o}" title="${t}">${e}<small>${t}</small></button>`).join("");
    const image = this.config.image ? `<img src="${encodeURI(this.config.image)}" alt="">` : `<div class="canard">🦆</div>`;
    this.shadowRoot.innerHTML = `<style>
      ha-card { padding: 16px; } .tete { display: flex; gap: 14px; align-items: center; }
      img, .canard { width: 72px; height: 72px; object-fit: contain; flex: 0 0 auto; } .canard { font-size: 52px; text-align: center; line-height: 72px; }
      h2 { margin: 0; font-size: 1.25rem; } .etat { color: var(--secondary-text-color); margin-top: 2px; }
      .alerte { color: var(--error-color, #b91c1c); font-weight: 600; }
      .jauge { display: grid; grid-template-columns: 70px 1fr 52px; gap: 8px; align-items: center; margin-top: 8px; font-size: .9rem; }
      .b { height: 8px; border-radius: 4px; background: var(--divider-color, #e7e4df); overflow: hidden; } .b i { display: block; height: 100%; }
      .jauge b { text-align: right; } .boutons { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 14px; }
      button { border: 1px solid var(--divider-color, #ddd); background: var(--card-background-color, #fff); color: var(--primary-text-color);
        border-radius: 12px; padding: 8px 4px; font-size: 1.3rem; cursor: pointer; } button small { display: block; font-size: .7rem; margin-top: 2px; }
      .calme { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; }
      .hs { opacity: .55; }
    </style><ha-card class="${dispo ? "" : "hs"}"><div class="tete">${image}<div><h2>${this.config.titre}</h2>
      <div class="etat ${tombe ? "alerte" : ""}">${!dispo ? "Indisponible" : tombe ? "Il est tombé !" : ETATS[etat] || etat || "—"}</div></div></div>
      ${barre("Batterie", batt, batt != null && batt < 20 ? "#c2410c" : "#2f855a")}${barre("Énergie", energie, "#f26a1b")}${barre("Éveil", eveil, "#2563eb")}
      ${calme ? `<div class="calme"><span>Mode calme</span><ha-switch ${calme.state === "on" ? "checked" : ""}></ha-switch></div>` : ""}
      ${boutons ? `<div class="boutons">${boutons}</div>` : ""}</ha-card>`;
    this.shadowRoot.querySelectorAll("button[data-b]").forEach((b) => b.addEventListener("click", () =>
      this._hass.callService("button", "press", { entity_id: `button.${this.config.prefixe}_${b.dataset.b}` })));
    const sw = this.shadowRoot.querySelector("ha-switch");
    if (sw) sw.addEventListener("change", () => this._hass.callService("switch", "toggle", { entity_id: `switch.${this.config.prefixe}_calme` }));
  }
}

customElements.define("microduck-card", MicroduckCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "microduck-card", name: "Microduck", description: "Ton canard : état, batterie, humeur, jeux." });
