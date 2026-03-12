#!/usr/bin/env python3
"""
Scout Agent - Code context retrieval using CodeGraph
"""

import subprocess
import sys
import json
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from config import TEMP_DIR


def main():
    if len(sys.argv) < 2:
        print("Usage: scout.py 'query'")
        sys.exit(1)

    query = sys.argv[1]

    # Check if index exists
    if not Path(".codegraph").exists():
        print("No CodeGraph index found. Run indexer.py first.")
        sys.exit(1)

    # Run CodeGraph search
    result = subprocess.run(
        ['cg', 'analyze', 'search', query, '--paths', './src', './docs',
         '--max-results', '5', '--output', 'json'],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        data = json.loads(result.stdout)
        
        # Write to TEMP_DIR
        scout_results_path = TEMP_DIR / "scout_results.json"
        with open(scout_results_path, 'w') as f:
            json.dump(data, f, indent=2)

        # Get dependencies of top file
        if data and len(data) > 0:
            top_file = data[0].get('file')
            if top_file:
                deps_path = TEMP_DIR / "deps.json"
                subprocess.run(
                    ['cg', 'analyze', 'dependencies', top_file, '--output', 'json'],
                    stdout=open(deps_path, 'w')
                )

        # Extract ADR lessons
        adr_lessons_path = TEMP_DIR / "adr_lessons.txt"
        subprocess.run(
            "grep -h 'Lessons Learned' -A10 docs/adr/*.md 2>/dev/null | grep -i '" + query + "' -B2 -A2 > " + str(adr_lessons_path),
            shell=True
        )

        print("Scout complete")
    else:
        print(f"Search failed: {result.stderr}")
        sys.exit(1)


if __name__ == "__main__":
    main()
