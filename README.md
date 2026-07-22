# Heuristic Shadow

> Desktop/OS-Level autonomous agent that watches your computer usage, discovers repetitive workflows, and auto-generates automation scripts — all running locally with privacy-first design.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()

---

## What It Does

```
YOU work normally  →  Agent observes clicks, keys, windows  →  Finds patterns
                                                                  ↓
                          YOU approve & run  ←  AI generates PyAutoGUI script
```

## Features

- Clicks, keystrokes, window switches — all captured via **pynput + Win32**
- Screen text around clicks extracted with **EasyOCR** (English + Chinese)
- **Privacy-first**: Banking/password apps filtered, all data stays local
- Repeating workflows mined with **PrefixSpan-inspired** sequence mining
- Scripts generated via **AI fallback chain**: DeepSeek → Qwen → Hunyuan
- Sandboxed **PyAutoGUI** execution with abort-on-corner fail-safe
- **System tray GUI** (right-click for Dashboard, Patterns, Scripts)

## Requirements

```
# UI & Monitoring
PySide6>=6.5.0           # System tray + dialogs (Qt)
pynput>=1.7.6            # Mouse & keyboard hooking
pyautogui>=0.9.54        # Script execution (simulate input)
pywin32>=306             # Windows API calls (window titles, etc.)
psutil>=5.9.5            # Process detection (privacy filter)

# OCR
easyocr>=1.7.0           # Screen text recognition (EN + CN)
numpy>=1.24.0
pillow>=10.0.0           # Screenshot capture

# AI — all providers use OpenAI-compatible API format
# DeepSeek, Qwen, Hunyuan accept the same request/response structure
openai>=1.6.0            # HTTP client for AI API calls (NOT OpenAI servers!)
httpx>=0.25.0

# Database
sqlalchemy>=2.0.20       # ORM (MySQL or SQLite)
pymysql>=1.1.0           # MySQL driver
cryptography>=41.0.0

# Utilities
python-dotenv>=1.0.0     # .env file loading
colorlog>=6.7.0          # Colored terminal logs
```

## AI Providers

| Provider | Model | Role |
|----------|-------|------|
| **DeepSeek** | deepseek-chat | Primary — first to try |
| **Qwen** | qwen-plus | Fallback #1 |
| **Hunyuan** | hunyuan-lite | Fallback #2 |

> **Why `openai` in requirements?** DeepSeek, Qwen, and Hunyuan all expose OpenAI-compatible APIs. The `openai` Python package is used only as an HTTP client library — it never calls OpenAI servers. All requests go to `api.deepseek.com`, `dashscope.aliyuncs.com`, or `api.hunyuan.cloud.tencent.com`.

## Architecture

```
Heuristic Shadow/
├── main.py                    # Entry: GUI / headless / mine-only / health
├── config.py                  # .env configuration loader
├── src/
│   ├── core/
│   │   ├── listener.py        # Event capture (mouse/keyboard/window)
│   │   ├── privacy.py         # Sensitive context filter
│   │   ├── ocr_engine.py      # EasyOCR wrapper
│   │   └── pattern_miner.py   # Sequence mining engine
│   ├── ai/
│   │   ├── llm_client.py      # DeepSeek→Qwen→Hunyuan fallback
│   │   └── script_generator.py # Pattern → PyAutoGUI script
│   ├── db/
│   │   ├── database.py        # SQLAlchemy (MySQL / SQLite)
│   │   └── models.py          # Events, Patterns, Scripts tables
│   ├── sandbox/
│   │   └── executor.py        # Validation + safe execution
│   └── ui/
│       ├── tray.py            # System tray icon + menus
│       └── overlay.py         # Authorization popup
└── scripts/generated/         # Output: auto-generated .py scripts
```

## Database Schema

| Table | Stores |
|-------|--------|
| `raw_events` | Mouse clicks, keystrokes, window changes |
| `detected_patterns` | Mined workflows + confidence scores |
| `automation_scripts` | Generated PyAutoGUI Python code |
| `pattern_dismissals` | User-rejected patterns |

## Quick Start

```bash
git clone https://github.com/simul49/Desktop-OS-Level-Heuristic-Shadow-Agent.git
cd Desktop-OS-Level-Heuristic-Shadow-Agent
pip install -r requirements.txt
```

Create `.env`:

```env
DB_NAME=HeuristicShadow
DB_USER=root
DB_PASSWORD=your_password
DB_HOST=127.0.0.1
DB_PORT=3306

DEEPSEEK_API_KEY=sk-xxx
QWEN_API_KEY=sk-xxx
HUNYUAN_API_KEY=sk-xxx
```

Run:

```bash
python main.py              # GUI (system tray)
python main.py --no-gui     # Headless background
python main.py --mine-only  # One-shot pattern mining
python main.py --health     # Verify all components
```

## Usage Flow

1. **Right-click** purple "HS" tray icon (`^` near clock)
2. Use computer normally — agent captures interactions
3. Every 5 min → patterns auto-mined
4. **Discovered Patterns** → pick one → **Generate Script**
5. **Automation Scripts** → review code → **Execute**

## License

MIT
