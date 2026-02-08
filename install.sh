#!/bin/bash

# ============================================
# PM Agent Installer for Mac/Linux
# ============================================

set -e  # Exit on error

echo ""
echo "========================================"
echo "  PM Agent Installation Wizard"
echo "========================================"
echo ""

# Step 1: Check if Python is installed
echo "[1/5] Checking for Python..."
if ! command -v python3 &> /dev/null; then
    echo ""
    echo "[ERROR] Python 3 not found!"
    echo ""
    echo "Please install Python 3.10 or newer:"
    echo "  Mac: brew install python@3.10"
    echo "  Ubuntu/Debian: sudo apt install python3.10 python3-pip python3-venv"
    echo "  Fedora: sudo dnf install python3.10"
    echo ""
    echo "Then run this installer again."
    exit 1
else
    python3 --version
    echo "[OK] Python found"
fi

# Step 2: Create virtual environment
echo ""
echo "[2/5] Creating isolated Python environment..."
if [ -d "venv" ]; then
    echo "[WARNING] Virtual environment already exists. Recreating..."
    rm -rf venv
fi
python3 -m venv venv
echo "[OK] Environment created"

# Step 3: Activate virtual environment and upgrade pip
echo ""
echo "[3/5] Activating environment and upgrading installer..."
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel > /dev/null 2>&1
echo "[OK] Environment ready"

# Step 4: Install dependencies
echo ""
echo "[4/5] Installing required packages (this may take 2-3 minutes)..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install dependencies"
    echo "Check your internet connection and try again"
    exit 1
fi
echo "[OK] All packages installed"

# Step 5: Create necessary directories
echo ""
echo "[5/5] Setting up folders..."
mkdir -p .tmp/logs
mkdir -p .tmp/sessions
mkdir -p config/clients
echo "[OK] Folders created"

# Create .env template if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Creating configuration template..."
    cat > .env << EOF
# PM Agent Configuration
# Fill in your API keys using configure.sh

ANTHROPIC_API_KEY=
CLIENT_API_KEY=pm_client_key_$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 16)
CLIENT_NAME=youtube_agency

SLACK_BOT_TOKEN=
SLACK_USER_TOKEN=

AIRTABLE_API_KEY=
AIRTABLE_BASE_ID=

GOOGLE_CREDENTIALS_JSON=
EOF
    echo "[OK] Configuration template created"
fi

# Create start script
cat > start_agent.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
echo ""
echo "========================================"
echo "  PM Agent Server Starting..."
echo "========================================"
echo ""
python execution/api_server.py
EOF
chmod +x start_agent.sh

# Create chat script
cat > agent_chat.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python -c "from execution.orchestrator import interactive_chat; interactive_chat()"
EOF
chmod +x agent_chat.sh

# Make configure script executable
chmod +x configure.sh 2>/dev/null || true

# Installation complete
echo ""
echo ""
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Get your API keys (see CLIENT_INSTALL.md for instructions):"
echo "   - Anthropic API key"
echo "   - Slack bot token"
echo "   - Airtable API key and base ID"
echo ""
echo "2. Run: ./configure.sh"
echo "   This will help you enter your API keys"
echo ""
echo "3. Start the agent:"
echo "   ./start_agent.sh"
echo ""
echo "4. Open your browser to: http://localhost:8000"
echo ""
echo ""
echo "For detailed instructions, see CLIENT_INSTALL.md"
echo ""
