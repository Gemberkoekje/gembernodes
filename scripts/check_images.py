#!/usr/bin/env python3
"""Checks that the container images a pull request adds or changes exist in their registries. From the
repository root:

    python3 scripts/check_images.py [base]

`base` is what the pull request merges into (default: origin/main). Most image tags here are commit SHAs
or build numbers that another repository's CI pushes once it has built them. A deploy PR merged before
that has finished rolls out an image that doesn't exist yet, and its pods sit in ImagePullBackOff (the
API deployments are `Recreate`, so the old pod is gone by then).

- An image the registry has passes; one it says it doesn't have (404) is looked for again every 30
  seconds for IMAGE_WAIT_MINUTES (20 by default), so a deploy PR opened while the image still builds
  turns green by itself, and then fails if it never shows up.
- An image the registry won't show us (a private package) can't be checked: a warning. On ghcr.io a
  token in GHCR_TOKEN is tried for those (the workflow passes its GITHUB_TOKEN, with packages: read,
  which reads only the packages that give this repository access).
- Only `image:` lines count, as Deployments, StatefulSets, CronJobs and Jobs write them; an image a Helm
  chart builds from separate repository and tag values isn't checked, nor one a line only moves.

Needs nothing beyond Python 3 and git.
"""

import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

IMAGE_LINE = re.compile(r"""^\+\s*(?:-\s*)?image:\s*["']?([^\s"'#]+)""")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")
MANIFEST_TYPES = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])
DOCKER_HUB = "registry-1.docker.io"
RETRY_SECONDS = 30

problems = {"error": 0, "warning": 0}


def report(level, message, file=None, line=None):
    """Prints a problem; in GitHub Actions also as an annotation on the file (as scripts/validate.py does)."""
    problems[level] += 1
    if os.environ.get("GITHUB_ACTIONS") == "true":
        where = ",".join(p for p in (f"file={file}" if file else "", f"line={line}" if line else "") if p)
        text = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::{level}{' ' + where if where else ''}::{text}")
    else:
        location = f"{file}{f':{line}' if line else ''}: " if file else ""
        print(f"{level.upper()}: {location}{message}")


def changed_images(base):
    """The image references the pull request adds, each with the first file and line that adds it."""
    diff = subprocess.run(
        ["git", "diff", "--unified=0", "--no-color", "--no-ext-diff", f"{base}...HEAD", "--", "*.yaml", "*.yml"],
        capture_output=True, text=True, check=True).stdout
    images = {}
    file, line = None, 0
    for text in diff.splitlines():
        if text.startswith("+++ "):
            file = text[6:] if text.startswith("+++ b/") else None
        elif text.startswith("@@"):
            match = HUNK.match(text)
            line = int(match.group(1)) if match else 0
        elif text.startswith("+") and file:
            match = IMAGE_LINE.match(text)
            # A templated reference (${...}, {{ ... }}) is filled in elsewhere: nothing to look up.
            if match and not any(mark in match.group(1) for mark in ("$", "{")):
                images.setdefault(match.group(1), (file, line))
            line += 1
    return images


def parse(image):
    """The registry host, repository and tag (or digest) of an image reference, as `docker pull` reads it."""
    name, reference = image, "latest"
    if "@" in name:
        name, reference = name.split("@", 1)
    elif ":" in name.rsplit("/", 1)[-1]:
        name, reference = name.rsplit(":", 1)
    first, _, rest = name.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        registry, repository = first, rest
    else:
        registry, repository = DOCKER_HUB, name
    if registry in ("docker.io", "index.docker.io"):
        registry = DOCKER_HUB
    if registry == DOCKER_HUB and "/" not in repository:
        repository = f"library/{repository}"
    return registry, repository, reference


def request(url, headers, method="GET"):
    """Status, headers and body of a request; an HTTP error is an answer like any other."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers, method=method), timeout=30) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def pull_token(challenge, repository, credentials):
    """A pull token from the registry's token service, as its WWW-Authenticate challenge names it."""
    fields = dict(re.findall(r'(\w+)="([^"]*)"', challenge or ""))
    if "realm" not in fields:
        return None
    query = urllib.parse.urlencode({"service": fields.get("service", ""), "scope": f"repository:{repository}:pull"})
    headers = {"Authorization": "Basic " + base64.b64encode(credentials.encode()).decode()} if credentials else {}
    status, _, body = request(f"{fields['realm']}?{query}", headers)
    if status != 200:
        return None
    data = json.loads(body or b"{}")
    return data.get("token") or data.get("access_token")


def look_up(image):
    """True when the registry has the image, False when it says it hasn't, None when it won't show us."""
    registry, repository, reference = parse(image)
    url = f"https://{registry}/v2/{repository}/manifests/{reference}"
    attempts = [None]
    if registry == "ghcr.io" and os.environ.get("GHCR_TOKEN"):
        attempts.append(f"x-access-token:{os.environ['GHCR_TOKEN']}")
    for credentials in attempts:
        status, headers, _ = request(url, {"Accept": MANIFEST_TYPES}, "HEAD")
        if status == 401:
            token = pull_token(headers.get("WWW-Authenticate"), repository, credentials)
            if token:
                status, _, _ = request(url, {"Accept": MANIFEST_TYPES, "Authorization": f"Bearer {token}"}, "HEAD")
        if status == 200:
            return True
        if status == 404:
            return False
    return None


def main():
    os.chdir(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    images = changed_images(base)
    if not images:
        print(f"No image added or changed against {base}.")
        return

    wait_minutes = float(os.environ.get("IMAGE_WAIT_MINUTES", "20"))
    deadline = time.monotonic() + wait_minutes * 60
    waiting = dict(images)
    while True:
        for image in list(waiting):
            found = look_up(image)
            if found is None:
                file, line = waiting.pop(image)
                report("warning", f"{image}: the registry won't show this image (a private package?), so it isn't checked", file, line)
            elif found:
                print(f"  found {image}")
                waiting.pop(image)
        if not waiting or time.monotonic() >= deadline:
            break
        print(f"  not there yet: {', '.join(sorted(waiting))}; looking again in {RETRY_SECONDS} seconds")
        time.sleep(RETRY_SECONDS)

    for image, (file, line) in sorted(waiting.items()):
        report("error", f"{image}: the registry doesn't have this image (after {wait_minutes:g} minutes); has its build pushed it?", file, line)

    print(f"\n{problems['error']} error(s), {problems['warning']} warning(s)")
    sys.exit(1 if problems["error"] else 0)


if __name__ == "__main__":
    main()
