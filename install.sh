#!/bin/bash
#
# YouTube CLI Installer (Definitive Symlink Method)
# This script creates an isolated environment for the application and then
# creates a symbolic link to make the command globally available for the user.
# This respects modern, externally-managed Python environments (PEP 668).
#

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- YouTube CLI Definitive Installer ---"
echo ""

# --- Dependency Check ---
echo "Step 1: Checking for required system dependencies..."

if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 is not installed. Please install Python 3.8+ and try again."
    exit 1
fi
echo "✅ Python 3 found."

if ! command -v mpv &> /dev/null; then
    echo "ERROR: mpv is not installed. Please install mpv using your package manager."
    exit 1
fi
echo "✅ mpv found."
echo ""

# --- Step 2: Create the Isolated Engine (Virtual Environment) ---
VENV_DIR="venv"
echo "Step 2: Building isolated application engine in './${VENV_DIR}'..."
if [ -d "$VENV_DIR" ]; then
    echo "--> Engine directory already exists. Re-validating."
else
    python3 -m venv "$VENV_DIR"
    echo "--> Engine directory created."
fi
# Activate the venv for the context of this script
source "${VENV_DIR}/bin/activate"
echo "--> Engine activated for installation."
echo ""

# --- Step 3: Install Application into the Isolated Engine ---
echo "Step 3: Installing application and dependencies into the engine..."
# We use pip to install into the now-active venv. This is safe.
pip install --upgrade pip
pip install -e .
echo "--> Application installed successfully."
echo ""

# --- Step 4: Forge the Global Key (Symbolic Link) ---
USER_BIN_DIR="$HOME/.local/bin"
EXECUTABLE_NAME="youtube-cli"
SYMLINK_PATH="${USER_BIN_DIR}/${EXECUTABLE_NAME}"
VENV_EXECUTABLE_PATH="$(pwd)/${VENV_DIR}/bin/${EXECUTABLE_NAME}"

echo "Step 4: Forging global command key..."
# Ensure the user's local bin directory exists
mkdir -p "$USER_BIN_DIR"
echo "--> Ensured '$USER_BIN_DIR' directory exists."

# Remove any old symlink to ensure we're creating a fresh one
if [ -L "${SYMLINK_PATH}" ]; then
    rm -f "${SYMLINK_PATH}"
    echo "--> Removed old key."
fi

# Create the symbolic link
ln -s "$VENV_EXECUTABLE_PATH" "$SYMLINK_PATH"
echo "--> Forged new key at '$SYMLINK_PATH'."
echo ""

# --- Step 5: PATH Verification ---
echo "Step 5: Verifying key is in system PATH..."
if [[ ":$PATH:" != *":$USER_BIN_DIR:"* ]]; then
    echo "⚠️  WARNING: Your PATH does not seem to include '$USER_BIN_DIR'."
    echo "    The 'youtube-cli' command may not be available until you log out and log back in,"
    echo "    or add the following line to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
    echo ""
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
else
    echo "✅ Your PATH is correctly configured to find the key."
fi

# --- Final Instructions ---
echo "--- ✅ DEPLOYMENT COMPLETE ---"
echo ""
echo "To run the application, open a NEW terminal session and simply type:"
echo ""
echo "   youtube-cli"
echo ""
