#!/bin/bash
# Gironimo Setup Script - Installs Gironimo in your project
# Run this from your project root after cloning Gironimo

set -e

echo "🦒 Gironimo Setup - Installing the herd in your project"
echo "=========================================================="

# Get the directory where this script is located (the gironimo repo)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIRONIMO_REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Current directory is assumed to be your project root
PROJECT_ROOT="$(pwd)"
GIRONIMO_DIR="$PROJECT_ROOT/gironimo"

echo "Installing Gironimo from: $GIRONIMO_REPO_ROOT"
echo "Into project: $PROJECT_ROOT"
echo ""

# Check if Gironimo is already installed
if [ -d "$GIRONIMO_DIR" ]; then
    echo "⚠️  Gironimo directory already exists at $GIRONIMO_DIR"
    read -p "Do you want to overwrite it? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 1
    fi
    rm -rf "$GIRONIMO_DIR"
fi

# Create Gironimo directory structure
echo "Creating directory structure..."
mkdir -p "$GIRONIMO_DIR"/{temp,logs}

# Copy agent scripts from the Gironimo repository
echo "Copying agent scripts..."
cp -r "$GIRONIMO_REPO_ROOT/agent-scripts" "$GIRONIMO_DIR/"

# Copy any other necessary files from the Gironimo repo
if [ -f "$GIRONIMO_REPO_ROOT/server/README.md" ]; then
    mkdir -p "$GIRONIMO_DIR/server"
    cp "$GIRONIMO_REPO_ROOT/server/README.md" "$GIRONIMO_DIR/server/" 2>/dev/null || true
fi

# Create .env template
echo "Creating .env template..."
cat > "$GIRONIMO_DIR/.env" << 'EOF'
# Gironimo Environment Configuration
# Edit with your DGX Spark IP

DGX_HOST=192.168.1.100
MAIN_PORT=8000
CODER_PORT=8001
VISION_PORT=8002
EOF
echo "Please edit $GIRONIMO_DIR/.env with your DGX Spark IP"

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Install bun if not present
if ! command -v bun &> /dev/null; then
    echo "Installing bun..."
    curl -fsSL https://bun.sh/install | bash
    export PATH="$HOME/.bun/bin:$PATH"
fi

# Create virtual environment with uv in gironimo directory
if [ ! -d "$GIRONIMO_DIR/.venv" ]; then
    echo "Creating Python virtual environment..."
    (cd "$GIRONIMO_DIR" && uv venv --python 3.11)
fi

# Activate and install dependencies
source "$GIRONIMO_DIR/.venv/bin/activate"
echo "Installing Python dependencies..."
uv pip install requests python-dotenv

# Install CodeGraph
if ! command -v cg &> /dev/null; then
    echo "Installing CodeGraph..."
    uv pip install codegraph-cli
fi

# Create required directories in project root
echo "Creating project directories..."
mkdir -p specs docs/adr docs/vendor

# Make scripts executable
find "$GIRONIMO_DIR/agent-scripts" -name "*.py" -exec chmod +x {} \;
find "$GIRONIMO_DIR" -name "*.sh" -exec chmod +x {} \;

# Create convenience symlink in project root
if [ -L "$PROJECT_ROOT/gironimo-run" ]; then
    rm "$PROJECT_ROOT/gironimo-run"
fi
ln -s gironimo/agent-scripts/orchestrator.py "$PROJECT_ROOT/gironimo-run"
echo "Created convenience symlink: ./gironimo-run"

# Create .gitignore entries if not present
GITIGNORE="$PROJECT_ROOT/.gitignore"
if [ -f "$GITIGNORE" ]; then
    # Check if Gironimo entries already exist
    if ! grep -q "# Gironimo" "$GITIGNORE"; then
        echo "" >> "$GITIGNORE"
        echo "# Gironimo" >> "$GITIGNORE"
        echo "gironimo/temp/" >> "$GITIGNORE"
        echo "gironimo/logs/" >> "$GITIGNORE"
        echo "gironimo/.venv/" >> "$GITIGNORE"
        echo ".codegraph/" >> "$GITIGNORE"
        echo "gironimo/.env" >> "$GITIGNORE"
        echo "Updated .gitignore with Gironimo entries"
    fi
else
    cat > "$GITIGNORE" << 'EOF'
# Gironimo
gironimo/temp/
gironimo/logs/
gironimo/.venv/
gironimo/.env
.codegraph/
__pycache__/
*.pyc
.DS_Store
EOF
    echo "Created .gitignore"
fi

echo ""
echo "✅ Gironimo setup complete!"
echo ""
echo "Project structure:"
echo "  $PROJECT_ROOT/"
echo "  ├── gironimo/           # Gironimo system directory 🦒"
echo "  │   ├── agent-scripts/   # The Gironimo herd"
echo "  │   ├── temp/            # Temporary files (gitignored)"
echo "  │   ├── logs/            # Log files (gitignored)"
echo "  │   ├── .venv/           # Python environment (gitignored)"
echo "  │   └── .env             # Environment config (gitignored)"
echo "  ├── specs/               # Human-approved specifications 📝"
echo "  ├── docs/"
echo "  │   ├── adr/             # Architecture Decision Records 📚"
echo "  │   └── vendor/          # Fetched dependency docs 📦"
echo "  └── gironimo-run         # Convenience symlink"
echo ""
echo "Next steps:"
echo "1. Edit gironimo/.env with your DGX Spark IP"
echo "2. Activate the environment: source gironimo/.venv/bin/activate"
echo "3. Test the setup: ./gironimo-run --check"
echo "4. Start using Gironimo: ./gironimo-run \"Your feature request\""
echo ""
echo "To permanently add uv/bun to your PATH, add to ~/.bashrc:"
echo '  export PATH="$HOME/.cargo/bin:$HOME/.bun/bin:$PATH"'
echo ""
echo "For DGX Spark setup instructions, see the Gironimo README"
