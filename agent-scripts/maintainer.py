#!/usr/bin/env python3
"""
Maintainer Agent - Repository hygiene and maintenance
"""

import subprocess
import sys
import os
import glob
from pathlib import Path
from datetime import datetime, timedelta


def run_formatters():
    """Run code formatters based on project type"""
    print("📝 Running formatters...")
    
    # Python
    if Path("pyproject.toml").exists() or Path("setup.py").exists():
        if subprocess.run(['which', 'black'], capture_output=True).returncode == 0:
            subprocess.run(['black', '.'], capture_output=True)
            print("  ✓ black")
        
        if subprocess.run(['which', 'isort'], capture_output=True).returncode == 0:
            subprocess.run(['isort', '.'], capture_output=True)
            print("  ✓ isort")
    
    # JavaScript/TypeScript
    if Path("package.json").exists():
        if subprocess.run(['which', 'prettier'], capture_output=True).returncode == 0:
            subprocess.run(['prettier', '--write', '.'], capture_output=True)
            print("  ✓ prettier")
        
        if subprocess.run(['which', 'eslint'], capture_output=True).returncode == 0:
            subprocess.run(['eslint', '--fix', '.'], capture_output=True)
            print("  ✓ eslint")
    
    # Go
    if Path("go.mod").exists():
        subprocess.run(['go', 'fmt', './...'], capture_output=True)
        print("  ✓ gofmt")
    
    # Rust
    if Path("Cargo.toml").exists():
        if subprocess.run(['which', 'rustfmt'], capture_output=True).returncode == 0:
            subprocess.run(['cargo', 'fmt'], capture_output=True)
            print("  ✓ rustfmt")


def check_adrs():
    """Check ADRs for missing lessons"""
    adr_files = glob.glob("docs/adr/*.md")
    missing_lessons = []
    
    for adr in adr_files:
        with open(adr) as f:
            content = f.read()
            if "## Lessons Learned" not in content:
                missing_lessons.append(adr)
    
    if missing_lessons:
        print("\n⚠️  ADRs missing Lessons Learned:")
        for adr in missing_lessons:
            print(f"  - {adr}")
    else:
        print("\n✓ All ADRs have Lessons Learned")


def prune_vendor_docs(days=30):
    """Remove old vendor documentation"""
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    
    for doc in glob.glob("docs/vendor/**/*.md", recursive=True):
        mtime = datetime.fromtimestamp(Path(doc).stat().st_mtime)
        if mtime < cutoff:
            Path(doc).unlink()
            removed += 1
    
    # Remove empty directories
    for dirpath in glob.glob("docs/vendor/**/", recursive=True):
        try:
            Path(dirpath).rmdir()
        except OSError:
            pass
    
    if removed:
        print(f"\n🧹 Removed {removed} old vendor docs")
    else:
        print("\n✓ No old vendor docs to prune")


def refresh_codegraph():
    """Refresh CodeGraph index"""
    if not Path(".codegraph").exists():
        print("\n📊 No CodeGraph index found. Run indexer.py first.")
        return
    
    print("\n📊 Refreshing CodeGraph index...")
    result = subprocess.run(
        ['cg', 'project', 'index', './src', './docs', '--output', './.codegraph'],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("  ✓ Index refreshed")
    else:
        print(f"  ✗ Refresh failed: {result.stderr[:100]}")


def check_large_files(threshold_mb=10):
    """Find files larger than threshold"""
    large_files = []
    
    for ext in ['*.py', '*.js', '*.ts', '*.go', '*.rs', '*.md', '*.json', '*.yaml']:
        for f in glob.glob(f"**/{ext}", recursive=True):
            size = Path(f).stat().st_size / (1024 * 1024)
            if size > threshold_mb:
                large_files.append((f, size))
    
    if large_files:
        print(f"\n⚠️  Files larger than {threshold_mb}MB:")
        for f, size in sorted(large_files, key=lambda x: x[1], reverse=True)[:10]:
            print(f"  - {f}: {size:.1f}MB")
    else:
        print(f"\n✓ No files larger than {threshold_mb}MB")


def main():
    full = '--full' in sys.argv
    
    print("\n🦒 Gironimo Maintenance")
    print("=" * 50)
    
    # Run formatters
    run_formatters()
    
    # Check ADRs
    check_adrs()
    
    # Full maintenance (optional)
    if full:
        prune_vendor_docs()
        refresh_codegraph()
        check_large_files()
    
    # Summary
    print("\n" + "=" * 50)
    print("Maintenance complete")
    
    if not full:
        print("\nTip: Run with --full for deep maintenance")
        print("     (prunes vendor docs, refreshes CodeGraph, checks large files)")


if __name__ == "__main__":
    main()
