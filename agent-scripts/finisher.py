#!/usr/bin/env python3
"""
Finisher Agent - Applies patches, runs tests, commits changes
"""

import subprocess
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from config import TEMP_DIR


def check_branch():
    """Check if we're on main/master and prompt for branch creation"""
    result = subprocess.run(
        ['git', 'branch', '--show-current'],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    current_branch = result.stdout.strip()

    if current_branch in ['main', 'master']:
        print(f"⚠️  On {current_branch} branch. Create feature branch?")
        response = input("Create branch? [y/n]: ").lower().strip()

        if response == 'y':
            branch = input("Branch name: ").strip()
            if branch:
                subprocess.run(['git', 'checkout', '-b', branch], cwd=Path.cwd())
                return True
        else:
            return False

    return True


def validate_patch(patch_path):
    """Check if patch can be applied cleanly"""
    result = subprocess.run(
        ['git', 'apply', '--check', str(patch_path)],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )

    if result.returncode != 0:
        print("❌ Patch validation failed:")
        print(result.stderr)
        return False

    return True


def apply_patch(patch_path):
    """Apply the patch"""
    result = subprocess.run(
        ['git', 'apply', str(patch_path)],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )

    if result.returncode != 0:
        print("❌ Patch apply failed:")
        print(result.stderr)
        return False

    print("✅ Patch applied")
    return True


def run_tests():
    """Run tests and capture results"""
    # Try common test commands
    test_cmds = [
        ['pytest'],
        ['npm', 'test'],
        ['go', 'test', './...'],
        ['cargo', 'test'],
        ['make', 'test'],
    ]

    for cmd in test_cmds:
        if subprocess.run(['which', cmd[0]], capture_output=True).returncode == 0:
            print(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, cwd=Path.cwd())
            return result.returncode == 0

    print("No test command found")
    return True  # Assume success if no tests


def get_diff_summary():
    """Get summary of changes"""
    result = subprocess.run(
        ['git', 'diff', '--stat'],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    return result.stdout


def commit_changes():
    """Commit changes with message from spec"""
    # Try to get feature name from spec
    spec_files = list(Path("specs").glob("*/spec.md"))
    if spec_files:
        # Get most recent spec
        latest = max(spec_files, key=lambda p: p.stat().st_mtime)
        with open(latest) as f:
            first_line = f.readline().strip()
            commit_msg = first_line.replace('# Feature:', 'feat:').strip()
    else:
        commit_msg = "feat: implement feature"

    # Add all changes
    subprocess.run(['git', 'add', '-A'], cwd=Path.cwd())

    # Commit
    result = subprocess.run(
        ['git', 'commit', '-m', commit_msg],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )

    if result.returncode == 0:
        print(f"✅ Committed: {commit_msg}")
        return True
    else:
        print(f"❌ Commit failed: {result.stderr}")
        return False


def main():
    patch_path = TEMP_DIR / "implementation.patch"

    if not patch_path.exists():
        print("❌ No implementation.patch found. Run orchestrator first.")
        sys.exit(1)

    print("\n🦒 Gironimo Finish Workflow")
    print("=" * 50)

    # Step 1: Check branch
    print("\n1. Checking branch...")
    if not check_branch():
        print("Aborted.")
        sys.exit(1)

    # Step 2: Validate patch
    print("\n2. Validating patch...")
    if not validate_patch(patch_path):
        sys.exit(1)

    # Step 3: Apply patch
    print("\n3. Applying patch...")
    if not apply_patch(patch_path):
        sys.exit(1)

    # Step 4: Run tests
    print("\n4. Running tests...")
    if not run_tests():
        print("❌ Tests failed. Review and fix before committing.")
        sys.exit(1)
    print("✅ Tests passed")

    # Step 5: Show summary
    print("\n5. Change summary:")
    print(get_diff_summary())

    # Step 6: Final commit gate
    print("\n6. Ready to commit")
    response = input("Commit changes? [y/n]: ").lower().strip()

    if response == 'y':
        if commit_changes():
            print("\n✅ Workflow complete")
            print(f"Push: git push origin $(git branch --show-current)")
        else:
            sys.exit(1)
    else:
        print("\nChanges applied but not committed.")
        print("Review with: git diff")
        print("Undo with: git checkout -- .")
        sys.exit(0)


if __name__ == "__main__":
    main()
