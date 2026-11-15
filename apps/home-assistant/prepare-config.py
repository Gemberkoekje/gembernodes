"""prepare-config.py [config dir] [definitions dir]: get the config volume ready before Home
Assistant starts.

Runs as an init container on Home Assistant's own image (deployment.yaml), so it needs nothing but
the Python standard library. Safe to run on every start.

1. Creates the files configuration.yaml includes (automations.yaml, scripts.yaml, scenes.yaml)
   with the same empty contents Home Assistant gives them on a fresh install. Home Assistant only
   writes them itself when it also writes configuration.yaml, and ours comes from Git. Existing
   files are left alone.
2. Copies our own Tuya Local device definitions (tuya-local/*.yaml, mounted from a ConfigMap)
   into custom_components/tuya_local/devices. Tuya Local only reads definitions from that folder,
   and a Tuya Local update from the Marketplace replaces the folder wholesale. An update needs a
   restart, so copying ours back on every start puts them back before Tuya Local loads. Skipped
   while Tuya Local isn't installed.

It used to install HACS too. Since 2026.11 HACS is built into Home Assistant as the Marketplace,
which blocks the old custom integration and deletes its folder (custom_components/hacs) by itself.
"""

import os
import sys

CONFIG = sys.argv[1] if len(sys.argv) > 1 else "/config"
DEFINITIONS = sys.argv[2] if len(sys.argv) > 2 else "/tuya-local-devices"

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


def install_tuya_local_definitions():
    if not os.path.isdir(DEFINITIONS):
        return
    target = os.path.join(CONFIG, "custom_components", "tuya_local", "devices")
    if not os.path.isdir(target):
        print("Tuya Local isn't installed; not copying its device definitions")
        return

    # A ConfigMap volume also holds hidden ..data entries; only the files themselves count.
    names = sorted(
        n
        for n in os.listdir(DEFINITIONS)
        if n.endswith(".yaml") and not n.startswith(".")
        and os.path.isfile(os.path.join(DEFINITIONS, n))
    )
    for name in names:
        with open(os.path.join(DEFINITIONS, name), "rb") as f:
            wanted = f.read()
        path = os.path.join(target, name)
        try:
            with open(path, "rb") as f:
                if f.read() == wanted:
                    print(f"Tuya Local definition {name} is up to date")
                    continue
        except FileNotFoundError:
            pass
        # Write next to it and rename, so Tuya Local never reads a half-written file.
        with open(path + ".tmp", "wb") as f:
            f.write(wanted)
        os.replace(path + ".tmp", path)
        print(f"installed Tuya Local definition {name}")


if __name__ == "__main__":
    create_included_files()
    install_tuya_local_definitions()
