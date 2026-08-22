#!/usr/bin/env python3
"""
metrics.py -- parses the model's answer and computes the scores.

Two jobs:
  1. parse_prediction()  turn one raw model output into (label, type)
  2. score()             turn lists of (truth, prediction) into numbers
"""

import json
from collections import defaultdict

# NO FALLBACK POLICY.
# A field that cannot be parsed from the model output is scored as a guaranteed
# MISS -- never remapped to a schema-valid guess, never rescued by aliases or a
# keyword scan.  PARSE_FAIL never equals any real truth label, so a silent or
# off-format model scores 0 instead of collecting lucky-guess accuracy.
PARSE_FAIL = "unparseable"


def parse_prediction(raw: str) -> tuple[str, str, bool]:
    """Strict, no-fallback parser: score whatever the model outputs, as-is.

    The model is instructed to return exactly one compact JSON object.  We parse
    that JSON and read its "label"/"type" fields verbatim -- stripped and
    lowercased only, so the schema's own casing ("DoS" -> "dos") still matches
    the canonical truth.  There is NO rescue: no alias remapping, no regex over
    malformed JSON, no free-text keyword scan, no code-fence stripping.

    Returns (label, type, parsed_ok).  parsed_ok is False when the output was
    not valid JSON with at least one usable field.
    """
    txt = (raw or "").strip()
    try:
        obj = json.loads(txt)
        if not isinstance(obj, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError, TypeError):
        return PARSE_FAIL, PARSE_FAIL, False

    label = str(obj.get("label", "")).strip().lower() or PARSE_FAIL
    typ = str(obj.get("type", "")).strip().lower() or PARSE_FAIL
    return label, typ, (label != PARSE_FAIL or typ != PARSE_FAIL)


def score(y_true: list[str], y_pred: list[str]) -> dict:
    """Confusion-matrix metrics: overall accuracy, macro averages, per class.

    Macro averages are taken over the classes that actually appear in the truth
    OR in the predictions, so junk predictions (including "unparseable") drag
    the macro score down instead of being ignored.
    """
    classes = sorted(set(y_true) | set(y_pred))
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    support = defaultdict(int)

    for yt, yp in zip(y_true, y_pred):
        support[yt] += 1
        if yt == yp:
            tp[yt] += 1
        else:
            fp[yp] += 1
            fn[yt] += 1

    per_class = {}
    precisions, recalls, f1s = [], [], []
    for c in classes:
        p = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0
        r = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        precisions.append(p)
        recalls.append(r)
        f1s.append(f1)
        per_class[c] = {
            "support":   support[c],
            "correct":   tp[c],
            "precision": round(p, 4),
            "recall":    round(r, 4),
            "f1":        round(f1, 4),
        }

    total = len(y_true) or 1
    n = len(classes) or 1
    return {
        "n":               len(y_true),
        "correct":         sum(1 for a, b in zip(y_true, y_pred) if a == b),
        "accuracy":        round(sum(1 for a, b in zip(y_true, y_pred) if a == b) / total, 4),
        "macro_precision": round(sum(precisions) / n, 4),
        "macro_recall":    round(sum(recalls) / n, 4),
        "macro_f1":        round(sum(f1s) / n, 4),
        "per_class":       per_class,
    }
