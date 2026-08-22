# AI For Cyber Security Testing midterm: testing your fine-tuned model

You write a prompt. The runner feeds your model one network flow at a time,
collects its answers, and scores them against the real labels.

## What you need

* Python 3.10 or newer
* your fine-tuned model as a `.gguf` file
* a labelled CSV to test against
* all the files below in **one folder**, together with your model and CSV

| file | what it does | do you edit it? |
|---|---|---|
| `prompter.py` | builds the prompt for each flow | **YES — this is the assignment** ! |
| `main.py` | the runner: ties everything together | no |
| `csv_reader.py` | hands over one flow at a time | no |
| `metrics.py` | parses the answer and computes the scores | no |
| `report.py` | writes the results workbook | no |
| `install.py` | sets up Python and the packages | no |
| `requirements.txt` | the dependency list | no |

!  Remember it's in the main assignment directory, but you need to place it with these files to test it!
  
## 1. Set up your environment

```
python install.py
```

This creates a virtual environment for you (a private Python just for this
assignment) and installs the tooling needed to load your model and score it.
Same command on Windows, macOS and Linux.

You are **not** required to use `install.py`,  set up your own environment if
you prefer. All it needs is Python 3.10+ and the packages in
`requirements.txt`.

If you let it make a virtual environment, activate it in every new terminal
window before running anything:

```
.venv\Scripts\activate           # Windows
source .venv/bin/activate        # macOS / Linux
```

You'll know it worked when your prompt starts with `(.venv)`.

Useful flags: `--cpu` (skip the GPU build), `--no-venv` (install into the
Python you already have), `-y` (accept every default), `--dry-run` (show what
it would do without doing it).

## 2. Write your prompt

Remember the main assignment! Make sure to open `prompter.py`. It is the only file you edit.
It must be placed in the folder you are running your. 
You build the message the model sees out of three pieces:

As a reward for reading all the readme files, here is are examples/hints:

Remember, assume the flow you were handed looks like this:

```python
    row = {"proto": "tcp", "state": "FIN", "service": "http",
           "sbytes": "1490", "dbytes": "354", "sttl": "31", ... }
```
In our example below a row may contain information about a family's pets:

```python
	row = {"cat": "britishBlue", "dog": "terrier", "horse": "ed","color":"blue",
           "age": "12", "hungry": "yes",... }
```

Let's say you really cared about those specific descriptors, you may chose to keep those. Different ways to do it:


(a) ONE FIELD, written as a sentence
```python
        def build_body(row):
            return f"The cat of the family is a {row['cat']}."
```
the model receives:
```python
The cat of the family is a britishBlue
```		
		
(b) A FEW FIELDS YOU PICKED, one per line

```python
def build_body(row):
    keep = ["cat", "dog", "horse", "color", "age", "hungry"]

    lines = []                          # collect one line per field
    for column in keep:                 # column is a name, e.g. "dog"
        value = row[column]             # value is what's in it, e.g. "terrier"
        lines.append(column + "=" + value)

    return "\n".join(lines)             # glue the lines together, one per row
```
and the text the model actually receives (made up values):

```python
cat=britishBlue
dog=terrier
horse=ed
color=blue
age=12
hungry=yes
```
 (c) THE SAME FIELDS, RELABELLED INTO PLAIN ENGLISH
 
```python
         def build_body(row):
            return (
                f"Cat Breed: {row['cat']}\n"
                f"Dog Breed: {row['dog']}\n"
                f"Horse Name: {row['horse']}, and is {row['age']} years old\n"
            )
```
the model receives:
```python
Cat Breed: britishBlue
Dog Breed: terrier
Horse Name: ed, and is 12 years old
```
  (d) EVERY FIELD, UNFILTERED
    
row.items() hands you the name and the content together, so you don't
need a `keep` list at all:
      
```python
        def build_body(row):
            lines = []
            for column, value in row.items():
                lines.append(column + "=" + value)
            return "\n".join(lines)
```
Easy to write, but and sends all 42 fields on every single row.
	  
  (e) A VALUE YOU WORK OUT YOURSELF
	  Nothing stops you from giving the model a number the CSV never
      contained.  Whether that helps is for you to test.
	  
Watch out: every value in `row` is a STRING.  "1490" + "354" gives you
"1490354", not 1844.  Convert with int() or float() first when you want to
compare or calculate -- and remember a numeric field can arrive as the word
"missing", which int() will refuse.


These are hints and mechanics examples, not an answer. Which fields matter and how you
describe them is what you're being graded on. `prompter.py`'s docstring has
more examples and the full column list. You get to test your prompter here against your chosen training data! 

## 3. Check your CSV

Whatever CSV you use must be formatted like the UNSW-NB15 dataset — the same
feature columns, **plus the two answer columns**:

| column | meaning |
|---|---|
| `label` | `0` = normal, `1` = attack |
| `attack_cat` | the attack type (`Exploits`, `DoS`, `Worms`, …; `Normal` for normal traffic) |

Without those two columns there is nothing to score against. The reader is
tolerant about the rest: column names can be upper or lower case, extra
whitespace in headers is stripped, and both the old and new UNSW-NB15 column
spellings are accepted. Identity and timestamp columns (`id`, `srcip`,
`sport`, `dstip`, `dsport`, `Stime`, `Ltime`) are dropped as noise, and
`label` / `attack_cat` are never shown to the model — that would be leaking
the answer.

## 4. Run it

```
python main.py --model my_model.gguf --csv UNSW_NB15_balanced_30k.csv --rows 50
```
Again we recommend you find MORE data than the balanced set we shared. Perhaps create your own set.
Just make sure it fits the UNSW_NB15 format!

Short flags work too:

```
python main.py -m my_model.gguf -c data.csv -r 200 --shuffle --out run2.xlsx
```

| flag | default | meaning |
|---|---|---|
| `-m, --model` | required | path to your `.gguf` |
| `-c, --csv` | required | path to the labelled CSV |
| `-r, --rows` | every row | how many rows to run |
| `-o, --out` | `results.xlsx` | where the report goes |
| `--shuffle` | off | sample randomly instead of top-to-bottom |
| `--seed` | 42 | shuffle seed (with `--shuffle`) |
| `--max-new-tokens` | 64 | generation cap per row |
| `--temperature` | 0.0 | 0.0 = same answer every time |
| `--n-ctx` | 4096 | context window |
| `--n-gpu-layers` | 0 | layers on the GPU; `-1` = all of them |
| `--no-warmup` | off | skip the throwaway first inference |

**About `--rows`:** leave it off and you run every row in your test set. Ask
for more rows than the CSV has and you get all of them. Start small — `-r 20`
— while you're still iterating on your prompt, then do a long run once you're
happy. Each row is a separate call to the model, so 30,000 rows takes roughly
30,000 × the per-row time you see on screen.

If a path has a space in it, wrap it in quotes:
`--csv "UNSW_NB15 balanced 30k.csv"`.

## 5. Read your results

`results.xlsx` is an Excel workbook with three tabs:

| tab | what's in it |
|---|---|
| **Summary** | your run settings, then the scores |
| **Results** | one line per flow: truth, prediction, whether each matched, seconds |
| **Prompts** | one line per flow: the full prompt sent, and the raw model output |

Two scores are reported:

* **BINARY** — normal vs attack
* **MULTICLASS** — which attack type

Each gives accuracy, macro precision / recall / F1, and a per-class table.

**When your score is bad, read the Prompts tab first.** It shows exactly what
the model was asked and exactly what it said back, before any parsing — which
is usually enough to tell whether the model got the flow wrong or just ignored
your output format.

While a run is going, rows are also appended to `results.partial.jsonl`, so
stopping a long run early doesn't lose the work already done. That file is
deleted once the workbook is written.

## Remember the output format is strict

Your model must reply with exactly one JSON object and nothing else:

```json
{"label": "attack", "type": "Exploits"}
```

* `label` is `normal` or `attack`
* `type` is one of `Normal`, `Fuzzers`, `Analysis`, `Backdoor`, `DoS`,
  `Exploits`, `Generic`, `Reconnaissance`, `Shellcode`, `Worms`

Case doesn't matter (`DoS`, `dos`, `DOS` all match) but spelling does.
Anything that isn't clean JSON is scored as **wrong** — there is no keyword
fallback, no alias remapping, no stripping of markdown fences. A chatty model
scores zero, so make the format instruction in your prompt strict and repeat
it.

## If something goes wrong

**`python: command not found`** — try `python3` instead of `python`, or
install Python from python.org.

**`main.py: error: csv not found: ...`** — check the spelling, and quote paths
containing spaces.

**`WARNING: prompter.py builds an EMPTY prompt`** — you haven't filled in
`prompter.py` yet. The run will score zero.

**`OSError: [WinError -1073741795] Windows Error 0xc000001d`** — the installed
`llama-cpp-python` was built for CPU features your machine doesn't have. This
is a build mismatch, not a bug in your prompt. Fix it with:

```
python install.py --cpu
```

The model is small; the CPU build is perfectly adequate here.

**A run is far too slow** — you're probably running the whole CSV. Use `-r 20`
while iterating. If you have an NVIDIA or Apple Silicon GPU, `python
install.py` can install a GPU build; then add `--n-gpu-layers -1`.
