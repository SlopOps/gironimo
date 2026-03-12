"""Gironimo shared configuration and utilities"""

import os
import time
import requests
import re
import json
from datetime import datetime
from pathlib import Path

# Project paths
PROJECT_ROOT = Path.cwd()
GIRONIMO_DIR = PROJECT_ROOT / "gironimo"
TEMP_DIR = GIRONIMO_DIR / "temp"
LOGS_DIR = GIRONIMO_DIR / "logs"

# Create directories
TEMP_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Remote server configuration
DGX_HOST = os.getenv('DGX_HOST', 'localhost')
MAIN_PORT = os.getenv('MAIN_PORT', '8000')
CODER_PORT = os.getenv('CODER_PORT', '8001')
VISION_PORT = os.getenv('VISION_PORT', '8002')

URLS = {
    'main': f"http://{DGX_HOST}:{MAIN_PORT}",
    'coder': f"http://{DGX_HOST}:{CODER_PORT}",
    'vision': f"http://{DGX_HOST}:{VISION_PORT}",
}

MODELS = {
    'main': 'Qwen/Qwen3-Next-80B-A3B-Instruct-FP8',
    'coder': 'Qwen/Qwen3-Coder-Next-int4-AutoRound',
    'vision': 'Qwen/Qwen2-VL-7B-Instruct',
}

# Phase limits with token budgets
LIMITS = {
    'spec': {'timeout': 60, 'max_tokens': 4000, 'budget': 4000},
    'arch': {'timeout': 90, 'max_tokens': 4000, 'budget': 4000},
    'impl': {'timeout': 120, 'max_tokens': 6000, 'budget': 6000},
    'review': {'timeout': 60, 'max_tokens': 2000, 'budget': 2000},
    'revision': {'timeout': 90, 'max_tokens': 4000, 'budget': 4000},
    'verify': {'timeout': 30, 'max_tokens': 500, 'budget': 500},
}

# Global workflow token budget
WORKFLOW_TOKEN_BUDGET = 50000
TOKEN_WARNING_PCT = 75

# Allowed file paths for patches
ALLOWED_PATHS = [
    "src/",
    "app/",
    "lib/",
    "tests/",
    "docs/",
    "scripts/",
]

# Required directories
REQUIRED_DIRS = [
    "specs",
    "docs/adr",
    "docs/vendor",
]


class Metrics:
    """Track LLM performance metrics"""
    
    @staticmethod
    def get_usage(endpoint_url):
        """Get current context window usage from vLLM metrics endpoint"""
        try:
            r = requests.get(f"{endpoint_url}/metrics", timeout=2)
            if r.status_code == 200:
                metrics = r.text
                
                cache_match = re.search(r'vllm:gpu_cache_usage_perc\{.*\}\s+([\d.]+)', metrics)
                cache_pct = float(cache_match.group(1)) * 100 if cache_match else None
                
                seq_match = re.search(r'vllm:num_requests_running\{.*\}\s+(\d+)', metrics)
                running = int(seq_match.group(1)) if seq_match else 0
                
                wait_match = re.search(r'vllm:num_requests_waiting\{.*\}\s+(\d+)', metrics)
                waiting = int(wait_match.group(1)) if wait_match else 0
                
                return {
                    'cache_usage_pct': cache_pct,
                    'running_requests': running,
                    'waiting_requests': waiting
                }
        except Exception:
            pass
        return None
    
    @staticmethod
    def calculate_tps(prompt_tokens, completion_tokens, duration_ms):
        """Calculate tokens per second"""
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
        if duration_ms and duration_ms > 0:
            tps = (total_tokens / (duration_ms / 1000))
            return round(tps, 1)
        return None


class TokenTracker:
    """Track token usage across workflow"""
    
    def __init__(self, budget=WORKFLOW_TOKEN_BUDGET):
        self.budget = budget
        self.used = 0
        self.phases = {}
    
    def add(self, phase, tokens):
        self.used += tokens
        self.phases[phase] = self.phases.get(phase, 0) + tokens
    
    def can_proceed(self, estimated=None):
        if estimated:
            return self.used + estimated <= self.budget
        return self.used <= self.budget
    
    def warning(self):
        pct = (self.used / self.budget) * 100
        if pct >= TOKEN_WARNING_PCT:
            return f"Token budget: {pct:.0f}% used ({self.budget - self.used} remaining)"
        return None
    
    def summary(self):
        """Return token usage summary"""
        return {
            'budget': self.budget,
            'used': self.used,
            'remaining': self.budget - self.used,
            'percent': (self.used / self.budget) * 100,
            'phases': self.phases
        }


class ResponseCache:
    """Simple LRU cache for LLM responses"""
    
    def __init__(self, max_size=100, ttl_seconds=3600):
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl_seconds
    
    def key(self, messages, phase):
        """Generate cache key from messages"""
        content = "".join([str(m.get("content", "")) for m in messages])
        return f"{phase}:{hash(content)}"
    
    def get(self, messages, phase):
        """Get cached response if available and fresh"""
        key = self.key(messages, phase)
        if key in self.cache:
            timestamp, response = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return response
            else:
                del self.cache[key]
        return None
    
    def set(self, messages, phase, response):
        """Cache response"""
        key = self.key(messages, phase)
        
        if len(self.cache) >= self.max_size:
            oldest = min(self.cache.keys(), key=lambda k: self.cache[k][0])
            del self.cache[oldest]
        
        self.cache[key] = (time.time(), response)


class StructuredLogger:
    """JSON-structured logging"""
    
    def __init__(self, log_file="gironimo.log"):
        self.log_file = LOGS_DIR / log_file
    
    def log(self, event_type, **kwargs):
        """Log structured event"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": event_type,
            **kwargs
        }
        
        with open(self.log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        if event_type in ["error", "warning"]:
            print(f"[{event_type}] {kwargs.get('message', '')}")


class Console:
    """Console output with metrics"""
    
    COLORS = {
        'reset': '\033[0m',
        'bold': '\033[1m',
        'dim': '\033[2m',
        'blue': '\033[34m',
        'green': '\033[32m',
        'yellow': '\033[33m',
        'red': '\033[31m',
        'cyan': '\033[36m',
    }
    
    @classmethod
    def color(cls, text, color):
        return f"{cls.COLORS.get(color, '')}{text}{cls.COLORS['reset']}"
    
    @classmethod
    def header(cls, text):
        print(f"\n{cls.color('═' * 60, 'bold')}")
        print(cls.color(f"  {text}", 'bold'))
        print(f"{cls.color('═' * 60, 'bold')}")
    
    @classmethod
    def phase(cls, num, name, status="starting"):
        icons = {
            "starting": cls.color("○", "yellow"),
            "running": cls.color("◐", "cyan"),
            "done": cls.color("✓", "green"),
            "error": cls.color("✗", "red"),
            "skipped": cls.color("-", "dim"),
        }
        icon = icons.get(status, "○")
        print(f"\n{icon} {cls.color(f'Phase {num}:', 'bold')} {name}")
    
    @classmethod
    def llm_call(cls, model, prompt_tokens=None, max_tokens=None, timeout=None, endpoint=None):
        print(f"  📝 LLM Call: {cls.color(model, 'cyan')}")
        
        if endpoint:
            usage = Metrics.get_usage(endpoint)
            if usage:
                cache_pct = usage.get('cache_usage_pct')
                if cache_pct is not None:
                    color = 'green' if cache_pct < 50 else 'yellow' if cache_pct < 80 else 'red'
                    print(f"    💾 KV Cache: {cls.color(f'{cache_pct:.1f}%', color)} used")
                
                if usage.get('running_requests'):
                    print(f"    ⚡ Running: {usage['running_requests']}")
                if usage.get('waiting_requests'):
                    print(f"    ⏳ Waiting: {usage['waiting_requests']}")
        
        if prompt_tokens:
            print(f"    📥 Input: ~{prompt_tokens} tokens")
        if max_tokens:
            print(f"    📤 Max output: {max_tokens} tokens")
        if timeout:
            print(f"    ⏱ Timeout: {timeout}s")
    
    @classmethod
    def llm_result(cls, prompt_tokens, completion_tokens, duration_ms, max_tokens=None):
        tps = Metrics.calculate_tps(prompt_tokens, completion_tokens, duration_ms)
        
        print(f"    ✓ Complete")
        
        metrics = []
        if prompt_tokens:
            metrics.append(f"in: {prompt_tokens}")
        if completion_tokens:
            metrics.append(f"out: {completion_tokens}")
        if tps:
            speed_color = 'green' if tps > 40 else 'yellow' if tps > 20 else 'red'
            metrics.append(f"{cls.color(f'{tps} t/s', speed_color)}")
        if duration_ms:
            metrics.append(f"time: {duration_ms/1000:.2f}s")
        
        if metrics:
            print(f"    📊 {', '.join(metrics)}")
        
        if completion_tokens and max_tokens:
            usage_pct = (completion_tokens / max_tokens) * 100
            if usage_pct >= TOKEN_WARNING_PCT:
                remaining = max_tokens - completion_tokens
                print(f"    ⚠ High token usage: {usage_pct:.0f}% ({remaining} remaining)")
                if usage_pct >= 90:
                    print(f"    ⚠ Near limit - consider breaking into smaller requests")
    
    @classmethod
    def tool_call(cls, agent, action, details="", timing=None):
        time_str = f" ({timing:.1f}s)" if timing else ""
        print(f"  → {cls.color(agent, 'cyan')}:{action}{cls.color(time_str, 'dim')}")
        if details:
            print(f"    {cls.color(details, 'dim')}")
    
    @classmethod
    def parallel_start(cls, name):
        print(f"\n  ▶ {cls.color(name, 'bold')} (parallel)")
    
    @classmethod
    def parallel_done(cls, name, results):
        print(f"  ▼ {name} complete:")
        for item in results:
            status = "✓" if item.get('ok') else "✗"
            time_str = f" ({item.get('time', 0):.1f}s)" if 'time' in item else ""
            print(f"    {status} {item.get('name', 'task')}: {item.get('status', 'done')}{cls.color(time_str, 'dim')}")
    
    @classmethod
    def human_gate(cls, artifact, description):
        print(f"\n{cls.color('┌' + '─' * 58 + '┐', 'yellow')}")
        print(cls.color(f"│  HUMAN REVIEW REQUIRED: {description[:35]:35} │", 'yellow'))
        print(cls.color(f"└{'─' * 58}┘", 'yellow'))
        print(f"  File: {cls.color(artifact, 'bold')}")
    
    @classmethod
    def result(cls, status, message=""):
        if status == "success":
            print(f"    ✓ {message or 'Success'}")
        elif status == "error":
            print(f"    ✗ {message or 'Failed'}")
        elif status == "warning":
            print(f"    ⚠ {message}")
        elif status == "skipped":
            print(f"    - {message or 'Skipped'}")
    
    @classmethod
    def timing(cls, label, seconds):
        print(f"  ⏱ {label}: {cls.color(f'{seconds:.2f}s', 'cyan')}")
    
    @classmethod
    def final_summary(cls, artifacts, total_time=None):
        print(f"\n{cls.color('═' * 60, 'bold')}")
        print(cls.color("  WORKFLOW COMPLETE", 'bold'))
        print(f"{cls.color('═' * 60, 'bold')}")
        print("\nArtifacts:")
        for name, path in artifacts.items():
            exists = "✓" if Path(path).exists() else "✗"
            print(f"  {exists} {cls.color(name + ':', 'bold')} {path}")
        
        if total_time:
            print(f"\n  ⏱ Total time: {cls.color(f'{total_time:.1f}s', 'cyan')}")
    
    @classmethod
    def adr_pending(cls):
        print(f"\n  📝 ADR drafted: {TEMP_DIR}/adr_draft_*.txt")
        print(f"     Run: {cls.color('./gironimo/agent-scripts/adr_manager.py --finalize', 'cyan')}")


# Global instances
_token_tracker = None
_response_cache = ResponseCache()
_structured_logger = StructuredLogger()


def get_token_tracker():
    """Get or create global token tracker"""
    global _token_tracker
    if _token_tracker is None:
        _token_tracker = TokenTracker()
    return _token_tracker


def get_response_cache():
    """Get global response cache"""
    return _response_cache


def get_logger():
    """Get global structured logger"""
    return _structured_logger


def call_model(endpoint, messages, phase='spec', retry=False, token_tracker=None, use_cache=True):
    """
    Call remote vLLM with token tracking and caching
    """
    limits = LIMITS.get(phase, LIMITS['spec'])
    model = MODELS.get(endpoint, MODELS['main'])
    url = f"{URLS[endpoint]}/v1/chat/completions"
    endpoint_url = URLS[endpoint]
    
    if use_cache:
        cached = _response_cache.get(messages, phase)
        if cached:
            Console.result("success", "Using cached response")
            return True, cached
    
    prompt_text = " ".join([str(m.get("content", "")) for m in messages])
    prompt_tokens = len(prompt_text) // 4
    
    if token_tracker:
        estimated_total = prompt_tokens + limits['max_tokens']
        if not token_tracker.can_proceed(estimated_total):
            Console.result("error", f"Token budget exceeded. Used: {token_tracker.used}, Need: {estimated_total}")
            return False, "Token budget exceeded"
    
    start_time = time.time()
    
    try:
        Console.llm_call(model, prompt_tokens, limits['max_tokens'], 
                        limits['timeout'], endpoint=endpoint_url)
        
        r = requests.post(
            url,
            json={
                "model": model,
                "messages": messages,
                "max_tokens": limits['max_tokens'],
                "temperature": 0.7
            },
            timeout=limits['timeout']
        )
        r.raise_for_status()
        
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        
        result = r.json()
        content = result['choices'][0]['message']['content']
        
        usage = result.get('usage', {})
        actual_prompt = usage.get('prompt_tokens', prompt_tokens)
        actual_completion = usage.get('completion_tokens', len(content) // 4)
        
        if token_tracker:
            token_tracker.add(phase, actual_prompt + actual_completion)
        
        Console.llm_result(actual_prompt, actual_completion, duration_ms, 
                          max_tokens=limits['max_tokens'])
        
        if token_tracker:
            warning = token_tracker.warning()
            if warning:
                Console.result("warning", warning)
        
        if use_cache:
            _response_cache.set(messages, phase, content)
        
        _structured_logger.log(
            "llm_call",
            model=model,
            phase=phase,
            prompt_tokens=actual_prompt,
            completion_tokens=actual_completion,
            duration_ms=duration_ms,
            success=True
        )
        
        return True, content
        
    except requests.Timeout:
        msg = f"Timeout after {limits['timeout']}s"
        if not retry:
            Console.result("warning", "Timeout, retrying...")
            time.sleep(5)
            return call_model(endpoint, messages, phase, retry=True, token_tracker=token_tracker, use_cache=use_cache)
        
        msg += f"\n  DGX Spark ({endpoint_url}) may be:"
        msg += "\n    - Warming up (wait 30s, retry)"
        msg += "\n    - Out of VRAM (check: ssh dgx nvidia-smi)"
        msg += f"\n    - Crashed (check: ssh dgx sudo systemctl status vllm-{endpoint})"
        
        _structured_logger.log("llm_error", model=model, phase=phase, error="timeout", message=msg)
        return False, msg
        
    except Exception as e:
        error_msg = str(e)
        _structured_logger.log("llm_error", model=model, phase=phase, error=error_msg)
        return False, error_msg
