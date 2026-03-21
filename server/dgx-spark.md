# Distributed Setup: DGX Spark (vLLM with Docker)

## Architecture Overview

| Component | Location | Responsibility |
|-----------|----------|----------------|
| vLLM Servers (3x) | DGX Spark | Model inference, GPU compute (Docker containers) |
| Agent Scripts | Laptop | Orchestration, file I/O, human gates |
| CodeGraph Index | Laptop | Code embeddings, semantic search |
| Project Files | Laptop | Source code, specs, ADRs |

---

# Docker Setup

## Verify Docker is Installed

```bash
docker --version
```

## Verify GPU Access

```bash
# Test that Docker can access the GPU
sudo docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

You should see your GPU (NVIDIA GB10) and CUDA version.

## Enable Docker on Boot

```bash
sudo systemctl enable docker
```

## Add User to Docker Group (Optional QoL)

```bash
sudo usermod -aG docker $USER
newgrp docker  # or log out and back in
```

---

# Docker Network

```bash
docker network create vllm-net || true
```

---

# Hugging Face CLI Installation (Required)

The model download script requires the **Hugging Face CLI**.

## Install

```bash
curl -LsSf https://hf.co/cli/install.sh | bash
```

This installs to:

```
$HOME/.local/bin/hf
```

## Add to PATH

### Bash

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## Verify

```bash
hf --version
```

## Login

```bash
hf auth login
```

---

# Build Optimized Docker Images

Clone the spark-vllm-docker repository which contains optimized builds for DGX Spark:

```bash
git clone https://github.com/eugr/spark-vllm-docker.git
cd spark-vllm-docker
```

## Build Main Optimized Image (for Main and Vision Models)

```bash
# Build with Transformers 5 support
./build-and-copy.sh -t vllm-optimized --pre-tf
```

## Build GLM-Optimized Image (for Coder Model)

```bash
# Build with Transformers 5 and GLM patch baked in
./build-and-copy.sh -t vllm-optimized-glm --pre-tf --apply-mod mods/fix-glm-4.7-flash-AWQ
```

## Verify Images

```bash
docker images | grep vllm-optimized
```

You should see:
- `vllm-optimized` - for main and vision models
- `vllm-optimized-glm` - for GLM coder model

---

# Persistent Model Storage

```
~/models/
```

## Storage Layout

```
~/models/
├── qwen3.5-35b-a3b-fp8/
├── glm-4.7-flash-awq-4bit/
└── qwen3-vl-4b-instruct/
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

if ! hf whoami > /dev/null 2>&1; then
    echo "Run: hf auth login"
    exit 1
fi

# Download models
hf download Qwen/Qwen3.5-35B-A3B-FP8 --local-dir "$MODEL_DIR/qwen3.5-35b-a3b-fp8"
hf download cyankiwi/GLM-4.7-Flash-AWQ-4bit --local-dir "$MODEL_DIR/glm-4.7-flash-awq-4bit"
hf download Qwen/Qwen3-VL-4B-Instruct --local-dir "$MODEL_DIR/qwen3-vl-4b-instruct"

du -sh "$MODEL_DIR"
```

Run the script:

```bash
chmod +x download-models.sh
./download-models.sh
```

## Create Symlinks for Docker Access

```bash
# Create symlinks from /root/models to actual model locations
sudo ln -sf ~/models/qwen3.5-35b-a3b-fp8 /root/models/qwen3.5-35b-a3b-fp8
sudo ln -sf ~/models/glm-4.7-flash-awq-4bit /root/models/glm-4.7-flash-awq-4bit
sudo ln -sf ~/models/qwen3-vl-4b-instruct /root/models/qwen3-vl-4b-instruct
```

---

# Systemd Services
Create these files in:
```
/etc/systemd/system/
```

---

## vllm-main.service

```ini
[Unit]
Description=vLLM Main Agent (Qwen3.5-35B-A3B-FP8) - Optimized
After=network.target docker.service
Requires=docker.service

[Service]
Type=exec
User=root
Restart=always
RestartSec=10
TimeoutStartSec=600
TimeoutStopSec=120

ExecStartPre=-/usr/bin/docker rm -f vllm-main

ExecStart=/usr/bin/docker run --rm --pull=never --name vllm-main --gpus all --network vllm-net -p 8000:8000 -v /root/models:/root/.cache/huggingface -v /root/models:/models --ipc=host --shm-size=32g --ulimit memlock=-1 --ulimit stack=67108864 -e CUDA_VISIBLE_DEVICES=0 -e PYTHONUNBUFFERED=1 -e VLLM_LOGGING_LEVEL=warning -e HF_HOME=/root/.cache/huggingface -e VLLM_MARLIN_USE_ATOMIC_ADD=1 -e VLLM_ATTENTION_BACKEND=FLASHINFER -e VLLM_WORKER_MULTIPROC_METHOD=spawn -e CUDA_DEVICE_MAX_CONNECTIONS=1 -e OMP_NUM_THREADS=8 -e MKL_NUM_THREADS=8 -e NUMEXPR_NUM_THREADS=8 -e TOKENIZERS_PARALLELISM=false vllm-optimized vllm serve /models/qwen3.5-35b-a3b-fp8 --download-dir /models --served-model-name Qwen/Qwen3.5-35B-A3B-FP8 --port 8000 --host 0.0.0.0 --quantization fp8 --kv-cache-dtype fp8 --attention-backend flashinfer --gpu-memory-utilization 0.50 --kv-cache-memory-bytes 15000000000 --max-model-len 262144 --max-num-batched-tokens 32768 --max-num-seqs 2 --max-cudagraph-capture-size 10 --enable-prefix-caching --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 --mamba-ssm-cache-dtype float16 --trust-remote-code --load-format fastsafetensors

ExecStartPost=/bin/bash -c 'for i in {1..300}; do curl -sf http://localhost:8000/health && sleep 5 && exit 0; sleep 2; done; exit 1'
ExecStop=/usr/bin/docker stop vllm-main || true

[Install]
WantedBy=multi-user.target
```

**Performance:** ~49.5 t/s | **Memory:** ~53.8 GB

---

## vllm-coder.service

```ini
[Unit]
Description=vLLM Coder Agent (GLM-4.7-Flash-AWQ) - Optimized
After=network.target docker.service vllm-main.service
Requires=docker.service vllm-main.service

[Service]
Type=exec
User=root
Restart=always
RestartSec=10
TimeoutStartSec=600
TimeoutStopSec=120

ExecStartPre=-/usr/bin/docker rm -f vllm-coder

ExecStart=/usr/bin/docker run --rm --pull=never --name vllm-coder --gpus all --network vllm-net -p 8001:8001 -v /root/models:/root/.cache/huggingface -v /root/models:/models --ipc=host --shm-size=16g --ulimit memlock=-1 --ulimit stack=67108864 -e CUDA_VISIBLE_DEVICES=0 -e PYTHONUNBUFFERED=1 -e VLLM_LOGGING_LEVEL=warning -e HF_HOME=/root/.cache/huggingface -e VLLM_MARLIN_USE_ATOMIC_ADD=1 -e VLLM_WORKER_MULTIPROC_METHOD=spawn -e CUDA_DEVICE_MAX_CONNECTIONS=1 -e OMP_NUM_THREADS=8 -e MKL_NUM_THREADS=8 -e NUMEXPR_NUM_THREADS=8 -e TOKENIZERS_PARALLELISM=false vllm-optimized-glm vllm serve /models/glm-4.7-flash-awq-4bit --download-dir /models --tool-call-parser glm47 --reasoning-parser glm45 --enable-auto-tool-choice --served-model-name glm-4.7-flash --max-model-len 202752 --max-num-batched-tokens 4096 --max-num-seqs 64 --gpu-memory-utilization 0.30 --host 0.0.0.0 --port 8001 --trust-remote-code --load-format fastsafetensors

ExecStartPost=/bin/bash -c 'for i in {1..300}; do curl -sf http://localhost:8001/health && sleep 5 && exit 0; sleep 2; done; exit 1'
ExecStop=/usr/bin/docker stop vllm-coder || true

[Install]
WantedBy=multi-user.target
```

**Performance:** ~45.5 t/s | **Memory:** ~36.6 GB

---

## vllm-vision.service

```ini
[Unit]
Description=vLLM Vision Model (Qwen3-VL-4B-Instruct) - Optimized
After=network.target docker.service vllm-main.service vllm-coder.service
Requires=docker.service vllm-main.service vllm-coder.service

[Service]
Type=exec
User=root
Restart=always
RestartSec=10
TimeoutStartSec=600
TimeoutStopSec=120

ExecStartPre=-/usr/bin/docker rm -f vllm-vision

ExecStart=/usr/bin/docker run --rm --pull=never --name vllm-vision --gpus all --network vllm-net -p 8002:8002 -v /root/models:/root/.cache/huggingface -v /root/models:/models --ipc=host --shm-size=8g --ulimit memlock=-1 --ulimit stack=67108864 -e CUDA_VISIBLE_DEVICES=0 -e PYTHONUNBUFFERED=1 -e VLLM_LOGGING_LEVEL=warning -e HF_HOME=/root/.cache/huggingface -e VLLM_WORKER_MULTIPROC_METHOD=spawn -e CUDA_DEVICE_MAX_CONNECTIONS=1 -e OMP_NUM_THREADS=4 -e NUMEXPR_NUM_THREADS=4 -e TOKENIZERS_PARALLELISM=false vllm-optimized vllm serve /models/qwen3-vl-4b-instruct --download-dir /models --served-model-name Qwen/Qwen3-VL-4B-Instruct --port 8002 --host 0.0.0.0 --dtype bfloat16 --kv-cache-dtype fp8 --attention-backend flashinfer --gpu-memory-utilization 0.10 --kv-cache-memory-bytes 2500000000 --max-model-len 24576 --max-num-batched-tokens 4096 --max-num-seqs 1 --enforce-eager --trust-remote-code --load-format fastsafetensors

ExecStartPost=/bin/bash -c 'for i in {1..300}; do curl -sf http://localhost:8002/health && sleep 5 && exit 0; sleep 2; done; exit 1'
ExecStop=/usr/bin/docker stop vllm-vision || true

[Install]
WantedBy=multi-user.target
```

**Performance:** ~21.9 t/s | **Memory:** ~12.8 GB

---

# Enable + Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable vllm-main vllm-coder vllm-vision
sudo systemctl start vllm-main vllm-coder vllm-vision
```

---

# Check Status

```bash
sudo systemctl status vllm-main vllm-coder vllm-vision
```

---

# View Logs

```bash
# Systemd logs
sudo journalctl -u vllm-main -f
sudo journalctl -u vllm-coder -f
sudo journalctl -u vllm-vision -f

# Docker container logs
docker logs vllm-main -f
docker logs vllm-coder -f
docker logs vllm-vision -f
```

---

# Test API

```bash
# Test main model
curl http://localhost:8000/v1/models

# Test coder model
curl http://localhost:8001/v1/models

# Test vision model
curl http://localhost:8002/v1/models
```

---

# Performance Summary

| Model | Tokens/sec | GPU Memory | Port |
|-------|------------|------------|------|
| Qwen3.5-35B-FP8 (Main) | **49.5 t/s** | 53.8 GB | 8000 |
| GLM-4.7-Flash-AWQ (Coder) | **45.5 t/s** | 36.6 GB | 8001 |
| Qwen3-VL-4B (Vision) | **21.9 t/s** | 12.8 GB | 8002 |
| **Total** | - | **~103 GB** | - |

All three models run simultaneously on a single DGX Spark with 128 GB unified memory, leaving ~25 GB headroom for system processes and overhead.
