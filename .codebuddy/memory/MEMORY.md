# Heuristic Shadow Project

## Overview
Desktop/OS-Level autonomous agent that observes human-computer interactions to discover and automate repetitive workflows. Python 3.13 + PySide6 (Qt) + MySQL + AI-powered (DeepSeek/Qwen/Hunyuan fallback).

## Key Configuration
- MySQL: HeuristicShadow @ 127.0.0.1:3306 (user: root)
- AI Providers: DeepSeek -> Qwen -> Hunyuan (automatic fallback chain)
- Pattern Confidence Threshold: 0.75
- OCR: EasyOCR (en + ch_sim)

## Architecture
```
main.py                          # Entry point (GUI/headless/mine-only/health modes)
config.py                        # Centralized .env-based configuration
src/
  core/
    listener.py                  # pynput + win32 event monitoring
    privacy.py                   # Sensitive context detection & masking
    ocr_engine.py                # EasyOCR screen text extraction
    pattern_miner.py             # PrefixSpan-inspired sequence mining
  ai/
    llm_client.py                # Multi-provider: DeepSeek/Qwen/Hunyuan
    script_generator.py          # LLM -> PyAutoGUI script synthesis
  db/
    database.py                  # SQLAlchemy MySQL/SQLite
    models.py                    # raw_events, detected_patterns, automation_scripts
  sandbox/
    executor.py                  # Script validation + sandbox execution
  ui/
    tray.py                      # PySide6 system tray application
    overlay.py                   # Floating authorization overlay
```

## Usage
- `python main.py` - GUI (system tray)
- `python main.py --no-gui` - Headless background service  
- `python main.py --mine-only` - One-shot pattern mining
- `python main.py --health` - Component health checks
- `python main.py -v` - Verbose logging

## Dependencies
PySide6, pynput, pyautogui, pillow, easyocr, sqlalchemy, pymysql, openai, httpx, python-dotenv, psutil, pywin32, numpy, colorlog
