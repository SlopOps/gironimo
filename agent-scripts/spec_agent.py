#!/usr/bin/env python3
"""
Spec Agent - Generates structured specifications from requests
"""

import sys
import os
import argparse
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from config import call_model


def generate_spec(request):
    """Generate specification from request"""
    
    system_prompt = """You are a technical spec writer. Create a specification with:

# Feature: [Name]

## Description
Clear description of what this feature does.

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Technical Impact
- Components affected
- Dependencies affected
- Configuration changes needed

## Testing Requirements
- Unit tests needed
- Integration tests needed
- Manual testing steps
"""
    
    ok, spec = call_model('main', [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": request}
    ], 'spec')
    
    return spec if ok else None


def revise_spec(request, feedback, current_spec):
    """Revise spec based on feedback"""
    
    prompt = f"""Original request: {request}

Current spec: {current_spec}

Feedback: {feedback}

Revise the specification based on this feedback."""
    
    ok, spec = call_model('main', [
        {"role": "system", "content": "Revise specification based on feedback."},
        {"role": "user", "content": prompt}
    ], 'spec')
    
    return spec if ok else None


def main():
    parser = argparse.ArgumentParser(description='Generate or revise specifications')
    parser.add_argument('request', help='Feature request description')
    parser.add_argument('--spec-path', help='Path to existing spec file (for revision)')
    
    args = parser.parse_args()
    
    # Check if we're in regenerate mode (stdin has feedback)
    if not sys.stdin.isatty():
        feedback = sys.stdin.read().strip()
        
        # Use provided spec path or default
        if args.spec_path and Path(args.spec_path).exists():
            current_spec = Path(args.spec_path).read_text()
        else:
            # Try common locations
            possible_paths = [
                Path("spec.md"),
                Path("specs") / args.request.replace(' ', '-')[:30] / "spec.md"
            ]
            current_spec = ""
            for path in possible_paths:
                if path.exists():
                    current_spec = path.read_text()
                    break
        
        spec = revise_spec(args.request, feedback, current_spec)
    else:
        spec = generate_spec(args.request)
    
    if spec is not None:
        print(spec)
    else:
        print("Failed to generate spec", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
