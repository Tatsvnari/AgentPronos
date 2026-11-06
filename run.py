#!/usr/bin/env python3
"""Pronos.

  run.py census              refresh the vault census from UniProtKB
  run.py publish <webroot>   write <webroot>/status.json
  run.py tick [n]            run n autonomous agent steps
  run.py agent [seconds]     run the agent forever, one step per interval
  run.py memory [show|review|recall <text>]   scientific memory (read-only over the record)
  run.py loop ...            research loop commands (see pronos/loop.py)"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pronos import agent, census, ledger, loop, memory, publish  # noqa: E402

if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else "help"
    if cmd == "census":
        print(census.run())
    elif cmd == "publish":
        print(json.dumps(publish.write(os.path.join(a[1] if len(a) > 1 else ".", "status.json"))))
    elif cmd == "tick":
        for _ in range(int(a[1]) if len(a) > 1 else 1):
            print(agent.tick())
    elif cmd == "agent":
        agent.run_forever(int(a[1]) if len(a) > 1 else 300)
    elif cmd == "memory":
        sub = a[1] if len(a) > 1 else "show"
        if sub == "recall":
            print(json.dumps(memory.recall(" ".join(a[2:])), indent=1))
        elif sub == "review":
            print(json.dumps(memory.review()["counts"]))
        else:
            print(json.dumps(memory.build(), indent=1))
    elif cmd == "loop":
        loop.main(a[1:])
    else:
        print(__doc__)
