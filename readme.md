# YouTube CLI

A modern, fast, and feature-rich TUI for searching and playing YouTube videos from your terminal.

![Screenshot of YouTube CLI in action](https://your-image-host.com/youtube-cli-screenshot.png) 
*(**Action Required:** Replace this with a link to a real screenshot of the app!)*

This application provides a keyboard-driven interface to YouTube, built with Python and the Textual framework. It's designed for developers and power-users who prefer to stay in the terminal.

## Features

- **Fast, Asynchronous Search:** Instantly search YouTube without leaving the terminal.
- **`mpv` Integration:** Uses the powerful `mpv` engine for high-quality, efficient video playback.
- **Autoplay & Queue System:** Automatically plays the next video or lets you build a custom "play next" queue.
- **Configurable Quality:** Defaults to a bandwidth-friendly 480p, but is fully configurable.
- **Focus Modes:** Seamlessly toggle between the search input and the results list with a single key.
- **Modern UI:** A clean, modern, and responsive terminal user interface.

## Installation

This project is designed for Linux-based systems.

### Prerequisites

You must have the following dependencies installed on your system:

1.  **Python 3.8+** and `pip`
2.  **`mpv`**: The video player.
    -   On Debian/Ubuntu: `sudo apt update && sudo apt install mpv`
    -   On Arch Linux: `sudo pacman -S mpv`
    -   On Fedora: `sudo dnf install mpv`

### Automated Installation

An installation script is provided to automate the setup.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/jamelyr/youtube-cli.git
    cd youtube-cli
    ```

2.  **Make the script executable:**
    ```bash
    chmod +x install.sh
    ```

3.  **Run the installer:**
    ```bash
    ./install.sh
    ```

This script will create a virtual environment, install all Python dependencies, and make the `youtube-cli` command available system-wide (within the context of the venv).

## Usage

Once installed, you can run the application from any directory:

```bash
# If you followed the install script, activate the venv first
source venv/bin/activate

# Run the application
youtube-cli
