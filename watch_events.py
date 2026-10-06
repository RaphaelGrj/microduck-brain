#!/usr/bin/env python3
"""Observateur d'evenements robotd — ne commande rien, log les changements d'etat.

Suit le flux robot.state et affiche un evenement quand la politique active change,
quand le canard tombe / se releve, ou quand la boucle perd des ticks.

Usage : python3 watch_events.py [duree_secondes]   (defaut 30 s)
"""
import sys
import time
from pathlib import Path

from poc_robotd_client import RobotdClient, SOCK_PATH


def main():
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    client = RobotdClient(SOCK_PATH)
    client.request("robot.subscribe", {})
    print(f"Observation pendant {duration:.0f}s sur {SOCK_PATH}", flush=True)

    last_policy = None
    last_fallen = None
    last_missed = None
    start = time.monotonic()
    frames = 0

    while time.monotonic() - start < duration:
        state = client.read_state_frame()
        frames += 1
        now = time.monotonic() - start
        policy = state.get("policy")
        fallen = (state.get("safety") or {}).get("fallen")
        missed = (state.get("loop") or {}).get("missed")

        if policy != last_policy:
            print(f"[{now:6.1f}s] politique: {last_policy} -> {policy}", flush=True)
            last_policy = policy
        if fallen != last_fallen:
            print(f"[{now:6.1f}s] fallen: {last_fallen} -> {fallen}", flush=True)
            last_fallen = fallen
        if missed is not None and last_missed is not None and missed > last_missed:
            print(f"[{now:6.1f}s] ticks manques: +{missed - last_missed}", flush=True)
        last_missed = missed

    print(f"Fin. {frames} trames lues.", flush=True)


if __name__ == "__main__":
    main()
