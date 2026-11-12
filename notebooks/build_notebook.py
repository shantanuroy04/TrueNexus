"""Turn email_classifier_v6.src.py (cells marked with '#%% [markdown]' / '#%% [code]') into a .ipynb.
Usage: python build_notebook.py email_classifier_v6.src.py email_classifier_v6.ipynb"""
import json
import re
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
cells = []
for kind, body in re.findall(r"^#%% \[(markdown|code)\]\n(.*?)(?=^#%% \[|\Z)", src.read_text(encoding="utf-8"), re.S | re.M):
    lines = body.rstrip("\n").split("\n")
    source = [line + "\n" for line in lines[:-1]] + [lines[-1]]
    cell = {"cell_type": kind, "metadata": {}, "source": source}
    if kind == "code":
        cell.update(execution_count=None, outputs=[])
    cells.append(cell)

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
        "kaggle": {"accelerator": "gpu", "isInternetEnabled": True},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
dst.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"{dst.name}: {len(cells)} cells ({sum(c['cell_type'] == 'code' for c in cells)} code)")
