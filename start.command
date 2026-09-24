#!/bin/bash
# macOS: double-click to run from source (python.org Python 3.10+ recommended).
cd "$(dirname "$0")" || exit 1
for py in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys, tkinter; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
        exec "$py" app.py
    fi
done
echo 'Python 3.10 이상(tkinter 포함)을 찾지 못했습니다. https://www.python.org/downloads/macos/ 에서 설치하세요.'
read -r -p '엔터를 누르면 창을 닫습니다...'
