#!/usr/bin/env bash
# 桌宠一键启动（git-bash / Linux 下使用）
cd "$(dirname "$0")" || exit 1
exec ./.venv/Scripts/python main.py "$@"
