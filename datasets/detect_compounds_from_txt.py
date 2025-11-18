#!/usr/bin/env python3
import re
import sys
import argparse
import csv
from collections import Counter

def build_patterns():
    # Order matters: longer comparisons first
    cmp_re = re.compile(r"(==|!=|<=|>=|<|>)")
    logical_double_re = re.compile(r"&&|\|\|")
    logical_words_re = re.compile(r"\b(and|or)\b", flags=re.IGNORECASE)
    bitwise_re = re.compile(r"(?<![&|])([&|])(?![&|])")   # single & or | (not &&/||)
    ternary_qmark_re = re.compile(r"\?")
    ternary_colon_re = re.compile(r":")
    return {
        "cmp_re": cmp_re,
        "logical_double_re": logical_double_re,
        "logical_words_re": logical_words_re,
        "bitwise_re": bitwise_re,
        "ternary_qmark_re": ternary_qmark_re,
        "ternary_colon_re": ternary_colon_re,
    }

def detect_categories(s: str, pats) -> set:
    """Return a set of categories that make this predicate 'compound'."""
    if not isinstance(s, str):
        s = str(s)
    t = s.strip()
    cats = set()
    if not t:
        return cats

    # Logical connectives
    if pats["logical_double_re"].search(t):
        cats.add("logical_&&_||")

    # Textual boolean words (standalone)
    if pats["logical_words_re"].search(t):
        cats.add("logical_and_or")

    # Bitwise single & or |
    if pats["bitwise_re"].search(t):
        cats.add("bitwise_&_pipe")

    # Multiple comparisons (>= 2)
    if len(pats["cmp_re"].findall(t)) >= 2:
        cats.add("multiple_comparisons")

    # Ternary operator ?:
    if pats["ternary_qmark_re"].search(t) and pats["ternary_colon_re"].search(t):
        cats.add("ternary_?:")
    return cats

def load_lines(path: str, dedup: bool) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f]
    # keep non-empty
    lines = [ln for ln in lines if ln]
    if dedup:
        # preserve order while deduping
        seen = set()
        uniq = []
        for ln in lines:
            if ln not in seen:
                seen.add(ln)
                uniq.append(ln)
        return uniq
    return lines

def main():
    ap = argparse.ArgumentParser(
        description="Detect compound Solidity invariants from a txt file (one invariant per line)."
    )
    ap.add_argument("infile", help="Path to .txt with one invariant per line")
    ap.add_argument("--dedup", action="store_true", help="De-duplicate identical lines (order-preserving)")
    ap.add_argument("--csv", metavar="OUT_CSV", help="Write compounds to CSV (predicate, categories)")
    ap.add_argument("--breakdown", metavar="OUT_BREAKDOWN_CSV", help="Write category counts to CSV")
    ap.add_argument("--examples", type=int, default=10, help="How many example compounds to print (default: 10)")
    args = ap.parse_args()

    pats = build_patterns()
    preds = load_lines(args.infile, args.dedup)

    compounds = []
    category_counter = Counter()

    for p in preds:
        cats = detect_categories(p, pats)
        if cats:
            compounds.append((p, ";".join(sorted(cats))))
            for c in cats:
                category_counter[c] += 1

    n_total = len(preds)
    n_comp = len(compounds)
    pct = (n_comp / n_total * 100.0) if n_total else 0.0

    print(f"Total invariants (after filtering): {n_total}")
    print(f"Compound invariants:               {n_comp} ({pct:.2f}%)")

    # Print a few examples
    if compounds:
        print("\nExamples:")
        for p, cats in compounds[: max(0, args.examples)]:
            print(f" - {p}    [{cats}]")

    # Optional CSV of compounds
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["predicate", "compound_categories"])
            for p, cats in compounds:
                w.writerow([p, cats])
        print(f"\nSaved compound predicates to: {args.csv}")

    # Optional breakdown CSV
    if args.breakdown:
        with open(args.breakdown, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["category", "count"])
            for cat, cnt in sorted(category_counter.items()):
                w.writerow([cat, cnt])
        print(f"Saved category breakdown to:  {args.breakdown}")

if __name__ == "__main__":
    main()
