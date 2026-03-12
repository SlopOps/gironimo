#!/usr/bin/env python3
"""
Test Agent - Runs tests and reports results
"""

import subprocess
import sys
import json
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from config import TEMP_DIR, call_model, get_token_tracker, Console


def detect_test_command():
    """Detect appropriate test command with priority ordering"""
    # Python projects
    if Path("pyproject.toml").exists():
        if Path("pytest.ini").exists() or Path("tests").exists():
            return ['python', '-m', 'pytest', '-v']
        return ['python', '-m', 'pytest', '-v', '--co']  # Collect only if no tests
    
    if Path("pytest.ini").exists() or (Path("tests").exists() and list(Path("tests").glob("test_*.py"))):
        return ['pytest', 'tests/', '-v']
    
    if Path("setup.py").exists() or Path("setup.cfg").exists():
        return ['python', 'setup.py', 'test']

    # Node.js projects
    if Path("package.json").exists():
        try:
            pkg = json.loads(Path("package.json").read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                return ['npm', 'test']
            # Check for alternative test runners
            if Path("vitest.config.ts").exists() or Path("vitest.config.js").exists():
                return ['npx', 'vitest', 'run']
            if Path("jest.config.js").exists() or Path("jest.config.ts").exists():
                return ['npx', 'jest']
        except json.JSONDecodeError:
            pass
        return ['npm', 'test']

    # Go projects
    if Path("go.mod").exists():
        return ['go', 'test', '-v', './...']

    # Rust projects
    if Path("Cargo.toml").exists():
        return ['cargo', 'test', '--', '--nocapture']

    # Ruby projects
    if Path("Gemfile").exists():
        if Path("spec").exists():
            return ['bundle', 'exec', 'rspec']
        return ['bundle', 'exec', 'rake', 'test']

    return None


def run_tests(cmd, cwd=None):
    """Run tests with proper error handling and output capture"""
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            cwd=cwd or Path.cwd(),
            timeout=300  # 5 minute timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Test execution timed out after 5 minutes"
    except FileNotFoundError as e:
        return -1, "", f"Command not found: {e}"
    except Exception as e:
        return -1, "", str(e)


def analyze_test_failure(stdout, stderr, implementation_path=None):
    """Analyze test output to identify failure patterns"""
    combined = stdout + stderr
    
    patterns = {
        'import_error': r'ImportError|ModuleNotFoundError|cannot import name',
        'syntax_error': r'SyntaxError|IndentationError',
        'assertion_fail': r'AssertionError|FAILED.*assert',
        'timeout': r'Timeout|time limit',
        'missing_dep': r'No module named|cannot find package',
    }
    
    import re
    issues = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, combined, re.IGNORECASE)
        if matches:
            issues[name] = len(matches)
    
    return issues


def generate_tests_with_llm(spec_path=None, implementation_path=None):
    """Generate test templates using the Coder model"""
    Console.tool_call("Tester", "generate_tests")
    
    # Gather context
    context = []
    
    if spec_path and Path(spec_path).exists():
        context.append(f"Specification:\n{Path(spec_path).read_text()[:2000]}")
    
    if implementation_path and Path(implementation_path).exists():
        context.append(f"Implementation:\n{Path(implementation_path).read_text()[:2000]}")
    
    # Look for existing source files to test
    src_files = []
    for pattern in ["src/**/*.py", "app/**/*.py", "lib/**/*.py", "*.py"]:
        src_files.extend(Path.cwd().glob(pattern))
    src_files = [f for f in src_files if not f.name.startswith('test_') and f.name != "tester.py"]
    
    if src_files:
        files_list = "\n".join([f"- {f}" for f in src_files[:5]])
        context.append(f"Source files to test:\n{files_list}")

    prompt = f"""Generate comprehensive test cases for this project.

{' '.join(context)}

Requirements:
1. Use pytest framework
2. Include positive and negative test cases
3. Test edge cases and error conditions
4. Use descriptive test names
5. Include setup/teardown if needed
6. Mock external dependencies

Output only the test code, ready to save to a file."""

    ok, test_code = call_model(
        'coder',
        [
            {"role": "system", "content": "You are a test engineer. Write thorough, production-quality tests."},
            {"role": "user", "content": prompt}
        ],
        'impl',
        token_tracker=get_token_tracker()
    )
    
    if not ok:
        print("Failed to generate tests via LLM")
        return False
    
    # Write generated tests
    tests_dir = Path("tests")
    tests_dir.mkdir(exist_ok=True)
    
    # Create __init__.py if needed
    (tests_dir / "__init__.py").touch(exist_ok=True)
    
    test_file = tests_dir / "test_generated.py"
    test_file.write_text(test_code)
    
    Console.result("success", f"Generated tests at {test_file}")
    return True


def create_test_directory_structure():
    """Create proper test directory structure if missing"""
    tests_dir = Path("tests")
    
    if not tests_dir.exists():
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "__init__.py").touch(exist_ok=True)
        
        # Create conftest.py with common fixtures
        conftest_content = '''import pytest
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))
'''
        (tests_dir / "conftest.py").write_text(conftest_content)
        return True
    return False


def main():
    # Check if we should generate tests only
    if "--generate" in sys.argv:
        spec_path = None
        impl_path = None
        
        # Look for recent spec and implementation
        specs_dir = Path("specs")
        if specs_dir.exists():
            specs = sorted(specs_dir.glob("*/spec.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if specs:
                spec_path = specs[0]
        
        temp_impl = TEMP_DIR / "implementation.txt"
        if temp_impl.exists():
            impl_path = temp_impl
            
        if generate_tests_with_llm(spec_path, impl_path):
            sys.exit(0)
        else:
            sys.exit(1)
    
    # Normal test execution flow
    cmd = detect_test_command()
    
    if not cmd:
        print("No test configuration detected")
        create_test_directory_structure()
        
        # Try to generate tests if none exist
        response = input("No tests found. Generate tests with LLM? [y/n]: ").lower().strip()
        if response == 'y':
            if generate_tests_with_llm():
                # Re-detect and run
                cmd = detect_test_command()
            else:
                sys.exit(1)
        else:
            print("Skipping tests")
            sys.exit(0)
    
    if not cmd:
        sys.exit(1)
    
    Console.tool_call("Tester", "run", " ".join(cmd))
    
    returncode, stdout, stderr = run_tests(cmd)
    
    # Write detailed output to TEMP_DIR
    test_output_path = TEMP_DIR / "test_output.txt"
    with open(test_output_path, 'w') as f:
        f.write(f"Command: {' '.join(cmd)}\\n")
        f.write(f"Return code: {returncode}\\n")
        f.write("=" * 60 + "\\n")
        f.write("STDOUT:\\n")
        f.write(stdout)
        if stderr:
            f.write("\\n" + "=" * 60 + "\\n")
            f.write("STDERR:\\n")
            f.write(stderr)
    
    # Print summary to console
    if stdout:
        # Print last 20 lines of output for context
        lines = stdout.split('\\n')
        if len(lines) > 20:
            print("... (truncated)")
        print('\\n'.join(lines[-20:]))
    
    if returncode == 0:
        Console.result("success", "All tests passed")
        
        # Parse and show summary
        if "passed" in stdout.lower():
            import re
            passed = re.search(r'(\\d+) passed', stdout)
            if passed:
                print(f"  ✓ {passed.group(1)} tests passed")
        
        sys.exit(0)
    else:
        Console.result("error", "Tests failed")
        
        # Analyze failures
        issues = analyze_test_failure(stdout, stderr)
        if issues:
            print("\\nFailure analysis:")
            for issue_type, count in issues.items():
                print(f"  - {issue_type}: {count} occurrences")
        
        # Offer to generate fixes
        if "--auto-fix" in sys.argv:
            print("\\nAttempting to generate fixes...")
            # This would call a fix generation agent
            pass
        else:
            print(f"\\nSee full output: {test_output_path}")
            print("Run with --generate to create missing tests")
        
        sys.exit(1)


if __name__ == "__main__":
    main()
