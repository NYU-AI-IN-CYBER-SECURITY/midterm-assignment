#!/usr/bin/env python3
"""
install.py -- one-command setup for testing your midterm project.

Works the same on Windows, macOS and Linux:

    python install.py

It will
  1. check your Python version,
  2. ask whether to create a local virtual environment (.venv) -- say yes
     unless you know why you don't want one,
  3. look for a GPU (NVIDIA CUDA or Apple Silicon) and offer the matching
     llama-cpp-python build,
  4. install everything in requirements.txt,
  5. LOAD-TEST the result against a real .gguf in this folder, and quietly step
     back down to a more conservative build if it crashes -- the accelerated
     wheels are compiled for newer CPUs and die with an illegal instruction
     (Windows 0xC000001D) on machines that lack those instructions,
  6. smoke-test the imports and print the exact command to run the assignment.

Flags (all optional -- without them the script just asks):
    --venv / --no-venv     skip the virtual-environment question
    --gpu / --cpu          skip the GPU question
    --yes, -y              accept every default, ask nothing (for lab images)
    --dry-run              print the commands instead of running them
"""

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import venv
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV_DIR = HERE / ".venv"
REQUIREMENTS = HERE / "requirements.txt"
MIN_PYTHON = (3, 10)

# llama-cpp-python publishes no wheels on PyPI -- a plain "pip install" there
# compiles the C++ from source, which needs a toolchain and takes many minutes.
# The project hosts prebuilt wheels per backend instead, so we point pip at
# those first and only fall back to a source build if none matches.
WHEEL_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/{tag}"
CUDA_WHEEL_TAGS = ["cu126", "cu125", "cu124", "cu123", "cu122", "cu121"]

# Extra CPU wheel flavours to fall back through, least conservative first.
# These exist for Linux only -- on Windows the ladder is cpu -> source build.
CPU_FALLBACK_TAGS = [] if platform.system() == "Windows" else ["avx", "basic"]

IS_WINDOWS = platform.system() == "Windows"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def say(msg=""):
    print(msg, flush=True)


def step(msg):
    say(f"\n=== {msg}")


def die(msg):
    say(f"\nERROR: {msg}")
    sys.exit(1)


def ask_yes_no(question: str, default: bool, auto: bool) -> bool:
    """Prompt for y/n.  Returns `default` when --yes was passed or stdin isn't
    a terminal (so the script still works from a CI job or a double-click)."""
    hint = "[Y/n]" if default else "[y/N]"
    if auto or not sys.stdin.isatty():
        say(f"{question} {hint} -> {'y' if default else 'n'} (auto)")
        return default
    while True:
        answer = input(f"{question} {hint} ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        say("Please answer y or n.")


def run(cmd, dry_run=False, check=True, quiet=False) -> int:
    """Run a command, echoing it first so students can see what happened."""
    printable = " ".join(str(c) for c in cmd)
    say(f"$ {printable}")
    if dry_run:
        return 0
    result = subprocess.run(
        [str(c) for c in cmd],
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.STDOUT if quiet else None,
    )
    if check and result.returncode != 0:
        die(f"command failed (exit {result.returncode}): {printable}")
    return result.returncode


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def check_python():
    step(f"Python {platform.python_version()} on {platform.system()} "
         f"({platform.machine()})")
    if sys.version_info < MIN_PYTHON:
        die(f"this project needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer. "
            f"You have {platform.python_version()}.  Install a newer Python and "
            f"re-run this script with it.")
    say("Python version OK.")


def venv_python(venv_dir: Path) -> Path:
    """Path to the interpreter inside a virtual environment."""
    return venv_dir / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def make_venv(dry_run: bool) -> Path:
    step(f"Creating virtual environment: {VENV_DIR}")
    target = venv_python(VENV_DIR)
    if target.exists():
        say(".venv already exists -- reusing it.")
        return target
    if dry_run:
        say(f"$ python -m venv {VENV_DIR}")
        return target
    try:
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV_DIR)
    except Exception as exc:                      # noqa: BLE001 - report and stop
        die(f"could not create the virtual environment: {exc}\n"
            f"On Debian/Ubuntu you may need:  sudo apt install python3-venv\n"
            f"Or re-run with --no-venv to install into your current Python.")
    if not target.exists():
        die(f"virtual environment created but {target} is missing.")
    say("Virtual environment ready.")
    return target


# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------

def detect_gpu() -> tuple[str, str]:
    """Returns (kind, human description).

    kind is "cuda" (NVIDIA), "metal" (Apple Silicon) or "cpu".
    """
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "metal", "Apple Silicon (Metal)"

    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run([smi], capture_output=True, text=True,
                                 timeout=20).stdout
            match = re.search(r"CUDA Version:\s*([0-9]+)\.([0-9]+)", out)
            name = re.search(r"\|\s+\d+\s+(NVIDIA[^|]*?)\s{2,}", out)
            gpu = (name.group(1).strip() if name else "NVIDIA GPU")
            if match:
                return "cuda", f"{gpu}, driver supports CUDA {match.group(1)}.{match.group(2)}"
            return "cuda", gpu
        except (subprocess.SubprocessError, OSError):
            pass
    return "cpu", "no supported GPU detected"


def cuda_wheel_tag() -> str:
    """Pick the newest prebuilt CUDA wheel the driver can run."""
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run([smi], capture_output=True, text=True,
                                 timeout=20).stdout
            m = re.search(r"CUDA Version:\s*([0-9]+)\.([0-9]+)", out)
            if m:
                driver = (int(m.group(1)), int(m.group(2)))
                for tag in CUDA_WHEEL_TAGS:
                    major, minor = int(tag[2:4]), int(tag[4:])
                    if (major, minor) <= driver:
                        return tag
        except (subprocess.SubprocessError, OSError, ValueError):
            pass
    return CUDA_WHEEL_TAGS[0]


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def pip_install(python: Path, extra_args, dry_run: bool, quiet=False) -> int:
    """pip install into `python`'s environment, coping with PEP 668."""
    base = [python, "-m", "pip", "install"]
    rc = run(base + extra_args, dry_run=dry_run, check=False, quiet=quiet)
    if rc != 0 and not dry_run:
        # Some system Pythons (Debian/Ubuntu, Homebrew) refuse to install
        # outside a venv.  Retry with the escape hatch before giving up.
        say("pip refused the install -- retrying with --break-system-packages ...")
        rc = run(base + ["--break-system-packages"] + extra_args,
                 dry_run=dry_run, check=False, quiet=quiet)
    return rc


def install_prebuilt(python: Path, tag: str, dry_run: bool, force=False) -> int:
    """Try the project's prebuilt wheels for one backend.

    --only-binary=:all: matters: without it a missing wheel silently turns into
    a 20-minute source build.  We want a clean failure we can fall back from.
    """
    args = ["llama-cpp-python", "--upgrade", "--prefer-binary",
            "--only-binary=:all:",
            "--extra-index-url", WHEEL_INDEX.format(tag=tag)]
    if force:
        args += ["--force-reinstall", "--no-cache-dir"]
    return pip_install(python, args, dry_run)


def install_from_source(python: Path, dry_run: bool) -> int:
    say("\nNo prebuilt wheel worked, so pip has to compile llama.cpp from")
    say("source.  This takes several minutes and needs a C++ toolchain.")
    return pip_install(python, ["llama-cpp-python", "--upgrade",
                                "--force-reinstall", "--no-cache-dir"], dry_run)


# The check below loads a real model (as a test).  An import is not enough: a wheel built
# for CPU features this machine lacks imports perfectly happily and then dies
# with an illegal instruction (Windows 0xC000001D) the moment llama.cpp
# initializes a context.  So a small test handles this. 
LOAD_TEST = r"""
import sys
from llama_cpp import Llama
llm = Llama(model_path=sys.argv[1], n_ctx=256, n_gpu_layers=0, verbose=False)
llm.create_chat_completion(messages=[{"role": "user", "content": "hi"}],
                           max_tokens=1)
print("LOAD_TEST_OK")
"""


def describe_exit(code: int) -> str:
    """Turn a crash exit code into something a student can act on."""
    unsigned = code & 0xFFFFFFFF
    known = {
        0xC000001D: "illegal instruction -- this build uses CPU features your "
                    "processor does not have",
        0xC0000005: "access violation -- the binary and your GPU driver disagree",
        0xC0000135: "a DLL is missing -- usually the CUDA runtime",
    }
    for signature, meaning in known.items():
        if unsigned == signature:
            return f"0x{signature:08X}: {meaning}"
    if code < 0:
        return f"killed by signal {-code}"
    return f"exit code {code}"


def load_test(python: Path, model: Path) -> tuple[bool, str]:
    """Actually load `model` in a subprocess.  Returns (ok, detail)."""
    result = subprocess.run([str(python), "-c", LOAD_TEST, str(model)],
                            capture_output=True, text=True)
    if result.returncode == 0 and "LOAD_TEST_OK" in result.stdout:
        return True, "loaded and generated a token"
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()
        hint = tail[-1] if tail else ""
        return False, f"{describe_exit(result.returncode)}{' | ' + hint if hint else ''}"
    return False, (result.stderr or "no output").strip()[-300:]


def install_dependencies(python: Path, gpu_kind: str, dry_run: bool) -> str:
    """Install, then prove the result actually runs.  Returns the backend used."""
    step("Upgrading pip")
    pip_install(python, ["--upgrade", "pip", "setuptools", "wheel"],
                dry_run, quiet=True)

    step("Installing requirements.txt (CPU baseline)")
    if REQUIREMENTS.exists():
        pip_install(python, ["-r", str(REQUIREMENTS)], dry_run)
    else:
        install_prebuilt(python, "cpu", dry_run)

    # Rungs to try, best first.  Each is (wheel tag, human label).
    ladder = []
    if gpu_kind == "cuda":
        ladder.append((cuda_wheel_tag(), "CUDA"))
    elif gpu_kind == "metal":
        ladder.append(("metal", "Metal"))
    ladder.append(("cpu", "CPU"))
    ladder += [(tag, f"CPU ({tag})") for tag in CPU_FALLBACK_TAGS]

    model, _ = find_files()
    if dry_run:
        for tag, label in ladder:
            say(f"(dry run) would try the {label} build [{tag}] and load-test it")
        return ladder[0][1]

    first = True
    for tag, label in ladder:
        if not first or tag != "cpu":          # cpu baseline is already in
            step(f"Installing the {label} build [{tag}]")
            if install_prebuilt(python, tag, dry_run, force=not first) != 0:
                say(f"No {label} wheel installed for your Python/OS -- "
                    f"trying the next option.")
                first = False
                continue
        first = False

        if model is None:
            say("\nNo .gguf in this folder, so the install can only be "
                "import-checked, not load-tested.\nIf main.py later dies with a "
                "Windows error like 0xC000001D, re-run:  python install.py --cpu")
            return label

        step(f"Load-testing the {label} build against {model.name}")
        ok, detail = load_test(python, model)
        if ok:
            say(f"{label} build works ({detail}).")
            if label in ("CUDA", "Metal"):
                say("Pass --n-gpu-layers -1 to main.py to actually use the GPU.")
            return label
        say(f"The {label} build failed: {detail}")
        say("Falling back to the next build down.")

    step("Last resort: building from source")
    if install_from_source(python, dry_run) != 0:
        die("could not install a working llama-cpp-python.\n"
            "  Windows: install the 'Desktop development with C++' workload\n"
            "           from the Visual Studio Build Tools, then re-run.\n"
            "  macOS:   xcode-select --install\n"
            "  Linux:   sudo apt install build-essential cmake")
    if model is not None:
        ok, detail = load_test(python, model)
        say(f"Source build: {'works' if ok else 'still failing -- ' + detail}")
    return "source build"


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

SMOKE_TEST = r"""
import sys
sys.path.insert(0, r"{here}")
import llama_cpp, csv_reader, metrics, prompter
print("  llama_cpp        ", llama_cpp.__version__)
print("  csv_reader       ", len(csv_reader.KEPT_COLUMNS), "feature columns")
print("  metrics          ", metrics.parse_prediction('{{"label":"attack","type":"DoS"}}'))
built = prompter.build_prompt(csv_reader.dummy_fields())
print("  prompter         ", "prompt is EMPTY -- filling it in is your assignment"
      if not built.strip() else f"prompt builds, {{len(built)}} characters on a test row")
"""


def verify(python: Path, dry_run: bool):
    step("Checking the install")
    if dry_run:
        say("(skipped in --dry-run)")
        return True
    code = SMOKE_TEST.format(here=str(HERE))
    result = subprocess.run([str(python), "-c", code],
                            capture_output=True, text=True)
    say(result.stdout.rstrip())
    if result.returncode != 0:
        say(result.stderr.rstrip())
        say("\nSomething is not importable yet -- see the error above.")
        return False
    say("All good.")
    return True


def find_files():
    """Best-effort: the model and CSV sitting next to this script."""
    model = next(iter(sorted(HERE.glob("*.gguf"))), None)
    csvs = [p for p in sorted(HERE.glob("*.csv")) if p.name != "results.csv"]
    return model, (csvs[0] if csvs else None)


def final_instructions(python: Path, used_venv: bool, backend: str = "CPU"):
    model, data = find_files()
    step("Done -- how to run the testing framework")

    if used_venv:
        activate = (r".venv\Scripts\activate" if IS_WINDOWS
                    else "source .venv/bin/activate")
        say(f"Activate the environment first (every new terminal):\n    {activate}")
        if IS_WINDOWS:
            say("If PowerShell blocks that with an execution-policy error, run once:")
            say("    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned")
        say("\n...or skip activation and call the venv's Python directly:")
        say(f"    {python}")

    m = model.name if model else "YOUR_MODEL.gguf"
    d = data.name if data else "YOUR_DATA.csv"
    quote = '"' if (data and " " in d) else ""
    gpu_flag = " --n-gpu-layers -1" if backend in ("CUDA", "Metal") else ""
    say(f"\nBackend installed: {backend}")
    say(f"\nThen edit prompter.py and run:")
    say(f"    python main.py -m {m} -c {quote}{d}{quote} -r 20{gpu_flag}")
    say("\nStart with a small -r while you iterate on the prompt.")
    if model is None:
        say("\n(No .gguf found in this folder -- put the model here or pass a full path.)")
    if data is None:
        say("(No .csv found in this folder -- put the dataset here or pass a full path.)")


# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Set up the midterm testing environment.")
    venv_group = p.add_mutually_exclusive_group()
    venv_group.add_argument("--venv", action="store_true",
                            help="create .venv without asking")
    venv_group.add_argument("--no-venv", action="store_true",
                            help="install into the current Python without asking")
    gpu_group = p.add_mutually_exclusive_group()
    gpu_group.add_argument("--gpu", action="store_true",
                           help="use the GPU build without asking")
    gpu_group.add_argument("--cpu", action="store_true",
                           help="force the CPU build")
    p.add_argument("-y", "--yes", action="store_true",
                   help="accept all defaults, ask nothing")
    p.add_argument("--dry-run", action="store_true",
                   help="show what would happen, change nothing")
    args = p.parse_args()

    say("=" * 70)
    say(" UNSW-NB15 midterm -- setup")
    say("=" * 70)
    check_python()

    # --- virtual environment -------------------------------------------------
    if args.venv:
        use_venv = True
    elif args.no_venv:
        use_venv = False
    else:
        say("\nA virtual environment keeps this assignment's packages separate")
        say("from the rest of your Python setup.  Recommended.")
        use_venv = ask_yes_no("Create one in .venv?", default=True, auto=args.yes)

    python = make_venv(args.dry_run) if use_venv else Path(sys.executable)
    if not use_venv:
        step(f"Installing into the current Python: {python}")

    # --- GPU -----------------------------------------------------------------
    kind, description = detect_gpu()
    step(f"Hardware check: {description}")
    if args.cpu:
        kind = "cpu"
    elif args.gpu:
        kind = kind if kind != "cpu" else "cpu"
        if kind == "cpu":
            say("--gpu was passed but no GPU was detected; using the CPU build.")
    elif kind != "cpu":
        label = "CUDA" if kind == "cuda" else "Metal"
        say(f"A {label} build can run the model considerably faster, but it is")
        say("more fragile to install.  Answering no gives you the plain CPU build,")
        say("which is fine for this assignment.")
        if not ask_yes_no(f"Install the {label} build?", default=True, auto=args.yes):
            kind = "cpu"

    backend = install_dependencies(python, kind, args.dry_run)
    ok = verify(python, args.dry_run)
    final_instructions(python, use_venv, backend)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\nCancelled.")
        sys.exit(130)
