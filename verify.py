"""Run the same isolated verification locally and during Windows deployment."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(command):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(command, cwd=ROOT, check=True, env=environment)


with tempfile.TemporaryDirectory(prefix="annotation-verify-") as directory:
    environment = os.environ.copy()
    database = (Path(directory) / "verification.db").as_posix()
    environment["ANNOTATION_DATABASE_URL"] = "sqlite:///" + database

    run([sys.executable, "-m", "pytest", "tests", "-q"])
    node = shutil.which("node")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not node or not npm:
        raise RuntimeError("Node.js and npm are required for frontend verification")
    for test in sorted((ROOT / "tests").glob("test_*.cjs")):
        run([node, str(test)])
    run([npm, "--prefix", "frontend", "run", "build"])

print("All backend, frontend, and build verification passed.")
