# Distributed Setup: DGX Spark (vLLM)

## Architecture Overview

| Component | Location | Responsibility |
|-----------|----------|----------------|
| vLLM Servers (3x) | DGX Spark | Model inference, GPU compute |
| Agent Scripts | Laptop | Orchestration, file I/O, human gates |
| CodeGraph Index | Laptop | Code embeddings, semantic search |
| Project Files | Laptop | Source code, specs, ADRs |

---

## Persistent Model Storage (Download Once)

Models are stored locally at `/opt/models/` to avoid re-downloading on every restart.

### Storage Layout

```
/opt/models/
├── qwen3.5-35b-a3b-fp8/         # Main agent (~70GB)
├── qwen3-coder-next-int4/        # Coder agent (~45GB)
└── qwen3-vl-4b/                  # Vision agent (~8GB)
```

### One-Time Download Script

Save as `download-models.sh` and run once:

```bash
#!/bin/bash
set -e

MODEL_DIR="/opt/models"
mkdir -p "$MODEL_DIR"

echo "=== Downloading models to $MODEL_DIR ==="
echo "Total: ~123GB. This will take a while on slow internet."
echo ""

# Main agent: Qwen3.5-35B-A3B-FP8
echo "[1/3] Downloading Qwen3.5-35B-A3B-FP8..."
if [ ! -d "$MODEL_DIR/qwen3.5-35b-a3b-fp8" ]; then
    huggingface-cli download Qwen/Qwen3.5-35B-A3B-FP8 \
        --local-dir "$MODEL_DIR/qwen3.5-35b-a3b-fp8" \
        --local-dir-use-symlinks False
else
    echo "    Already exists, skipping."
fi

# Coder agent: Qwen3-Coder-Next-int4-AutoRound
echo "[2/3] Downloading Qwen3-Coder-Next-int4-AutoRound..."
if [ ! -d "$MODEL_DIR/qwen3-coder-next-int4" ]; then
    huggingface-cli download Qwen/Qwen3-Coder-Next-int4-AutoRound \
        --local-dir "$MODEL_DIR/qwen3-coder-next-int4" \
        --local-dir-use-symlinks False
else
    echo "    Already exists, skipping."
fi

# Vision agent: Qwen3-VL-4B-Instruct
echo "[3/3] Downloading Qwen3-VL-4B-Instruct..."
if [ ! -d "$MODEL_DIR/qwen3-vl-4b" ]; then
    huggingface-cli download Qwen/Qwen3-VL-4B-Instruct \
        --local-dir "$MODEL_DIR/qwen3-vl-4b" \
        --local-dir-use-symlinks False
else
    echo "    Already exists, skipping."
fi

echo ""
echo "=== All models downloaded! ==="
echo "Total size: $(du -sh $MODEL_DIR | cut -f1)"
echo ""
echo "Disk check: Ensure /opt has at least 150GB free (models + cache)"
df -h /opt
```

**Run it:**
```bash
chmod +x download-models.sh
sudo mkdir -p /opt/models && sudo chown $USER:$USER /opt/models
./download-models.sh
```

### API Key Setup (One-Time)

```bash
# Generate unique keys for each service
mkdir -p ~/.keys
openssl rand -hex 32 > ~/.keys/vllm_main_key
openssl rand -hex 32 > ~/.keys/vllm_coder_key
openssl rand -hex 32 > ~/.keys/vllm_vision_key
chmod 600 ~/.keys/*

# Symlinks for systemd
ln -sf ~/.keys/vllm_main_key ~/.vllm_main_key
ln -sf ~/.keys/vllm_coder_key ~/.vllm_coder_key
ln -sf ~/.keys/vllm_vision_key ~/.vllm_vision_key
```

---

## DGX Spark: Systemd Services

Create these three files in `/etc/systemd/system/`:

### `/etc/systemd/system/vllm-main.service`

```ini
[Unit]
Description=vLLM Main Agent (Qwen3.5-35B-A3B-FP8)
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/agent-stack

# Prevent swapping
LimitMEMLOCK=infinity

# Logging - don't drop lines
LogRateLimitIntervalSec=0

# Thread control - prevent oversubscription
Environment="PATH=/home/youruser/agent-stack/.venv/bin:/usr/local/bin:/usr/bin"
Environment="CUDA_VISIBLE_DEVICES=0"
Environment="PYTHONUNBUFFERED=1"
Environment="VLLM_LOGGING_LEVEL=warning"
Environment="HF_HOME=/opt/models/.cache/huggingface"
Environment="VLLM_API_KEY_FILE=/home/youruser/.vllm_main_key"
Environment="VLLM_MARLIN_USE_ATOMIC_ADD=1"
Environment="VLLM_ATTENTION_BACKEND=FLASHINFER"
Environment="VLLM_CUDA_GRAPH_MODE=full_and_piecewise"
Environment="VLLM_WORKER_MULTIPROC_METHOD=spawn"
Environment="CUDA_DEVICE_MAX_CONNECTIONS=1"
Environment="OMP_NUM_THREADS=8"
Environment="MKL_NUM_THREADS=8"
Environment="NUMEXPR_NUM_THREADS=8"
Environment="TOKENIZERS_PARALLELISM=false"

# Main gets priority memory for reasoning/spec/architecture
ExecStart=/home/youruser/agent-stack/.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model /opt/models/qwen3.5-35b-a3b-fp8 \
  --served-model-name Qwen/Qwen3.5-35B-A3B-FP8 \
  --download-dir /opt/models \
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
StartLimitInterval=60s
StartLimitBurst=3

ExecStartPost=/bin/bash -c 'for i in {1..60}; do \
    curl -sf -H "Authorization: Bearer $(cat /home/youruser/.vllm_main_key)" \
    http://localhost:8000/health && exit 0; sleep 2; done; exit 1'

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/vllm-coder.service`

```ini
[Unit]
Description=vLLM Coder Agent (Qwen3-Coder-Next-int4-AutoRound)
After=network.target vllm-main.service

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/agent-stack

LimitMEMLOCK=infinity
LogRateLimitIntervalSec=0

Environment="PATH=/home/youruser/agent-stack/.venv/bin:/usr/local/bin:/usr/bin"
Environment="CUDA_VISIBLE_DEVICES=0"
Environment="PYTHONUNBUFFERED=1"
Environment="VLLM_LOGGING_LEVEL=warning"
Environment="HF_HOME=/opt/models/.cache/huggingface"
Environment="VLLM_API_KEY_FILE=/home/youruser/.vllm_coder_key"
Environment="VLLM_MARLIN_USE_ATOMIC_ADD=1"
Environment="VLLM_ATTENTION_BACKEND=FLASHINFER"
Environment="VLLM_CUDA_GRAPH_MODE=full_and_piecewise"
Environment="VLLM_WORKER_MULTIPROC_METHOD=spawn"
Environment="CUDA_DEVICE_MAX_CONNECTIONS=1"
Environment="OMP_NUM_THREADS=8"
Environment="MKL_NUM_THREADS=8"
Environment="NUMEXPR_NUM_THREADS=8"
Environment="TOKENIZERS_PARALLELISM=false"

ExecStart=/home/youruser/agent-stack/.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model /opt/models/qwen3-coder-next-int4 \
  --served-model-name Qwen/Qwen3-Coder-Next-int4-AutoRound \
  --download-dir /opt/models \
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
StartLimitInterval=60s
StartLimitBurst=3

ExecStartPost=/bin/bash -c 'for i in {1..60}; do \
    curl -sf -H "Authorization: Bearer $(cat /home/youruser/.vllm_coder_key)" \
    http://localhost:8001/health && exit 0; sleep 2; done; exit 1'

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/vllm-vision.service`

```ini
[Unit]
Description=vLLM Vision Model (Qwen3-VL-4B-Instruct)
After=network.target vllm-main.service vllm-coder.service

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/agent-stack

LimitMEMLOCK=infinity
LogRateLimitIntervalSec=0

Environment="PATH=/home/youruser/agent-stack/.venv/bin:/usr/local/bin:/usr/bin"
Environment="CUDA_VISIBLE_DEVICES=0"
Environment="PYTHONUNBUFFERED=1"
Environment="VLLM_LOGGING_LEVEL=warning"
Environment="HF_HOME=/opt/models/.cache/huggingface"
Environment="VLLM_API_KEY_FILE=/home/youruser/.vllm_vision_key"
Environment="VLLM_ATTENTION_BACKEND=FLASHINFER"
Environment="VLLM_CUDA_GRAPH_MODE=full_and_piecewise"
Environment="VLLM_WORKER_MULTIPROC_METHOD=spawn"
Environment="CUDA_DEVICE_MAX_CONNECTIONS=1"
Environment="OMP_NUM_THREADS=8"
Environment="MKL_NUM_THREADS=8"
Environment="NUMEXPR_NUM_THREADS=8"
Environment="TOKENIZERS_PARALLELISM=false"

ExecStart=/home/youruser/agent-stack/.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model /opt/models/qwen3-vl-4b \
  --served-model-name Qwen/Qwen3-VL-4B-Instruct \
  --download-dir /opt/models \
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
StartLimitInterval=60s
StartLimitBurst=3

ExecStartPost=/bin/bash -c 'for i in {1..60}; do \
    curl -sf -H "Authorization: Bearer $(cat /home/youruser/.vllm_vision_key)" \
    http://localhost:8002/health && exit 0; sleep 2; done; exit 1'

[Install]
WantedBy=multi-user.target
```

### Enable and Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable vllm-main vllm-coder vllm-vision
sudo systemctl start vllm-main vllm-coder vllm-vision

# Check status
sudo systemctl status vllm-main vllm-coder vllm-vision

# View logs (no rate limiting)
sudo journalctl -u vllm-main -f

# Check GPU memory
watch -n 1 nvidia-smi
```

### Test with API Key

```bash
curl -H "Authorization: Bearer $(cat ~/.vllm_main_key)" \
     http://localhost:8000/v1/models

# Test tool calling
curl -H "Authorization: Bearer $(cat ~/.vllm_main_key)" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "Qwen/Qwen3.5-35B-A3B-FP8",
       "messages": [{"role": "user", "content": "Generate a spec for OAuth2"}],
       "tools": [{
         "type": "function",
         "function": {
           "name": "generate_spec",
           "description": "Create a specification document",
           "parameters": {"type": "object", "properties": {"title": {"type": "string"}}}
         }
       }]
     }' \
     http://localhost:8000/v1/chat/completions
```

### Firewall

```bash
sudo ufw allow 8000/tcp
sudo ufw allow 8001/tcp
sudo ufw allow 8002/tcp
```

---

## Model Summary

| Agent | Model | Local Path | Size | GPU Mem | Swap | Est. VRAM | Key Optimizations |
|-------|-------|------------|------|---------|------|-----------|-------------------|
| **Main** | Qwen3.5-35B-A3B-FP8 | `/opt/models/qwen3.5-35b-a3b-fp8` | ~70GB | **0.55** | 16GB | **~70GB** | 262K context, swap safety |
| Coder | Qwen3-Coder-Next-int4 | `/opt/models/qwen3-coder-next-int4` | ~45GB | 0.33 | 16GB | ~42GB | 262K context, swap safety |
| Vision | Qwen3-VL-4B-Instruct | `/opt/models/qwen3-vl-4b` | ~8GB | 0.05 | - | ~6GB | `--enforce-eager`, bfloat16 |
| **Total** | | | **~123GB** | **0.93** | **32GB** | **~118GB** | **~10GB headroom** ✅ |

---

## Environment Variables Summary

| Variable | Value | Purpose |
|----------|-------|---------|
| `OMP_NUM_THREADS` | 8 | OpenMP parallelism |
| `MKL_NUM_THREADS` | 8 | Intel MKL BLAS threads |
| `NUMEXPR_NUM_THREADS` | 8 | NumExpr math threads |
| `TOKENIZERS_PARALLELISM` | false | Prevents tokenizer deadlock |
| `CUDA_DEVICE_MAX_CONNECTIONS` | 1 | Reduces scheduler thrash |
| `VLLM_WORKER_MULTIPROC_METHOD` | spawn | Safer multiprocessing |
