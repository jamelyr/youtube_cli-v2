#!/bin/bash

# This script installs the dependencies for the Advanced YouTube CLI.
# It installs Python packages via pip and attempts to install the 'mpv' media player.

echo "--- Advanced YouTube CLI Installer ---"

# --- Step 1: Install Python dependencies ---
echo ""
echo "[1/2] Installing Python packages from requirements.txt..."

# It's highly recommended to run this in a virtual environment.
# python3 -m venv venv
# source venv/bin/activate

pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "Error: Failed to install Python packages. Please check your pip and Python setup."
    exit 1
fi

echo "Python packages installed successfully."

# --- Step 2: Install MPV media player ---
echo ""
echo "[2/2] Checking for and installing 'mpv' media player..."
echo "This may require you to enter your administrator (sudo) password."

# Check for package manager and install mpv
if command -v apt-get &> /dev/null; then
    # Debian/Ubuntu
    echo "Detected apt-get. Installing mpv..."
    sudo apt-get update
    sudo apt-get install mpv -y
elif command -v dnf &> /dev/null; then
    # Fedora/CentOS
    echo "Detected dnf. Installing mpv..."
    sudo dnf install mpv -y
elif command -v pacman &> /dev/null; then
    # Arch Linux
    echo "Detected pacman. Installing mpv..."
    sudo pacman -Syu --noconfirm mpv
elif command -v brew &> /dev/null; then
    # macOS with Homebrew
    echo "Detected Homebrew. Installing mpv..."
    brew install mpv
else
    echo "Could not detect a supported package manager (apt, dnf, pacman, brew)."
    echo "Please install 'mpv' manually from your system's package manager or from https://mpv.io/installation/"
    exit 1
fi

if [ $? -ne 0 ]; then
    echo "Error: Failed to install 'mpv'. Please try installing it manually."
    exit 1
fi

echo ""
echo "--- Installation Complete! ---"
echo "You can now run the application with: python3 youtube_cli.py"
