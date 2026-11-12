"""prepare-config.py [config dir]: get the config volume ready before Home Assistant starts.

Runs as an init container on Home Assistant's own image (deployment.yaml), so it needs nothing but
the Python standard library. Safe to run on every start: it only adds what is missing.

1. Creates the files configuration.yaml includes (automations.yaml, scripts.yaml, scenes.yaml)
   with the same empty contents Home Assistant gives them on a fresh install. Home Assistant only
   writes them itself when it also writes configuration.yaml, and ours comes from Git.
2. Installs HACS into custom_components/hacs if it isn't there yet: the release zip named by
   HACS_VERSION, checked against HACS_SHA256 before anything is unpacked. Once installed, HACS
   updates itself from its own page, and this step leaves it alone.

Neither step stops Home Assistant from starting: a failed download, or a zip that doesn't match
its checksum, is logged and skipped. Home Assistant then starts without HACS, and the next start
tries again. A zip that fails the checksum is never unpacked.
"""

import hashlib
import io
import os
import shutil
import sys
import urllib.request
import zipfile

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


def install_hacs():
    version = os.environ["HACS_VERSION"]
    expected = os.environ["HACS_SHA256"].lower()
    components = os.path.join(CONFIG, "custom_components")
    target = os.path.join(components, "hacs")
    if os.path.exists(os.path.join(target, "manifest.json")):
        print("HACS is already installed; leaving it alone")
        return

    url = f"https://github.com/hacs/integration/releases/download/{version}/hacs.zip"
    print(f"installing HACS {version} from {url}")
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    except OSError as e:
        print(f"HACS download failed, starting without it: {e}")
        return

    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        print(f"HACS zip checksum mismatch (expected {expected}, got {actual}); not installing it")
        return

    # Unpack next to the target and rename, so a half-unpacked folder never looks installed.
    staging = os.path.join(components, ".hacs-staging")
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        archive.extractall(staging)
    shutil.rmtree(target, ignore_errors=True)
    os.rename(staging, target)
    print(f"HACS {version} installed in {target}")


if __name__ == "__main__":
    create_included_files()
    install_hacs()
