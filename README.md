# 🦒 Gironimo

A distributed AI development system named after a very brave stuffed giraffe. Runs large language models on DGX Spark while orchestrating **specification-driven workflows** from your laptop.

**Design philosophy:** Stand tall, see far, move deliberately.

---

## Architecture

```
┌─────────────────┐         Network           ┌─────────────────┐
│     Laptop      │  ═══════════════════════► │   DGX Spark     │
│                 │                           │                 │
│  🦒 Gironimo    │  ──► vLLM (35B)  :8000    │  GPU Compute    │
│  Orchestrator   │  ──► vLLM (GLM)  :8001    │  128GB VRAM     │
│  Scout Agent    │  ──► vLLM (Vision):8002   │                 │
│  CodeGraph      │                           │  Systemd        │
│  ADR Manager    │                           │  Auto-restart   │
│  (File I/O)     │                           │                 │
└─────────────────┘                           └─────────────────┘
```

---

## How Gironimo Differs

| Approach          | Flow Control        | Gates                       | Human Role         | Model Role        |
| ----------------- | ------------------- | --------------------------- | ------------------ | ----------------- |
| **Gironimo**      | Python orchestrator | Spec, architecture, staging | Judgment, approval | Focused execution |
| **Typical Agent** | Model decides       | Interrupt/override          | Monitor            | Plans + executes  |
| **Copilot**       | Developer           | Continuous                  | Writes code        | Autocomplete      |

Gironimo treats models as **deterministic components**, not autonomous agents.

---

## Philosophy: Spec-Driven Development

LLMs are powerful—but without structure, they drift.

Gironimo enforces a simple contract:

1. **Spec First** 📝
   Define *what* and *why*. Human-reviewed.

2. **Architecture Second** 🏗️
   Define *how*. Also human-gated.

3. **Implementation Last** 🛠️
   Generate code only after intent is validated.

This keeps output aligned with decisions—not guesses.

### Why CLI?

* **Transparent**: Every step is visible and interruptible
* **Versioned**: Specs, plans, ADRs live in git
* **Composable**: Unix-style tools, loosely coupled
* **Reproducible**: Stateless execution with explicit context

The pipeline extends your reach without hiding the work.

---

## Workflow

```
Request → Spec 🚪 → Scout 🔍 → Architecture 🚪 → Implementation → Review → Test → ADR 📚
```

**Execution model:**

* Parallel where safe (indexing, scanning, spec generation)
* Sequential where required (implementation after approved architecture)

**Two-model critique:**

* Main model generates
* Coder model reviews and challenges
* Revision loop until verification passes

**Knowledge capture:**

* ADRs are drafted automatically at each phase
* Past decisions feed future prompts
* Finalized by humans when complete

---

## Key Design Decisions

**Separate spec and architecture**
Different concerns, different reviewers. Prevents mixing intent with implementation.

**Two-model critique**
A second model catches what the first misses. This reduces silent failures.

**Human gates 🚪**
Critical decisions require approval:

* Requirements
* Architecture
* User-facing changes

**Auto-draft ADRs 📚**
Documentation is created by default, not as an afterthought.

**Local-first infrastructure**
Models, data, and execution stay under your control.

---

## Usage

```bash
./gironimo-run "Add OAuth2 authentication with Google and GitHub"
```

### Workflow Phases

1. **Spec generation** → 🚪 approve
2. **Context gathering** (docs + code)
3. **Architecture design** → 🚪 approve
4. **Implementation + critique loop**
5. **Testing**
6. **Staging (if UI)** → 🚪 approve
7. **Summary + ADR draft**

Apply results:

```bash
./gironimo/agent-scripts/finisher.py
```

---

## Safety Features 🛡️

**Patch validation**

* Blocks dangerous commands
* Detects destructive diffs
* Validates before apply

**Path restrictions**

* Limits writable directories

**Branch protection**

* Warns on main/master
* Encourages feature branches

---

## Observability 📊

Every LLM call reports:

* Tokens in/out
* Tokens/sec
* Latency
* KV cache usage
* Active requests

**Structured logs** + **response caching** included.

**Stateless calls**: context is injected per step, preventing drift across runs.

---

## Models 🧠

| Role       | Model       | Purpose                            |
| ---------- | ----------- | ---------------------------------- |
| 🦒 Main    | Qwen3.5-35B | Spec, architecture, implementation |
| ⚡ Coder    | GLM-4.7     | Critique, revision, verification   |
| 👁️ Vision | Qwen3-VL-4B | UI validation                      |

---

## Core Idea

AI is not the developer.
It is a tool in a controlled system.

Structure determines reliability.

---

*Stand tall. See far. Move deliberately.* 🦒✨
