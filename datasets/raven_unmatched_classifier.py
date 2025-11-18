#!/usr/bin/env python3
"""
raven_unmatched_classifier.py

Classify "UNMATCHED:" guard/revert lines from Solidity/Vyper logs into semantic categories.
Usage:
  python raven_unmatched_classifier.py --in unmatched.txt --csv summary.csv --json summary.json --examples examples.json

If --in is omitted, reads from stdin.
"""
from __future__ import annotations
import argparse, sys, re, json, csv
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

# (category, regex pattern) ordered from most specific to more generic
PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("Slippage/MinReturn", re.compile(r"(returnamount\s*\*\s*desc\.amount\s*<\s*desc\.minreturnamount\s*\*\s*spentamount)|(returnamount\s*<\s*(minreturn|minreturnamount|desc\.minreturnamount))", re.I)),
    ("Insufficient ETH/Native", re.compile(r"(insufficienteth\(\))|(amount\s*>\s*address\(this\)\.balance)|(value\s*<\s*amountminimum)", re.I)),
    ("Insufficient Allowance", re.compile(r"(insufficientallowance\(\))|(allowed\s*<\s*value)", re.I)),
    ("Insufficient Token Balance", re.compile(r"(insufficientbalance\(\))|(gt\s*\(\s*amount\s*,\s*frombalance\s*\))|(t\.frombalance\s*<\s*t\.fromlockedlength)", re.I)),
    ("Trading Not Enabled/Paused", re.compile(r"(tradingnotenabled|trading\s*not\s*(yet\s*)?enabled|tradingnotopen|tradingnotactive|tradingdisabled)", re.I)),
    ("Order Invalid/Status", re.compile(r"(invalidorder(status)?\(\))|(orderisalreadyexpired\(\))|(status\s*!=\s*status\.created)", re.I)),
    ("Signature Issues", re.compile(r"(invalidsignature(?:length)?\(\))|(signatureexpired\(\))|(signaturealreadyused)|(cosignaturehasexpired)|(paymentprocessor__signature)|(expiredsignature)", re.I)),
    ("Deadline/Expiry", re.compile(r"(deadlineviolation\(\))|(paymentdeadlinereached\(\))|(validto\s*<\s*block\.timestamp)|(block\.timestamp\s*>\s*(mintopenuntil|_signaturetimestamp))", re.I)),
    ("Whitelist/Access Control", re.compile(r"(notwhitelisted\(\))|(transfernotallowed\(\))|(only\s+admin)|(unauthorized\(\))|(hasanyrole\()", re.I)),
    ("Supply Cap/Max Supply", re.compile(r"(maxsupplyexceeded\(\))|(maxsupply\(\))|(currenttokenid\s*>=\s*maxsupply)|(totalsupply\(\)\s*\+\s*amount\s*>\s*limit)|(exceedslimit\(\))|(exceedmaxperwallet\(\))|(numberofmintsexceeded\(\))|(maxperwallet)", re.I)),
    ("Already Claimed/Nothing To Claim", re.compile(r"(alreadyclaimed\(\))|(zeroclaim\(\))|(nothingtoclaim\(\))|(zerounstakeable\(\))", re.I)),
    ("Merkle Proof / Claim Fee", re.compile(r"(invalidmerkleproof\(\))|(incorrectclaimfee\(\))", re.I)),
    ("Price Limit", re.compile(r"(invalidpricelimit\(\))", re.I)),
    ("Gas Price Constraint", re.compile(r"(tx\.gasprice\s*>\s*[\w\.\[\]$]+)|not\s+enough\s+gas\s+fees", re.I)),
    ("RFQ/Quote Expired", re.compile(r"(rfqquoteexpired\(\))", re.I)),
    ("Cross-Chain / LayerZero", re.compile(r"(lz_insufficientfee|lz_uln_verifying|lz_payloadhashnotfound)", re.I)),
    ("Invalid Time Window", re.compile(r"(invalidtime_error_selector)|(starttime)|(endtime).*error_length", re.I)),
    ("EOA Instead of Contract", re.compile(r"(iszero\s*\(\s*extcodesize\()", re.I)),
    ("Panic/Low-level Revert", re.compile(r"(panic\(uint256\))|(revertdatasize)|(returndatacopy\()|(callbytes failed)|(call failed)|(swapfailed\(\))|(assembly\s*\{[^}]*revert)", re.I)),
    ("Oracle Freshness/Signature", re.compile(r"(nofreshupdate\(\))|(expiredoraclesignature\(\))", re.I)),
    ("Auction/Market", re.compile(r"(nftmarketreserveauction_cannot_finalize)", re.I)),
    ("Pool/Capacity", re.compile(r"(exceedsmaxpoolsize)", re.I)),
    ("Route/Allowlist", re.compile(r"(routenotallowlisted)", re.I)),
    ("Token Locked/Transfers Locked", re.compile(r"(transferslocked\(\))|(exchangetokenlocked\(\))", re.I)),
    ("Minting Epoch Rules", re.compile(r"(blocksbetweenmints\s*>=\s*2\^\^epoch)", re.I)),
    ("Invariant/Math Check", re.compile(r"(clipperinvariant\(\))", re.I)),
    ("Config Digest Mismatch", re.compile(r"(configdigestmismatch\(\))", re.I)),
    ("Claim/Rewards Flow", re.compile(r"(invalidclaimrequest\(\))|(rewardsclaimed\()|(claimableamount)", re.I)),
    ("Payment Processor", re.compile(r"(paymentprocessor__)", re.I)),
    ("Price Feed / Quote", re.compile(r"(quote\.deadlinetimestamp\s*<\s*block\.timestamp)", re.I)),
]

NORMALIZE_REPLACEMENTS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\s+"), " "),
    (re.compile(r"0x[0-9a-fA-F]+"), "0xHEX"),
    (re.compile(r"\b\d+\b"), "N"),
    (re.compile(r"\bmsg\.sender\b", re.I), "MSG.SENDER"),
    (re.compile(r"\bblock\.timestamp\b", re.I), "BLOCK.TIMESTAMP"),
]

def normalize(line: str) -> str:
    s = line.strip()
    if s.lower().startswith("unmatched:"):
        s = s[len("UNMATCHED:"):].strip()
    # collapse memory-heavy assembly payloads
    if "assembly {" in s:
        s = re.sub(r"assembly\s*\{.*\}", "assembly { ... }", s, flags=re.S)
    for pat, repl in NORMALIZE_REPLACEMENTS:
        s = pat.sub(repl, s)
    return s

def categorize(line: str) -> str:
    low = line.lower()
    for cat, pat in PATTERNS:
        if pat.search(low):
            return cat
    return "Other/Unmapped"

def process(lines: List[str]):
    from collections import Counter, defaultdict
    counts = Counter()
    examples = defaultdict(list)
    normalized_seen = set()

    for raw in lines:
        if not raw.strip():
            continue
        norm = normalize(raw)
        cat = categorize(norm)
        counts[cat] += 1
        key = (cat, norm)
        if key not in normalized_seen and len(examples[cat]) < 5:
            examples[cat].append(norm)
            normalized_seen.add(key)

    total = sum(counts.values())
    dist = {cat: {"count": c, "pct": (100.0*c/total if total else 0.0), "examples": examples.get(cat, [])}
            for cat, c in counts.most_common()}
    return {"total": total, "distribution": dist}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", help="Input file containing UNMATCHED lines. If omitted, reads stdin.")
    ap.add_argument("--csv", dest="csv_out", help="Write category counts to CSV.")
    ap.add_argument("--json", dest="json_out", help="Write full summary (with examples) to JSON.")
    ap.add_argument("--examples", dest="examples_out", help="Write examples per category to JSON (only examples).")
    args = ap.parse_args()

    if args.infile:
        with open(args.infile, "r", encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.read().splitlines()

    summary = process(lines)
    # Pretty-print to stdout
    print(f"Total lines: {summary['total']}")
    print("Category counts:")
    for cat, info in summary["distribution"].items():
        print(f"  - {cat:32s} {info['count']:6d}  ({info['pct']:.2f}%)")

    if args.csv_out:
        with open(args.csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["category", "count", "percent"])
            for cat, info in summary["distribution"].items():
                w.writerow([cat, info["count"], f"{info['pct']:.2f}"])

    if args.json_out:
        import json
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    if args.examples_out:
        only_ex = {cat: info["examples"] for cat, info in summary["distribution"].items()}
        with open(args.examples_out, "w", encoding="utf-8") as f:
            json.dump(only_ex, f, indent=2)

if __name__ == "__main__":
    main()
