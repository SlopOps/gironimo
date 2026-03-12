#!/usr/bin/env python3
"""
Reviewer Agent - Two-model critique system
Reviews implementation against spec and architecture
"""

import sys
import json
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from config import call_model, get_token_tracker


def critique(spec, architecture, implementation):
    """First model reviews second model's work"""
    
    prompt = f"""You are a senior code reviewer. Critique this implementation against the spec and architecture.

SPECIFICATION:
{spec[:2000]}

ARCHITECTURE PLAN:
{architecture[:2000]}

IMPLEMENTATION:
{implementation[:4000]}

Identify specific issues with:

1. Bugs or logic errors
2. Missing error handling
3. Security vulnerabilities
4. Performance problems
5. Deviations from architecture plan
6. Missing test cases
7. Code style issues

Format your response as:

## Issues Found (by severity)
- [HIGH] Issue description and fix suggestion
- [MEDIUM] Issue description and fix suggestion
- [LOW] Issue description

## Suggestions for Improvement
- Optional improvements

## Verdict
APPROVED / NEEDS_REVISION
"""
    
    ok, response = call_model('coder', [
        {"role": "system", "content": "You are a critical code reviewer. Be thorough and specific about issues."},
        {"role": "user", "content": prompt}
    ], 'review', token_tracker=get_token_tracker())
    
    return response if ok else ""


def revise(spec, architecture, implementation, critique, max_loops=2):
    """Revise implementation based on critique with optional second review"""
    
    current = implementation
    
    for loop in range(max_loops):
        prompt = f"""Revise this implementation based on the review critique.

ORIGINAL IMPLEMENTATION:
{current}

REVIEW CRITIQUE:
{critique}

Requirements:
1. Fix all [HIGH] severity issues
2. Address [MEDIUM] issues where possible
3. Consider [LOW] issues and suggestions
4. Maintain the original architecture
5. Keep code clean and well-documented

Output the complete revised implementation.
"""
        
        ok, revised = call_model('main', [
            {"role": "system", "content": "You are implementing reviewer feedback. Be thorough in fixing issues."},
            {"role": "user", "content": prompt}
        ], 'revision', token_tracker=get_token_tracker())
        
        if not ok:
            return current
        
        # Quick verification (optional)
        if loop < max_loops - 1:
            verify_prompt = f"""Quickly verify if these issues are fixed:

Original critique: {critique}

Revised implementation: {revised[:2000]}

Respond with FIXED if all HIGH issues addressed, or list remaining issues."""
            
            ok_verify, verify = call_model('coder', [
                {"role": "system", "content": "Quick verification only."},
                {"role": "user", "content": verify_prompt}
            ], 'verify')
            
            if ok_verify and "FIXED" in verify:
                return revised
            else:
                critique = verify if ok_verify else critique
                current = revised
        else:
            return revised
    
    return current


def verify(implementation):
    """Quick verification pass"""
    prompt = f"""Quickly verify this implementation for obvious issues:

{implementation[:3000]}

Check for:
- Syntax errors
- Missing imports
- Obvious security issues

Respond with PASS or list issues."""
    
    ok, response = call_model('coder', [
        {"role": "system", "content": "Quick verification only."},
        {"role": "user", "content": prompt}
    ], 'verify')
    
    return response if ok else "Verification failed"


def main():
    if len(sys.argv) < 2:
        print("Usage: reviewer.py [--critique|--revise|--verify]")
        sys.exit(1)
    
    mode = sys.argv[1]
    
    # Read input from stdin
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading stdin: {e}", file=sys.stderr)
        sys.exit(1)
    
    if mode == "--critique":
        result = critique(
            data.get('spec', ''),
            data.get('architecture', ''),
            data.get('implementation', '')
        )
        print(result)
        
    elif mode == "--revise":
        result = revise(
            data.get('spec', ''),
            data.get('architecture', ''),
            data.get('implementation', ''),
            data.get('critique', '')
        )
        print(result)
        
    elif mode == "--verify":
        result = verify(data.get('implementation', ''))
        print(result)
    
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
