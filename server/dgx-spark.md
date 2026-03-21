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

# Persistent Model Storage

```
~/models/
```

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

if ! hf whoami > /dev/null 2>&1; then
    echo "Run: hf auth login"
    exit 1
fi

hf download Qwen/Qwen3.5-35B-A3B-FP8 --local-dir "$MODEL_DIR/qwen3.5-35b-a3b-fp8"
hf download Qwen/Qwen3-Coder-Next-FP8 --local-dir "$MODEL_DIR/qwen3-coder-next-fp8"
hf download Qwen/Qwen3-VL-4B-Instruct --local-dir "$MODEL_DIR/qwen3-vl-4b-instruct"

du -sh "$MODEL_DIR"
```

Run the script:

```bash
chmod +x download-models.sh
./download-models.sh

ln -sf ~/models/qwen3.5-35b-a3b-fp8 /root/models/qwen3.5-35b-a3b-fp8
ln -sf ~/models/qwen3-coder-next-fp8 /root/models/qwen3-coder-next-fp8
ln -sf ~/models/qwen3-vl-4b-instruct /root/models/qwen3-vl-4b-instruct
```

---

# Pull vLLM Image

```bash
docker pull vllm/vllm-openai:v0.17.1-cu130
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
Description=vLLM Main Agent (Qwen3.5-35B-A3B-FP8) - Docker
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

ExecStart=/usr/bin/docker run --rm --pull=never --name vllm-main --gpus all --network vllm-net -p 8000:8000 -v /root/models:/root/.cache/huggingface -v /root/models:/models --ipc=host --shm-size=32g --ulimit memlock=-1 --ulimit stack=67108864 -e CUDA_VISIBLE_DEVICES=0 -e PYTHONUNBUFFERED=1 -e VLLM_LOGGING_LEVEL=warning -e HF_HOME=/root/.cache/huggingface -e VLLM_MARLIN_USE_ATOMIC_ADD=1 -e VLLM_ATTENTION_BACKEND=FLASHINFER -e VLLM_CUDA_GRAPH_MODE=full_and_piecewise -e VLLM_WORKER_MULTIPROC_METHOD=spawn -e CUDA_DEVICE_MAX_CONNECTIONS=1 -e OMP_NUM_THREADS=8 -e MKL_NUM_THREADS=8 -e NUMEXPR_NUM_THREADS=8 -e TOKENIZERS_PARALLELISM=false vllm/vllm-openai:v0.17.1-cu130 --model /models/qwen3.5-35b-a3b-fp8 --download-dir /models --served-model-name Qwen/Qwen3.5-35B-A3B-FP8 --port 8000 --host 0.0.0.0 --quantization fp8 --kv-cache-dtype fp8 --attention-backend flashinfer --gpu-memory-utilization 0.38 --swap-space 24 --max-model-len 262144 --max-num-batched-tokens 32768 --max-num-seqs 2 --max-cudagraph-capture-size 10 --enable-prefix-caching --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 --mamba-ssm-cache-dtype float16 --trust-remote-code

ExecStartPost=/bin/bash -c 'for i in {1..300}; do curl -sf http://localhost:8000/health && sleep 5 && exit 0; sleep 2; done; exit 1'
ExecStop=/usr/bin/docker stop vllm-main || true

[Install]
WantedBy=multi-user.target
```

---

## vllm-coder.service

```ini
[Unit]
Description=vLLM Coder Agent (Qwen3-Coder-Next-int4-AutoRound) - Docker
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

ExecStart=/usr/bin/docker run --rm --pull=never --name vllm-coder --gpus all --network vllm-net -p 8001:8001 -v /root/models:/root/.cache/huggingface -v /root/models:/models --ipc=host --shm-size=16g --ulimit memlock=-1 --ulimit stack=67108864 -e CUDA_VISIBLE_DEVICES=0 -e PYTHONUNBUFFERED=1 -e VLLM_LOGGING_LEVEL=warning -e HF_HOME=/root/.cache/huggingface -e VLLM_MARLIN_USE_ATOMIC_ADD=1 -e VLLM_WORKER_MULTIPROC_METHOD=spawn -e CUDA_DEVICE_MAX_CONNECTIONS=1 -e OMP_NUM_THREADS=8 -e MKL_NUM_THREADS=8 -e NUMEXPR_NUM_THREADS=8 -e TOKENIZERS_PARALLELISM=false -e VLLM_TARGET_DEVICE=cuda vllm/vllm-openai:v0.17.1-cu130 --model /models/qwen3-coder-next-int4-autoround --download-dir /models --served-model-name Intel/Qwen3-Coder-Next-int4-AutoRound --port 8001 --host 0.0.0.0 --quantization int4 --dtype bfloat16 --gpu-memory-utilization 0.20 --kv-cache-memory-bytes 12000000000 --max-model-len 24576 --max-num-batched-tokens 12288 --max-num-seqs 2 --max-cudagraph-capture-size 4 --attention-backend flashinfer --enable-prefix-caching --enable-auto-tool-choice --tool-call-parser qwen3_coder --trust-remote-code

ExecStartPost=/bin/bash -c 'for i in {1..300}; do curl -sf http://localhost:8001/health && sleep 5 && exit 0; sleep 2; done; exit 1'
ExecStop=/usr/bin/docker stop vllm-coder || true

[Install]
WantedBy=multi-user.target
```

---

## vllm-vision.service

```ini
[Unit]
Description=vLLM Vision Model (Qwen3-VL-4B-Instruct) - Docker
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

ExecStart=/usr/bin/docker run --rm --pull=never --name vllm-vision --gpus all --network vllm-net -p 8002:8002 -v /root/models:/root/.cache/huggingface -v /root/models:/models --ipc=host --shm-size=8g --ulimit memlock=-1 --ulimit stack=67108864 -e CUDA_VISIBLE_DEVICES=0 -e PYTHONUNBUFFERED=1 -e VLLM_LOGGING_LEVEL=warning -e HF_HOME=/root/.cache/huggingface -e VLLM_WORKER_MULTIPROC_METHOD=spawn -e CUDA_DEVICE_MAX_CONNECTIONS=1 -e OMP_NUM_THREADS=4 -e NUMEXPR_NUM_THREADS=4 -e TOKENIZERS_PARALLELISM=false vllm/vllm-openai:v0.17.1-cu130 --model /models/qwen3-vl-4b-instruct --download-dir /models --served-model-name Qwen/Qwen3-VL-4B-Instruct --port 8002 --host 0.0.0.0 --dtype bfloat16 --kv-cache-dtype fp8 --attention-backend flashinfer --gpu-memory-utilization 0.10 --kv-cache-memory-bytes 3000000000 --max-model-len 32768 --max-num-batched-tokens 4096 --max-num-seqs 1 --enforce-eager --trust-remote-code

ExecStartPost=/bin/bash -c 'for i in {1..300}; do curl -sf http://localhost:8002/health && sleep 5 && exit 0; sleep 2; done; exit 1'
ExecStop=/usr/bin/docker stop vllm-vision || true

[Install]
WantedBy=multi-user.target
```

---

## Enable + Start

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
sudo journalctl -u vllm-coder -f
sudo journalctl -u vllm-vision -f

# Docker container logs
docker logs vllm-main -f
docker logs vllm-coder -f
docker logs vllm-vision -f
```

---

## Test API

```bash
# Test main model
curl http://localhost:8000/v1/models

# Test coder model
curl http://localhost:8001/v1/models

# Test vision model
curl http://localhost:8002/v1/models
```

---

## Firewall (if needed)

```bash
sudo ufw allow 8000/tcp
sudo ufw allow 8001/tcp
sudo ufw allow 8002/tcp
```
