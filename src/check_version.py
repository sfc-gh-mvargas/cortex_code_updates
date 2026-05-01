import re
import subprocess
from pathlib import Path


DATA_DIR = Path(__file__).parent.parent / "data"
VERSION_FILE = DATA_DIR / "cortex_code_cli_version"


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


def main():
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
