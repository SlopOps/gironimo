#!/usr/bin/env python3
"""
Documentation Scout - Fetches and indexes vendor documentation
"""

import sys
import subprocess
import requests
from pathlib import Path

# Import paths from config
sys.path.insert(0, str(Path(__file__).parent))
from config import TEMP_DIR


def read_dependencies():
    """Read dependencies from .dependencies.txt"""
    deps_file = TEMP_DIR / ".dependencies.txt"
    if not deps_file.exists():
        # Fallback to root for backwards compatibility
        deps_file = Path(".dependencies.txt")
        if not deps_file.exists():
            return []

    with open(deps_file) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]


def fetch_python_doc(package, version=None):
    """Fetch Python package documentation from various sources"""
    vendor_dir = Path("docs/vendor") / package
    vendor_dir.mkdir(parents=True, exist_ok=True)

    # Try to fetch from ReadTheDocs
    try:
        url = f"https://{package}.readthedocs.io/en/latest/"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            doc_file = vendor_dir / "README.md"
            doc_file.write_text(f"# {package} Documentation\n\nSource: {url}\n\n{response.text[:5000]}")
            return True
    except requests.RequestException:
        pass

    # Fallback to PyPI info
    try:
        url = f"https://pypi.org/pypi/{package}/json"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            info = data.get('info', {})

            doc_content = f"""# {package} Documentation

**Version:** {info.get('version', 'unknown')}
**Summary:** {info.get('summary', '')}
**Homepage:** {info.get('home_page', '')}
**Author:** {info.get('author', '')}

## Description
{info.get('description', 'No description available.')[:5000]}
"""
            doc_file = vendor_dir / "pypi.md"
            doc_file.write_text(doc_content)
            return True
    except requests.RequestException:
        pass

    return False


def fetch_npm_doc(package):
    """Fetch npm package documentation"""
    vendor_dir = Path("docs/vendor") / package
    vendor_dir.mkdir(parents=True, exist_ok=True)

    try:
        url = f"https://registry.npmjs.org/{package}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            latest = data.get('dist-tags', {}).get('latest', 'unknown')
            versions = data.get('versions', {})
            info = versions.get(latest, {})

            doc_content = f"""# {package} Documentation

**Version:** {latest}
**Description:** {info.get('description', '')}
**Homepage:** {info.get('homepage', '')}

## README
{info.get('readme', 'No README available.')[:5000]}
"""
            doc_file = vendor_dir / "npm.md"
            doc_file.write_text(doc_content)
            return True
    except requests.RequestException:
        pass

    return False


def fetch_go_doc(package):
    """Fetch Go package documentation"""
    vendor_dir = Path("docs/vendor") / package.replace('/', '_')
    vendor_dir.mkdir(parents=True, exist_ok=True)

    try:
        url = f"https://pkg.go.dev/{package}?tab=doc"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            doc_file = vendor_dir / "README.md"
            doc_file.write_text(f"# {package} Documentation\n\nSource: {url}\n\nDocumentation available at {url}")
            return True
    except requests.RequestException:
        pass

    return False


def index_vendor_docs():
    """Re-index CodeGraph with vendor docs"""
    try:
        result = subprocess.run(
            ['cg', 'project', 'index', './src', './docs', '--output', './.codegraph'],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            print("  ✓ CodeGraph re-indexed")
        else:
            print(f"  ⚠ CodeGraph re-index failed: {result.stderr[:100]}")
    except Exception as e:
        print(f"  ⚠ Failed to re-index CodeGraph: {e}")


def main():
    print("📚 Documentation Scout")

    deps = read_dependencies()
    if not deps:
        print("No dependencies found")
        return

    print(f"Processing {len(deps)} packages...")

    fetched = 0
    for dep in deps[:10]:  # Limit to first 10 for now
        print(f"  {dep}...", end="", flush=True)

        # Extract package name (remove version constraints)
        if '==' in dep or '>=' in dep or '<=' in dep:
            # Python-style version constraint
            name = dep.split('==')[0].split('>=')[0].split('<=')[0].strip()
        elif '@' in dep:
            # npm-style version
            name = dep.split('@')[0].strip()
        else:
            name = dep

        success = False

        # Try Python first
        if fetch_python_doc(name):
            success = True
        # Try npm
        elif fetch_npm_doc(name):
            success = True
        # Try Go
        elif fetch_go_doc(name):
            success = True

        if success:
            print(" ✓")
            fetched += 1
        else:
            print(" ✗")

    print(f"\nFetched docs for {fetched} packages")

    if fetched > 0:
        print("Re-indexing CodeGraph...")
        index_vendor_docs()


if __name__ == "__main__":
    main()
