#!/data/data/com.termux/files/usr/bin/bash
set -e

printf '\n◈ EXCLUSION INC — TERMUX SETUP\n\n'

pkg update -y
pkg install -y git python clang cmake make curl

if [ ! -d "$HOME/llama.cpp" ]; then
  git clone --depth=1 https://github.com/ggml-org/llama.cpp.git "$HOME/llama.cpp"
fi

cd "$HOME/llama.cpp"
cmake -B build
cmake --build build --config Release -j2 --target llama-server llama-cli

mkdir -p "$HOME/exclusion-inc/models"
cd "$HOME/exclusion-inc"

if [ ! -f models/qwen2.5-3b-instruct-q4_k_m.gguf ]; then
  echo "Downloading Qwen2.5-3B-Instruct Q4_K_M (~2.1 GB)..."
  curl -L --fail --progress-bar \
    'https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf?download=true' \
    -o models/qwen2.5-3b-instruct-q4_k_m.gguf
fi

chmod +x run.sh 2>/dev/null || true

echo
echo 'Setup complete.'
echo 'Start Exclusion Inc with:'
echo '  cd ~/exclusion-inc && ./run.sh'
echo
echo 'Inside the UI:'
echo '  #endconvo              close Exclusion Inc'
echo '  !help                  show commands'
echo '  !status                show system stats'
echo '  !models                list installed models'
echo '  !model <file>          switch model and refresh the server'
echo '  !clear                 clear chat context'
echo '  !reload                restart the local model server'
echo
