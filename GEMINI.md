# Bilibili Follow Manager

A modern, GUI-based tool for managing Bilibili followings, allowing users to view, search, export, and batch unfollow/follow users efficiently.

## Project Overview

This application provides a user-friendly interface to manage Bilibili subscriptions. It uses `tkinter` for the GUI and direct API calls for interacting with Bilibili's services. It includes features for automatic login (via Selenium), local data caching, and anti-scraping protection mechanisms.

### Key Features
- **Auto Login:** Captures login credentials using a Selenium-controlled browser.
- **Smart Display:** Shows detailed user info (UID, sign, follow time).
- **Batch Operations:** Support for batch unfollowing and following.
- **Data Management:** Export and import follow lists as JSON.
- **Anti-Control:** Built-in delays and retries to avoid API rate limiting.

## File Structure

- **`app.py`**: The main entry point of the application.
- **`gui.py`**: Contains the complete GUI implementation, including:
    - `BilibiliManagerGUI`: Main window and event handling.
    - `DataManager`: Handles local data storage (`data/following_data.json`) and caching.
    - `SearchService`: Provides search functionality with history.
- **`bilibili_api.py`**: Handles all network interactions with Bilibili APIs.
    - Includes `AntiAntiControl` class to manage request delays and retries.
- **`auto_login.py`**: Uses Selenium to open a browser for the user to log in, then extracts cookies to `config.json`.
- **`launch.bat`**: Windows batch script to launch the application.
- **`config.json`** (Generated): Stores session cookies and application settings.

## Setup and Usage

### Prerequisites
- Python 3.x
- Google Chrome (required for the login process)

### Installation

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### Running the Application

1.  **Start the GUI:**
    ```bash
    python app.py
    ```
    Or run `launch.bat` on Windows.

2.  **First Time Login:**
    - Click "🔐 设置登录" (Setup Login) in the GUI.
    - A Chrome window will open. Log in to Bilibili manually.
    - The application will automatically detect the login and save credentials to `config.json`.

## Development Conventions

- **GUI Framework:** Built with `tkinter` and `ttk`.
- **Data Persistence:** User data is cached in `data/following_data.json` to reduce API calls.
- **API Safety:** `bilibili_api.py` implements exponential backoff and random jitter to mimic human behavior and avoid bans.
- **Configuration:** Settings and auth tokens are stored in `config.json`. **Do not commit this file.**

## Troubleshooting

- **Login Fails:** Ensure Google Chrome is installed and updated. The `webdriver-manager` library will attempt to download the matching driver automatically.
- **API Errors:** If you encounter persistent errors, Bilibili may have updated their API or triggered a temporary IP ban. Wait a while before retrying.
