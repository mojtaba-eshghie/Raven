#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
revert_decoder.py
-----------------
Decode Solidity revert payloads into human-readable reasons.

Supports:
- Error(string)           -> selector 0x08c379a0
- Panic(uint256)          -> selector 0x4e487b71 (with code → name mapping)
- Custom errors (Solidity >= 0.8.4) using provided ABI(s) or metadata

Usage examples:
  python3 revert_decoder.py --data 0x08c379a0...              # decode Error(string)
  python3 revert_decoder.py --data 0x4e487b71...              # decode Panic(uint256)
  python3 revert_decoder.py --data 0x12345678... --abi MyContract.abi.json
  python3 revert_decoder.py --data @data_hexes.txt --abi-dir ./abis/
  python3 revert_decoder.py --data 0x... --metadata ./metadata.json

Note: For custom-error decoding and for decoding Error(string) conveniently,
      this script requires 'eth-abi' and 'eth-utils':
          pip install eth-abi eth-utils

Author: ChatGPT
License: MIT
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from eth_abi import decode as abi_decode
except Exception:  # pragma: no cover - allow running without deps for --help
    abi_decode = None  # type: ignore

try:
    from eth_utils import keccak, to_checksum_address
except Exception:  # pragma: no cover
    keccak = None  # type: ignore
    def to_checksum_address(x: str) -> str:  # fallback noop
        return x

# --- Constants ---------------------------------------------------------------

ERROR_SELECTOR = "0x08c379a0"   # Error(string)
PANIC_SELECTOR = "0x4e487b71"   # Panic(uint256)

# From Solidity 0.8.0 release notes
PANIC_CODES: Dict[int, str] = {
    0x01: "assert(false) or internal error",
    0x11: "arithmetic overflow/underflow",
    0x12: "division or modulo by zero",
    0x21: "invalid enum conversion",
    0x22: "incorrectly encoded storage byte array",
    0x31: "pop on empty array",
    0x32: "array/bytesN/slice out-of-bounds",
    0x41: "memory allocation overflow",
    0x51: "call to uninitialized internal function",
}

# --- Helpers -----------------------------------------------------------------

def _strip_0x(data: str) -> str:
    return data[2:] if data.startswith("0x") else data

def _is_hex(data: str) -> bool:
    try:
        int(_strip_0x(data) or "0", 16)
        return True
    except Exception:
        return False

def _hex_to_bytes(data: str) -> bytes:
    return bytes.fromhex(_strip_0x(data))

def _bytes_to_hex(b: bytes) -> str:
    return "0x" + b.hex()

def _chunk(data_hex: str, start_bytes: int, length_bytes: int) -> str:
    h = _strip_0x(data_hex)
    start = start_bytes * 2
    end = start + length_bytes * 2
    return "0x" + h[start:end]

def first4(data_hex: str) -> str:
    h = _strip_0x(data_hex).ljust(8, "0")
    return "0x" + h[:8]

def _canonical_tuple_type(components: List[Dict[str, Any]]) -> str:
    # Build canonical type for a tuple, recursively
    inner = ",".join(_canonical_type(c) for c in components)
    return f"({inner})"

def _canonical_type(param: Dict[str, Any]) -> str:
    t = param.get("type", "")
    if t.startswith("tuple"):
        # retain any array suffix, e.g., "tuple[2][]" → "({inner})[2][]"
        suffix = t[len("tuple"):]
        comp = param.get("components", [])
        return _canonical_tuple_type(comp) + suffix
    return t

def _encode_error_signature(err_abi: Dict[str, Any]) -> str:
    """
    Given an error ABI item, return its canonical signature string:
      Name(Type1,Type2,...)
    """
    name = err_abi.get("name", "")
    inputs = err_abi.get("inputs", [])
    type_list = ",".join(_canonical_type(p) for p in inputs)
    return f"{name}({type_list})"

def _selector(sig: str) -> str:
    if keccak is None:
        raise RuntimeError("eth-utils is required to compute selectors. pip install eth-utils")
    return "0x" + keccak(text=sig)[:4].hex()

def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _iter_files_with_ext(root: str, *exts: str) -> Iterable[str]:
    exts = tuple(e.lower() for e in exts)
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith(exts):
                yield os.path.join(dirpath, fn)

# --- ABI index for errors ----------------------------------------------------

@dataclass
class ErrorSpec:
    selector: str
    signature: str
    abi: Dict[str, Any]
    source: str  # where we got it from (filename or label)

class ErrorIndex:
    def __init__(self):
        self.by_selector: Dict[str, ErrorSpec] = {}

    def add_abi(self, abi: List[Dict[str, Any]], source: str = "abi") -> None:
        for item in abi:
            if item.get("type") == "error":
                sig = _encode_error_signature(item)
                sel = _selector(sig)
                self.by_selector[sel] = ErrorSpec(selector=sel, signature=sig, abi=item, source=source)

    def add_metadata(self, metadata: Dict[str, Any], source: str = "metadata") -> None:
        # standard solc metadata: output.abi
        abi = metadata.get("output", {}).get("abi", [])
        if isinstance(abi, list):
            self.add_abi(abi, source=source)

    def match(self, selector: str) -> Optional[ErrorSpec]:
        return self.by_selector.get(selector.lower()) or self.by_selector.get(selector.upper()) or self.by_selector.get(selector)

# --- Decoding ----------------------------------------------------------------

@dataclass
class DecodedRevert:
    kind: str                 # "empty" | "error" | "panic" | "custom" | "unknown"
    selector: Optional[str]   # 4-byte selector as hex, if present
    summary: str              # one-line human string
    details: Dict[str, Any]   # structured info

def decode_error_string(data_hex: str) -> DecodedRevert:
    if abi_decode is None:
        raise RuntimeError("eth-abi is required. pip install eth-abi")
    payload = _hex_to_bytes(data_hex)[4:]  # strip selector
    # Error(string) is encoded as ABI-encoded single string argument
    try:
        (msg,) = abi_decode(["string"], payload)
    except Exception as e:
        return DecodedRevert(
            kind="error",
            selector=ERROR_SELECTOR,
            summary=f"Error(string) – failed to decode payload: {e}",
            details={"raw": data_hex},
        )
    return DecodedRevert(
        kind="error",
        selector=ERROR_SELECTOR,
        summary=f'Error(string): "{msg}"',
        details={"message": msg},
    )

def decode_panic(data_hex: str) -> DecodedRevert:
    if abi_decode is None:
        raise RuntimeError("eth-abi is required. pip install eth-abi")
    payload = _hex_to_bytes(data_hex)[4:]  # strip selector
    try:
        (code,) = abi_decode(["uint256"], payload)
        code_int = int(code)
    except Exception as e:
        return DecodedRevert(
            kind="panic",
            selector=PANIC_SELECTOR,
            summary=f"Panic(uint256) – failed to decode code: {e}",
            details={"raw": data_hex},
        )
    name = PANIC_CODES.get(code_int, "unknown panic code")
    return DecodedRevert(
        kind="panic",
        selector=PANIC_SELECTOR,
        summary=f"Panic({hex(code_int)}): {name}",
        details={"code": code_int, "code_hex": hex(code_int), "meaning": name},
    )

def decode_custom_error(data_hex: str, err_index: ErrorIndex) -> DecodedRevert:
    if abi_decode is None:
        raise RuntimeError("eth-abi is required. pip install eth-abi")
    sel = first4(data_hex)
    spec = err_index.match(sel)
    if not spec:
        return DecodedRevert(
            kind="unknown",
            selector=sel,
            summary=f"Unknown custom error (selector {sel})",
            details={"selector": sel, "raw": data_hex},
        )
    payload = _hex_to_bytes(data_hex)[4:]
    # Build the canonical type list for decoding
    types = [_canonical_type(inp) for inp in spec.abi.get("inputs", [])]
    try:
        values = list(abi_decode(types, payload)) if types else []
    except Exception as e:
        return DecodedRevert(
            kind="custom",
            selector=sel,
            summary=f"{spec.signature} – failed to decode args: {e}",
            details={"signature": spec.signature, "inputs": spec.abi.get("inputs", []), "raw": data_hex},
        )
    # Human-friendly key:value mapping
    named = {}
    for i, (inp, val) in enumerate(zip(spec.abi.get("inputs", []), values)):
        key = inp.get("name") or f"arg{i}"
        # Pretty address formatting if possible
        if isinstance(val, bytes) and len(val) == 20:
            try:
                val_fmt = to_checksum_address(_bytes_to_hex(val))
            except Exception:
                val_fmt = _bytes_to_hex(val)
            named[key] = val_fmt
        else:
            named[key] = val
    return DecodedRevert(
        kind="custom",
        selector=sel,
        summary=f"{spec.signature}({', '.join(f'{k}={v}' for k, v in named.items())})",
        details={
            "signature": spec.signature,
            "inputs": spec.abi.get("inputs", []),
            "args": named,
            "source": spec.source,
        },
    )

def decode_revert(data_hex: str, error_index: Optional[ErrorIndex] = None) -> DecodedRevert:
    """
    Master decoder. Accepts hex revert data (with or without 0x).
    If custom-error ABI is provided via error_index, will decode custom errors.
    """
    if not data_hex or _strip_0x(data_hex) == "":
        return DecodedRevert(kind="empty", selector=None, summary="Empty revert data", details={})
    if not _is_hex(data_hex):
        raise ValueError("Input is not valid hex.")
    sel = first4(data_hex)
    if sel.lower() == ERROR_SELECTOR:
        return decode_error_string(data_hex)
    if sel.lower() == PANIC_SELECTOR:
        return decode_panic(data_hex)
    if error_index is not None:
        return decode_custom_error(data_hex, error_index)
    return DecodedRevert(kind="unknown", selector=sel, summary=f"Unknown selector {sel}", details={"raw": data_hex})

# --- Loading ABIs / metadata -------------------------------------------------

def build_error_index(
    abi_files: Optional[List[str]] = None,
    abi_dir: Optional[str] = None,
    metadata_files: Optional[List[str]] = None,
) -> ErrorIndex:
    idx = ErrorIndex()
    if abi_files:
        for path in abi_files:
            try:
                abi = _load_json(path)
                if isinstance(abi, dict) and "abi" in abi:
                    abi = abi["abi"]
                if not isinstance(abi, list):
                    raise ValueError(f"ABI at {path} is not a list")
                idx.add_abi(abi, source=os.path.basename(path))
            except Exception as e:
                print(f"[warn] failed to load ABI {path}: {e}", file=sys.stderr)
    if abi_dir and os.path.isdir(abi_dir):
        for path in _iter_files_with_ext(abi_dir, ".json", ".abi"):
            try:
                abi = _load_json(path)
                if isinstance(abi, dict) and "abi" in abi:
                    abi = abi["abi"]
                if isinstance(abi, list):
                    idx.add_abi(abi, source=os.path.relpath(path, abi_dir))
            except Exception as e:
                print(f"[warn] failed to load ABI {path}: {e}", file=sys.stderr)
    if metadata_files:
        for path in metadata_files:
            try:
                md = _load_json(path)
                idx.add_metadata(md, source=os.path.basename(path))
            except Exception as e:
                print(f"[warn] failed to load metadata {path}: {e}", file=sys.stderr)
    return idx

# --- CLI ---------------------------------------------------------------------

def _read_data_arg(arg: str) -> List[str]:
    """
    If arg starts with '@', treat as a file of hex strings (one per line).
    Otherwise, return [arg].
    """
    if arg.startswith("@"):
        path = arg[1:]
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        return lines
    return [arg]

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Decode Solidity revert data into human-readable reasons.")
    p.add_argument("--data", required=True,
                   help="Revert data hex (e.g., 0x08c379a0...) or @file.txt with one hex per line.")
    p.add_argument("--abi", nargs="*", help="Path(s) to ABI JSON files (either pure ABI array or {\"abi\": [...]}).")
    p.add_argument("--abi-dir", help="Directory to scan recursively for ABI JSON files.")
    p.add_argument("--metadata", nargs="*", help="Path(s) to solc metadata.json (containing output.abi)")
    args = p.parse_args(argv)

    try:
        datas = _read_data_arg(args.data)
    except Exception as e:
        print(f"error: failed to read --data: {e}", file=sys.stderr)
        return 2

    idx: Optional[ErrorIndex] = None
    if any([args.abi, args.abi_dir, args.metadata]):
        idx = build_error_index(args.abi, args.abi_dir, args.metadata)
        print(f"[info] Loaded {len(idx.by_selector)} custom error signatures.")

    for d in datas:
        try:
            dec = decode_revert(d, idx)
        except Exception as e:
            print(json.dumps({"input": d, "error": str(e)}, ensure_ascii=False))
            continue
        out = {
            "input": d,
            "kind": dec.kind,
            "selector": dec.selector,
            "summary": dec.summary,
            "details": dec.details,
        }
        print(json.dumps(out, ensure_ascii=False))

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
