import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml


BASE_DATA_DIR = Path(__file__).parent.parent / "data"
CORTEX_DIR = Path("~/.local/share/cortex").expanduser()

SNAPSHOT_PATTERN = re.compile(r"^plugins_v([\d.]+)\.json$")


def get_cli_version() -> str:
    result = subprocess.run(["cortex", "--version"], capture_output=True, text=True)
    version_line = result.stdout.strip()
    match = re.search(r"v?([\d.]+\+?\S*)", version_line)
    return match.group(1) if match else version_line


def clean_version(version: str) -> str:
    return version.split("+")[0]


def find_version_path(version_clean: str) -> Path | None:
    for d in CORTEX_DIR.iterdir():
        if d.is_dir() and d.name.startswith(version_clean):
            return d
    return None


def get_version_date(version_path: Path) -> datetime:
    cortex_bin = version_path / "cortex"
    src = cortex_bin if cortex_bin.exists() else version_path
    return datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc)


def parse_skill_md(skill_dir: Path) -> str | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    content = skill_md.read_text(encoding="utf-8")
    match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None
    try:
        frontmatter = yaml.safe_load(match.group(1))
        desc = frontmatter.get("description", "")
        if isinstance(desc, str):
            return desc.strip()
    except yaml.YAMLError:
        pass
    return None


def get_subskills_dfs(skill_dir: Path) -> list[dict]:
    subskills = []
    for entry in sorted(skill_dir.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / "SKILL.md").exists():
            continue
        description = parse_skill_md(entry)
        subskills.append({
            "name": entry.name,
            "description": description,
            "path": str(entry),
            "subskills": get_subskills_dfs(entry),
        })
    return subskills


def _read_plugin_json(plugin_dir: Path) -> dict | None:
    for meta_dir in (".claude-plugin", ".cortex-plugin"):
        candidate = plugin_dir / meta_dir / "plugin.json"
        if candidate.exists():
            try:
                with open(candidate) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
    return None


def _get_plugin_skills(plugin_dir: Path) -> list[dict]:
    skills_dir = plugin_dir / "skills"
    if not skills_dir.exists():
        return []
    skills = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        description = parse_skill_md(skill_dir)
        skills.append({
            "name": skill_dir.name,
            "description": description,
            "path": str(skill_dir),
            "subskills": get_subskills_dfs(skill_dir),
        })
    return skills


def get_plugins_from_version(version_path: Path) -> list[dict]:
    plugins = []
    for source_label, subdir in [("bundled", "bundled_plugins"), ("external", "bundled_external_plugins")]:
        plugins_dir = version_path / subdir
        if not plugins_dir.exists():
            continue
        for plugin_dir in sorted(plugins_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue
            meta = _read_plugin_json(plugin_dir)
            if meta is None:
                continue
            plugins.append({
                "name": meta.get("name", plugin_dir.name),
                "version": meta.get("version", ""),
                "status": "enabled",
                "source": source_label,
                "description": meta.get("description", ""),
                "path": str(plugin_dir),
                "components": "",
                "skills": _get_plugin_skills(plugin_dir),
            })
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

    version_path = find_version_path(version_clean)
    if version_path is None:
        print(f"ERROR: No local version folder found for {version_clean} in {CORTEX_DIR}")
        return

    print(f"Reading from: {version_path.name}")

    prev_version, previous = get_previous_snapshot(data_dir, cli_version)

    if prev_version is None:
        print("WARNING: No previous snapshot found — CDC will mark everything as NEW.")

    if prev_version:
        print(f"Version changed: {prev_version} -> {version_clean}")
    else:
        print(f"First snapshot for version {version_clean}")

    plugins = get_plugins_from_version(version_path)
    print(f"Discovered {len(plugins)} plugins")
    for p in plugins:
        skill_count = len(p.get("skills", []))
        print(f"  [{p['source']}] {p['name']} v{p['version']} ({skill_count} skills)")

    version_dt = get_version_date(version_path)
    version_date = version_dt.strftime("%Y-%m-%d")
    cdc = compute_cdc(plugins, previous)

    snapshot = {
        "cli_version": cli_version,
        "captured_at": version_dt.isoformat(),
        "ingestion_date": version_date,
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
        cdc_payload = {
            "detected_date": version_date,
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
        "date_of": version_date,
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
