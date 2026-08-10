"""
AutoHunter v3.0-dev
Configuration
"""


APP_NAME = "AutoHunter"

VERSION = "3.0-dev"


# Vehicle search

BRAND = "Audi"

MODEL = "A5 Cabrio"


# Database

DATABASE = "carhunter.db"


SOURCE_REGISTRY = {
    "autoscout24": {
        "enabled": True,
        "max_pages": 100,
    }
}


# Logging

DEBUG_LEVEL = "INFO"
