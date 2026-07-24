"""
AutoHunter v2.4
Debug and logging framework
"""

from datetime import datetime
import os


DEBUG_LEVEL = "INFO"


def enable_debug():

    global DEBUG_LEVEL

    DEBUG_LEVEL = "DEBUG"


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

LOG_DIR = os.path.join(
    BASE_DIR,
    "logs"
)

LOG_FILE = os.path.join(
    LOG_DIR,
    "autohunter.log"
)

def log(level, message):

    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    line = (
        f"{timestamp} [{level}] {message}"
    )

    # console output
    print(line)

    # logfile output
    with open(
        LOG_FILE,
        "a",
        encoding="utf-8"
    ) as file:
        file.write(line + "\n")


def info(message):
    log(
        "INFO",
        message
    )


def warning(message):
    log(
        "WARNING",
        message
    )


def error(message):
    log(
        "ERROR",
        message
    )


def debug(message):

    if DEBUG_LEVEL == "DEBUG":
        log(
            "DEBUG",
            message
        )
