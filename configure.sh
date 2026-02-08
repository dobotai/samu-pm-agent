#!/bin/bash

# ============================================
# PM Agent Configuration Wizard
# ============================================

set -e  # Exit on error

echo ""
echo "========================================"
echo "  PM Agent Configuration Wizard"
echo "========================================"
echo ""
echo "This wizard will help you set up your API keys."
echo ""
echo "Prerequisites:"
echo "- Anthropic API key (from console.anthropic.com)"
echo "- Slack bot token (from api.slack.com/apps)"
echo "- Airtable API key (from airtable.com/create/tokens)"
echo "- Airtable base ID (from your Airtable URL)"
echo ""
echo "See CLIENT_INSTALL.md for detailed instructions."
echo ""
read -p "Press Enter to continue..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "[ERROR] Virtual environment not found!"
    echo "Please run ./install.sh first."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Create backup of existing .env
if [ -f .env ]; then
    echo "Creating backup of existing configuration..."
    cp .env .env.backup
    echo "[OK] Backup saved as .env.backup"
    echo ""
fi

# Start configuration
echo "========================================"
echo "Step 1: Anthropic API Key"
echo "========================================"
echo ""
echo "This is required to power the AI agent."
echo "Get it from: https://console.anthropic.com/settings/keys"
echo ""
echo "Format: sk-ant-api03-..."
echo ""
read -p "Enter your Anthropic API key: " ANTHROPIC_API_KEY

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "[ERROR] API key cannot be empty"
    exit 1
fi

echo ""
echo "Testing Anthropic connection..."
python -c "import anthropic; client = anthropic.Anthropic(api_key='$ANTHROPIC_API_KEY'); print('[OK] Anthropic API key is valid')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[ERROR] Invalid Anthropic API key or connection failed"
    echo "Please check your key and internet connection"
    exit 1
fi

# Step 2: Slack
echo ""
echo "========================================"
echo "Step 2: Slack Bot Token"
echo "========================================"
echo ""
echo "Required to read messages and send notifications."
echo "Get it from: https://api.slack.com/apps"
echo ""
echo "Format: xoxb-..."
echo ""
read -p "Enter your Slack bot token: " SLACK_BOT_TOKEN

if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "[ERROR] Slack token cannot be empty"
    exit 1
fi

echo ""
echo "Testing Slack connection..."
python -c "from slack_sdk import WebClient; client = WebClient(token='$SLACK_BOT_TOKEN'); client.auth_test(); print('[OK] Slack bot token is valid')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[ERROR] Invalid Slack token or connection failed"
    echo "Please check your token and internet connection"
    exit 1
fi

# Step 3: Slack User Token (optional)
echo ""
read -p "Do you have a Slack user token? (y/n) " has_user_token
if [[ "$has_user_token" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Format: xoxp-..."
    read -p "Enter your Slack user token: " SLACK_USER_TOKEN
else
    SLACK_USER_TOKEN=""
fi

# Step 4: Airtable
echo ""
echo "========================================"
echo "Step 3: Airtable Configuration"
echo "========================================"
echo ""
echo "Required to read project data."
echo "Get token from: https://airtable.com/create/tokens"
echo ""
echo "Format: pat..."
echo ""
read -p "Enter your Airtable API key: " AIRTABLE_API_KEY

if [ -z "$AIRTABLE_API_KEY" ]; then
    echo "[ERROR] Airtable API key cannot be empty"
    exit 1
fi

echo ""
echo "Now enter your Airtable base ID."
echo "Find it in your Airtable URL: https://airtable.com/appXXXXXXXXXXXXXX/..."
echo ""
echo "Format: app..."
echo ""
read -p "Enter your Airtable base ID: " AIRTABLE_BASE_ID

if [ -z "$AIRTABLE_BASE_ID" ]; then
    echo "[ERROR] Base ID cannot be empty"
    exit 1
fi

echo ""
echo "Testing Airtable connection..."
python -c "from pyairtable import Api; api = Api('$AIRTABLE_API_KEY'); base = api.base('$AIRTABLE_BASE_ID'); print('[OK] Airtable credentials are valid')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[ERROR] Invalid Airtable credentials or base ID"
    echo "Please check your API key and base ID"
    exit 1
fi

# Step 5: Generate client API key
echo ""
echo "Generating secure client API key..."
CLIENT_API_KEY="pm_client_$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 24)"

# Step 6: Google Drive (optional)
echo ""
echo "========================================"
echo "Step 4: Google Drive (Optional)"
echo "========================================"
echo ""
read -p "Do you want to enable Google Drive access? (y/n) " enable_drive
if [[ "$enable_drive" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Please provide the path to your Google service account JSON file:"
    echo "Example: /path/to/service-account.json"
    echo ""
    read -p "Enter path to Google credentials: " GOOGLE_CREDS_PATH

    if [ -f "$GOOGLE_CREDS_PATH" ]; then
        echo "[OK] Google credentials file found"
        GOOGLE_CREDENTIALS_JSON="$GOOGLE_CREDS_PATH"
    else
        echo "[WARNING] File not found. Skipping Google Drive setup."
        GOOGLE_CREDENTIALS_JSON=""
    fi
else
    GOOGLE_CREDENTIALS_JSON=""
fi

# Write .env file
echo ""
echo "========================================"
echo "Saving Configuration"
echo "========================================"
echo ""

cat > .env << EOF
# PM Agent Configuration
# Generated by configure.sh on $(date)
# DO NOT COMMIT THIS FILE TO VERSION CONTROL

# ============================================
# CORE CREDENTIALS
# ============================================

ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
CLIENT_API_KEY=$CLIENT_API_KEY
CLIENT_NAME=youtube_agency

# ============================================
# SLACK INTEGRATION
# ============================================

SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN
SLACK_USER_TOKEN=$SLACK_USER_TOKEN

# ============================================
# AIRTABLE INTEGRATION
# ============================================

AIRTABLE_API_KEY=$AIRTABLE_API_KEY
AIRTABLE_BASE_ID=$AIRTABLE_BASE_ID

# ============================================
# GOOGLE DRIVE (OPTIONAL)
# ============================================

GOOGLE_CREDENTIALS_JSON=$GOOGLE_CREDENTIALS_JSON

# ============================================
# OPTIONAL INTEGRATIONS
# ============================================

SLACK_WEBHOOK_URL=
SENDGRID_API_KEY=
GOOGLE_TOKEN_JSON=
EOF

# Set restrictive permissions on .env
chmod 600 .env

echo "[OK] Configuration saved to .env"
echo ""
echo ""
echo "========================================"
echo "  Configuration Complete!"
echo "========================================"
echo ""
echo "Your API keys are securely stored in .env"
echo ""
echo "IMPORTANT SECURITY NOTES:"
echo "- Keep the .env file private"
echo "- Never share it or commit it to version control"
echo "- If compromised, regenerate all API keys immediately"
echo ""
echo "Next steps:"
echo ""
echo "1. Start the agent:"
echo "   ./start_agent.sh"
echo ""
echo "2. Open your browser to: http://localhost:8000"
echo ""
echo "3. Try asking questions like:"
echo "   - 'What videos are due this week?'"
echo "   - 'Show me urgent tasks'"
echo "   - \"What's Taylor's video status?\""
echo ""
echo ""
