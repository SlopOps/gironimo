# Distributed Setup: DGX Spark (vLLM with Docker)

## Architecture Overview

| Component         | Location  | Responsibility                                   |
| ----------------- | --------- | ------------------------------------------------ |
| vLLM Servers (3x) | DGX Spark | Model inference, GPU compute (Docker containers) |
| Agent Scripts     | Laptop    | Orchestration, file I/O, human gates             |
| CodeGraph Index   | Laptop    | Code embeddings, semantic search                 |
| Project Files     | Laptop    | Source code, specs, ADRs                         |

---

# Docker Installation (Required)

## Install Docker Engine

```bash
sudo apt update
sudo apt install -y ca-certificates curl

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

---

## Install NVIDIA Container Toolkit

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit

sudo nvidia-ctk runtime configure --runtime=nvidia
sudo systemctl restart docker

docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

---

# Docker Network

```bash
docker network create vllm-net
```

---

# Systemd Services

---

## vllm-main.service

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
TimeoutStartSec=600

ExecStart=/usr/bin/docker run \
  --pull=never \
  --name vllm-main \
  --runtime=nvidia \
  --gpus all \
  --network vllm-net \
  -p 8000:8000 \
  -v %h/models:/root/.cache/huggingface \
  -v %h/models:/models \
  --ipc=host \
  --shm-size=32g \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e PYTHONUNBUFFERED=1 \
  -e HF_HOME=/root/.cache/huggingface \
  -e VLLM_API_KEY=$$(cat %h/.vllm_main_key) \
  -e VLLM_MARLIN_USE_ATOMIC_ADD=1 \
  -e VLLM_ATTENTION_BACKEND=FLASHINFER \
  -e VLLM_CUDA_GRAPH_MODE=full_and_piecewise \
  -e VLLM_WORKER_MULTIPROC_METHOD=spawn \
  -e CUDA_DEVICE_MAX_CONNECTIONS=1 \
  -e OMP_NUM_THREADS=8 \
  -e MKL_NUM_THREADS=8 \
  -e NUMEXPR_NUM_THREADS=8 \
  -e TOKENIZERS_PARALLELISM=false \
  vllm/vllm-openai:v0.17.1-cu130 \
  --model /models/qwen3.5-35b-a3b-fp8 \
  --served-model-name Qwen/Qwen3.5-35B-A3B-FP8 \
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

ExecStartPost=/bin/bash -c 'for i in {1..60}; do curl -sf http://localhost:8000/health && exit 0; sleep 2; done; exit 1'
ExecStop=/usr/bin/docker stop vllm-main

[Install]
WantedBy=multi-user.target
```

---

## vllm-coder.service

```ini
[Unit]
Description=vLLM Coder Agent - Docker
After=network.target docker.target vllm-main.service
Requires=docker.target

[Service]
Type=simple
User=%u
Restart=always
RestartSec=10

ExecStart=/usr/bin/docker run \
  --pull=never \
  --name vllm-coder \
  --runtime=nvidia \
  --gpus all \
  --network vllm-net \
  -p 8001:8001 \
  -v %h/models:/root/.cache/huggingface \
  -v %h/models:/models \
  --ipc=host \
  --shm-size=16g \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e PYTHONUNBUFFERED=1 \
  -e HF_HOME=/root/.cache/huggingface \
  -e VLLM_API_KEY=$$(cat %h/.vllm_coder_key) \
  -e VLLM_MARLIN_USE_ATOMIC_ADD=1 \
  -e VLLM_ATTENTION_BACKEND=FLASHINFER \
  -e VLLM_CUDA_GRAPH_MODE=full_and_piecewise \
  -e VLLM_WORKER_MULTIPROC_METHOD=spawn \
  -e CUDA_DEVICE_MAX_CONNECTIONS=1 \
  -e OMP_NUM_THREADS=8 \
  -e MKL_NUM_THREADS=8 \
  -e NUMEXPR_NUM_THREADS=8 \
  -e TOKENIZERS_PARALLELISM=false \
  vllm/vllm-openai:v0.17.1-cu130 \
  --model /models/qwen3-coder-next-int4 \
  --served-model-name Qwen/Qwen3-Coder-Next-int4-AutoRound \
  --port 8001 \
  --host 0.0.0.0 \
  --quantization int4 \
  --dtype bfloat16 \
  --load-format fastsafetensors \
  --gpu-memory-utilization 0.33 \
  --swap-space 16 \
  --max-model-len 262144 \
  --max-num-batched-tokens 32768 \
  --max-num-seqs 4 \
  --max-cudagraph-capture-size 10 \
  --enable-prefix-caching \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --trust-remote-code

ExecStop=/usr/bin/docker stop vllm-coder

[Install]
WantedBy=multi-user.target
```

---

## vllm-vision.service

```ini
[Unit]
Description=vLLM Vision Model - Docker
After=network.target docker.target vllm-main.service vllm-coder.service
Requires=docker.target

[Service]
Type=simple
User=%u
Restart=always
RestartSec=10

ExecStart=/usr/bin/docker run \
  --pull=never \
  --name vllm-vision \
  --runtime=nvidia \
  --gpus all \
  --network vllm-net \
  -p 8002:8002 \
  -v %h/models:/root/.cache/huggingface \
  -v %h/models:/models \
  --ipc=host \
  --shm-size=8g \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e PYTHONUNBUFFERED=1 \
  -e HF_HOME=/root/.cache/huggingface \
  -e VLLM_API_KEY=$$(cat %h/.vllm_vision_key) \
  -e VLLM_ATTENTION_BACKEND=FLASHINFER \
  -e VLLM_CUDA_GRAPH_MODE=full_and_piecewise \
  -e VLLM_WORKER_MULTIPROC_METHOD=spawn \
  -e CUDA_DEVICE_MAX_CONNECTIONS=1 \
  -e OMP_NUM_THREADS=4 \
  -e NUMEXPR_NUM_THREADS=4 \
  -e TOKENIZERS_PARALLELISM=false \
  vllm/vllm-openai:v0.17.1-cu130 \
  --model /models/qwen3-vl-4b \
  --served-model-name Qwen/Qwen3-VL-4B-Instruct \
  --port 8002 \
  --host 0.0.0.0 \
  --dtype bfloat16 \
  --load-format fastsafetensors \
  --gpu-memory-utilization 0.05 \
  --max-model-len 32768 \
  --max-num-batched-tokens 4096 \
  --max-num-seqs 2 \
  --max-cudagraph-capture-size 4 \
  --enforce-eager \
  --trust-remote-code

ExecStop=/usr/bin/docker stop vllm-vision

[Install]
WantedBy=multi-user.target
```
