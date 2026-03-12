#!/usr/bin/env python3
"""
Gironimo Orchestrator - Main workflow controller
Runs on laptop, coordinates all agents and phases
"""

import requests
import subprocess
import sys
import json
import concurrent.futures
import time
import re
import os
from datetime import datetime
from pathlib import Path

from config import (
    URLS, MODELS, LIMITS, Console, Metrics, 
    TokenTracker, ResponseCache, StructuredLogger,
    get_token_tracker, get_response_cache, get_logger,
    call_model, REQUIRED_DIRS, WORKFLOW_TOKEN_BUDGET,
    PROJECT_ROOT, GIRONIMO_DIR, TEMP_DIR, LOGS_DIR
)

AGENT_DIR = GIRONIMO_DIR / "agent-scripts"
STATE_FILE = TEMP_DIR / ".orchestrator_state.json"
WORKFLOW_LOG = LOGS_DIR / "workflow.log"

# Global instances
token_tracker = get_token_tracker()
response_cache = get_response_cache()
logger = get_logger()


def log_event(agent, action, status, details=""):
    """Simple workflow logging"""
    log = {
        "time": datetime.now().isoformat(),
        "agent": agent,
        "action": action,
        "status": status,
        "details": details
    }
    with open(WORKFLOW_LOG, "a") as f:
        f.write(json.dumps(log) + "\n")
    
    logger.log("agent_event", agent=agent, action=action, status=status, details=details)


def check_servers():
    """Check remote DGX Spark servers"""
    servers = [
        (URLS['main'] + "/v1/models", "Main 80B"),
        (URLS['coder'] + "/v1/models", "Coder"),
        (URLS['vision'] + "/v1/models", "Vision"),
    ]
    ok = True
    for url, name in servers:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                print(f"  {name}: ok")
            else:
                print(f"  {name}: error {r.status_code}")
                ok = False
        except Exception as e:
            print(f"  {name}: unreachable ({e})")
            ok = False
    return ok


def ensure_directories():
    """Create required directories if they don't exist"""
    for d in REQUIRED_DIRS:
        path = PROJECT_ROOT / d
        path.mkdir(parents=True, exist_ok=True)
        Console.result("success" if path.exists() else "error", 
                      f"Directory: {d}")


def scan_dependencies():
    """Fast local dependency scan"""
    deps = []
    
    req = PROJECT_ROOT / "requirements.txt"
    if req.exists():
        deps.extend([l.strip() for l in req.read_text().split('\n') 
                    if l.strip() and not l.startswith('#')])
    
    pkg = PROJECT_ROOT / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            deps.extend(list(data.get("dependencies", {}).keys()))
        except:
            pass
    
    go_mod = PROJECT_ROOT / "go.mod"
    if go_mod.exists():
        with open(go_mod) as f:
            for line in f:
                if line.strip() and not line.startswith(('module', 'go ', 'require', ')')):
                    deps.append(line.strip())
    
    cargo = PROJECT_ROOT / "Cargo.toml"
    if cargo.exists():
        in_deps = False
        with open(cargo) as f:
            for line in f:
                if '[dependencies]' in line:
                    in_deps = True
                elif in_deps and line.strip() and not line.startswith('['):
                    deps.append(line.split('=')[0].strip())
                elif line.startswith('['):
                    in_deps = False
    
    deps_file = TEMP_DIR / ".dependencies.txt"
    deps_file.write_text('\n'.join(sorted(set(deps))))
    return deps


def run_agent(script, args="", stdin_data=None, timeout=120):
    """Run another agent script"""
    script_path = AGENT_DIR / script
    cmd = f"timeout {timeout + 10} {script_path} {args}"
    try:
        if stdin_data:
            result = subprocess.run(cmd, shell=True, input=stdin_data,
                                  capture_output=True, text=True, timeout=timeout)
        else:
            result = subprocess.run(cmd, shell=True, capture_output=True, 
                                  text=True, timeout=timeout)
        
        if result.returncode == 124:
            return False, "", "Killed by timeout"
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Timeout after {timeout}s"
    except Exception as e:
        return False, "", str(e)


def human_gate(artifact_path, description):
    """Pause for human review"""
    Console.human_gate(str(artifact_path), description)
    
    if not Path(artifact_path).exists():
        print(f"ERROR: {artifact_path} not found")
        return 'a'
    
    content = Path(artifact_path).read_text()
    print(f"\n--- Preview (first 800 chars) ---")
    print(content[:800])
    if len(content) > 800:
        print(f"... ({len(content) - 800} more chars)")
    print(f"--- End Preview ---\n")
    
    print("Options: c = Continue, r = Regenerate, a = Abort")
    
    while True:
        response = input("\nChoice [c/r/a]: ").lower().strip()
        if response in ['c', 'r', 'a']:
            return response
        print("Invalid choice")


def load_lessons_for_context(query):
    """Load relevant ADR lessons for context"""
    lessons = []
    adr_dir = PROJECT_ROOT / "docs/adr"
    
    if not adr_dir.exists():
        return ""
    
    adr_files = list(adr_dir.glob("*.md"))
    
    for adr in adr_files[-5:]:  # Last 5 ADRs
        try:
            with open(adr) as f:
                content = f.read()
                
                if "## Lessons Learned" in content:
                    parts = content.split("## Lessons Learned")
                    if len(parts) > 1:
                        lesson_text = parts[1].split("##")[0].strip()
                        
                        query_words = set(query.lower().split())
                        lesson_words = set(lesson_text.lower().split())
                        if query_words & lesson_words:
                            lessons.append(f"From {adr.name}:\n{lesson_text[:500]}")
        except Exception as e:
            continue
    
    return "\n\n".join(lessons)


def draft_adr(requester, decision, context, lessons):
    """Auto-create ADR draft"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    draft_path = TEMP_DIR / f"adr_draft_{timestamp}.txt"
    
    adr_content = f"""Requester: {requester}
Decision: {decision}
Context: {context}
Alternatives: Not formally evaluated
Consequences: Documented in implementation
Lessons: {lessons}
"""
    draft_path.write_text(adr_content)
    Console.adr_pending()
    return draft_path


def save_state(phase, data):
    """Save workflow state for resume"""
    state = {
        "phase": phase,
        "data": data,
        "token_usage": token_tracker.used,
        "timestamp": datetime.now().isoformat()
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def load_state():
    """Load previous workflow state"""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return None


def main():
    start_time = time.time()
    
    if len(sys.argv) < 2:
        print("Usage: ./gironimo/agent-scripts/orchestrator.py 'feature request'")
        print("   or: ./gironimo/agent-scripts/orchestrator.py --check")
        print("   or: ./gironimo/agent-scripts/orchestrator.py --resume")
        sys.exit(1)
    
    if sys.argv[1] == "--resume":
        state = load_state()
        if not state:
            print("No state to resume")
            sys.exit(1)
        print(f"Resuming from phase {state['phase']}")
        token_tracker.used = state.get('token_usage', 0)
        print("Full resume not yet implemented - re-run from start")
        sys.exit(0)
    
    if sys.argv[1] == "--check":
        Console.header("SYSTEM CHECK")
        ok = check_servers()
        if not ok:
            print(f"\nTroubleshooting:")
            print(f"  1. SSH to DGX: ssh youruser@{os.getenv('DGX_HOST', 'localhost')}")
            print("  2. Check services: sudo systemctl status vllm-main vllm-coder vllm-vision")
            print("  3. Check logs: sudo journalctl -u vllm-main -f")
            print("  4. Restart: sudo systemctl restart vllm-main")
        sys.exit(0 if ok else 1)
    
    request = sys.argv[1]
    Console.header(f"Gironimo Orchestrator")
    print(f"Request: {request[:80]}")
    print(f"DGX Spark: {URLS['main']}")
    print(f"Token Budget: {token_tracker.budget:,}")
    
    if not check_servers():
        print(f"\nDGX Spark servers not ready")
        sys.exit(1)
    
    ensure_directories()
    
    # PHASE 1: Discovery & Specification
    Console.phase(1, "Discovery & Specification", "starting")
    phase_start = time.time()
    
    Console.parallel_start("Background Tasks")
    parallel_results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        f_deps = ex.submit(scan_dependencies)
        f_index = ex.submit(run_agent, "indexer.py", "--check")
        
        Console.tool_call("Dependency Scanner", "scan")
        deps_start = time.time()
        deps = f_deps.result()
        deps_time = time.time() - deps_start
        parallel_results.append({
            'name': 'Dependencies', 
            'ok': True, 
            'status': f"{len(deps)} packages found",
            'time': deps_time
        })
        
        Console.tool_call("Indexer", "check")
        idx_start = time.time()
        idx_ok, _, _ = f_index.result()
        idx_time = time.time() - idx_start
        parallel_results.append({
            'name': 'CodeGraph', 
            'ok': idx_ok, 
            'status': 'indexed' if idx_ok else 'needs rebuild',
            'time': idx_time
        })
        
        Console.tool_call("Spec Agent", "generate")
        spec_start = time.time()
        spec_ok, spec = run_agent("spec_agent.py", f'"{request}"')
        spec_time = time.time() - spec_start
        
        if not spec_ok:
            Console.result("error", f"Spec generation failed")
            sys.exit(1)
        
        parallel_results.append({
            'name': 'Spec', 
            'ok': True, 
            'status': f"{len(spec)} chars",
            'time': spec_time
        })
    
    Console.parallel_done("Discovery", parallel_results)
    Console.timing("Phase 1 total", time.time() - phase_start)
    
    slug = request.lower().replace(' ', '-')[:30]
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    spec_dir = PROJECT_ROOT / "specs" / slug
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / "spec.md"
    spec_path.write_text(spec)
    Console.result("success", f"Saved to specs/{slug}/spec.md")
    
    save_state("spec_complete", {"slug": slug, "spec_path": str(spec_path)})
    
    gate = human_gate(spec_path, "Feature Specification")
    
    if gate == 'r':
        Console.tool_call("Spec Agent", "regenerate")
        clarification = input("\nWhat should change? ")
        spec_ok, spec = run_agent("spec_agent.py", f'"{request}" --spec-path "{spec_path}"', stdin_data=clarification)
        if not spec_ok:
            Console.result("error", f"Retry failed")
            sys.exit(1)
        spec_path.write_text(spec)
        Console.result("success", "Spec revised")
        gate = human_gate(spec_path, "Revised Feature Specification")
    
    if gate == 'a':
        Console.result("error", "Aborted by user")
        sys.exit(0)
    
    draft_adr("Spec Agent", f"Implement: {request[:50]}", 
              f"Feature requested: {request}", 
              "Spec approved by human")
    
    # PHASE 2: Documentation & Context
    Console.phase(2, "Documentation & Context", "starting")
    phase_start = time.time()
    
    lessons = load_lessons_for_context(request)
    if lessons:
        Console.result("success", f"Found relevant lessons from past ADRs")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_doc = ex.submit(run_agent, "doc_scout.py")
        f_scout = ex.submit(run_agent, "scout.py", f'"{request}"')
        
        doc_ok, _, _ = f_doc.result()
        if doc_ok:
            Console.result("success", "Documentation fetched")
        else:
            Console.result("skipped", "Documentation fetch skipped")
        
        scout_ok, _, _ = f_scout.result()
        if scout_ok:
            Console.result("success", "Context gathered")
        else:
            Console.result("warning", "Scout failed, continuing")
    
    context_file = TEMP_DIR / "adr_lessons.txt"
    context = context_file.read_text()[:800] if context_file.exists() else ""
    
    Console.timing("Phase 2 total", time.time() - phase_start)
    
    # PHASE 3: Architecture Design
    Console.phase(3, "Architecture Design", "starting")
    phase_start = time.time()
    
    arch_prompt = f"Feature: {request}\n\nSpec:\n{spec[:1000]}\n\n"
    if context:
        arch_prompt += f"Context from codebase:\n{context}\n\n"
    if lessons:
        arch_prompt += f"Relevant past lessons:\n{lessons}\n\n"
    arch_prompt += "Design a solution. List specific files to modify. Identify risks and dependencies."
    
    arch_start = time.time()
    arch_ok, plan = call_model('main', [
        {"role": "system", "content": "You are a software architect. Be specific about files, interfaces, and potential issues."},
        {"role": "user", "content": arch_prompt}
    ], 'arch', token_tracker=token_tracker)
    arch_time = time.time() - arch_start
    
    if not arch_ok:
        Console.result("error", f"Architecture failed: {plan[:100]}")
        sys.exit(1)
    
    Console.timing("Phase 3 total", time.time() - phase_start)
    
    plan_path = TEMP_DIR / "plan.txt"
    plan_path.write_text(plan)
    Console.result("success", f"Architecture complete ({len(plan)} chars)")
    
    save_state("architecture_complete", {"slug": slug, "plan_path": str(plan_path)})
    
    gate = human_gate(plan_path, "Architecture Plan")
    
    if gate == 'r':
        Console.tool_call("Architect", "revise")
        clarification = input("\nWhat should change? ")
        arch_ok, plan = call_model('main', [
            {"role": "system", "content": "Revise architecture based on feedback."},
            {"role": "user", "content": f"Spec: {spec[:500]}\nPrior plan: {plan[:500]}\nFeedback: {clarification}"}
        ], 'arch', token_tracker=token_tracker)
        if not arch_ok:
            Console.result("error", f"Retry failed: {plan[:100]}")
            sys.exit(1)
        plan_path.write_text(plan)
        Console.result("success", "Plan revised")
        gate = human_gate(plan_path, "Revised Architecture Plan")
    
    if gate == 'a':
        Console.result("error", "Aborted by user")
        sys.exit(0)
    
    draft_adr("Architect", f"Architecture: {request[:40]}", 
              "Based on spec and context", 
              "Plan approved by human")
    
    # PHASE 4: Implementation & Review
    Console.phase(4, "Implementation & Review", "starting")
    phase_start = time.time()
    
    Console.tool_call("Implementor", "generate")
    impl_start = time.time()
    impl_ok, implementation = call_model('main', [
        {"role": "system", "content": "Write clean, tested code with error handling and comments."},
        {"role": "user", "content": f"Implement this architecture plan:\n\n{plan}"}
    ], 'impl', token_tracker=token_tracker)
    impl_time = time.time() - impl_start
    
    if not impl_ok:
        Console.result("error", f"Implementation failed: {implementation[:100]}")
        sys.exit(1)
    
    Console.result("success", f"Initial implementation: {len(implementation)} chars")
    
    Console.tool_call("Reviewer", "critique")
    review_ok, critique = run_agent("reviewer.py", "--critique", 
                                   stdin_data=json.dumps({
                                       "spec": spec[:2000],
                                       "architecture": plan[:2000],
                                       "implementation": implementation[:4000]
                                   }))
    
    if review_ok:
        Console.result("success", "Review complete")
        
        if "NEEDS_REVISION" in critique or "[HIGH]" in critique:
            Console.result("warning", "Issues found, revising...")
            
            rev_ok, revised = run_agent("reviewer.py", "--revise", 
                                       stdin_data=json.dumps({
                                           "spec": spec[:2000],
                                           "architecture": plan[:2000],
                                           "implementation": implementation,
                                           "critique": critique
                                       }))
            
            if rev_ok:
                implementation = revised
                Console.result("success", "Revision complete")
                
                Console.tool_call("Reviewer", "verify")
                verify_ok, _ = run_agent("reviewer.py", "--verify", 
                                         stdin_data=json.dumps({
                                             "implementation": implementation[:3000]
                                         }))
                if verify_ok:
                    Console.result("success", "Revision approved")
                else:
                    Console.result("warning", "Revision still has issues, but continuing")
            else:
                Console.result("warning", "Revision failed, using original")
    else:
        Console.result("warning", "Review skipped")
    
    Console.tool_call("Patcher", "generate")
    patch_ok, patch = run_agent("patcher.py", "--generate", stdin_data=implementation)
    
    if not patch_ok:
        Console.result("error", "Patch generation failed")
        sys.exit(1)
    
    patch_path = TEMP_DIR / "implementation.patch"
    with open(patch_path, 'w') as f:
        f.write(patch)
    Console.result("success", f"Patch generated: {len(patch)} chars")
    
    Console.tool_call("Patcher", "validate")
    validate_ok, issues = run_agent("patcher.py", "--validate", stdin_data=patch)
    
    if not validate_ok:
        Console.result("error", f"Patch validation failed:\n{issues}")
        sys.exit(1)
    
    Console.result("success", "Patch validated")
    
    impl_path = TEMP_DIR / "implementation.txt"
    impl_path.write_text(implementation)
    
    Console.timing("Phase 4 total", time.time() - phase_start)
    
    # PHASE 5: Testing
    Console.phase(5, "Testing", "starting")
    phase_start = time.time()
    
    Console.tool_call("Tester", "run")
    test_start = time.time()
    test_ok, test_out, _ = run_agent("tester.py")
    test_time = time.time() - test_start
    
    Console.timing("Phase 5 total", time.time() - phase_start)
    
    if test_ok:
        Console.result("success", "All tests passed")
        test_lessons = "All tests passed"
    else:
        Console.result("warning", "Tests failed, see test_output.txt")
        test_lessons = "Failures logged in test_output.txt"
    
    draft_adr("Tester", f"Testing: {request[:40]}", 
              "Validated implementation", test_lessons)
    
    # PHASE 6: Staging Review
    Console.phase(6, "Staging Review", "starting")
    
    ui_keywords = ['ui', 'page', 'component', 'css', 'html', 'frontend', 
                   'react', 'vue', 'angular', 'svelte', 'screen', 'view']
    
    if any(k in plan.lower() for k in ui_keywords):
        Console.result("warning", "UI changes detected")
        print(f"\nOptions:")
        print(f"  1. Run staging review (Docker + screenshots + vision)")
        print(f"  2. Skip staging review")
        
        choice = input("\nChoice [1/2]: ").strip()
        
        if choice == '1':
            staging_ok, _ = run_agent("staging.py", "--review")
            if staging_ok:
                Console.result("success", "Staging approved")
                draft_adr("Staging", f"UI validation: {request[:40]}", 
                          "Visual review completed", "UI approved")
            else:
                Console.result("error", "Staging rejected")
                sys.exit(1)
        else:
            Console.result("skipped", "Staging review skipped")
    else:
        Console.result("skipped", "No UI changes detected")
    
    total_time = time.time() - start_time
    
    token_summary = token_tracker.summary()
    logger.log("workflow_complete", 
               request=request[:100],
               total_time=total_time,
               token_usage=token_summary)
    
    Console.final_summary({
        'Specification': str(spec_path),
        'Architecture': str(plan_path),
        'Implementation': str(impl_path),
        'Patch': str(patch_path),
        'ADR Draft': f'{TEMP_DIR}/adr_draft_*.txt'
    }, total_time)
    
    print(f"\nToken usage: {token_summary['used']:,} / {token_summary['budget']:,} ({token_summary['percent']:.1f}%)")
    print(f"\nNext steps:")
    print(f"  1. Review ADR drafts and finalize: ./gironimo/agent-scripts/adr_manager.py --finalize")
    print(f"  2. Apply changes and commit: ./gironimo/agent-scripts/finisher.py")
    print(f"  3. Run maintenance: ./gironimo/agent-scripts/maintainer.py")


if __name__ == "__main__":
    main()
