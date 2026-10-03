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
