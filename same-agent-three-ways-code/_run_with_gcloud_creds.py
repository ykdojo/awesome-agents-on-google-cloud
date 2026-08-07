"""Test-only shim, not part of the article. This machine has gcloud CLI auth
but no application default credentials, so patch google.auth.default to use a
token minted by gcloud, then exec the target script.

Usage: python _run_with_gcloud_creds.py method1_interactions.py [args...]
"""

import os
import subprocess
import sys

import google.auth
import google.oauth2.credentials

token = subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()
project = os.environ.get("GOOGLE_CLOUD_PROJECT") or subprocess.check_output(
    ["gcloud", "config", "get-value", "project"]).decode().strip()
creds = google.oauth2.credentials.Credentials(token=token)
google.auth.default = lambda *a, **k: (creds, project)
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)

target = sys.argv[1]
sys.argv = sys.argv[1:]
exec(compile(open(target).read(), target, "exec"))
