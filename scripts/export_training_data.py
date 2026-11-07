"""Explicitly export saved labels for local experiments; never runs automatically."""

import argparse
from pathlib import Path

from abacus.classification import export_examples
from abacus.db import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with Session() as db, args.output.open("x", encoding="utf-8") as output:
        count = export_examples(db, output)
    print(f"Exported {count} saved labels to {args.output}. Keep this file private.")


if __name__ == "__main__":
    main()
