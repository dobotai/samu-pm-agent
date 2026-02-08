#!/bin/bash

# ============================================
# Client Package Builder
# Creates a clean package ready to send to client
# ============================================

set -e

echo ""
echo "========================================"
echo "  Client Package Builder"
echo "========================================"
echo ""

# Set package name
PACKAGE_NAME="pm-agent-client-package"
TIMESTAMP=$(date +%Y%m%d)
OUTPUT_DIR="../${PACKAGE_NAME}"

echo "This will create a clean package in:"
echo "$OUTPUT_DIR"
echo ""
echo "WARNING: Your .env file with API keys will NOT be included."
echo "The client will need to create their own .env file."
echo ""
read -p "Continue? (y/n) " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    exit 0
fi

# Create output directory
echo ""
echo "[1/6] Creating package directory..."
if [ -d "$OUTPUT_DIR" ]; then
    echo "Cleaning existing package directory..."
    rm -rf "$OUTPUT_DIR"
fi
mkdir -p "$OUTPUT_DIR"
echo "[OK] Directory created"

# Copy core files (exclude sensitive files)
echo ""
echo "[2/6] Copying core files..."
rsync -av \
    --exclude='.env' \
    --exclude='.env.backup' \
    --exclude='credentials.json' \
    --exclude='token.json' \
    --exclude='.tmp/' \
    --exclude='.git/' \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='test_*.py' \
    --exclude='package_for_client.sh' \
    --exclude='package_for_client.bat' \
    --exclude='.DS_Store' \
    --exclude='tmpclaude-*' \
    --exclude='nul' \
    . "$OUTPUT_DIR/"
echo "[OK] Core files copied"

# Remove any remaining sensitive files
echo ""
echo "[3/6] Removing sensitive files..."
find "$OUTPUT_DIR" -name ".env*" -exec rm -f {} \; 2>/dev/null || true
find "$OUTPUT_DIR" -name "credentials.json" -exec rm -f {} \; 2>/dev/null || true
find "$OUTPUT_DIR" -name "token.json" -exec rm -f {} \; 2>/dev/null || true
find "$OUTPUT_DIR" -name "*.pyc" -exec rm -f {} \; 2>/dev/null || true
find "$OUTPUT_DIR" -name "__pycache__" -type d -exec rm -rf {} \; 2>/dev/null || true
echo "[OK] Sensitive files removed"

# Create .tmp directory structure
echo ""
echo "[4/6] Creating empty directories..."
mkdir -p "$OUTPUT_DIR/.tmp/logs"
mkdir -p "$OUTPUT_DIR/.tmp/sessions"
mkdir -p "$OUTPUT_DIR/config/clients"
echo "[OK] Directories created"

# Create placeholder .env
echo ""
echo "[5/6] Creating configuration template..."
cat > "$OUTPUT_DIR/.env" << 'EOF'
# PM Agent Configuration
# Run configure.sh to set up your API keys

ANTHROPIC_API_KEY=
CLIENT_API_KEY=
CLIENT_NAME=youtube_agency

SLACK_BOT_TOKEN=
SLACK_USER_TOKEN=

AIRTABLE_API_KEY=
AIRTABLE_BASE_ID=

GOOGLE_CREDENTIALS_JSON=
EOF
echo "[OK] Template created"

# Create verification file
echo ""
echo "[6/6] Creating package manifest..."
cat > "$OUTPUT_DIR/START_HERE.txt" << EOF
PM Agent Client Package
Generated: $(date)

INSTALLATION INSTRUCTIONS:
1. Read CLIENT_PACKAGE_README.md
2. Follow CLIENT_INSTALL.md for detailed setup
3. Run install.sh (Mac/Linux) or install.bat (Windows)
4. Run configure.sh/bat to enter API keys
5. Start the agent with start_agent.sh/bat

SUPPORT: Contact your agent provider for assistance
EOF
echo "[OK] Manifest created"

# Make scripts executable
chmod +x "$OUTPUT_DIR"/*.sh 2>/dev/null || true

# Create ZIP archive (optional)
echo ""
read -p "Create ZIP archive? (y/n) " create_zip
if [[ "$create_zip" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Creating ZIP archive..."
    cd ..
    zip -r "${PACKAGE_NAME}-${TIMESTAMP}.zip" "${PACKAGE_NAME}" -x "*.DS_Store" > /dev/null
    cd - > /dev/null
    echo "[OK] ZIP created: ../${PACKAGE_NAME}-${TIMESTAMP}.zip"
fi

# Summary
echo ""
echo ""
echo "========================================"
echo "  Package Created Successfully!"
echo "========================================"
echo ""
echo "Location: $OUTPUT_DIR"
if [[ "$create_zip" =~ ^[Yy]$ ]]; then
    echo "ZIP file: ../${PACKAGE_NAME}-${TIMESTAMP}.zip"
fi
echo ""
echo "Next steps:"
echo "1. Review $OUTPUT_DIR to verify everything looks correct"
echo "2. Check DEPLOYMENT_CHECKLIST.md for final verification"
echo "3. Send the package to your client"
echo ""
echo "The package is ready to send to your client!"
echo ""
