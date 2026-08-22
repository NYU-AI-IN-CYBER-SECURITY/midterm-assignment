#!/usr/bin/env python3
"""
csv_reader.py -- reads the test set CSV and hands back ONE flow at a time.

Single responsibility: turn a CSV row into
    ({column: value} dict of features, true label, true attack type)
It knows nothing about prompts, models, or scoring.  What to *do* with those
fields -- which to show the model, in what wording -- is prompter.py's job (you built this!).

NOTE: this module is deliberately NOT named csv.py -- a local csv.py would
shadow Python's built-in csv module and break the import below. Fun little Application Security fact for you!
"""

import csv
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# Feature columns shown to the model, IN ORDER.  Identity columns (id, srcip,
# sport, dstip, dsport) and time columns (Stime, Ltime) are dropped as noise;
# attack_cat / label are the targets and must never leak in.  Only these
# columns are ever emitted.
#
# Names follow the cleaned UNSW-NB15 header (sload, spkts, smean, ...).  The
# older raw-schema spellings (Sload, Spkts, smeansz, ...) are accepted too via
# COLUMN_ALIASES below, and header lookup is case-insensitive, so either CSV
# flavour works.  A column the CSV doesn't have is simply skipped.
KEPT_COLUMNS = [
    "proto", "state", "service", "dur", "rate",
    "spkts", "dpkts", "sbytes", "dbytes", "sttl", "dttl", "sload", "dload",
    "sloss", "dloss", "sinpkt", "dinpkt", "sjit", "djit",
    "swin", "dwin", "stcpb", "dtcpb", "tcprtt", "synack", "ackdat",
    "smean", "dmean", "trans_depth", "response_body_len",
    "is_sm_ips_ports", "ct_state_ttl", "ct_flw_http_mthd", "is_ftp_login",
    "ct_ftp_cmd", "ct_srv_src", "ct_srv_dst", "ct_dst_ltm", "ct_src_ltm",
    "ct_src_dport_ltm", "ct_dst_sport_ltm", "ct_dst_src_ltm",
]

# kept-column name -> other header spellings that mean the same feature.
# Matching is case-insensitive, so only genuinely different words are listed.
COLUMN_ALIASES = {
    "spkts":             ["Spkts"],
    "dpkts":             ["Dpkts"],
    "sload":             ["Sload"],
    "dload":             ["Dload"],
    "sinpkt":            ["Sintpkt"],
    "dinpkt":            ["Dintpkt"],
    "sjit":              ["Sjit"],
    "djit":              ["Djit"],
    "smean":             ["smeansz"],
    "dmean":             ["dmeansz"],
    "response_body_len": ["res_bdy_len"],
}

# Nominal / free-text columns are emitted RAW -- no lowercasing, no remap
# (state=INT, service=-).  A blank passes through empty ("service="), unlike
# blank numerics, which render "missing".
STRING_COLS = {"proto", "state", "service"}

# Float columns render with "%g" (e.g. 9e-06, 8.88889e+07, 0.009).  Every other
# numeric column renders as a plain integer, so large counters (e.g. stcpb) are
# NOT forced into scientific notation.
FLOAT_COLS = {"dur", "rate", "sload", "dload", "sjit", "djit",
              "sinpkt", "dinpkt", "tcprtt", "synack", "ackdat"}

# The dataset ships malformed attack categories (" Worm ", "worm", "backdoor";
# stray whitespace/case/singular).  Canonicalize the ground truth through this
# map so it agrees with what the model is asked to emit.  This cleans noisy
# TRUTH only -- model output is scored as-is, with no fallback.
CATEGORY_CANON = {
    "normal": "normal",
    "fuzzers": "fuzzers", "fuzzer": "fuzzers",
    "analysis": "analysis",
    "backdoor": "backdoor", "backdoors": "backdoor",
    "dos": "dos",
    "exploits": "exploits", "exploit": "exploits",
    "generic": "generic",
    "reconnaissance": "reconnaissance", "recon": "reconnaissance",
    "shellcode": "shellcode", "shellcodes": "shellcode", "shell code": "shellcode",
    "worms": "worms", "worm": "worms",
}

# Canonical (lowercase) category -> the Title-case spelling the model must EMIT.
SCHEMA_TITLE = {
    "normal": "Normal", "fuzzers": "Fuzzers", "analysis": "Analysis",
    "backdoor": "Backdoor", "dos": "DoS", "exploits": "Exploits",
    "generic": "Generic", "reconnaissance": "Reconnaissance",
    "shellcode": "Shellcode", "worms": "Worms",
}


@dataclass
class Sample:
    """One flow: the feature values, plus the two ground-truth answers.

    `fields` is an ordered {column: value} dict -- every value already
    formatted as a string, in KEPT_COLUMNS order.  It is handed straight to
    prompter.build_prompt(); deciding which of those fields to show the model,
    and how to word them, is the assignment.
    """
    index: int              # 1-based position in the run
    fields: dict            # {column: value}, both strings
    truth_label: str        # "normal" | "attack" | "unknown"
    truth_type: str         # canonical lowercase category, or "unknown"


def canon_category(raw: str):
    """Malformed / variant attack_cat -> canonical lowercase type, or None."""
    return CATEGORY_CANON.get((raw or "").strip().lower())


def _lookup(row: dict, col: str):
    """Fetch `col` from a row whose header spelling may differ.

    Tries the exact name, then a case-insensitive match, then the aliases in
    COLUMN_ALIASES (also case-insensitively).  Returns None when the CSV simply
    doesn't carry that column.
    """
    if col in row:
        return row[col]
    lower = {k.lower(): v for k, v in row.items()}
    for candidate in [col] + COLUMN_ALIASES.get(col, []):
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    return None


def row_fields(row: dict) -> dict:
    """Turn one raw CSV row into the ordered {column: value} dict the prompt
    is built from.

      * only KEPT_COLUMNS appear, in order, under their kept-column name (so
        the same field names work whichever CSV flavour is loaded)
      * STRING_COLS pass through RAW -- a blank stays blank ("service": "")
      * a blank / "nan" numeric becomes the string "missing"
      * FLOAT_COLS render with "%g"; every other numeric renders as a plain int
      * every value is a str, so it drops straight into an f-string
    """
    fields = {}
    for col in KEPT_COLUMNS:
        raw = _lookup(row, col)
        if raw is None:
            continue                      # this CSV doesn't have the column
        s = str(raw).strip()
        if col in STRING_COLS:
            val = s
        elif s == "" or s.lower() == "nan":
            val = "missing"
        elif col in FLOAT_COLS:
            try:
                val = f"{float(s):g}"
            except ValueError:
                val = s
        else:
            try:
                val = str(int(float(s)))
            except ValueError:
                val = s
        fields[col] = val
    return fields


def dummy_fields() -> dict:
    """A fake row carrying every kept column -- used for the warm-up pass so a
    student's build_body() never trips over a missing key before the run
    starts."""
    return {col: ("-" if col in STRING_COLS else "0") for col in KEPT_COLUMNS}


def truth_from_row(row: dict) -> tuple[str, str]:
    """Pull both ground-truth answers out of the row.

      label = 0  -> ("normal", "normal")
      label = 1  -> ("attack", canonical attack category)

    The target columns are found case-insensitively ("label" / "Label",
    "attack_cat" / " attack_cat").  An attack row whose category is blank or
    unrecognized gets "unknown" and is dropped from the affected task rather
    than being silently relabeled.
    """
    lower = {k.lower(): v for k, v in row.items()}
    try:
        is_attack = int(float(lower["label"])) == 1
    except (KeyError, ValueError, TypeError):
        return "unknown", "unknown"
    if not is_attack:
        return "normal", "normal"
    cat = canon_category(lower.get("attack_cat", ""))
    return "attack", (cat if cat is not None else "unknown")


def _clean(row: dict) -> dict:
    """UNSW-NB15 CSVs often ship whitespace in header names (" attack_cat").
    Strip every key and value so lookups are reliable."""
    return {(k or "").strip(): (v or "").strip() for k, v in row.items()}


def count_rows(path: Path) -> int:
    """Number of data rows in the CSV (header excluded)."""
    with Path(path).open(encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def iter_samples(path: Path, limit: int | None = None,
                 shuffle: bool = False, seed: int = 42) -> Iterator[Sample]:
    """Yield Samples one at a time.

    shuffle=False (default): stream top-to-bottom and stop after `limit` rows.
    shuffle=True:            read the whole file, shuffle deterministically with
                             `seed`, then take the first `limit` rows.
    `limit=None` means every row in the file.  Asking for more rows than the
    file has simply yields everything.
    """
    path = Path(path)

    if shuffle:
        with path.open(encoding="utf-8", newline="") as f:
            raw_rows = [_clean(r) for r in csv.DictReader(f)]
        if not raw_rows:
            raise ValueError(f"CSV {path} has no data rows")
        random.Random(seed).shuffle(raw_rows)
        if limit is not None:
            raw_rows = raw_rows[:limit]
        for i, row in enumerate(raw_rows, start=1):
            tl, tt = truth_from_row(row)
            yield Sample(i, row_fields(row), tl, tt)
        return

    emitted = 0
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if limit is not None and emitted >= limit:
                break
            row = _clean(row)
            tl, tt = truth_from_row(row)
            emitted += 1
            yield Sample(emitted, row_fields(row), tl, tt)
    if emitted == 0:
        raise ValueError(f"CSV {path} has no data rows")
