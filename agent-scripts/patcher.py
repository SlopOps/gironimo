#!/usr/bin/env python3
"""
Patcher Agent - Generates and validates unified diffs
"""

import sys
import os
import re
import subprocess
import tempfile
from pathlib import Path
from difflib import unified_diff

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import ALLOWED_PATHS, Console


def parse_implementation_to_files(implementation):
    """Parse implementation text into file dict"""
    files = {}
    current_file = None
    current_content = []
    
    for line in implementation.split('\n'):
        # Detect file markers
        if line.startswith('### ') or line.startswith('File: ') or line.startswith('# File:'):
            if current_file:
                files[current_file] = '\n'.join(current_content)
            # Extract filename
            current_file = line.replace('### ', '').replace('File: ', '').replace('# File:', '').strip()
            current_content = []
        elif line.startswith('```'):
            continue  # Skip code fences
        else:
            current_content.append(line)
    
    # Save last file
    if current_file and current_content:
        files[current_file] = '\n'.join(current_content)
    
    return files


def validate_path(filepath):
    """Check if file is in allowed paths"""
    for allowed in ALLOWED_PATHS:
        if filepath.startswith(allowed):
            return True, None
    
    return False, f"Path not allowed: {filepath} (must be in {ALLOWED_PATHS})"


def generate_patch(files, repo_root=None):
    """Generate unified diff format patch"""
    if repo_root is None:
        repo_root = Path.cwd()
    
    patch_lines = []
    
    for filepath, new_content in files.items():
        # Validate path
        valid, error = validate_path(filepath)
        if not valid:
            raise ValueError(error)
        
        full_path = repo_root / filepath
        
        # Check if file exists
        if full_path.exists():
            with open(full_path) as f:
                old_content = f.read()
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            
            # Generate diff
            diff = unified_diff(
                old_lines, new_lines,
                fromfile=f'a/{filepath}',
                tofile=f'b/{filepath}',
                n=3
            )
            patch_lines.extend(diff)
        else:
            # New file
            dir_path = full_path.parent
            dir_path.mkdir(parents=True, exist_ok=True)
            
            patch_lines.append(f"diff --git a/{filepath} b/{filepath}")
            patch_lines.append(f"new file mode 100644")
            patch_lines.append(f"--- /dev/null")
            patch_lines.append(f"+++ b/{filepath}")
            
            new_lines = new_content.splitlines(keepends=True)
            patch_lines.append(f"@@ -0,0 +1,{len(new_lines)} @@")
            for line in new_lines:
                patch_lines.append(f"+{line.rstrip()}")
            
            patch_lines.append("")
    
    return '\n'.join(patch_lines)


def validate_patch(patch):
    """Safety checks on patch content"""
    issues = []
    
    # Check for dangerous patterns
    dangerous_patterns = [
        (r'rm\s+-rf\s+/', 'rm -rf / detected'),
        (r'mkfs\.', 'Filesystem creation detected'),
        (r'dd\s+if=', 'dd command detected'),
        (r'>\s+/dev/sd[a-z]', 'Direct device write detected'),
        (r'chmod\s+777', 'Excessive permissions'),
        (r'chown\s+[^ ]+:\s*/', 'Ownership change on root'),
        (r'sudo\s+', 'sudo command detected'),
        (r'curl.*\|\s*bash', 'curl pipe to bash detected'),
        (r'wget.*-O-\s*\|\s*bash', 'wget pipe to bash detected'),
    ]
    
    for pattern, msg in dangerous_patterns:
        if re.search(pattern, patch, re.IGNORECASE):
            issues.append(msg)
    
    # Check for massive deletions (more than 50 lines without additions)
    deletion_count = patch.count('\n-')
    addition_count = patch.count('\n+')
    
    if deletion_count > 50 and addition_count < deletion_count / 2:
        issues.append(f"Large deletion detected: -{deletion_count}, +{addition_count}")
    
    # Check if patch can be applied
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
            f.write(patch)
            temp_patch = f.name
        
        result = subprocess.run(
            ['git', 'apply', '--check', temp_patch],
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        
        if result.returncode != 0:
            issues.append(f"Patch apply check failed: {result.stderr[:200]}")
        
        os.unlink(temp_patch)
    except Exception as e:
        issues.append(f"Patch validation error: {e}")
    
    return issues


def main():
    if len(sys.argv) < 2:
        print("Usage: patcher.py [--generate|--validate]")
        sys.exit(1)
    
    mode = sys.argv[1]
    
    # Read input from stdin
    if sys.stdin.isatty():
        print("Reading from stdin...")
        content = sys.stdin.read()
    else:
        content = sys.stdin.read()
    
    if mode == "--generate":
        try:
            files = parse_implementation_to_files(content)
            patch = generate_patch(files)
            print(patch)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
            
    elif mode == "--validate":
        issues = validate_patch(content)
        if issues:
            for issue in issues:
                print(f"- {issue}", file=sys.stderr)
            sys.exit(1)
        print("Patch validation passed")
    
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
