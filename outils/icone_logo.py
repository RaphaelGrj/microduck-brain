#!/usr/bin/env python3
"""L'icone de l'application (interface/icone.png : APK Android, ecran d'accueil du telephone, page d'appairage) :
le logo outils/logo.png sur un carre arrondi orange Microduck, 512 x 512.

    uv run --with pillow python outils/icone_logo.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ICI = Path(__file__).resolve().parent
ORANGE = (242, 106, 27, 255)         # --orange de interface/style.css
TAILLE, MARGE, COINS = 512, 0.12, 0.22


def main():
    logo = Image.open(ICI / "logo.png").convert("RGBA")
    logo = logo.crop(logo.getchannel("A").getbbox())
    masque = Image.new("L", (TAILLE, TAILLE), 0)
    ImageDraw.Draw(masque).rounded_rectangle((0, 0, TAILLE - 1, TAILLE - 1), radius=int(TAILLE * COINS), fill=255)
    icone = Image.new("RGBA", (TAILLE, TAILLE), (0, 0, 0, 0))
    icone.paste(Image.new("RGBA", (TAILLE, TAILLE), ORANGE), (0, 0), masque)
    largeur = int(TAILLE * (1 - 2 * MARGE))
    hauteur = round(logo.height * largeur / logo.width)
    icone.alpha_composite(logo.resize((largeur, hauteur), Image.LANCZOS), ((TAILLE - largeur) // 2, (TAILLE - hauteur) // 2))
    sortie = ICI.parent / "interface" / "icone.png"
    icone.save(sortie, optimize=True)
    print(sortie, sortie.stat().st_size // 1024, "Ko")


if __name__ == "__main__":
    main()
