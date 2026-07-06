"""Run the rule-based likelihood engine over all unconfirmed brands.

Usage: python scripts/assess.py
Safe to re-run any time (e.g. after re-clustering or new confirmations).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whoowns.engine import MODEL_VERSION, assess_all


def main() -> None:
    counts = assess_all()
    print(
        f"[{MODEL_VERSION}] Estimated: {counts['Likely']} Likely, "
        f"{counts['Possible']} Possible, {counts['Unlikely']} Unlikely. "
        f"Skipped {counts['skipped_confirmed']} confirmed brand(s)."
    )


if __name__ == "__main__":
    main()
