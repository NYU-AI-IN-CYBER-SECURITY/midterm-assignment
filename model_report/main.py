#!/usr/bin/env python3
"""
main.py -- the runner.  Students should not need to edit this file.

It wires the three pieces together:

    csv_reader.py  -> gives one flow at a time
    prompter.py    -> turns that flow into the prompt (THIS is what you edit)
    metrics.py     -> parses the answer and computes the scores

and writes a single CSV report: one line per flow, then the score summary.

Example
-------
    python main.py --model my_model.gguf \
                   --csv "UNSW_NB15_balanced_30k .csv" \
                   --rows 50

    python main.py -m my_model.gguf -c data.csv -r 200 --shuffle --out run2.csv

If --rows is larger than the number of rows in the CSV, every row is used.
"""

import argparse
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import csv_reader
import metrics
import prompter
import report as report_mod


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def load_model(gguf_path: Path, n_ctx: int, n_gpu_layers: int):
    """Load the GGUF through llama-cpp-python."""
    try:
        from llama_cpp import Llama
    except ImportError:
        sys.exit("llama-cpp-python is not installed.  Run:  pip install llama-cpp-python")

    size_gb = gguf_path.stat().st_size / 1e9
    print(f"[main] loading model: {gguf_path.name} ({size_gb:.2f} GB) ...", flush=True)
    t0 = time.perf_counter()
    try:
        llm = Llama(
            model_path   = str(gguf_path),
            n_ctx        = n_ctx,
            n_gpu_layers = n_gpu_layers,
            verbose      = False,
        )
    except OSError as exc:
        # A llama-cpp-python wheel built for the wrong CPU or GPU imports fine
        # and then dies here, inside the C++ library, with a bare OS error.
        sys.exit(bad_binary_message(exc))
    print(f"[main] model loaded ({time.perf_counter() - t0:.1f}s)", flush=True)
    return llm


def bad_binary_message(exc: OSError) -> str:
    """Translate a crash inside llama.cpp into something actionable."""
    code = getattr(exc, "winerror", None) or 0
    known = {
        0xC000001D: "illegal instruction -- the installed llama-cpp-python was "
                    "built for CPU\n        features this machine does not have "
                    "(common with the CUDA wheels)",
        0xC0000005: "access violation -- the binary and your GPU driver disagree",
        0xC0000135: "a required DLL is missing, usually the CUDA runtime",
    }
    meaning = known.get(code & 0xFFFFFFFF, str(exc))
    return (f"\n[main] llama-cpp-python crashed while starting the model.\n"
            f"        {meaning}\n\n"
            f"        Reinstall the plain CPU build, which works everywhere:\n"
            f"            python install.py --cpu\n"
            f"        (The CPU build is fine for this assignment -- the model is "
            f"small.)")


def ask_model(llm, prompt: str, max_new_tokens: int, temperature: float) -> str:
    """One flow in, one raw answer out.  Uses the GGUF's own chat template."""
    resp = llm.create_chat_completion(
        messages    = [{"role": "user", "content": prompt}],
        max_tokens  = max_new_tokens,
        temperature = temperature,
    )
    return resp["choices"][0]["message"]["content"].strip()


def make_prompt(fields: dict, index: int) -> str:
    """Call the student's prompter, and explain clearly if it blows up."""
    try:
        prompt = prompter.build_prompt(fields)
    except KeyError as exc:
        sys.exit(f"\n[main] prompter.build_body() asked for column {exc}, which "
                 f"this CSV does not have.\n"
                 f"        Available columns: {', '.join(fields)}")
    except Exception as exc:                      # noqa: BLE001 - student code
        sys.exit(f"\n[main] prompter.build_prompt() raised {type(exc).__name__}: "
                 f"{exc}\n        (while building the prompt for row {index})")
    if not isinstance(prompt, str):
        sys.exit(f"\n[main] prompter.build_prompt() returned "
                 f"{type(prompt).__name__}, not a string.")
    return prompt


def warmup(llm, max_new_tokens: int, temperature: float):
    """One throwaway inference so the first real row isn't a timing outlier.

    Uses a dummy row carrying every column, so a build_body() that reads an
    unusual field still works here."""
    print("[main] warming up ...", end=" ", flush=True)
    t0 = time.perf_counter()
    ask_model(llm, make_prompt(csv_reader.dummy_fields(), 0),
              max_new_tokens, temperature)
    print(f"done ({time.perf_counter() - t0:.2f}s)", flush=True)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_summary(name: str, m: dict):
    print(f"\n{name}: acc={m['accuracy']}  P={m['macro_precision']}  "
          f"R={m['macro_recall']}  F1={m['macro_f1']}  (n={m['n']})")
    print(f"  {'class':<16}{'support':>8}{'correct':>9}{'prec':>8}{'rec':>8}{'f1':>8}")
    for cls, s in sorted(m["per_class"].items()):
        print(f"  {cls:<16}{s['support']:>8}{s['correct']:>9}"
              f"{s['precision']:>8}{s['recall']:>8}{s['f1']:>8}")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(args) -> int:
    available = csv_reader.count_rows(args.csv)
    if available == 0:
        sys.exit(f"[main] {args.csv} has no data rows")
    if args.rows is not None and args.rows < 0:
        sys.exit(f"[main] --rows must be 0 or more (got {args.rows})")

    # No --rows, or --rows 0, means "the whole file".  Otherwise take what was
    # asked for, capped at what the CSV actually holds.
    requested = args.rows or None
    n_rows = available if requested is None else min(requested, available)
    if requested is not None and requested > available:
        print(f"[main] asked for {requested} rows, CSV only has {available} -- using {available}",
              flush=True)

    print(f"[main] csv     {args.csv}")
    print(f"[main] rows    {n_rows} of {available}"
          f"{'  (shuffled, seed=%d)' % args.seed if args.shuffle else ''}")

    # Check the student's prompter before spending a minute loading the model.
    preview = make_prompt(csv_reader.dummy_fields(), 0)
    if not preview.strip():
        print("\n[main] WARNING: prompter.py builds an EMPTY prompt -- the model "
              "will be sent nothing\n"
              "        but whitespace and will score zero.  Fill in "
              "PROMPT_HEADER and build_body().\n", flush=True)

    llm = load_model(args.model, args.n_ctx, args.n_gpu_layers)
    if not args.no_warmup:
        warmup(llm, args.max_new_tokens, args.temperature)

    yt_bin, yp_bin = [], []
    yt_mul, yp_mul = [], []
    parse_failures = 0
    started = datetime.now()
    t_run = time.perf_counter()

    report = report_mod.Report(args.out)
    print(f"[main] report  {report.path}", flush=True)

    samples = csv_reader.iter_samples(args.csv, n_rows, args.shuffle, args.seed)
    for s in samples:
        prompt = make_prompt(s.fields, s.index)

        t0 = time.perf_counter()
        raw = ask_model(llm, prompt, args.max_new_tokens, args.temperature)
        elapsed = time.perf_counter() - t0

        pred_label, pred_type, parsed_ok = metrics.parse_prediction(raw)
        if not parsed_ok:
            parse_failures += 1

        # A row is dropped from a task only when its GROUND TRUTH is
        # malformed, so bad CSV rows can't inject a fake class.  A bad
        # PREDICTION always counts, and always counts as wrong.
        if s.truth_label != "unknown":
            yt_bin.append(s.truth_label)
            yp_bin.append(pred_label)
        if s.truth_type != "unknown":
            yt_mul.append(s.truth_type)
            yp_mul.append(pred_type)

        report.add(s.index, s.truth_label, pred_label,
                   s.truth_type, pred_type, parsed_ok, elapsed,
                   prompt, raw)

        print(f"[main] {s.index:>5}/{n_rows}  {elapsed:>6.2f}s  "
              f"truth=({s.truth_label:<7},{s.truth_type:<14})  "
              f"pred=({pred_label:<12},{pred_type:<14})  "
              f"bin={'OK' if pred_label == s.truth_label else '--'}  "
              f"mul={'OK' if pred_type == s.truth_type else '--'}",
              flush=True)

    binary = metrics.score(yt_bin, yp_bin)
    multiclass = metrics.score(yt_mul, yp_mul)
    total_sec = time.perf_counter() - t_run

    out_path = report.write(binary, multiclass, parse_failures, {
        "model":        args.model.name,
        "csv":          Path(args.csv).name,
        "rows_run":     n_rows,
        "rows_in_csv":  available,
        "shuffle":      args.shuffle,
        "seed":         args.seed if args.shuffle else "",
        "temperature":  args.temperature,
        "max_new_tokens": args.max_new_tokens,
        "started_at":   started.isoformat(timespec="seconds"),
        "total_sec":    round(total_sec, 1),
        "sec_per_row":  round(total_sec / n_rows, 2) if n_rows else 0,
    })

    print_summary("BINARY     (normal vs attack)", binary)
    print_summary("MULTICLASS (attack type)", multiclass)
    print(f"\n[main] parse failures: {parse_failures}/{n_rows}")
    print(f"[main] report written: {out_path}")
    print( "[main]   Summary tab = scores | Results tab = per-row | "
           "Prompts tab = what the model saw and said")
    return 0


def parse_args():
    p = argparse.ArgumentParser(
        description="Run the prompt in prompter.py over a UNSW-NB15 CSV and score it.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("-m", "--model", type=Path, required=True,
                   help="path to the .gguf model file")
    p.add_argument("-c", "--csv", type=Path, required=True,
                   help="path to the labelled CSV")
    p.add_argument("-r", "--rows", type=int, default=None,
                   help="how many rows to run, capped at the CSV's row count "
                        "(default: every row; 0 also means every row)")
    p.add_argument("-o", "--out", type=Path, default=Path("results.xlsx"),
                   help="report to write (.xlsx)")
    p.add_argument("--shuffle", action="store_true",
                   help="shuffle the CSV before taking rows (default: top-to-bottom)")
    p.add_argument("--seed", type=int, default=42,
                   help="shuffle seed (only used with --shuffle)")
    p.add_argument("--max-new-tokens", type=int, default=64,
                   help="generation cap per row")
    p.add_argument("--temperature", type=float, default=0.0,
                   help="0.0 = deterministic")
    p.add_argument("--n-ctx", type=int, default=4096,
                   help="context window")
    p.add_argument("--n-gpu-layers", type=int, default=0,
                   help="layers to offload to GPU (-1 = all)")
    p.add_argument("--no-warmup", action="store_true",
                   help="skip the throwaway warm-up inference")

    args = p.parse_args()
    if args.rows is not None and args.rows <= 0:
        args.rows = None            # 0 / negative means "the whole file"
    if not args.model.exists():
        p.error(f"model not found: {args.model}")
    if not args.csv.exists():
        p.error(f"csv not found: {args.csv}")
    return args


if __name__ == "__main__":
    try:
        sys.exit(run(parse_args()))
    except KeyboardInterrupt:
        print("\n[main] interrupted -- partial report kept", flush=True)
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
