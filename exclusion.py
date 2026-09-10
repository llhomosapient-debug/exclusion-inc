#!/usr/bin/env python3
"""Exclusion Inc: local AI terminal dashboard + llama.cpp client."""
from __future__ import annotations

import curses
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
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
chat_lines: list[str] = []

PATTERNS = [
    r"(?:show|give|print|reveal|dump|tell)\b.{0,100}(?:system prompt|system message|hidden prompt)",
    r"(?:show|give|read|print|dump)\b.{0,100}(?:protected\.json|secret|credential|private key)",
    r"(?:ignore|bypass|disable)\b.{0,100}(?:security|audit|protection)",
]


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def audit(kind: str, text: str) -> None:
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        previous = "0" * 64
        if AUDIT.exists():
            try:
                last = AUDIT.read_text(encoding="utf-8").splitlines()[-1]
                previous = json.loads(last).get("event_hash", previous)
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
    if preferred.exists() and preferred.is_file():
        return preferred
    available = models()
    return available[0] if available else None


def stop_server() -> None:
    global server
    if server is not None:
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
        log_handle = SERVER_LOG.open("w", encoding="utf-8")
        server = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=log_handle,
            start_new_session=True,
        )
        # The child owns the file descriptor after Popen; close our copy.
        log_handle.close()
    except (OSError, ValueError) as exc:
        try:
            log_handle.close()
        except Exception:
            pass
        server = None
        return False, f"Could not start llama-server: {exc}"

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if server.poll() is not None:
            return False, server_error_tail()
        try:
            with urllib.request.urlopen(
                f"http://{HOST}:{PORT}/health", timeout=0.6
            ) as response:
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
        return answer
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            detail = str(exc)
        return f"Local model HTTP error {exc.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return f"Local model error: {exc}"


def cpu() -> str:
    try:
        def read_cpu() -> tuple[int, int]:
            first = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
            values = [int(x) for x in first]
            return sum(values), values[3] + values[4]
        before = read_cpu()
        time.sleep(0.02)
        after = read_cpu()
        total = after[0] - before[0]
        idle = after[1] - before[1]
        return f"{100 * (1 - idle / max(total, 1)):4.1f}%"
    except (OSError, IndexError, ValueError):
        return "N/A"


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
                ["getprop", "ro.build.version.release"],
                text=True,
                timeout=1,
                stderr=subprocess.DEVNULL,
            ).strip()
            return f"Android {version or '?'} / Termux"
        except (OSError, subprocess.SubprocessError):
            pass
    return f"{platform.system()} / Termux"


def box(title: str, width: int) -> list[str]:
    width = max(20, min(width - 1, 78))
    inner = width - 2
    content = f" {title} "[:inner].ljust(inner)
    return ["╔" + "═" * inner + "╗", "║" + content + "║", "╚" + "═" * inner + "╝"]


def bar(value: int, total: int, width: int = 18) -> str:
    try:
        fraction = max(0.0, min(1.0, value / max(total, 1)))
        filled = int(fraction * width)
        return "█" * filled + "░" * (width - filled)
    except (TypeError, ZeroDivisionError):
        return "░" * width


def redraw(screen, status: str, text: str) -> None:
    try:
        screen.erase()
        height, width = screen.getmaxyx()
        model = selected()
        model_name = model.name if model else "NO MODEL"
        pulse = ["◈", "◇", "◆", "◇"][int(time.time() * 5) % 4] if status in ("GENERATING", "LOADING") else SYMBOL
        lines: list[tuple[str, bool]] = []

        for row in box(f"{pulse}  EXCLUSION INC  //  LOCAL AI", width):
            lines.append((row, True))
        lines.append((f"  TIME {time.strftime('%H:%M:%S')}   CPU {cpu()}   RAM {ram()}   STORAGE {disk()}", False))
        lines.append((f"  OS {os_name()}   KERNEL {platform.release()}", False))
        for row in box("SYSTEM", width):
            lines.append((row, True))
        lines.extend([
            ("  ENGINE   llama.cpp", False),
            (f"  MODEL    {model_name}", False),
            (f"  CONTEXT  {CONTEXT} tokens", False),
            (f"  TEMP     {TEMP:.2f}", False),
            (f"  SERVER   {HOST}:{PORT}", False),
        ])
        for row in box("STATUS", width):
            lines.append((row, True))
        lines.append((f"  ● {status}", False))
        lines.append(("─" * max(1, min(width - 1, 78)), False))

        footer = 4
        usable = max(1, height - len(lines) - footer)
        lines.extend((line, False) for line in chat_lines[-usable:])
        while len(lines) < height - footer:
            lines.append(("", False))
        lines.extend([
            ("─" * max(1, min(width - 1, 78)), False),
            (f"  CONTEXT  {bar(len(messages), max(1, CONTEXT // 20))}  messages={len(messages)}", False),
            (f"  {pulse}  You › {text}", False),
        ])

        for y, (row, bold) in enumerate(lines[:height]):
            try:
                screen.addstr(y, 0, row[: max(1, width - 1)], curses.A_BOLD if bold else 0)
            except curses.error:
                pass
        screen.refresh()
    except curses.error:
        # A resize or terminal redraw race should never kill the AI session.
        try:
            screen.touchwin()
            screen.refresh()
        except curses.error:
            pass


def wrap(prefix: str, value: str, width: int) -> list[str]:
    available = max(10, width - len(prefix) - 2)
    wrapped = textwrap.wrap(str(value), available) or [""]
    return [prefix + wrapped[0]] + [" " * len(prefix) + line for line in wrapped[1:]]


def handle_command(command: str, screen) -> tuple[bool, str]:
    global MODEL
    if command.lower() in ("#endconvo", "!exit", "/exit"):
        return True, ""
    if command in ("!help", "/help"):
        chat_lines.extend([
            "SYSTEM › !help  !status  !models  !model <file>  !clear  !reload  #endconvo",
            "SYSTEM › Local-only inference • localhost server • ◈ Exclusion Inc",
        ])
        return False, "READY"
    if command in ("!status", "/status"):
        chat_lines.append(f"SYSTEM › CPU {cpu()} | RAM {ram()} | STORAGE {disk()} | {os_name()} | kernel {platform.release()}")
        return False, "READY"
    if command in ("!models", "/models"):
        available = models()
        if not available:
            chat_lines.append("SYSTEM › Models: none")
        else:
            chat_lines.append("SYSTEM › Models: " + ", ".join(x.name for x in available))
        return False, "READY"
    if command in ("!clear", "/clear"):
        chat_lines.clear()
        messages.clear()
        return False, "READY"
    if command in ("!reload", "/reload"):
        ok, message = start_server()
        return False, message if ok else "ERROR: " + message
    if command.startswith("!model ") or command.startswith("/model "):
        name = command.split(None, 1)[1].strip()
        candidate = MODEL_DIR / name
        if candidate.exists() and candidate.is_file() and candidate.suffix.lower() == ".gguf":
            MODEL = candidate.name
            ok, message = start_server()
            return False, "MODEL CHANGED: " + message if ok else "ERROR: " + message
        return False, "Model not found: " + name
    return False, ""


def ui(screen) -> None:
    global server
    try:
        curses.curs_set(1)
    except curses.error:
        pass
    try:
        screen.keypad(True)
        screen.timeout(100)
    except curses.error:
        pass

    text = ""
    status = "LOADING"
    ok, message = start_server()
    status = message if ok else "ERROR: " + message

    while True:
        redraw(screen, status, text)
        try:
            key = screen.get_wch()
        except curses.error:
            # Termux/Python curses may raise "no input" on a timed get_wch().
            # Treat it exactly like a timeout instead of crashing.
            continue
        except KeyboardInterrupt:
            return

        if key == curses.KEY_RESIZE:
            continue
        if isinstance(key, str) and key in ("\n", "\r"):
            query = text.strip()
            text = ""
            if not query:
                continue
            should_exit, command_status = handle_command(query, screen)
            if should_exit:
                return
            if command_status:
                status = command_status
                continue

            if server is None or server.poll() is not None:
                ok, message = start_server()
                status = message if ok else "ERROR: " + message
            if server is None or server.poll() is not None:
                chat_lines.append("SYSTEM › " + status)
                continue

            width = screen.getmaxyx()[1]
            chat_lines.extend(wrap("YOU  › ", query, width))
            status = "GENERATING"
            redraw(screen, status, text)
            answer = chat(query)
            chat_lines.extend(wrap("AI   › ", answer, width))
            status = "READY"
        elif key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
            text = text[:-1]
        elif isinstance(key, str) and key.isprintable():
            text += key


def main() -> None:
    try:
        curses.wrapper(ui)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        # Keep failures readable instead of dumping an obscure traceback.
        print(f"\nExclusion Inc error: {type(exc).__name__}: {exc}")
    finally:
        stop_server()
        print("\nExclusion Inc stopped.")


if __name__ == "__main__":
    main()
