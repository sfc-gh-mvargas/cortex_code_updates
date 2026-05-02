import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE_DATA_DIR = Path(__file__).parent.parent / "data"

SNAPSHOT_PATTERN = re.compile(r"^plugins_v([\d.]+)\.json$")


def get_cli_version() -> str:
    result = subprocess.run(["cortex", "--version"], capture_output=True, text=True)
    version_line = result.stdout.strip()
    match = re.search(r"v?([\d.]+\+?\S*)", version_line)
    return match.group(1) if match else version_line


def clean_version(version: str) -> str:
    return version.split("+")[0]


def parse_plugin_list() -> list[dict]:
    result = subprocess.run(["cortex", "plugin", "list"], capture_output=True, text=True)
    output = result.stdout + result.stderr

    plugins = []
    current: dict | None = None

    header_pattern = re.compile(r"^\s{2}(\S+)\s+v([\d.]+)\s+\[([^\]]+)\]")

    for line in output.splitlines():
        header_match = header_pattern.match(line)
        if header_match:
            if current:
                plugins.append(current)
            name = header_match.group(1)
            version = header_match.group(2)
            flags = [f.strip() for f in header_match.group(3).split(",")]
            status = "enabled" if "enabled" in flags else "disabled"
            source = next((f for f in flags if f in ("bundled", "managed", "external")), "unknown")
            current = {
                "name": name,
                "version": version,
                "status": status,
                "source": source,
                "description": "",
                "path": "",
                "components": "",
            }
            continue

        if current:
            stripped = line.strip()
            if stripped.startswith("Path:"):
                current["path"] = stripped[len("Path:"):].strip()
            elif stripped.startswith("Source:"):
                current["source"] = stripped[len("Source:"):].strip()
            elif stripped.startswith("Components:"):
                current["components"] = stripped[len("Components:"):].strip()
            elif stripped and not stripped.startswith("Discovered") and not current["description"]:
                current["description"] = stripped

    if current:
        plugins.append(current)

    return plugins


def get_previous_snapshot(data_dir: Path, current_version: str) -> tuple[str | None, list[dict] | None]:
    current_clean = clean_version(current_version)
    snapshots = []
    for f in data_dir.glob("plugins_v*.json"):
        m = SNAPSHOT_PATTERN.match(f.name)
        if m and m.group(1) != current_clean:
            snapshots.append((m.group(1), f))

    if not snapshots:
        return None, None

    snapshots.sort(key=lambda x: x[0], reverse=True)
    prev_version, prev_path = snapshots[0]
    with open(prev_path) as f:
        return prev_version, json.load(f)["plugins"]


def compute_cdc(current: list[dict], previous: list[dict] | None) -> list[dict]:
    if previous is None:
        return [{"plugin_name": p["name"], "action": "NEW", "detail": None} for p in current]

    prev_map = {p["name"]: p for p in previous}
    curr_map = {p["name"]: p for p in current}

    changes = []

    for name, plugin in curr_map.items():
        if name not in prev_map:
            changes.append({"plugin_name": name, "action": "NEW", "detail": None})
        else:
            prev = prev_map[name]
            diffs = []
            if plugin.get("version") != prev.get("version"):
                diffs.append("version_changed")
            if plugin.get("description") != prev.get("description"):
                diffs.append("description_changed")
            if plugin.get("status") != prev.get("status"):
                diffs.append("status_changed")
            if plugin.get("source") != prev.get("source"):
                diffs.append("source_changed")
            if plugin.get("components") != prev.get("components"):
                diffs.append("components_changed")
            if diffs:
                changes.append({"plugin_name": name, "action": "MODIFIED", "detail": ", ".join(diffs)})

    for name in prev_map:
        if name not in curr_map:
            changes.append({"plugin_name": name, "action": "DELETED", "detail": None})

    return changes


def main():
    parser = argparse.ArgumentParser(description="Ingest Cortex Code CLI plugins")
    parser.add_argument("--beta", action="store_true", help="Ingest from beta channel (writes to data/plugins/beta/)")
    args = parser.parse_args()

    data_dir = BASE_DATA_DIR / "plugins" / "beta" if args.beta else BASE_DATA_DIR / "plugins"
    data_dir.mkdir(parents=True, exist_ok=True)

    channel = "beta" if args.beta else "stable"
    print(f"Channel: {channel}")

    cli_version = get_cli_version()
    version_clean = clean_version(cli_version)
    print(f"Cortex CLI version: {cli_version} (clean: {version_clean})")

    snapshot_path = data_dir / f"plugins_v{version_clean}.json"
    if snapshot_path.exists():
        print(f"Snapshot already exists: {snapshot_path.name}. Nothing to do.")
        return

    if not args.beta:
        beta_dir = BASE_DATA_DIR / "plugins" / "beta"
        prev_version, previous = get_previous_snapshot(beta_dir, cli_version)
    else:
        prev_version, previous = get_previous_snapshot(data_dir, cli_version)

    if prev_version is None:
        print("WARNING: No previous snapshot found — CDC will mark everything as NEW.")

    if prev_version:
        print(f"Version changed: {prev_version} -> {version_clean}")
    else:
        print(f"First snapshot for version {version_clean}")

    plugins = parse_plugin_list()
    print(f"Discovered {len(plugins)} plugins")

    for p in plugins:
        print(f"  [{p['source']}] {p['name']} v{p['version']} ({p['status']})")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cdc = compute_cdc(plugins, previous)

    snapshot = {
        "cli_version": cli_version,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "ingestion_date": today,
        "plugin_count": len(plugins),
        "channel": channel,
        "plugins": plugins,
    }

    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"Wrote snapshot to {snapshot_path}")

    if cdc:
        if prev_version:
            cdc_filename = f"cdc_v{prev_version}_v{version_clean}.json"
        else:
            cdc_filename = f"cdc_v{version_clean}.json"
        cdc_path = data_dir / cdc_filename
        cdc_path = data_dir / cdc_filename
        cdc_payload = {
            "detected_date": today,
            "from_version": prev_version,
            "to_version": version_clean,
            "cli_version": cli_version,
            "channel": channel,
            "changes": cdc,
        }
        with open(cdc_path, "w") as f:
            json.dump(cdc_payload, f, indent=2)
        print(f"CDC: {len(cdc)} changes written to {cdc_path}")
        for c in cdc:
            print(f"  {c['action']}: {c['plugin_name']} {c['detail'] or ''}")
    else:
        print("CDC: No changes detected")

    new_plugins = [p for p in cdc if p["action"] == "NEW"] if cdc else []
    plugins_map = {p["name"]: p for p in plugins}
    if prev_version:
        new_plugins_filename = f"new_plugins_v{prev_version}_v{version_clean}.json"
    else:
        new_plugins_filename = f"new_plugins_v{version_clean}.json"
    new_plugins_path = data_dir / new_plugins_filename
    new_plugins_payload = {
        "date_of": today,
        "from_version": prev_version,
        "to_version": version_clean,
        "cli_version": cli_version,
        "channel": channel,
        "new_plugins": [
            {
                "name": p["plugin_name"],
                "description": plugins_map.get(p["plugin_name"], {}).get("description") or "",
                "version": plugins_map.get(p["plugin_name"], {}).get("version") or "",
                "source": plugins_map.get(p["plugin_name"], {}).get("source") or "",
            }
            for p in new_plugins
        ],
        "count": len(new_plugins),
    }
    with open(new_plugins_path, "w") as f:
        json.dump(new_plugins_payload, f, indent=2)
    print(f"New plugins JSON written to {new_plugins_path}")


if __name__ == "__main__":
    main()
