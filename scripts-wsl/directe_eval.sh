#!/bin/bash
# Compare la passe directe a la passe actuelle (balayage kick_sweep, meme grille). Usage : directe_eval.sh right|left <iteration directe> <iteration passe>
pied="$1"; it="$2"; itp="$3"
case "$pied" in right) S=Right ;; left) S=Left ;; esac
export PATH="$HOME/.local/bin:$PATH"
RUN=$(ls -d $HOME/microduck_rl/logs/rsl_rl/ball_kick_directe_$pied/*/ | while read d; do [ -f "${d}model_${it}.pt" ] && echo "$d"; done | grep -v init | tail -1)
OUT="$HOME/.cache/duck-sim/policies/passe/kick_directe_${pied}_${it}.onnx"
cd $HOME/microduck_rl && uv run python scripts/export.py "Mjlab-BallKickPasseDirecte-Flat-Backlash-MicroDuck-$S" --checkpoint-file "${RUN}model_${it}.pt" --onnx-file "$OUT" --num-envs 1 2>&1 | grep -i "written\|error"
cd $HOME && bash run-scene.sh arena | tail -1
cd $HOME/microduck-brain
export KICK_VMIN=0.22 KICK_VMAX=0.9 KICK_DXS=-0.02,0,0.02 KICK_DYS=-0.02,0,0.02
for cas in directe passe; do
  if [ $cas = directe ]; then F=$OUT; else F=$HOME/.cache/duck-sim/policies/passe/kick_passe_${pied}_${itp}.onnx; fi
  bash ~/run-brain.sh charge_politique.py kick_$pied $F 2>&1 | head -1 >/dev/null; sleep 3
  echo "=== $cas $pied ==="
  bash ~/run-brain.sh kick_sweep.py $pied 3 2>&1 | grep "dx=" | grep -v "^$" > ~/sweep_${cas}_$pied.txt
  python3 - <<PYEOF
import re,statistics
t=open("/home/raphael/sweep_${cas}_$pied.txt").read()
a=[(int(m.group(1)),int(m.group(2)),float(m.group(3))) for m in re.finditer(r"dx= *([+-]\d+) dy= *([+-]\d+): vmax=\S+ m/s  depart= *([+-][\d.]+) deg",t)]
ok=[x for x in re.findall(r"-> (OK|rate)",t)]
print("essais",len(ok),"OK",ok.count("OK"))
ang=[x[2] for x in a]
if ang: print("depart moyen %+.1f ecart-type %.1f  min %+.0f max %+.0f"%(statistics.mean(ang),statistics.pstdev(ang),min(ang),max(ang)))
PYEOF
done
bash ~/run-brain.sh charge_politique.py kick_$pied officielle 2>&1 | head -1 >/dev/null
bash ~/stop_sim.sh >/dev/null 2>&1
