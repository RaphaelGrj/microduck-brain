# Zone morte de la politique de marche (mesures sur `duck-sim`, 2026-10-03)

Pas de démarche en dessous d'un certain seuil de commande, **même si `robotd` affiche
`policy=walk` et applique la commande en entier** (`move.applied` = demandé, gain 200) :
les jambes restent figées (amplitude ~0,0 rad après la 1re seconde).

| Commande | Résultat (5 s) |
|---|---|
| `vx` 0,10 / 0,15 / 0,20 m/s | **rien** (jambes figées, ~1 cm) |
| `vx` 0,30 m/s | marche, ~0,11 m/s réels (0,5 m en 5 s) |
| `vx` 0,40 m/s | marche, ~0,125 m/s réels (0,63 m) |
| `vx` −0,30 m/s | **rien** |
| `vx` −0,40 m/s | marche arrière, ~0,15 m/s réels (0,73 m) |
| `vyaw` 0,5 / 0,8 rad/s | **rien** (≤ 11° en 5 s) |
| `vyaw` 1,2 / 1,5 rad/s | tourne, ~0,9–1,0 rad/s réels (≈ 50–65 % de la consigne) |

Conséquences pour le cerveau :
- Marche : `vx ≥ 0,3` (avant), `≤ −0,4` (arrière). Rotation : `|vyaw| ≥ 1,2`.
- **Pas de pilotage fin à basse vitesse par le corps.** L'alignement fin se fait avec la
  **tête** (`robot.head`, continu, sans zone morte), le corps ne fait que de grosses
  corrections (rotation par à-coups, marche à vitesse mini).
- Le script officiel `scripts/duck-sim drive` utilise 0,15 m/s par défaut : sur cette
  installation il ne fait donc pas marcher le canard (il ne faut pas s'y fier comme test).
- L'odométrie est cohérente avec ces mesures (confirmé par comparaison d'images avant/après).

Ce n'est PAS dû à : la caméra (même résultat sans), le dock (géométrie purement visuelle),
la vitesse de simulation (corrigée à 1,00× temps réel : rendu sans ombres + 10 images/s).
Le coût du rendu logiciel sous WSL2 (llvmpipe, 142 ms/image avec ombres) faisait tomber la
physique à 0,36× ; options ajoutées au fork `microduck_rl` : `DUCK_SIM_CAMERA_FLAT=1`,
`DUCK_SIM_CAMERA_FPS`.

Pas encore testé : la politique `velstand.onnx` (marche par défaut depuis le 14/09 selon le
manifeste officiel, « marche aussi à l'arrêt ») pourrait ne pas avoir cette zone morte ;
`duck-sim` charge `alpha_walking.onnx` + `alpha_stand.onnx`.

## Table des rafales (arène, vérité terrain, `bursts.py`, 2026-10-03)

Déplacement du tronc pour une commande tenue T secondes depuis l'arrêt (le canard se
stabilise ensuite). Moyennes sur 2 essais, tête neutre :

| Commande | 0,25 s | 0,5 s | 1,0 s |
|---|---|---|---|
| `vx` +0,4 | ~2 cm | ~6 cm | ~15 cm (dérive latérale −2…−4 cm, cap ±10°) |
| `vx` −0,4 | — | −3,5…−6 cm | ~−15 cm |
| `vy` +0,4 (gauche) | rien | 1…4 cm (irrégulier) | 5…6 cm |
| `vy` −0,4 (droite) | rien | ~5 cm (+9° de cap) | ~10 cm |
| `vyaw` +1,5 | rien | ~25° | ~55° |
| `vyaw` ±1,2 | rien | 0…19° (irrégulier) | ~30° |

→ Débit de marche ≈ 18 cm/s après 0,14 s de démarrage ; rotation ≈ 50°/s ; résolution
minimale réaliste ≈ 2–3 cm en avant, ≈ 25° en rotation, ≈ 4–5 cm en pas de côté.
Le pas de côté **gauche est nettement plus faible que le droit**.

## La tête baissée tue la rotation du corps (et affaiblit la marche arrière / le pas à gauche)

Mêmes rafales avec la tête baissée (`head_pitch` en offset) :

| Inclinaison | `vyaw` 1,5 pendant 1 s | `vx` −0,4 pendant 0,5 s |
|---|---|---|
| 0,0 | ~55° | −3,5…−6 cm |
| 0,3 / 0,5 | ~45–60° | — |
| 0,7 | ~30° (0 à 0,5 s) | — |
| 1,0 | **0…2°** | **rien** |
| 1,5 | **0…1°** | **rien** |

La marche avant et le pas de côté droit restent à peu près corrects. Hypothèse (non
vérifiée) : l'inclinaison de la tête fait partie des observations de la politique de marche
(`head4` du contrat de 61 entrées) et sort de ce qu'elle a vu à l'entraînement.
**Règle : tête à ≤ 0,4 pendant les rafales du corps, baissée seulement à l'arrêt pour regarder.**

## Le tir exige la tête au neutre

`kick_left` / `kick_right` avec la balle à x = 0,07 m devant le tronc, tête tenue à
différentes inclinaisons : neutre → **1,1–1,3 m/s, balle à 0,7 m en 1 s** (les deux pieds) ;
tête à 0,5 / 1,0 / 1,5 → **0 m/s, le pied ne touche rien**. Le contrôleur d'approche ramène
donc la tête au neutre (1,4 s) avant `robot.do`.

## Fenêtre de tir (arène, canard remis à l'origine à chaque essai, `kick_sweep.py`)

Position de la balle dans le repère du tronc, par rapport au point d'entraînement
(0,09 ; ±0,042). Résultats identiques sur 2 répétitions (simulation déterministe) :

- **Profondeur : très étroite.** Succès à dx = −2 cm (balle à 7 cm) pour les deux pieds ;
  dx = 0 réussit surtout au pied gauche ; dx ≥ +2 cm : le pied ne touche **rien** ; dx = −4 cm :
  touche mollement (0,2 m/s).
- **Latéral : ±3 cm tolérés** autour de ±0,042.
- Le ballon part à ~±15…25° de l'axe, vers l'extérieur (pied droit −10…−27°, pied gauche
  +15…+22°), pas droit devant : compenser le cap pour viser.
- L'appartement est inutilisable pour ces mesures (le couloir de naissance fait 40 cm de large,
  la balle est repoussée par les murs) : utiliser `scripts-wsl/run-scene.sh arena`.
