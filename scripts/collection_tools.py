#!/usr/bin/env python3
"""Build/install local Collections in dependency order; never fetch sibling packages from Galaxy."""

import argparse
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ORDER = (
    "nodejs",
    "github",
    "gandi",
    "spaceship",
    "vercel",
    "supabase",
    "kamal",
    "hetzner",
    "application",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "install"))
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--path", type=Path, help="Collection installation directory")
    parser.add_argument(
        "--no-deps", action="store_true", help="Do not install external dependencies"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if args.path:
        from ansible.constants import COLLECTIONS_PATHS

        env["ANSIBLE_COLLECTIONS_PATH"] = os.pathsep.join(
            [str(args.path.resolve())] + [str(path) for path in COLLECTIONS_PATHS]
        )
    for name in ORDER:
        source = ROOT / "collections" / name
        metadata = yaml.safe_load((source / "galaxy.yml").read_text())
        subprocess.run(
            [
                "ansible-galaxy",
                "collection",
                "build",
                str(source),
                "--force",
                "--output-path",
                str(args.output),
            ],
            env=env,
            check=True,
        )
        if args.action == "install":
            archive = args.output / (
                "madebyphunky-" + name + "-" + str(metadata["version"]) + ".tar.gz"
            )
            command = [
                "ansible-galaxy",
                "collection",
                "install",
                str(archive),
                "--force",
            ]
            if args.path:
                command += ["-p", str(args.path.resolve())]
            if args.no_deps:
                command.append("--no-deps")
            subprocess.run(command, env=env, check=True)


if __name__ == "__main__":
    main()
