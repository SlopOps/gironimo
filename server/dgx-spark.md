# Distributed Setup: DGX Spark (vLLM)

## Architecture Overview

| Component         | Location  | Responsibility                       |
| ----------------- | --------- | ------------------------------------ |
| vLLM Servers (3x) | DGX Spark | Model inference, GPU compute         |
| Agent Scripts     | Laptop    | Orchestration, file I/O, human gates |
| CodeGraph Index   | Laptop    | Code embeddings, semantic search     |
| Project Files     | Laptop    | Source code, specs, ADRs             |

---

# Hugging Face CLI Installation (Required)

The model download script requires the **Hugging Face CLI**.

Install it once per user.

## Install

```bash
curl -LsSf https://hf.co/cli/install.sh | bash
```

This installs the CLI to:

```
$HOME/.local/bin/hf
```

---

## Add to PATH (Current User)

Ensure `$HOME/.local/bin` is in your PATH.

### Bash

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Zsh

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

## Verify Installation

```bash
hf --version
```

---

## Login to Hugging Face

Some models require authentication.

```bash
hf auth login
```

Create a token here if needed:

[https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

---

# Persistent Model Storage (Download Once)

Models are stored locally at:

```
~/models/
```

This avoids re-downloading on every restart.

---

## Storage Layout

```
~/models/
├── qwen3.5-35b-a3b-fp8/
├── qwen3-coder-next-int4/
└── qwen3-vl-4b/
```

---

# One-Time Download Script

Save as **download-models.sh**

```bash
#!/bin/bash
set -e

MODEL_DIR="$HOME/models"
mkdir -p "$MODEL_DIR"

export HF_HUB_DOWNLOAD_TIMEOUT=120

echo "=== Downloading models to $MODEL_DIR ==="
echo "Total: ~123GB. This will take a while on slow internet."
echo ""

if ! hf whoami > /dev/null 2>&1; then
    echo "Please login first using: hf auth login"
    exit 1
fi

echo "[1/3] Downloading Qwen3.5-35B-A3B-FP8..."

if [ ! -d "$MODEL_DIR/qwen3.5-35b-a3b-fp8" ]; then
    hf download Qwen/Qwen3.5-35B-A3B-FP8 \
        --local-dir "$MODEL_DIR/qwen3.5-35b-a3b-fp8"
else
    echo "Already exists, skipping."
fi

echo "[2/3] Downloading Qwen3-Coder-Next-int4-AutoRound..."

if [ ! -d "$MODEL_DIR/qwen3-coder-next-int4" ]; then
    hf download Intel/Qwen3-Coder-Next-int4-AutoRound \
        --local-dir "$MODEL_DIR/qwen3-coder-next-int4"
else
    echo "Already exists, skipping."
fi

echo "[3/3] Downloading Qwen3-VL-4B-Instruct..."

if [ ! -d "$MODEL_DIR/qwen3-vl-4b" ]; then
    hf download Qwen/Qwen3-VL-4B-Instruct \
        --local-dir "$MODEL_DIR/qwen3-vl-4b"
else
    echo "Already exists, skipping."
fi

echo ""
echo "=== All models downloaded ==="
echo "Total size: $(du -sh "$MODEL_DIR" | cut -f1)"

df -h "$HOME"
```

---

## Run the Script

```bash
chmod +x download-models.sh
./download-models.sh
```

---

# API Key Setup (One-Time)

```bash
mkdir -p ~/.keys

openssl rand -hex 32 > ~/.keys/vllm_main_key
openssl rand -hex 32 > ~/.keys/vllm_coder_key
openssl rand -hex 32 > ~/.keys/vllm_vision_key

chmod 600 ~/.keys/*
```

Create symlinks used by systemd:

```bash
ln -sf ~/.keys/vllm_main_key ~/.vllm_main_key
ln -sf ~/.keys/vllm_coder_key ~/.vllm_coder_key
ln -sf ~/.keys/vllm_vision_key ~/.vllm_vision_key
```

---

# DGX Spark: Systemd Services

Create these files in:

```
/etc/systemd/system/
```

---

# vllm-main.service

```
/etc/systemd/system/vllm-main.service
```

```ini
[Unit]
Description=vLLM Main Agent (Qwen3.5-35B-A3B-FP8)
After=network.target

[Service]
Type=simple
User=%u
WorkingDirectory=%h/Documents/gironimo/server

LimitMEMLOCK=infinity
LogRateLimitIntervalSec=0

Environment="PATH=%h/Documents/gironimo/server/.venv/bin:/usr/local/bin:/usr/bin"
Environment="CUDA_VISIBLE_DEVICES=0"
Environment="PYTHONUNBUFFERED=1"
Environment="VLLM_LOGGING_LEVEL=warning"
Environment="HF_HOME=%h/models/.cache/huggingface"
Environment="VLLM_API_KEY_FILE=%h/.vllm_main_key"
Environment="VLLM_MARLIN_USE_ATOMIC_ADD=1"
Environment="VLLM_ATTENTION_BACKEND=FLASHINFER"
Environment="VLLM_CUDA_GRAPH_MODE=full_and_piecewise"
Environment="VLLM_WORKER_MULTIPROC_METHOD=spawn"
Environment="CUDA_DEVICE_MAX_CONNECTIONS=1"
Environment="OMP_NUM_THREADS=8"
Environment="MKL_NUM_THREADS=8"
Environment="NUMEXPR_NUM_THREADS=8"
Environment="TOKENIZERS_PARALLELISM=false"

ExecStart=%h/Documents/gironimo/server/.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model %h/models/qwen3.5-35b-a3b-fp8 \
  --served-model-name Qwen/Qwen3.5-35B-A3B-FP8 \
  --download-dir %h/models \
  --port 8000 \
  --host 0.0.0.0 \
  --quantization fp8 \
  --kv-cache-dtype fp8 \
  --load-format fastsafetensors \
  --attention-backend flashinfer \
  --gpu-memory-utilization 0.55 \
  --swap-space 16 \
  --max-model-len 262144 \
  --max-num-batched-tokens 32768 \
  --max-num-seqs 4 \
  --max-cudagraph-capture-size 10 \
  --enable-prefix-caching \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen \
  --mamba-ssm-cache-dtype float16 \
  --trust-remote-code

Restart=always
RestartSec=5

ExecStartPost=/bin/bash -c 'for i in {1..60}; do \
curl -sf -H "Authorization: Bearer $(cat %h/.vllm_main_key)" \
http://localhost:8000/health && exit 0; sleep 2; done; exit 1'

[Install]
WantedBy=multi-user.target
```

---

# vllm-coder.service

```
/etc/systemd/system/vllm-coder.service
```

```ini
[Unit]
Description=vLLM Coder Agent (Qwen3-Coder-Next-int4-AutoRound)
After=network.target vllm-main.service

[Service]
Type=simple
User=%u
WorkingDirectory=%h/Documents/gironimo/server

LimitMEMLOCK=infinity
LogRateLimitIntervalSec=0

Environment="PATH=%h/Documents/gironimo/server/.venv/bin:/usr/local/bin:/usr/bin"
Environment="CUDA_VISIBLE_DEVICES=0"
Environment="PYTHONUNBUFFERED=1"
Environment="VLLM_LOGGING_LEVEL=warning"
Environment="HF_HOME=%h/models/.cache/huggingface"
Environment="VLLM_API_KEY_FILE=%h/.vllm_coder_key"
Environment="VLLM_MARLIN_USE_ATOMIC_ADD=1"
Environment="VLLM_ATTENTION_BACKEND=FLASHINFER"
Environment="VLLM_CUDA_GRAPH_MODE=full_and_piecewise"
Environment="VLLM_WORKER_MULTIPROC_METHOD=spawn"
Environment="CUDA_DEVICE_MAX_CONNECTIONS=1"
Environment="OMP_NUM_THREADS=8"
Environment="MKL_NUM_THREADS=8"
Environment="NUMEXPR_NUM_THREADS=8"
Environment="TOKENIZERS_PARALLELISM=false"

ExecStart=%h/Documents/gironimo/server/.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model %h/models/qwen3-coder-next-int4 \
  --served-model-name Qwen/Qwen3-Coder-Next-int4-AutoRound \
  --download-dir %h/models \
  --port 8001 \
  --host 0.0.0.0 \
  --quantization int4 \
  --dtype bfloat16 \
  --load-format fastsafetensors \
  --attention-backend flashinfer \
  --gpu-memory-utilization 0.33 \
  --swap-space 16 \
  --max-model-len 262144 \
  --max-num-batched-tokens 32768 \
  --max-num-seqs 4 \
  --enable-prefix-caching \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder

Restart=always
RestartSec=5
```

---

# vllm-vision.service

```
/etc/systemd/system/vllm-vision.service
```

```ini
[Unit]
Description=vLLM Vision Model (Qwen3-VL-4B-Instruct)
After=network.target vllm-main.service vllm-coder.service

[Service]
Type=simple
User=%u
WorkingDirectory=%h/Documents/gironimo/server

LimitMEMLOCK=infinity
LogRateLimitIntervalSec=0

Environment="PATH=%h/Documents/gironimo/server/.venv/bin:/usr/local/bin:/usr/bin"
Environment="CUDA_VISIBLE_DEVICES=0"
Environment="PYTHONUNBUFFERED=1"
Environment="VLLM_LOGGING_LEVEL=warning"
Environment="HF_HOME=%h/models/.cache/huggingface"
Environment="VLLM_API_KEY_FILE=%h/.vllm_vision_key"
Environment="VLLM_ATTENTION_BACKEND=FLASHINFER"
Environment="VLLM_CUDA_GRAPH_MODE=full_and_piecewise"
Environment="VLLM_WORKER_MULTIPROC_METHOD=spawn"
Environment="CUDA_DEVICE_MAX_CONNECTIONS=1"
Environment="OMP_NUM_THREADS=8"
Environment="MKL_NUM_THREADS=8"
Environment="NUMEXPR_NUM_THREADS=8"
Environment="TOKENIZERS_PARALLELISM=false"

ExecStart=%h/Documents/gironimo/server/.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model %h/models/qwen3-vl-4b \
  --served-model-name Qwen/Qwen3-VL-4B-Instruct \
  --download-dir %h/models \
  --port 8002 \
  --host 0.0.0.0 \
  --dtype bfloat16 \
  --load-format fastsafetensors \
  --attention-backend flashinfer \
  --gpu-memory-utilization 0.05 \
  --max-model-len 32768 \
  --max-num-batched-tokens 4096 \
  --max-num-seqs 2 \
  --enforce-eager

Restart=always
RestartSec=5
```

---

# Enable and Start Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable vllm-main vllm-coder vllm-vision
sudo systemctl start vllm-main vllm-coder vllm-vision
```

---

## Check Status

```bash
sudo systemctl status vllm-main vllm-coder vllm-vision
```

---

## View Logs

```bash
sudo journalctl -u vllm-main -f
```

---

## Check GPU Memory

```bash
watch -n 1 nvidia-smi
```

---

# Test API

```bash
curl -H "Authorization: Bearer $(cat ~/.vllm_main_key)" \
http://localhost:8000/v1/models
```

---

# Firewall

```bash
sudo ufw allow 8000/tcp
sudo ufw allow 8001/tcp
sudo ufw allow 8002/tcp
```

---

# Model Summary

| Agent     | Model                 | Path                             | Size       | GPU Util | Swap     | Context   | Est VRAM   |
| --------- | --------------------- | -------------------------------- | ---------- | -------- | -------- | --------- | ---------- |
| Main      | Qwen3.5-35B-A3B-FP8   | `~/models/qwen3.5-35b-a3b-fp8`   | ~35GB      | 0.38     | 24GB     | 262K      | ~48GB      |
| Coder     | Qwen3-Coder-Next-int4 | `~/models/qwen3-coder-next-int4` | ~16GB      | 0.28     | 32GB     | 32K       | ~35GB      |
| Vision    | Qwen3-VL-4B           | `~/models/qwen3-vl-4b`           | ~8GB       | 0.04     | -        | 32K       | ~5GB       |
| **Total** |                       |                                  | **~59GB**  | **0.70** | **56GB** |           | **~88GB**  |

---

# Environment Variables Summary

All services use these environment variables for performance and stability:

| Variable | Value | Purpose |
|----------|-------|---------|
| `OMP_NUM_THREADS` | 8 (Main/Coder), 4 (Vision) | Thread control |
| `TOKENIZERS_PARALLELISM` | false | Prevent deadlocks |
| `CUDA_DEVICE_MAX_CONNECTIONS` | 1 | Reduce scheduler thrash |
| `VLLM_WORKER_MULTIPROC_METHOD` | spawn | Safe multiprocessing |

Additional optimizations are set via command-line flags:
- `--kv-cache-dtype fp8` (50% KV cache memory savings)
- `--attention-backend flashinfer` (optimized attention)
- `--max-num-seqs 2` (single-user concurrency)
