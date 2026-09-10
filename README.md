# ◈ Exclusion Inc

A local-first AI assistant for Android/Termux. The goal is a clean terminal dashboard with local inference, live device telemetry, model switching, and no cloud AI API.

## The stack

- **AI engine:** `llama.cpp`
- **Default AI model:** **Qwen2.5-3B-Instruct**
- **Default quantization:** **Q4_K_M** (~2.1 GB model file)
- **Format:** GGUF
- **Context:** 4096 tokens by default for safer phone memory usage
- **Network:** model requests are sent only to `127.0.0.1:8080`
- **UI symbol:** `◈`
- **OS target:** Android + Termux
- **Kernel:** the Android/Linux kernel reported by the device at runtime

Qwen provides official GGUF variants including Q4_K_M, and llama.cpp supports running GGUF models locally. The official llama.cpp Android/Termux guidance also recommends starting with a reasonable context size because a larger context can increase memory use. citeturn0search3turn0search0

## What the UI shows

The dashboard continuously refreshes while you use it:

```text
◈  EXCLUSION INC  //  LOCAL AI
TIME 17:42:08   CPU 12.4%   RAM 2840/7620 MB   SSD 41.2/128.0 GB
OS Linux ...    KERNEL ...
ENGINE llama.cpp   MODEL qwen2.5-3b-instruct-q4_k_m.gguf
CTX 4096   TEMP 0.7   SERVER 127.0.0.1:8080
STATUS READY
────────────────────────────────────────
YOU  › hello
AI   › Hello! I'm Exclusion Inc...
────────────────────────────────────────
You ›
```

The exact OS/kernel values depend on the Android device running Termux. Storage is displayed as local device storage rather than assuming the phone uses an SSD.

## Fast install — recommended

After cloning the repository, run:

```bash
cd ~/exclusion-inc
bash setup-termux.sh
```

The setup script installs the required Termux packages, builds the `llama.cpp` server/CLI, creates the model directory, and downloads the default Qwen2.5-3B-Instruct Q4_K_M model.

The model is about 2.1 GB according to the official Qwen GGUF repository. citeturn0search3

## Manual install

```bash
pkg update && pkg upgrade -y
pkg install -y git python clang cmake make curl

git clone https://github.com/llhomosapient-debug/exclusion-inc.git
cd exclusion-inc

git clone --depth=1 https://github.com/ggml-org/llama.cpp.git ~/llama.cpp
cd ~/llama.cpp
cmake -B build
cmake --build build --config Release -j2 --target llama-server llama-cli
```

Then create the model directory:

```bash
mkdir -p ~/exclusion-inc/models
```

Download the default model into it, or use another llama.cpp-compatible GGUF model. llama.cpp supports Hugging Face GGUF models and local GGUF files. citeturn0search12

## Start Exclusion Inc

```bash
cd ~/exclusion-inc
chmod +x run.sh
./run.sh
```

Or:

```bash
python exclusion.py
```

The UI starts the local llama.cpp server automatically. The server is bound to `127.0.0.1`, so Exclusion Inc does not expose its model server to the LAN.

## Commands

| Command | Action |
|---|---|
| `#endconvo` | Close Exclusion Inc cleanly |
| `!help` | Show command list |
| `!status` | Show live CPU/RAM/storage/OS information |
| `!models` | List installed GGUF models |
| `!model <file>` | Switch model, restart server, and update the dashboard |
| `!reload` | Restart the current local model server |
| `!clear` | Clear conversation context and chat display |
| `!exit` | Close Exclusion Inc |

Example model switch:

```text
!models
!model qwen2.5-3b-instruct-q4_k_m.gguf
```

The `MODEL` line in the dashboard changes immediately after the new model server is ready.

## Model choices

The default is **Qwen2.5-3B-Instruct Q4_K_M** because it is a reasonable quality/size starting point for a phone. Qwen's official GGUF release also provides Q2_K, Q3_K_M, Q4_0, Q5_0, Q5_K_M, Q6_K and Q8_0 variants. Smaller quantizations use less storage/RAM at the cost of quality; larger ones generally need more resources. citeturn0search3turn0search6

If the phone struggles, a smaller Q3_K_M or Q2_K build can be used. If the phone has enough RAM and you want more quality, Q5_K_M is an option.

## Resource behavior

When idle, Exclusion Inc waits for input and does not continuously generate model tokens. During generation, CPU/RAM usage naturally rises because the model is running locally.

The dashboard's CPU/RAM/storage values are device telemetry. They are not fake fixed values.

## Security

Normal conversations are not uploaded or committed to GitHub. Protected-resource attempts can create a local hash-chained security event in:

```text
logs/security.audit
```

The event stores a SHA-256 digest of the evidence rather than copying the entire message into the audit file. Model files, audit logs, credentials, and keys are excluded from Git.

## Update

Update Exclusion Inc:

```bash
cd ~/exclusion-inc
git pull
```

Update llama.cpp:

```bash
cd ~/llama.cpp
git pull
cmake -B build
cmake --build build --config Release -j2 --target llama-server llama-cli
```

## Troubleshooting

### `llama-server not found`

Build it:

```bash
cd ~/llama.cpp
cmake -B build
cmake --build build --config Release -j1 --target llama-server llama-cli
```

### `No .gguf model in models/`

Put a GGUF file in:

```bash
~/exclusion-inc/models/
```

Then run:

```bash
!models
!reload
```

### Phone runs out of memory

Use a smaller quantization/model and/or lower the context in `config/exclusion.json` from `4096` to `2048`.

### Build is too heavy

Use one build thread:

```bash
cmake --build build --config Release -j1
```

## Roadmap

- [x] Local-only shell
- [x] Hash-chained security audit
- [x] `#endconvo`
- [x] Live terminal dashboard
- [x] CPU/RAM/storage telemetry
- [x] Runtime OS/kernel display
- [x] Local llama.cpp server integration
- [x] Model switching commands
- [x] Qwen2.5-3B-Instruct default model
- [x] One-command Termux setup
- [ ] Custom font installer/theme presets
- [ ] Streaming token output
- [ ] Better long-session rolling memory
- [ ] Optional security-event email alerts
