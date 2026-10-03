#!/bin/bash
# Attend que duck-sim soit debout (max 2 min) puis resume l'etat (duck, mediad, console web).
for i in $(seq 1 40); do
  grep -q "Your duck is up\|did not stand up" "$HOME/duck-sim.out" 2>/dev/null && break
  sleep 3
done
grep "standing (" "$HOME/duck-sim.out" | cut -c1-100
echo "--- mediad:"
ps -eo etime,args | grep "[m]ediad" | cut -c1-60
curl -s -o /dev/null -w "console HTTP %{http_code}\n" --max-time 5 http://127.0.0.1:8080
