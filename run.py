#!/usr/bin/env python3
"""
run.py - lancia tutta la pipeline in fila.

    python run.py                # ingest -> cluster -> render
    python run.py --ore 12
    python run.py --senza-api    # solo ingest e render, per vedere se i feed girano
"""
import argparse
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def passo(nome, argomenti):
    print("\n" + "=" * 58)
    print(nome)
    print("=" * 58)
    r = subprocess.run([sys.executable, str(BASE / nome)] + argomenti)
    if r.returncode != 0:
        sys.exit("\n%s si e' fermato con errore %d." % (nome, r.returncode))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ore", type=int, default=24)
    ap.add_argument("--max", type=int, default=15)
    ap.add_argument("--senza-api", action="store_true", help="salta il raggruppamento")
    args = ap.parse_args()

    passo("ingest.py", ["--ore", str(args.ore)])
    if args.senza_api:
        print("\nSalto cluster.py (--senza-api). Serve ANTHROPIC_API_KEY per il resto.")
        return
    passo("cluster.py", [])
    passo("render.py", ["--max", str(args.max)])

    print("\nFatto. Apri:  %s" % (BASE / "web" / "index.html"))


if __name__ == "__main__":
    main()
