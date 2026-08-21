#!/usr/bin/env python3
"""
prompter.py -- THIS IS THE ONLY FILE YOU EDIT.

Everything else (main.py, csv_reader.py, metrics.py) is plumbing to help you test your model.
Your job is to build the message the model sees for ONE network flow, out of three pieces:

    PROMPT_HEADER   fixed text before the flow   (you write it)
    build_body(row) the flow itself              (you write it)
    PROMPT_FOOTER   fixed text after the flow    (you write it)

Run it with:

    python main.py -m LFM2.5-350M.Q4_K_M.gguf -c UNSW_NB15_balanced_30k.csv
    
Provide here any dataset you want for testing (it's recommended you do).
Just make sure it's formatted properly!

===============================================================================
WHAT YOU ARE GIVEN
===============================================================================
build_body() receives `row`: a plain Python dict of ONE flow, {column: value},
with every value already a string.  Nothing is pre-formatted into a prompt --
choosing what the model sees is the actual assignment.

    row["proto"]   -> "tcp"
    row["sttl"]    -> "31"
    row["dur"]     -> "0.121478"
    row["service"] -> "-"          (a dash means no service was identified)
    row["swin"]    -> "255"

A blank numeric arrives as the string "missing".  Columns are in the order
listed below, and a column your CSV doesn't carry is simply absent from the
dict -- so `row.get("rate", "")` is safer than `row["rate"]` if you're not sure.

===============================================================================
COLUMNS IN `row` (typically in this order)
===============================================================================
proto, state, service, dur, rate, spkts, dpkts, sbytes, dbytes, sttl, dttl,
sload, dload, sloss, dloss, sinpkt, dinpkt, sjit, djit, swin, dwin, stcpb,
dtcpb, tcprtt, synack, ackdat, smean, dmean, trans_depth, response_body_len,
is_sm_ips_ports, ct_state_ttl, ct_flw_http_mthd, is_ftp_login, ct_ftp_cmd,
ct_srv_src, ct_srv_dst, ct_dst_ltm, ct_src_ltm, ct_src_dport_ltm,
ct_dst_sport_ltm, ct_dst_src_ltm

Identity columns (id, srcip, sport, dstip, dsport) and time columns (Stime,
Ltime) are dropped as noise.  attack_cat and label are the ANSWERS and are
never in the dict.

===============================================================================
WHAT THE MODEL MUST OUTPUT
===============================================================================
Exactly ONE compact JSON object and nothing else -- no prose, no markdown
fences, no explanation:

    {"label": "attack", "type": "Exploits"}

  * "label" must be either  normal  or  attack
  * "type"  must be one of: Normal, Fuzzers, Analysis, Backdoor, DoS,
                            Exploits, Generic, Reconnaissance, Shellcode, Worms
                            
    (If label is "normal", type is "Normal".)
    
    Case doesn't matter,"DoS", "dos" and "DOS" all match, but the spelling
    does matters: "Backdoors" is NOT "Backdoor".

NO FALLBACK POLICY: if the output is not clean JSON, or a field is missing,
that field is scored as a guaranteed MISS.  A chatty or off-format model scores
zero. It is never rescued by keyword scanning or alias remapping.  So spend
real effort on forcing the format.

===============================================================================
HOW TO PUT A ROW VALUE INTO TEXT -- worked examples
===============================================================================
These are here to show you the mechanics.  They are NOT a suggested answer;
which fields matter, and how to describe them, is what you are being graded on.

  (a) one field, written out as a sentence
        return f"The connection used protocol {row['proto']}."

  (b) a few fields you picked, as key=value lines
        keep = ["proto", "state", "service", "sbytes", "dbytes", "sttl"]
        return "\\n".join(f"{col}={row[col]}" for col in keep)

  (c) the same few fields, but relabelled into plain English
        return (
            f"protocol: {row['proto']}\\n"
            f"connection state: {row['state']}\\n"
            f"bytes sent: {row['sbytes']}, bytes received: {row['dbytes']}\\n"
            f"source TTL: {row['sttl']}\\n"
        )

  (d) every field, unfiltered (easy, but high token consumption)
        return "\\n".join(f"{col}={val}" for col, val in row.items())

  (e) a value you computed yourself from the row
        ratio = int(row["sbytes"]) / max(int(row["dbytes"]), 1)
        return f"send/receive byte ratio: {ratio:.2f}"

Watch out: values are STRINGS.  int(row["sbytes"]) or float(row["dur"]) first
if you want to compare or do arithmetic, and remember a numeric field can be
the word "missing".

===============================================================================
TIPS
===============================================================================
  * Be explicit about the output format!
  * A tiny model (what we are using) follows a short, concrete instruction better than a long essay.
  * Every field you include is context the model must chew through on EVERY
    row. More is not automatically better, in accuracy or in runtime.
  * Test on a small number of rows (-r 20) before committing to a long run.
  * You cannot install any other dependencies except those already included.
===============================================================================
"""

# Not used but permitted (not required), uncomment if using

#import pandas as pd
#import math
#import decimal

# ---------------------------------------------------------------------------
# 1. HEADER (SYSTEM PROMPT) -- fixed text placed BEFORE the flow.  Instructions, the output
#    schema, any worked example.  Same for every row.
# ---------------------------------------------------------------------------
PROMPT_HEADER = (
    'I \n'
    'Prompt \n'
    'A lot \n'
)

# You cannot specify the dataset provided as part of your prompt.


# ---------------------------------------------------------------------------
# 2. BODY (USER PROMPT) -- the flow itself.  Called once per row.  See the worked examples
#    in the docstring above for how to get values out of `row`.
#    Return a string.  Returning "" means the model sees no data at all.
# ---------------------------------------------------------------------------
def build_body(row: dict) -> str:
    """Turn one flow's {column: value} dict into the text the model reads."""

    # YOUR CODE HERE.  Delete the line below and build the body you want.
    return (
    " THINK HERE "
)


# ---------------------------------------------------------------------------
# 3. FOOTER (ALSO USER PROMPT)-- fixed text placed AFTER the flow. Leave "" if you don't want one.
# ---------------------------------------------------------------------------
PROMPT_FOOTER = ""


# ---------------------------------------------------------------------------
# Assembly.  main.py calls this once per row.  You can edit it too: e.g. to
# drop the footer, or to reorder the pieces, but the three parts above are
# where the work normally goes. The point is, we return a string to prompt our model!
# ---------------------------------------------------------------------------
def build_prompt(row: dict) -> str:
    """Header + body + footer = the single user message sent to the model."""
    return PROMPT_HEADER + build_body(row) + PROMPT_FOOTER
