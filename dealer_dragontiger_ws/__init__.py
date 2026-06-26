"""
Package initialiser – installs SelectorEventLoopPolicy on Windows **before**
any module asks asyncio for a loop.
"""
import sys, asyncio, logging

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    logging.getLogger("asyncio").info(
        "SelectorEventLoopPolicy installed (Dragon-Tiger)")
