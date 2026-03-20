# Distributed Setup: DGX Spark (vLLM with Docker)

## Architecture Overview

| Component         | Location  | Responsibility                       |
| ----------------- | --------- | ------------------------------------ |
| vLLM Servers (3x) | DGX Spark | Model inference, GPU compute (Docker containers) |
| Agent Scripts     | Laptop    | Orchestration, file I/O, human gates |
| CodeGraph Index   | Laptop    | Code embeddings, semantic search     |
| Project Files     | Laptop    | Source code, specs, ADRs             |

---

# Docker Installation (Required)

## Install Docker Engine

```bash
# Update package index
sudo apt update

# Install prerequisites
sudo apt install -y ca-certificates curl

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## Install NVIDIA Container Toolkit

```bash
# Add NVIDIA package repositories
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install the toolkit
sudo apt update
sudo apt install -y nvidia-container-toolkit

# Configure Docker to use NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime= nvidia
sudo systemctl restart docker

# Verify NVIDIA Docker support
docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

## Add User to Docker Group (Optional, avoids sudo)

```bash
sudo usermod -aG docker $USER
newgrp docker  # or log out and back in
```

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

## Verify Installation

```bash
hf --version
```

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

# Docker Network Setup

Create a dedicated network for the vLLM containers:

```bash
docker network create vllm-net
```

---

# DGX Spark: Systemd Services

Create these files in:

```
/etc/systemd/system/
```

---

# vllm-main.service (Docker)

```
/etc/systemd/system/vllm-main.service
```

```ini
[Unit]
Description=vLLM Main Agent (Qwen3.5-35B-A3B-FP8) - Docker
After=network.target docker.target
Requires=docker.target

[Service]
Type=simple
User=%u
Restart=always
RestartSec=10
TimeoutStartSec=300
TimeoutStopSec=120

Environment="HOME=%h"
Environment="MODEL_DIR=%h/models"
Environment="API_KEY_FILE=%h/.vllm_main_key"

# Read API key from file
ExecStartPre=/bin/bash -c 'API_KEY=$$(cat %h/.vllm_main_key); echo "API_KEY=$$API_KEY" > /tmp/vllm_main_key.env'

ExecStart=/usr/bin/docker run \
  --rm \
  --name vllm-main \
  --runtime=nvidia \
  --gpus all \
  --network vllm-net \
  -p 8000:8000 \
  -v %h/models:/root/.cache/huggingface \
  -v %h/models:/models \
  --ipc=host \
  --shm-size=32g \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e VLLM_LOGGING_LEVEL=warning \
  -e VLLM_ATTENTION_BACKEND=FLASHINFER \
  -e VLLM_CUDA_GRAPH_MODE=full_and_piecewise \
  -e OMP_NUM_THREADS=8 \
  -e MKL_NUM_THREADS=8 \
  -e TOKENIZERS_PARALLELISM=false \
  -e VLLM_API_KEY=$$(cat %h/.vllm_main_key) \
  vllm/vllm-openai:latest \
  --model /models/qwen3.5-35b-a3b-fp8 \
  --served-model-name Qwen/Qwen3.5-35B-A3B-FP8 \
  --port 8000 \
  --host 0.0.0.0 \
  --quantization fp8 \
  --kv-cache-dtype fp8 \
  --gpu-memory-utilization 0.55 \
  --swap-space 16 \
  --max-model-len 262144 \
  --max-num-batched-tokens 32768 \
  --max-num-seqs 4 \
  --enable-prefix-caching \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen \
  --trust-remote-code

ExecStop=/usr/bin/docker stop vllm-main

[Install]
WantedBy=multi-user.target
```

---

# vllm-coder.service (Docker)

```
/etc/systemd/system/vllm-coder.service
```

```ini
[Unit]
Description=vLLM Coder Agent (Qwen3-Coder-Next-int4-AutoRound) - Docker
After=network.target docker.target vllm-main.service
Requires=docker.target

[Service]
Type=simple
User=%u
Restart=always
RestartSec=10
TimeoutStartSec=300
TimeoutStopSec=120

Environment="HOME=%h"
Environment="MODEL_DIR=%h/models"

ExecStart=/usr/bin/docker run \
  --rm \
  --name vllm-coder \
  --runtime=nvidia \
  --gpus all \
  --network vllm-net \
  -p 8001:8001 \
  -v %h/models:/root/.cache/huggingface \
  -v %h/models:/models \
  --ipc=host \
  --shm-size=16g \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e VLLM_LOGGING_LEVEL=warning \
  -e VLLM_ATTENTION_BACKEND=FLASHINFER \
  -e VLLM_CUDA_GRAPH_MODE=full_and_piecewise \
  -e OMP_NUM_THREADS=8 \
  -e MKL_NUM_THREADS=8 \
  -e TOKENIZERS_PARALLELISM=false \
  -e VLLM_API_KEY=$$(cat %h/.vllm_coder_key) \
  vllm/vllm-openai:latest \
  --model /models/qwen3-coder-next-int4 \
  --served-model-name Qwen/Qwen3-Coder-Next-int4-AutoRound \
  --port 8001 \
  --host 0.0.0.0 \
  --quantization int4 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.33 \
  --swap-space 16 \
  --max-model-len 262144 \
  --max-num-batched-tokens 32768 \
  --max-num-seqs 4 \
  --enable-prefix-caching \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --trust-remote-code

ExecStop=/usr/bin/docker stop vllm-coder

[Install]
WantedBy=multi-user.target
```

---

# vllm-vision.service (Docker)

```
/etc/systemd/system/vllm-vision.service
```

```ini
[Unit]
Description=vLLM Vision Model (Qwen3-VL-4B-Instruct) - Docker
After=network.target docker.target vllm-main.service vllm-coder.service
Requires=docker.target

[Service]
Type=simple
User=%u
Restart=always
RestartSec=10
TimeoutStartSec=300
TimeoutStopSec=120

Environment="HOME=%h"
Environment="MODEL_DIR=%h/models"

ExecStart=/usr/bin/docker run \
  --rm \
  --name vllm-vision \
  --runtime=nvidia \
  --gpus all \
  --network vllm-net \
  -p 8002:8002 \
  -v %h/models:/root/.cache/huggingface \
  -v %h/models:/models \
  --ipc=host \
  --shm-size=8g \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e VLLM_LOGGING_LEVEL=warning \
  -e VLLM_ATTENTION_BACKEND=FLASHINFER \
  -e OMP_NUM_THREADS=4 \
  -e TOKENIZERS_PARALLELISM=false \
  -e VLLM_API_KEY=$$(cat %h/.vllm_vision_key) \
  vllm/vllm-openai:latest \
  --model /models/qwen3-vl-4b \
  --served-model-name Qwen/Qwen3-VL-4B-Instruct \
  --port 8002 \
  --host 0.0.0.0 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.05 \
  --max-model-len 32768 \
  --max-num-batched-tokens 4096 \
  --max-num-seqs 2 \
  --enforce-eager \
  --trust-remote-code

ExecStop=/usr/bin/docker stop vllm-vision

[Install]
WantedBy=multi-user.target
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
# Systemd logs
sudo journalctl -u vllm-main -f

# Docker container logs
docker logs vllm-main -f
docker logs vllm-coder -f
docker logs vllm-vision -f
```

---

## Check GPU Memory

```bash
watch -n 1 nvidia-smi
```

---

## Test API

```bash
# Test main model
curl -H "Authorization: Bearer $(cat ~/.vllm_main_key)" \
http://localhost:8000/v1/models

# Test coder model
curl -H "Authorization: Bearer $(cat ~/.vllm_coder_key)" \
http://localhost:8001/v1/models

# Test vision model
curl -H "Authorization: Bearer $(cat ~/.vllm_vision_key)" \
http://localhost:8002/v1/models
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

| Agent     | Model                 | Path                             | Size       | GPU Mem  | Swap     | Est VRAM   |
| --------- | --------------------- | -------------------------------- | ---------- | -------- | -------- | ---------- |
| Main      | Qwen3.5-35B-A3B-FP8   | `~/models/qwen3.5-35b-a3b-fp8`   | ~70GB      | 0.55     | 16GB     | ~70GB      |
| Coder     | Qwen3-Coder-Next-int4 | `~/models/qwen3-coder-next-int4` | ~45GB      | 0.33     | 16GB     | ~42GB      |
| Vision    | Qwen3-VL-4B           | `~/models/qwen3-vl-4b`           | ~8GB       | 0.05     | -        | ~6GB       |
| **Total** |                       |                                  | **~123GB** | **0.93** | **32GB** | **~118GB** |

---

# Docker Management Commands

## Useful Docker Commands

```bash
# List running containers
docker ps

# View container logs
docker logs vllm-main

# Stop all containers
docker stop vllm-main vllm-coder vllm-vision

# Start containers manually (without systemd)
docker start vllm-main vllm-coder vllm-vision

# Remove stopped containers
docker container prune

# Check disk usage
docker system df

# Clean up unused images
docker image prune -a
```

---

# Troubleshooting

## Container Won't Start

Check Docker logs:

```bash
# Check if container exists
docker ps -a | grep vllm

# Remove stuck container
docker rm vllm-main

# Restart service
sudo systemctl restart vllm-main
```

## Out of Memory Errors

If you encounter OOM errors:

1. **Reduce GPU memory utilization** in service files:
   - Main: `--gpu-memory-utilization 0.45`
   - Coder: `--gpu-memory-utilization 0.28`
   - Vision: `--gpu-memory-utilization 0.03`

2. **Increase swap space** in Docker:
   ```ini
   --swap-space 32
   ```

3. **Use sequential loading** (already configured via systemd dependencies)

## CUDA Version Mismatch

If you get CUDA errors, ensure you're using the correct vLLM image:

```bash
# Pull a specific CUDA version
docker pull vllm/vllm-openai:latest-cu130

# Or use nightly build
docker pull vllm/vllm-openai:nightly
```

Update service files to use the specific image tag.

## Container Not Accessible

Check Docker network:

```bash
# Verify network exists
docker network ls | grep vllm-net

# Inspect container network
docker inspect vllm-main | grep IPAddress

# Test connectivity
docker exec vllm-main curl http://localhost:8000/health
```

---

# Environment Variables Summary

| Variable                       | Value | Purpose                    |
| ------------------------------ | ----- | -------------------------- |
| `OMP_NUM_THREADS`              | 8/4   | OpenMP parallelism         |
| `MKL_NUM_THREADS`              | 8     | BLAS thread control        |
| `TOKENIZERS_PARALLELISM`       | false | Prevent tokenizer deadlock |
| `VLLM_ATTENTION_BACKEND`       | FLASHINFER | Optimized attention |
| `VLLM_CUDA_GRAPH_MODE`         | full_and_piecewise | CUDA graph optimization |
| `CUDA_VISIBLE_DEVICES`         | 0     | GPU device selection |
