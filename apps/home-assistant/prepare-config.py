"""prepare-config.py [config dir]: get the config volume ready before Home Assistant starts.

Runs as an init container on Home Assistant's own image (deployment.yaml), so it needs nothing but
the Python standard library. Safe to run on every start: it only adds what is missing.

It creates the files configuration.yaml includes (automations.yaml, scripts.yaml, scenes.yaml)
with the same empty contents Home Assistant gives them on a fresh install. Home Assistant only
writes them itself when it also writes configuration.yaml, and ours comes from Git.

It used to install HACS too. Since 2026.11 HACS is built into Home Assistant as the Marketplace,
which blocks the old custom integration and deletes its folder (custom_components/hacs) by itself.
"""

import os
import sys

CONFIG = sys.argv[1] if len(sys.argv) > 1 else "/config"

# Home Assistant's own contents for these files on a fresh install (homeassistant/config.py).
INCLUDED_FILES = {
    "automations.yaml": "[]",
    "scripts.yaml": "",
    "scenes.yaml": "",
}


def create_included_files():
    for name, content in INCLUDED_FILES.items():
        path = os.path.join(CONFIG, name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"created {name}")


if __name__ == "__main__":
    create_included_files()
