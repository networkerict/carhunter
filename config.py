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


# Source plugins and instances
# Each source plugin can have multiple instances (e.g., regional variants)
# The registry loads plugins and instances from this configuration

SOURCE_REGISTRY = {
    "autoscout24": {
        "enabled": True,
        "max_pages": 100,
    },
    "mobile_de": {
        "enabled": True,
        "max_pages": 10,
        "page_size": 50,
    },
    "pkw_de": {
        "enabled": True,
        "max_pages": 20,
    },
}

# Source instances configuration
# Maps instance_id -> instance configuration
# The multi-source coordinator will execute all enabled instances

SOURCE_INSTANCES = {
    "autoscout24_primary": {
        "source_family": "autoscout24",
        "plugin_id": "autoscout24",
        "enabled": True,
        "provenance_identity": "autoscout24.de",
    },
    "mobile_de_primary": {
        "source_family": "mobile_de",
        "plugin_id": "mobile_de",
        "enabled": True,
        "provenance_identity": "mobile.de",
    },
    "pkw_de_primary": {
        "source_family": "pkw_de",
        "plugin_id": "pkw_de",
        "enabled": True,
        "provenance_identity": "pkw.de",
    },
}


# Logging

DEBUG_LEVEL = "INFO"
