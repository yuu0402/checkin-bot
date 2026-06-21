#!/usr/bin/env python3
"""cron_checkin.py - 兼容旧 crontab/手动调用"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tg_bot import run_all, logger

if __name__ == '__main__':
    logger.info("=== Direct cron invocation ===")
    run_all()
