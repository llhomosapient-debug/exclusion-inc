#!/usr/bin/env python3
"""Exclusion Inc: stable local AI terminal UI for Termux/Android."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG_PATH = ROOT / "config" / "exclusion.json"
CFG = json.loads(CFG_PATH.read_text(encoding="utf-8"))
MODEL_DIR = ROOT / "models"
AUDIT = ROOT / "logs" / "security.audit"
SERVER_LOG = ROOT / "logs" / "llama-server.log"
LLAMA = Path.home() / "llama.cpp" / "build" / "bin" / "llama-server"

HOST = CFG.get("host", "127.0.0.1")
PORT = int(CFG.get("port", 8080))
CONTEXT = int(CFG.get("context", 4096))
TEMP = float(CFG.get("temperature", 0.7))
SYMBOL = str(CFG.get("symbol", "◈"))
MODEL = str(CFG.get("default_model", "qwen2.5-3b-instruct-q4_k_m.gguf"))

server: subprocess.Popen | None = None
messages: list[dict[str, str]] = []

# ANSI colors. No curses, no full-screen redraws, and no terminal animation.
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
BLUE = "\033[34m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
WHITE = "\033[97m"

PATTERNS = [
    r"(?:show|give|print|reveal|dump|tell)\b.{0,100}(?:system prompt|system message|hidden prompt)",
    r"(?:show|give|read|print|dump)\b.{0,100}(?:protected\.json|secret|credential|private key)",
    r"(?:ignore|bypass|disable)\b.{0,100}(?:security|audit|protection)",
]


def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("TERM", "") != "dumb"


def c(code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if supports_color() else text


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def audit(kind: str, text: str) -> None:
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        previous = "0" * 64
        if AUDIT.exists():
            try:
                previous = json.loads(AUDIT.read_text(encoding="utf-8").splitlines()[-1]).get("event_hash", previous)
            except (OSError, ValueError, IndexError, KeyError):
                pass
        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event_type": kind,
            "evidence_sha256": sha(text),
            "previous_event_hash": previous,
        }
        event["event_hash"] = sha(json.dumps(event, sort_keys=True, separators=(",", ":")))
        with AUDIT.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
    except OSError:
        pass


def security_check(text: str) -> bool:
    for pattern in PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            audit("protected-resource-attempt", text)
            return True
    return False


def models() -> list[Path]:
    try:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        return sorted(MODEL_DIR.glob("*.gguf"))
    except OSError:
        return []


def selected() -> Path | None:
    preferred = MODEL_DIR / MODEL
    if preferred.is_file():
        return preferred
    available = models()
    return available[0] if available else None


def stop_server() -> None:
    global server
    if server is None:
        return
    try:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=2)
    except (OSError, subprocess.SubprocessError):
        try:
            server.kill()
        except OSError:
            pass
    finally:
        server = None


def server_error_tail() -> str:
    try:
        if not SERVER_LOG.exists():
            return "llama-server exited during startup"
        lines = SERVER_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        useful = [line.strip() for line in lines[-8:] if line.strip()]
        return "llama-server exited: " + (useful[-1][:180] if useful else "unknown error")
    except OSError:
        return "llama-server exited during startup"


def start_server() -> tuple[bool, str]:
    global server, MODEL
    model = selected()
    if not LLAMA.exists():
        return False, f"llama-server not found: {LLAMA}"
    if model is None:
        return False, "No .gguf model found in models/"

    MODEL = model.name
    stop_server()
    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(LLAMA), "-m", str(model),
        "--host", HOST, "--port", str(PORT),
        "-c", str(CONTEXT), "--temp", str(TEMP),
        "--no-webui",
    ]
    try:
        with SERVER_LOG.open("w", encoding="utf-8") as log_handle:
            server = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=log_handle,
                start_new_session=True,
            )
    except (OSError, ValueError) as exc:
        server = None
        return False, f"Could not start llama-server: {exc}"

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if server.poll() is not None:
            return False, server_error_tail()
        try:
            with urllib.request.urlopen(f"http://{HOST}:{PORT}/health", timeout=0.6) as response:
                if response.status == 200:
                    return True, f"Loaded {model.name}"
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.15)
    return False, "Model server timeout (check logs/llama-server.log)"


def chat(prompt: str) -> str:
    if security_check(prompt):
        return "Protected Exclusion Inc resources are not available."

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": CFG.get("system_prompt", "You are Exclusion Inc.")},
            *messages,
            {"role": "user", "content": prompt},
        ],
        "temperature": TEMP,
        "max_tokens": 512,
        "stream": False,
    }
    request = urllib.request.Request(
        f"http://{HOST}:{PORT}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        started = time.monotonic()
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
        choices = payload.get("choices") or []
        if not choices:
            return "Local model error: server returned no choices."
        answer = str(choices[0].get("message", {}).get("content", "")).strip()
        if not answer:
            return "Local model error: empty response."
        messages.extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": answer},
        ])
        elapsed = time.monotonic() - started
        print(c(DIM, f"  {elapsed:.1f}s"))
        return answer
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            detail = str(exc)
        return f"Local model HTTP error {exc.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return f"Local model error: {exc}"


def ram() -> str:
    try:
        data: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, value = line.split(":", 1)
            data[key] = int(value.split()[0])
        total = data["MemTotal"]
        available = data.get("MemAvailable", data.get("MemFree", 0))
        return f"{(total - available) / 1024:.0f}/{total / 1024:.0f} MB"
    except (OSError, KeyError, ValueError, IndexError):
        return "N/A"


def cpu() -> str:
    try:
        def read_cpu() -> tuple[int, int]:
            values = [int(x) for x in Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]]
            return sum(values), values[3] + values[4]
        a = read_cpu()
        time.sleep(0.01)
        b = read_cpu()
        total = b[0] - a[0]
        idle = b[1] - a[1]
        return f"{100 * (1 - idle / max(total, 1)):4.1f}%"
    except (OSError, IndexError, ValueError):
        return "N/A"


def disk() -> str:
    try:
        usage = shutil.disk_usage(Path.home())
        return f"{usage.used / 2**30:.1f}/{usage.total / 2**30:.1f} GB"
    except OSError:
        return "N/A"


def os_name() -> str:
    if shutil.which("getprop"):
        try:
            version = subprocess.check_output(
                ["getprop", "ro.build.version.release"], text=True, timeout=1, stderr=subprocess.DEVNULL
            ).strip()
            return f"Android {version or '?'} / Termux"
        except (OSError, subprocess.SubprocessError):
            pass
    return f"{platform.system()} / Termux"


def width() -> int:
    try:
        return max(40, shutil.get_terminal_size((80, 24)).columns)
    except OSError:
        return 80


def line(char="─") -> str:
    return char * min(width(), 78)


def print_header(status: str = "READY") -> None:
    model = selected()
    model_name = model.name if model else "NO MODEL"
    print()
    print(c(CYAN + BOLD, "╔" + "═" * 58 + "╗"))
    print(c(CYAN + BOLD, "║") + c(WHITE + BOLD, "   ◈  EXCLUSION INC  //  LOCAL AI") + c(CYAN + BOLD, "".ljust(25) + "║"))
    print(c(CYAN + BOLD, "╚" + "═" * 58 + "╝"))
    print(c(DIM, f"  {os_name()}  •  llama.cpp  •  {HOST}:{PORT}"))
    print(c(DIM, f"  MODEL {model_name}  •  CTX {CONTEXT}  •  TEMP {TEMP:.2f}"))
    print(c(GREEN, f"  ● {status}"))
    print(line())


def print_help() -> None:
    print(c(CYAN + BOLD, "  COMMANDS"))
    print(c(WHITE, "  !help                 Show commands"))
    print(c(WHITE, "  !status               System/model status"))
    print(c(WHITE, "  !models               List GGUF models"))
    print(c(WHITE, "  !model <file>         Switch model"))
    print(c(WHITE, "  !clear                Clear conversation context"))
    print(c(WHITE, "  !reload               Restart local model server"))
    print(c(WHITE, "  #endconvo             Exit Exclusion Inc"))
    print(line())


def handle_command(command: str) -> bool:
    global MODEL
    if command.lower() in ("#endconvo", "!exit", "/exit"):
        return True
    if command in ("!help", "/help"):
        print_help()
        return False
    if command in ("!status", "/status"):
        print(c(CYAN, f"  CPU {cpu()}  |  RAM {ram()}  |  STORAGE {disk()}"))
        print(c(DIM, f"  {os_name()}  |  kernel {platform.release()}  |  server {HOST}:{PORT}"))
        print(line())
        return False
    if command in ("!models", "/models"):
        available = models()
        if not available:
            print(c(YELLOW, "  No GGUF models found."))
        else:
            print(c(CYAN + BOLD, "  MODELS"))
            for model in available:
                marker = "●" if model.name == MODEL else "○"
                size = model.stat().st_size / 2**30
                print(c(GREEN if marker == "●" else WHITE, f"  {marker} {model.name}  ({size:.2f} GB)"))
        print(line())
        return False
    if command in ("!clear", "/clear"):
        messages.clear()
        print(c(GREEN, "  ✓ Conversation context cleared."))
        print(line())
        return False
    if command in ("!reload", "/reload"):
        print(c(YELLOW, "  ◌ Restarting local model server..."))
        ok, message = start_server()
        print(c(GREEN if ok else RED, "  ✓ " + message if ok else "  ✗ " + message))
        print(line())
        return False
    if command.startswith("!model ") or command.startswith("/model "):
        name = command.split(None, 1)[1].strip()
        candidate = MODEL_DIR / name
        if candidate.is_file() and candidate.suffix.lower() == ".gguf":
            MODEL = candidate.name
            print(c(YELLOW, f"  ◌ Loading {MODEL}..."))
            ok, message = start_server()
            print(c(GREEN if ok else RED, "  ✓ " + message if ok else "  ✗ " + message))
        else:
            print(c(RED, "  ✗ Model not found: " + name))
        print(line())
        return False
    return False


def main() -> None:
    global server
    try:
        ok, message = start_server()
        if not ok:
            print_header("ERROR")
            print(c(RED, "  ✗ " + message))
            print(c(DIM, "  Check logs/llama-server.log for server details."))
            return

        # Important: this UI intentionally does NOT use curses, clear-screen loops,
        # cursor movement, or animation. Termux can render it like a normal shell.
        print_header("READY")
        print(c(DIM, "  Type !help for commands. Your terminal handles scrolling normally."))
        print()

        while True:
            try:
                prompt = input(c(MAGENTA + BOLD, "  ◈ You › ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not prompt:
                continue
            if handle_command(prompt):
                break
            if prompt.startswith("!") or prompt.startswith("/"):
                # Known commands have already been handled; unknown commands fall through as chat.
                if prompt.split(None, 1)[0] in {"!help", "!status", "!models", "!clear", "!reload", "!model", "/help", "/status", "/models", "/clear", "/reload", "/model", "!exit", "/exit"}:
                    continue

            print(c(YELLOW, "  ◌ Exclusion is thinking..."))
            answer = chat(prompt)
            print()
            print(c(CYAN + BOLD, "  ◈ Exclusion ›"))
            for paragraph in answer.splitlines() or [""]:
                if not paragraph.strip():
                    print()
                    continue
                wrapped = textwrap.wrap(paragraph, width=max(20, width() - 5), break_long_words=False, break_on_hyphens=False) or [""]
                for part in wrapped:
                    print(c(WHITE, "  " + part))
            print(line())

    finally:
        stop_server()
        print(c(DIM, "\n  Exclusion Inc stopped."))


if __name__ == "__main__":
    main()
