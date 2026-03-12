#!/usr/bin/env python3
"""
Indexer Agent - Maintains CodeGraph index
"""

import os
import sys
import subprocess
from pathlib import Path


def check_coder_model():
    """Verify Coder model is reachable"""
    dgx_host = os.getenv('DGX_HOST', 'localhost')
    coder_port = os.getenv('CODER_PORT', '8001')
    
    result = subprocess.run(
        ['curl', '-s', f"http://{dgx_host}:{coder_port}/v1/models"],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def main():
    force = '--force' in sys.argv
    
    if not check_coder_model():
        print("Error: Coder model not reachable")
        print(f"Check: ssh {os.getenv('DGX_HOST', 'localhost')} sudo systemctl status vllm-coder")
        sys.exit(1)
    
    if force or not Path(".codegraph").exists():
        print("Building CodeGraph index...")
        result = subprocess.run(
            ['cg', 'project', 'index', './src', './docs', '--output', './.codegraph'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Indexed")
        else:
            print(f"❌ Indexing failed: {result.stderr}")
            sys.exit(1)
    else:
        print("Index exists (use --force to rebuild)")


if __name__ == "__main__":
    main()
