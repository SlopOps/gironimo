# 🦒 Gironimo

A distributed AI development system named after a very brave stuffed giraffe. Runs large language models on DGX Spark while orchestrating specification-driven development workflows from your laptop.

## Architecture

```
┌─────────────────┐         Network           ┌─────────────────┐
│     Laptop      │  ═══════════════════════► │   DGX Spark     │
│                 │                           │                 │
│  🦒 Gironimo    │  ──► vLLM (35B)  :8000    │  GPU Compute    │
│  Orchestrator   │  ──► vLLM (Coder):8001    │  128GB VRAM     │
│  Scout Agent    │  ──► vLLM (Vision):8002   │                 │
│  CodeGraph      │                           │  Systemd        │
│  ADR Manager    │                           │  Auto-restart   │
│  (File I/O)     │                           │                 │
└─────────────────┘                           └─────────────────┘
```

**Design philosophy:** Stand tall, see far, move deliberately.

## How Gironimo Differs

| Approach | Flow Control | Human Role | Model Role |
|----------|--------------|------------|------------|
| **Gironimo** | Python orchestrator | Gates at decision points | Focused task execution |
| **Typical Agent** | Model decides | Monitor/Intervene | Plans + executes |
| **Copilot** | Developer | Writes code | Autocomplete |

Gironimo treats models as specialized components in a deterministic pipeline, not autonomous agents.

## Philosophy: Spec-Driven Development

Traditional development often drifts from intent. Gironimo enforces a contract:

1. **Spec First** 📝: Define what before how. The specification is a binding contract reviewed by humans.
2. **Architecture Second** 🏗️: Design how, separately. Architecture is also human-gated.
3. **Implementation Last** 🛠️: Code generation only after both spec and architecture are approved.

**Why CLI tools?**

- **Transparency**: Every step is visible, interruptible, modifiable
- **Version control**: Specs, plans, and ADRs are text files in git
- **Human agency**: Gates force reflection at high-leverage decision points
- **Composability**: Unix philosophy—tools do one thing, pipe together

Like a giraffe's long neck, the pipeline extends your reach while keeping your feet (and your data) firmly on the ground.

## Workflow

```
Request → Spec (human gate 🚪) → Scout (context 🔍) → Architecture (human gate 🚪) → Implementation → Review → Test → ADR 📚
```

**Parallel execution where safe:**
- Dependency scanning, CodeGraph indexing, and spec generation run simultaneously
- Sequential execution where order matters: implementation depends on approved architecture

**Two-model critique pattern:**
- Coder model reviews Main model's implementation
- High-severity issues trigger automatic revision
- Verification pass confirms fixes

**Automatic knowledge capture:**
- ADRs drafted at each phase capture decisions and lessons
- Lessons from past ADRs feed into future prompts
- Human finalizes with `--finalize` when satisfied

## Installation

### DGX Spark (GPU Server) — The Savannah

1. Install vLLM and dependencies:
```bash
mkdir ~/gironimo && cd ~/gironimo
uv venv --python 3.11
source .venv/bin/activate
uv pip install vllm
```

2. Install systemd services for auto-restart:
```bash
sudo cp systemd/vllm-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vllm-main vllm-coder vllm-vision
sudo systemctl start vllm-main vllm-coder vllm-vision
```

Services restart automatically on crash or reboot. The herd stays together.

### Laptop (Development Machine) — The Observer

1. Run setup script (installs uv, bun, and dependencies):
```bash
./gironimo/setup.sh
# Edit gironimo/.env with your DGX Spark IP
```

2. Configure environment:
```bash
# gironimo/.env file created by setup.sh
DGX_HOST=192.168.1.100
MAIN_PORT=8000
CODER_PORT=8001
VISION_PORT=8002
```

3. Activate environment:
```bash
source gironimo/.venv/bin/activate
```

## Usage

### Check System Health 🩺
```bash
./gironimo-run --check
```

### Run Development Workflow 🦒
```bash
./gironimo-run "Add OAuth2 authentication with Google and GitHub"
```

The orchestrator will:
1. **Phase 1: Discovery & Specification** (parallel)
   - Scan dependencies
   - Check CodeGraph index
   - Generate specification via `spec_agent.py`
   - 🚪 **Human gate**: Review and approve spec

2. **Phase 2: Documentation & Context** (parallel)
   - Fetch vendor documentation via `doc_scout.py`
   - Gather code context via `scout.py`
   - Load relevant lessons from past ADRs

3. **Phase 3: Architecture Design**
   - Generate architecture plan with context injection
   - 🚪 **Human gate**: Review and approve architecture

4. **Phase 4: Implementation & Review**
   - Generate implementation via Main model
   - Critique via Coder model (`reviewer.py --critique`)
   - Revise if needed (`reviewer.py --revise`)
   - Verify fixes (`reviewer.py --verify`)
   - Generate patch via `patcher.py`
   - Validate patch safety

5. **Phase 5: Testing**
   - Run tests via `tester.py`
   - Capture results

6. **Phase 6: Staging Review** (if UI changes detected)
   - Build Docker image via `staging.py`
   - Deploy and screenshot via `staging.py --review`
   - 🚪 **Human gate**: Approve or reject staging

7. **Final Summary**
   - Token usage report
   - Artifact locations
   - 📚 Draft ADR for finalization

### Apply Changes and Commit ✅
```bash
./gironimo/agent-scripts/finisher.py
```
Applies the validated patch, runs tests, and commits with message derived from spec.

### Review and Finalize ADRs 📚
```bash
./gironimo/agent-scripts/adr_manager.py --list
./gironimo/agent-scripts/adr_manager.py --finalize
```

### Repository Maintenance 🧹
```bash
./gironimo/agent-scripts/maintainer.py        # Quick formatters + ADR check
./gironimo/agent-scripts/maintainer.py --full # Deep maintenance (prune docs, refresh index, check large files)
```

## Project Structure

```
your-project/
├── gironimo/                 # Gironimo system directory 🦒
│   ├── agent-scripts/        # The Gironimo herd
│   │   ├── config.py         # Shared config, metrics, console, LLM client
│   │   ├── orchestrator.py   # Main workflow controller
│   │   ├── spec_agent.py     # Specification generation
│   │   ├── reviewer.py       # Two-model critique (critique/revise/verify)
│   │   ├── patcher.py        # Diff generation + validation
│   │   ├── scout.py          # Code context retrieval
│   │   ├── indexer.py        # CodeGraph index maintenance
│   │   ├── tester.py         # Test execution
│   │   ├── doc_scout.py      # Documentation fetcher
│   │   ├── vision.py         # UI validation via screenshots
│   │   ├── staging.py        # Docker + staging review
│   │   ├── finisher.py       # Apply + commit workflow
│   │   ├── maintainer.py     # Repo maintenance
│   │   └── adr_manager.py    # Architecture Decision Records
│   ├── temp/                 # Temporary files (gitignored)
│   │   ├── implementation.patch
│   │   ├── implementation.txt
│   │   ├── plan.txt
│   │   ├── adr_draft_*.txt
│   │   └── .orchestrator_state.json
│   ├── logs/                 # Structured JSON logs (gitignored)
│   │   └── gironimo.log
│   ├── .venv/                # Python virtual environment (gitignored)
│   ├── .env                  # Environment configuration (gitignored)
│   └── setup.sh              # Setup and migration script
├── specs/                    # Human-approved specifications 📝
│   └── feature-name/
│       └── spec.md
├── docs/
│   ├── adr/                  # Architecture Decision Records 📚
│   │   ├── 001-gironimo-stack.md
│   │   └── DRAFT-oauth2.md
│   └── vendor/               # Fetched dependency docs 📦
│       └── package-name/
├── .codegraph/               # Code index (gitignored) 🔍
├── gironimo-run              # Convenience symlink → gironimo/agent-scripts/orchestrator.py
└── .gitignore                # Gironimo entries added by setup.sh
```

## Key Design Decisions

**Why separate spec and architecture?**

The specification defines *what* and *why*. The architecture defines *how*. Separating them allows:
- Different reviewers (product vs. technical)
- Iteration on implementation approach without redefining requirements
- Reuse of specs across different technical approaches

**Why two-model critique?**

The Coder model (specialized for code) reviews the Main model's implementation:
- Catches bugs the generator missed
- Enforces security and performance standards
- Provides specific, actionable feedback
- Revision loop continues until verification passes

**Why human gates? 🚪**

LLMs are confident generators of plausible text. Human gates catch:
- Misunderstood requirements
- Overly complex architectures
- Security or compliance issues
- Opportunities for simplification

Like a giraffe surveying the landscape from above, human review spots issues invisible at ground level.

**Why auto-draft ADRs? 📚**

ADRs fail when writing them is optional work. Auto-drafting makes them unavoidable artifacts that humans only need to approve or refine. Past ADR lessons automatically feed into future prompts.

**Why CLI over GUI?**

- Scriptable and composable
- Works over SSH
- Integrates with existing editor workflows
- Transparent—every operation is visible

## Metrics and Observability 📊

Every LLM call displays:
- **💾 KV Cache usage**: GPU memory pressure on DGX Spark
- **⚡ Running/Waiting requests**: Load on remote servers
- **📥📤 Tokens in/out**: Actual usage vs. limits
- **🚀 Tokens/second**: Generation speed
- **⏱️ Time elapsed**: Wall-clock duration
- **💰 Budget remaining**: Workflow token tracking

Warnings at 75% token utilization help you catch approaches that may need decomposition.

**Structured logging** (`gironimo/logs/gironimo.log`):
```json
{"timestamp": "2024-01-15T09:23:17.342891", "event": "llm_call", "model": "Qwen/Qwen3.5-35B-A3B-FP8", "phase": "arch", "prompt_tokens": 1247, "completion_tokens": 892, "duration_ms": 2341.5, "success": true}
```

**Response caching**: Expensive operations (architecture, specification) are cached to avoid re-generation on retries.

## Troubleshooting 🔧

**DGX Spark unreachable:**
```bash
ssh $DGX_HOST sudo systemctl status vllm-main
ssh $DGX_HOST sudo journalctl -u vllm-main -f
ssh $DGX_HOST nvidia-smi
```

**Slow generation:**
- Check KV cache usage (high = memory pressure)
- Check running requests (should be 1 per model)
- Restart services if needed: `sudo systemctl restart vllm-main`

**Token budget exceeded:**
- Workflow has 50K token budget
- Check `gironimo/logs/gironimo.log` for usage by phase
- Consider breaking request into smaller features

**Workflow interrupted:**
- State is saved after each phase in `gironimo/temp/.orchestrator_state.json`
- Resume: `./gironimo-run --resume` (basic implementation)

## Models 🧠

| Role | Model | Quantization | Speed | Purpose |
|------|-------|--------------|-------|---------|
| 🦒 Main | Qwen3.5-35B-A3B-Instruct | FP8 | ~50 t/s | Spec, architecture, implementation reasoning |
| ⚡ Coder | Qwen3-Coder-Next-int4-AutoRound | int4 | ~69 t/s | Code critique, revision, verification |
| 👁️ Vision | Qwen3-VL-4B-Instruct | bfloat16 | ~60 t/s | UI validation via screenshots |

Selected for quality/speed tradeoff on DGX Spark 128GB VRAM. Tall models for tall tasks.

## Phase Limits ⏱️

| Phase | Timeout | Max Tokens | Purpose |
|-------|---------|------------|---------|
| spec | 60s | 4,000 | Specification generation |
| arch | 90s | 4,000 | Architecture design |
| impl | 120s | 6,000 | Implementation (largest) |
| review | 60s | 2,000 | Code critique |
| revision | 90s | 4,000 | Implementation revision |
| verify | 30s | 500 | Quick verification pass |

## Safety Features 🛡️

**Patch validation** (`patcher.py --validate`):
- Blocks dangerous patterns (`rm -rf /`, `mkfs`, `dd`, `sudo`, pipe-to-bash)
- Detects massive deletions (>50 lines without additions)
- Validates with `git apply --check` before application

**Path restrictions** (`ALLOWED_PATHS`):
- Only `src/`, `app/`, `lib/`, `tests/`, `docs/`, `scripts/` can be modified
- Prevents accidental changes to system files

**Branch protection** (`finisher.py`):
- Warns when on `main`/`master`
- Prompts to create feature branch

---

*For a certain brave giraffe who always reaches higher.* 🦒✨
```
