#!/usr/bin/env python3
"""
extract_disl_guards.py

Extract all Solidity `require(...)` and `assert(...)` statements from the DISL dataset
(https://huggingface.co/datasets/ASSERT-KTH/DISL), focusing on the *decomposed* collection.
Only rows with language == "Solidity" are analyzed, and the source text is read from the
`source_code` column.

Outputs (in --out-dir):
  - disl_guards.parquet          (combined)
  - disl_requires.parquet        (only require)
  - disl_asserts.parquet         (only assert)

Each row contains (schema may evolve minimally as needed):
  - contract_address:   str or None
  - file_path:          str or None         (path within the verified source archive)
  - compiler_version:   str or None
  - license_type:       str or None
  - contract_name:      str or None
  - statement_kind:     'require' | 'assert'
  - statement_index:    int                 (0-based index within this file)
  - full_statement:     str                 (e.g., require(x>0, "msg");)
  - predicate:          str                 (first argument)
  - message:            str or None         (second argument for require, if present)
  - normalized_pred:    str                 (predicate with whitespace normalized & outer parens stripped)
  - line_start:         int                 (1-based line where the keyword starts)
  - col_start:          int                 (1-based column where the keyword starts)
  - file_sha1:          str                 (sha1 of full source_code to disambiguate same file_path across addresses)

You can cluster `require` and `assert` *separately* by reading the *_requires.parquet and *_asserts.parquet files,
or by filtering the combined file on `statement_kind`.

Usage (Hugging Face online):
    pip install datasets pyarrow pandas tqdm
    python extract_disl_guards.py --hf-dataset ASSERT-KTH/DISL --subset decomposed --out-dir out/

Usage (local parquet shards directory with DISL decomposed files):
    python extract_disl_guards.py --local-parquet-dir /path/to/DISL/decomposed_shards --out-dir out/

Notes:
  * The script uses a streaming/iterative approach and writes to Parquet incrementally.
  * No network calls beyond HuggingFace `datasets` unless you use the local parquet mode.
"""

from __future__ import annotations
import argparse
import hashlib
import io
import os
import re
import sys
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Tuple, Dict

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

try:
    from datasets import load_dataset, Dataset, IterableDataset
except Exception as e:
    load_dataset = None

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except Exception:
    _HAS_TQDM = False


# --------------------------
# Robust scanner utilities
# --------------------------

def _is_ident_char(ch: str) -> bool:
    return ch.isalnum() or ch == '_'

def _strip_outer_parens(s: str) -> str:
    s2 = s.strip()
    while s2.startswith('(') and s2.endswith(')'):
        depth = 0
        ok = True
        for i, c in enumerate(s2):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0 and i != len(s2) - 1:
                    ok = False
                    break
        if ok and depth == 0:
            s2 = s2[1:-1].strip()
        else:
            break
    return s2

def _normalize_ws(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()

def _split_top_level_commas(s: str) -> List[str]:
    """Split by commas not nested in parentheses/brackets/braces or strings."""
    parts = []
    buf = []
    depth_par = depth_brk = depth_brc = 0
    in_str = False
    str_delim = ''
    esc = False
    i = 0
    while i < len(s):
        ch = s[i]
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == str_delim:
                in_str = False
            i += 1
            continue

        if ch in ("'", '"'):
            in_str = True
            str_delim = ch
            buf.append(ch)
            i += 1
            continue

        if ch == '(':
            depth_par += 1
        elif ch == ')':
            depth_par -= 1
        elif ch == '[':
            depth_brk += 1
        elif ch == ']':
            depth_brk -= 1
        elif ch == '{':
            depth_brc += 1
        elif ch == '}':
            depth_brc -= 1
        elif ch == ',' and depth_par == 0 and depth_brk == 0 and depth_brc == 0:
            parts.append(''.join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1

    if buf:
        parts.append(''.join(buf).strip())
    return parts

@dataclass
class Hit:
    kind: str                 # 'require' or 'assert'
    start_idx: int            # index of the 'r' in 'require' or 'a' in 'assert'
    end_idx: int              # index of the semicolon ending the statement (inclusive)
    args_text: str            # inside (...) exactly (without outer parentheses)
    full_stmt: str            # e.g., "require(x>0, \"msg\");"
    line: int                 # 1-based
    col: int                  # 1-based

def scan_require_assert(src: str) -> List[Hit]:
    """
    Scan Solidity source and extract all `require(...)` and `assert(...)` statements.
    Skips content inside strings and comments; balances parentheses to capture args.
    """
    hits: List[Hit] = []
    n = len(src)
    i = 0
    line = 1
    col = 1

    # Comment/string state
    in_line_comment = False
    in_block_comment = False
    in_str = False
    str_delim = ''
    esc = False

    # Keep line/col tracking; also need to be able to compute line/col for a given index.
    # We'll track line/col forward; also keep a mapping from absolute index to (line,col) at hits.
    def pos_tuple(idx: int) -> Tuple[int, int]:
        # Not efficient to recompute; but we track line/col as we go.
        # We'll actually capture the (line,col) when we detect a hit.
        return (line, col)

    while i < n:
        ch = src[i]
        nxt = src[i+1] if i+1 < n else ''

        # Handle line breaks for col/line tracking
        def advance(c):
            nonlocal line, col
            if c == '\n':
                line += 1
                col = 1
            else:
                col += 1

        if in_line_comment:
            advance(ch)
            i += 1
            if ch == '\n':
                in_line_comment = False
            continue

        if in_block_comment:
            # Look for closing */
            if ch == '*' and nxt == '/':
                advance(ch); i += 1
                advance(nxt); i += 1
                in_block_comment = False
                continue
            advance(ch); i += 1
            continue

        if in_str:
            # Inside a string literal
            if esc:
                esc = False
                advance(ch); i += 1
                continue
            if ch == '\\':
                esc = True
                advance(ch); i += 1
                continue
            advance(ch); i += 1
            if ch == str_delim:
                in_str = False
            continue

        # Not in comment/string: maybe starting a comment?
        if ch == '/' and nxt == '/':
            # line comment
            advance(ch); i += 1
            advance(nxt); i += 1
            in_line_comment = True
            continue
        if ch == '/' and nxt == '*':
            # block comment
            advance(ch); i += 1
            advance(nxt); i += 1
            in_block_comment = True
            continue

        # Not in comment/string: maybe starting a string?
        if ch in ("'", '"'):
            in_str = True
            str_delim = ch
            advance(ch); i += 1
            continue

        # Check for 'require' or 'assert' tokens here
        keyword = None
        if ch == 'r' and src[i:i+7] == 'require' and (i == 0 or not _is_ident_char(src[i-1])):
            after = i + 7
            keyword = 'require'
        elif ch == 'a' and src[i:i+6] == 'assert' and (i == 0 or not _is_ident_char(src[i-1])):
            after = i + 6
            keyword = 'assert'

        if keyword:
            # Skip whitespace then expect '('
            j = after
            while j < n and src[j].isspace():
                # update tracking for line/col while skipping
                advance(src[j]); j += 1

            if j < n and src[j] == '(':
                # Grab inside (...) with balanced parens
                start_par = j
                depth = 0
                k = j
                # local states for string/escape while scanning args
                in_str2 = False
                str_delim2 = ''
                esc2 = False
                while k < n:
                    c = src[k]
                    # string handling inside args
                    if in_str2:
                        if esc2:
                            esc2 = False
                        elif c == '\\':
                            esc2 = True
                        elif c == str_delim2:
                            in_str2 = False
                        k += 1
                        continue
                    if c in ("'", '"'):
                        in_str2 = True
                        str_delim2 = c
                        k += 1
                        continue

                    if c == '(':
                        depth += 1
                    elif c == ')':
                        depth -= 1
                        if depth == 0:
                            # args from (start_par+1) .. (k-1)
                            args_text = src[start_par+1:k]
                            # find the semicolon that ends the statement (skip ws/comments)
                            m = k + 1
                            # skip whitespace/comments to semicolon
                            # (we assume typical formatting; semicolon should appear soon)
                            # We'll just move forward until first ';'
                            while m < n and src[m] != ';':
                                m += 1
                            if m < n and src[m] == ';':
                                full_stmt = src[i:m+1]
                                hit_line, hit_col = line, col  # position at i
                                hits.append(Hit(keyword, i, m, args_text, full_stmt, hit_line, hit_col))
                                # advance positions to m+1
                                # But we are tracking line/col as we go; for simplicity we will fast-forward and recompute line/col by counting substring.
                                seg = src[i:m+1]
                                # recompute line/col relative moves
                                for c2 in seg:
                                    advance(c2)
                                i = m + 1
                                break
                    k += 1
                else:
                    # Unbalanced parens; just advance one char
                    advance(ch); i += 1
                    continue
                # handled by break above
                continue

        # default advance
        advance(ch); i += 1

    return hits


# --------------------------
# Dataset reading utilities
# --------------------------

DISL_COL_CANDIDATES = {
    "contract_address": ["contract_address", "address", "contract address"],
    "file_path": ["file_path", "filepath", "file path", "path"],
    "language": ["language", "lang"],
    "source_code": ["source_code", "source", "source code", "code"],
    "compiler_version": ["compiler_version", "compiler version", "solc_version"],
    "license_type": ["license_type", "license", "license type"],
    "contract_name": ["contract_name", "contract name", "name"],
}

def _normalize_key(k: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', k.lower()).strip()

def _pick_col(record: Dict, key: str) -> Optional[str]:
    wanted = DISL_COL_CANDIDATES[key]
    norm_map = { _normalize_key(k): k for k in record.keys() }
    for cand in wanted:
        nk = _normalize_key(cand)
        if nk in norm_map:
            return record[norm_map[nk]]
    return None

def _sha1_text(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8', errors='ignore')).hexdigest()

def _first_non_none(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


# --------------------------
# Parquet incremental writers
# --------------------------

class ParquetMultiWriter:
    def __init__(self, out_path_combined: str, out_path_requires: str, out_path_asserts: str):
        self.paths = {
            "combined": out_path_combined,
            "require": out_path_requires,
            "assert": out_path_asserts,
        }
        self.writers = {k: None for k in self.paths.keys()}
        self.schema = None  # decided on first write

    def _ensure_writer(self, kind: str, table: pa.Table):
        if self.writers[kind] is None:
            os.makedirs(os.path.dirname(self.paths[kind]), exist_ok=True)
            self.writers[kind] = pq.ParquetWriter(self.paths[kind], table.schema, use_dictionary=True, compression='snappy')

    def write_rows(self, rows: List[Dict]):
        if not rows:
            return
        table = pa.Table.from_pandas(pd.DataFrame(rows), preserve_index=False)
        # combined
        self._ensure_writer("combined", table)
        self.writers["combined"].write_table(table)
        # split by kind
        df = table.to_pandas()
        req_df = df[df["statement_kind"] == "require"]
        if not req_df.empty:
            req_table = pa.Table.from_pandas(req_df, preserve_index=False)
            self._ensure_writer("require", req_table)
            self.writers["require"].write_table(req_table)
        asr_df = df[df["statement_kind"] == "assert"]
        if not asr_df.empty:
            asr_table = pa.Table.from_pandas(asr_df, preserve_index=False)
            self._ensure_writer("assert", asr_table)
            self.writers["assert"].write_table(asr_table)

    def close(self):
        for w in self.writers.values():
            if w is not None:
                w.close()


# --------------------------
# Core processing
# --------------------------

def process_record(record: Dict, keep_empty: bool=False) -> List[Dict]:
    lang = _pick_col(record, "language")
    if (lang or "").strip().lower() != "solidity":
        return []
    src = _pick_col(record, "source_code")
    if not isinstance(src, str) or not src.strip():
        return []

    contract_address = _pick_col(record, "contract_address")
    file_path = _pick_col(record, "file_path")
    compiler_version = _pick_col(record, "compiler_version")
    license_type = _pick_col(record, "license_type")
    contract_name = _pick_col(record, "contract_name")

    file_sha1 = _sha1_text(src)

    hits = scan_require_assert(src)
    out_rows: List[Dict] = []

    for idx, h in enumerate(hits):
        # Split args into predicate/message (message only for require)
        args = _split_top_level_commas(h.args_text)
        predicate = args[0].strip() if args else ""
        message = None
        if h.kind == "require" and len(args) >= 2:
            # If there are more than 2 args, treat everything after the first comma as message blob
            message = ','.join(args[1:]).strip()

        normalized_pred = _normalize_ws(_strip_outer_parens(predicate))

        out_rows.append({
            "contract_address": contract_address,
            "file_path": file_path,
            "compiler_version": compiler_version,
            "license_type": license_type,
            "contract_name": contract_name,
            "statement_kind": h.kind,
            "statement_index": idx,
            "full_statement": h.full_stmt.strip(),
            "predicate": predicate,
            "message": message,
            "normalized_pred": normalized_pred,
            "line_start": h.line,
            "col_start": h.col,
            "file_sha1": file_sha1,
        })

    if keep_empty and not out_rows:
        out_rows.append({
            "contract_address": contract_address,
            "file_path": file_path,
            "compiler_version": compiler_version,
            "license_type": license_type,
            "contract_name": contract_name,
            "statement_kind": None,
            "statement_index": None,
            "full_statement": None,
            "predicate": None,
            "message": None,
            "normalized_pred": None,
            "line_start": None,
            "col_start": None,
            "file_sha1": file_sha1,
        })

    return out_rows


def iter_local_parquets(parquet_dir: str) -> Iterator[Dict]:
    import glob
    paths = sorted(glob.glob(os.path.join(parquet_dir, '**', '*.parquet'), recursive=True))
    for p in paths:
        try:
            df = pd.read_parquet(p, engine='pyarrow')
        except Exception:
            continue
        for _, row in df.iterrows():
            yield row.to_dict()


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--hf-dataset', type=str, help='HuggingFace dataset path, e.g., ASSERT-KTH/DISL')
    mode.add_argument('--local-parquet-dir', type=str, help='Directory with local parquet shards for the decomposed collection')
    ap.add_argument('--subset', type=str, default='decomposed', help='Dataset subset/config to use (default: decomposed)')
    ap.add_argument('--split', type=str, default=None, help='Split name if the dataset exposes one (often None or train)')
    ap.add_argument('--out-dir', type=str, required=True, help='Output directory for parquet files')
    ap.add_argument('--flush-every', type=int, default=50000, help='Flush rows to parquet every N statements (default: 50k)')
    ap.add_argument('--keep-empty', action='store_true', help='Also emit rows for files without any require/assert (mostly for diagnostics)')
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    out_combined = os.path.join(args.out_dir, 'disl_guards.parquet')
    out_requires = os.path.join(args.out_dir, 'disl_requires.parquet')
    out_asserts = os.path.join(args.out_dir, 'disl_asserts.parquet')
    writer = ParquetMultiWriter(out_combined, out_requires, out_asserts)

    rows_buffer: List[Dict] = []

    try:
        if args.hf_dataset:
            if load_dataset is None:
                raise RuntimeError("HuggingFace 'datasets' is not installed. Run: pip install datasets")
            # Attempt to load the HF dataset; some datasets expose a 'config' or 'name' for subsets like 'decomposed'
            # We'll try name=args.subset first; fall back if needed.
            hf_kwargs = {"path": args.hf_dataset, "name": args.subset}
            if args.split:
                hf_kwargs["split"] = args.split
            try:
                ds = load_dataset(**hf_kwargs)
                # If multiple splits returned, pick the requested one or first available
                if isinstance(ds, dict):
                    if args.split and args.split in ds:
                        ds = ds[args.split]
                    else:
                        split_key = sorted(ds.keys())[0]
                        ds = ds[split_key]
            except Exception:
                # try without 'name'
                hf_kwargs2 = {"path": args.hf_dataset}
                if args.split:
                    hf_kwargs2["split"] = args.split
                ds = load_dataset(**hf_kwargs2)
                # if multiple splits are returned, pick the requested or first
                if isinstance(ds, dict):
                    if args.split and args.split in ds:
                        ds = ds[args.split]
                    else:
                        split_key = sorted(ds.keys())[0]
                        ds = ds[split_key]

            # Iterate
            it = ds
            total = None
            prog = tqdm(it, desc="Scanning DISL") if _HAS_TQDM else it
            for rec in prog:
                out_rows = process_record(rec, keep_empty=args.keep_empty)
                if out_rows:
                    rows_buffer.extend(out_rows)
                    if len(rows_buffer) >= args.flush_every:
                        writer.write_rows(rows_buffer)
                        rows_buffer.clear()

        else:
            # Local parquet mode
            it = iter_local_parquets(args.local_parquet_dir)
            prog = tqdm(it, desc="Scanning local DISL parquets") if _HAS_TQDM else it
            for rec in prog:
                out_rows = process_record(rec, keep_empty=args.keep_empty)
                if out_rows:
                    rows_buffer.extend(out_rows)
                    if len(rows_buffer) >= args.flush_every:
                        writer.write_rows(rows_buffer)
                        rows_buffer.clear()

        # Final flush
        if rows_buffer:
            writer.write_rows(rows_buffer)
            rows_buffer.clear()

    finally:
        writer.close()


if __name__ == '__main__':
    main()
