// Marketplace : les pieces du depot microduck-catalogue (catalogue.json, fabrique par son GitHub Action). Lu par le
// TELEPHONE sur Internet ; le canard n'y participe pas. Telechargement chez Printables / Cults (navigateur).
"use strict";

(function () {
  const CATALOGUE = "https://raw.githubusercontent.com/RaphaelGrj/microduck-catalogue/main/catalogue.json";
  const CATEGORIES = { "tête": "Tête", corps: "Corps", pieds: "Pieds", accessoire: "Accessoires", support: "Supports", autre: "Autres" };
  const SITES = { printables: "Printables", cults: "Cults", autre: "Autre site" };
  const $ = (s) => document.querySelector(s);
  let pieces = null, filtre = null;

  function el(tag, props, ...enfants) {
    const e = Object.assign(document.createElement(tag), props || {});
    e.append(...enfants.filter((x) => x != null));
    return e;
  }

  function libelleLien(site, url) {
    if (site !== "autre") return SITES[site] || site;
    try {                                                // « autre » : le nom du site (GitHub, Thingiverse...)
      const h = new URL(url).hostname.replace(/^www\./, "").split(".")[0];
      return h === "github" ? "GitHub" : h.charAt(0).toUpperCase() + h.slice(1);
    } catch (e) { return SITES.autre; }
  }

  function carte(p) {
    const photos = el("div", { className: "photos" },
      ...(p.photos.length ? p.photos.map((src) => el("img", { src, alt: p.nom, loading: "lazy",
          onerror() { this.replaceWith(el("div", { className: "sans-photo", textContent: "🦆" })); } }))
        : [el("div", { className: "sans-photo", textContent: "🦆" })]));
    const meta = el("div", { className: "meta" },
      el("span", { className: "etiquette", textContent: CATEGORIES[p.categorie] || p.categorie }),
      p.exemple ? el("span", { className: "etiquette alerte", textContent: "Exemple (démo)" }) : null,
      p.remplace_nom ? el("span", { className: "etiquette", textContent: "remplace : " + p.remplace_nom }) : null);
    const imp = p.impression || {};
    const details = [imp.materiau, imp.temps, imp.filament_g ? imp.filament_g + " g" : null,
      imp.supports === true ? "avec supports" : imp.supports === false ? "sans support" : null].filter(Boolean).join(" · ");
    const liens = Object.entries(p.liens || {}).map(([site, url], i) =>
      el("a", { href: url, target: "_blank", rel: "noopener", className: i ? "secondaire" : "", textContent: libelleLien(site, url) }));
    const corps = el("div", { className: "corps-piece" },
      el("h3", { textContent: p.nom }), meta,
      p.description ? el("p", { textContent: p.description }) : null,
      details ? el("p", { className: "discret petit", textContent: details }) : null,
      p.auteur || p.licence ? el("p", { className: "discret petit", textContent: [p.auteur, p.licence].filter(Boolean).join(" · ") }) : null,
      liens.length ? el("div", { className: "liens" }, ...liens)
        : el("p", { className: "discret", textContent: p.bientot ? "Bientôt en téléchargement." : "" }));
    if (p.apercu && p.remplace) {
      const b = el("button", { className: "essayer", textContent: "Essayer sur mon Microduck" });
      b.addEventListener("click", async () => {
        try {
          if (!window.MicroduckDesign) await import("/design.js");
          $("#boutique").hidden = true;                      // le design prend la place de la marketplace
          await window.MicroduckDesign.essayer(p.apercu, p.remplace, p.nom);
        } catch (e) { window.toast("Aperçu indisponible"); }
      });
      corps.append(b);
    }
    return el("li", { className: "piece" }, photos, corps);
  }

  function afficher() {
    const cats = [...new Set(pieces.map((p) => p.categorie))];
    $("#filtres").replaceChildren(...(cats.length > 1 ? [null, ...cats] : []).map((c) => {
      const b = el("button", { textContent: c ? (CATEGORIES[c] || c) : "Tout" });
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(c === filtre));
      b.addEventListener("click", () => { filtre = c; afficher(); });
      return b;
    }));
    const vues = pieces.filter((p) => !filtre || p.categorie === filtre);
    $("#pieces").replaceChildren(...vues.map(carte));
    $("#boutique-etat").hidden = vues.length > 0;
    $("#boutique-etat").textContent = "Pas encore de pièce dans le catalogue.";
  }

  async function charger() {
    $("#boutique-etat").hidden = false;
    $("#boutique-etat").textContent = "Chargement du catalogue…";
    try {
      const arret = new AbortController();
      const minuteur = setTimeout(() => arret.abort(), 10000);     // reseau qui ne repond pas : pas d'attente sans fin
      const r = await fetch(CATALOGUE, { cache: "no-cache", signal: arret.signal }).finally(() => clearTimeout(minuteur));
      if (!r.ok) throw new Error(r.status);
      pieces = (await r.json()).pieces || [];
    } catch (e) {
      pieces = null;
    }
    if ((!pieces || !pieces.length) && window.MicroduckDemo) pieces = window.MicroduckDemo.exemplesBoutique();
    if (!pieces) {
      $("#pieces").replaceChildren();
      $("#boutique-etat").textContent = "Catalogue injoignable : le téléphone a-t-il accès à Internet ?";
      return;
    }
    afficher();
  }

  $("#ouvrir-boutique").addEventListener("click", () => {
    $("#boutique").hidden = false;
    $("#boutique").scrollTo(0, 0);
    history.pushState({ ecran: "boutique" }, "");
    charger();
  });
})();
