import argparse
import re
import subprocess
from pathlib import Path


DATA_DIR = Path(__file__).parent.parent / "data"
VERSION_FILE = DATA_DIR / "cortex_code_cli_version"
BETA_VERSION_FILE = DATA_DIR / "beta" / "cortex_code_cli_version"


def get_installed_version() -> str:
    result = subprocess.run(["cortex", "--version"], capture_output=True, text=True)
    version_line = result.stdout.strip()
    match = re.search(r"v?([\d.]+\+?\S*)", version_line)
    return match.group(1) if match else version_line


def get_stored_version() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return ""


def update_stored_version(version: str) -> None:
    VERSION_FILE.write_text(version + "\n")


def get_stored_version_beta() -> str:
    if BETA_VERSION_FILE.exists():
        return BETA_VERSION_FILE.read_text().strip()
    return ""


def update_stored_version_beta(version: str) -> None:
    BETA_VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    BETA_VERSION_FILE.write_text(version + "\n")


def get_installed_version_beta() -> str:
    result = subprocess.run(["cortex", "--version"], capture_output=True, text=True,
                           env={**__import__('os').environ, "CORTEX_CHANNEL": "beta"})
    version_line = result.stdout.strip()
    match = re.search(r"v?([\d.]+\+?\S*)", version_line)
    return match.group(1) if match else version_line


def main():
    parser = argparse.ArgumentParser(description="Check Cortex CLI version")
    parser.add_argument("--beta", action="store_true", help="Check beta channel version")
    args = parser.parse_args()

    if args.beta:
        current = get_installed_version_beta()
        stored = get_stored_version_beta()
        print(f"[beta] Installed version: {current}")
        print(f"[beta] Stored version:    {stored}")
        if current != stored:
            print("VERSION_CHANGED=true")
            update_stored_version_beta(current)
        else:
            print("VERSION_CHANGED=false")
    else:
        current = get_installed_version()
        stored = get_stored_version()
        print(f"Installed version: {current}")
        print(f"Stored version:    {stored}")
        if current != stored:
            print("VERSION_CHANGED=true")
            update_stored_version(current)
        else:
            print("VERSION_CHANGED=false")


if __name__ == "__main__":
    main()
