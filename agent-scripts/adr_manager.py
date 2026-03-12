#!/usr/bin/env python3
"""
ADR Manager - Creates and manages Architecture Decision Records
"""

import os
import sys
import re
import glob
from datetime import datetime
from pathlib import Path

ADR_DIR = Path("docs/adr")


def next_adr_number():
    """Find the next available ADR number"""
    files = list(ADR_DIR.glob("[0-9][0-9][0-9]-*.md"))
    if not files:
        return 1
    
    nums = []
    for f in files:
        match = re.search(r'(\d{3})', f.name)
        if match:
            nums.append(int(match.group(1)))
    
    return max(nums) + 1 if nums else 1


def parse_adr_request(text):
    """Parse ADR request from stdin or file"""
    sections = {
        "requester": "unknown",
        "decision": "",
        "context": "",
        "alternatives": "",
        "consequences": "",
        "lessons": ""
    }
    
    current = None
    for line in text.split('\n'):
        line_lower = line.lower()
        
        if line_lower.startswith("requester:"):
            sections["requester"] = line.split(':', 1)[1].strip()
        elif line_lower.startswith("decision:"):
            current = "decision"
            sections[current] = line.split(':', 1)[1].strip()
        elif line_lower.startswith("context:"):
            current = "context"
        elif line_lower.startswith("alternatives:"):
            current = "alternatives"
        elif line_lower.startswith("consequences:"):
            current = "consequences"
        elif line_lower.startswith("lessons:"):
            current = "lessons"
        elif current and line.strip():
            sections[current] += " " + line.strip()
    
    return sections


def create_adr(data, draft=False):
    """Create a new ADR file"""
    if not data.get("decision"):
        print("Error: Decision required")
        return None
    
    if draft:
        # For drafts, use descriptive filename
        slug = re.sub(r'[^a-z0-9-]', '', data["decision"].lower().replace(' ', '-')[:50])
        filename = ADR_DIR / f"DRAFT-{slug}.md"
    else:
        # For final ADRs, use sequential numbering
        num = f"{next_adr_number():03d}"
        slug = re.sub(r'[^a-z0-9-]', '', data["decision"].lower().replace(' ', '-')[:30])
        filename = ADR_DIR / f"{num}-{slug}.md"
    
    content = f"""# ADR{f'-{num}' if not draft else ''}: {data['decision']}

**Date:** {datetime.now():%Y-%m-%d}
**Status:** {'Draft' if draft else 'Accepted'}
**Requested by:** {data['requester']}

## Decision
{data['decision']}

## Context
{data.get('context', 'No context provided.')}

## Alternatives Considered
{data.get('alternatives', 'None documented.')}

## Consequences
{data.get('consequences', 'To be determined.')}

## Lessons Learned
{data.get('lessons', 'None yet.')}
"""
    
    filename.write_text(content)
    print(f"Created {filename}")
    return filename


def finalize_drafts():
    """Convert draft ADRs to numbered ADRs"""
    drafts = list(ADR_DIR.glob("DRAFT-*.md"))
    
    if not drafts:
        print("No draft ADRs found")
        return
    
    for draft in drafts:
        print(f"\nProcessing: {draft.name}")
        content = draft.read_text()
        
        # Parse draft content
        sections = parse_adr_request(content)
        
        # Create final ADR
        final = create_adr(sections, draft=False)
        
        if final:
            # Remove draft
            draft.unlink()
            print(f"  → {final.name}")


def list_adrs(show_drafts=True):
    """List all ADRs"""
    files = sorted(ADR_DIR.glob("[0-9][0-9][0-9]-*.md"))
    
    if not files and not show_drafts:
        print("No ADRs found")
        return
    
    if files:
        print("\n📚 Architecture Decision Records")
        print("=" * 50)
        for f in files:
            content = f.read_text()
            title = re.search(r'# ADR-\d+: (.+)', content)
            title = title.group(1) if title else f.name
            print(f"{f.name}: {title}")
    
    if show_drafts:
        drafts = list(ADR_DIR.glob("DRAFT-*.md"))
        if drafts:
            print("\n📝 Draft ADRs")
            print("=" * 50)
            for d in drafts:
                print(f"{d.name}")


def main():
    ADR_DIR.mkdir(parents=True, exist_ok=True)
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  ./adr_manager.py --list              # List all ADRs")
        print("  ./adr_manager.py --finalize          # Finalize drafts")
        print("  echo 'Decision: ...' | ./adr_manager.py  # Create ADR")
        print("  cat adr_draft_*.txt | ./adr_manager.py   # Import draft")
        sys.exit(1)
    
    if sys.argv[1] == "--list":
        list_adrs()
        return
    
    if sys.argv[1] == "--finalize":
        finalize_drafts()
        return
    
    # Read from stdin
    if sys.stdin.isatty():
        print("No input provided")
        sys.exit(1)
    
    content = sys.stdin.read()
    
    # Check if this is a timestamped draft from orchestrator
    if 'adr_draft_' in content:
        sections = parse_adr_request(content)
        create_adr(sections, draft=True)
    else:
        sections = parse_adr_request(content)
        create_adr(sections, draft=False)


if __name__ == "__main__":
    main()
