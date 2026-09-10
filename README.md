# Exclusion Inc

A local-first AI assistant designed to run on Android/Termux with a local GGUF model. No cloud AI API is required.

## Features

- Local model inference through `llama.cpp`
- No API key or per-message token cost
- Interactive terminal chat
- `#endconvo` cleanly exits the assistant
- Security checks are limited to attempts against protected Exclusion Inc resources
- Security events are stored locally in a tamper-evident hash chain
- Normal chat messages are not uploaded or stored by the application

> Local does not mean unlimited compute: generation uses your phone's CPU/RAM, and the model still has a finite context window. Rolling history/summarization can later support longer sessions.

## Requirements

Recommended: Android + Termux. A device with 8 GB RAM or more gives you more model choices, but smaller quantized models can run on less RAM.

Install the basic packages:

```bash
pkg update && pkg upgrade -y
pkg install -y git python clang cmake make
```

Clone the project:

```bash
git clone https://github.com/llhomosapient-debug/exclusion-inc.git
cd exclusion-inc
```

## Install llama.cpp

Clone llama.cpp into your home directory:

```bash
cd ~
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
cmake -B build
cmake --build build --config Release -j2
```

Check the CLI:

```bash
~/llama.cpp/build/bin/llama-cli --help
```

## Add a local GGUF model

Create the model directory:

```bash
mkdir -p ~/exclusion-inc/models
```

Place a compatible GGUF instruct model in that directory. Start with a small 1B–3B parameter Q4 model for better speed and RAM usage on a phone.

Example layout:

```text
~/exclusion-inc/
├── exclusion.py
├── config/
├── security/
├── logs/
└── models/
    └── model.gguf
```

Do not commit model files to GitHub; `.gitignore` excludes them.

## Run Exclusion Inc

```bash
cd ~/exclusion-inc
python exclusion.py
```

The interactive shell stays open until you end the session. While waiting for input, it does not continuously generate CPU load.

## Commands

### End the AI session

Type:

```text
#endconvo
```

This exits the assistant cleanly.

### Normal messages

Type your message normally:

```text
You > hello
```

The local model backend will generate the response on-device.

## Security audit

Ordinary chat is not logged. When a message appears to target protected Exclusion Inc resources, a local security event can be recorded in:

```text
logs/security.audit
```

The audit uses a hash chain so each event depends on the previous event. The message itself is represented by a SHA-256 digest rather than copied into the audit file.

Logs, credentials, and model files are ignored by Git and remain local.

## Update Exclusion Inc

```bash
cd ~/exclusion-inc
git pull
```

Update llama.cpp separately:

```bash
cd ~/llama.cpp
git pull
cmake -B build
cmake --build build --config Release -j2
```

## Troubleshooting

If Python is missing:

```bash
pkg install -y python
```

If compilation causes high memory usage:

```bash
cmake --build build --config Release -j1
```

If the model is too slow or Android runs out of RAM, use a smaller GGUF model or lower quantization.

## Roadmap

- [x] Termux-compatible project shell
- [x] `#endconvo`
- [x] Local-only security audit foundation
- [ ] Connect the shell to `llama.cpp`
- [ ] Add rolling conversation context
- [ ] Add polished custom terminal UI and font setup
- [ ] Add optional security email alerts for security events only
- [ ] Add one-command installer
