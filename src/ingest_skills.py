import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml


BASE_DATA_DIR = Path(__file__).parent.parent / "data"


def get_cli_version() -> str:
    result = subprocess.run(["cortex", "--version"], capture_output=True, text=True)
    version_line = result.stdout.strip()
    match = re.search(r"v?([\d.]+\+?\S*)", version_line)
    return match.group(1) if match else version_line


def parse_skill_list() -> list[dict]:
    result = subprocess.run(["cortex", "skill", "list"], capture_output=True, text=True)
    output = result.stdout + result.stderr

    skills = []
    current_section = None
    section_pattern = re.compile(r"^\s+\[(BUNDLED|REMOTE|EXTERNAL)\]")
    skill_pattern = re.compile(r"^\s+-\s+(\S+):\s+(.+)$")

    for line in output.splitlines():
        section_match = section_pattern.match(line)
        if section_match:
            current_section = section_match.group(1)
            continue

        if current_section:
            skill_match = skill_pattern.match(line)
            if skill_match:
                name = skill_match.group(1)
                path = skill_match.group(2).strip()
                skills.append({
                    "name": name,
                    "type": current_section,
                    "path": path,
                })

    return skills


def read_skill_description(skill_path: str) -> str | None:
    skill_md = Path(skill_path) / "SKILL.md"
    if not skill_md.exists():
        return None

    content = skill_md.read_text(encoding="utf-8")
    match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
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


def get_previous_snapshot(data_dir: Path, today: str) -> list[dict] | None:
    today_file = f"skills_{today}.json"
    snapshots = sorted(
        [s for s in data_dir.glob("skills_*.json") if s.name != today_file],
        reverse=True,
    )
    if not snapshots:
        return None
    with open(snapshots[0]) as f:
        return json.load(f)["skills"]


def compute_cdc(current: list[dict], previous: list[dict] | None) -> list[dict]:
    if previous is None:
        return [{"skill_name": s["name"], "action": "NEW", "detail": None} for s in current]

    prev_map = {s["name"]: s for s in previous}
    curr_map = {s["name"]: s for s in current}

    changes = []

    for name, skill in curr_map.items():
        if name not in prev_map:
            changes.append({"skill_name": name, "action": "NEW", "detail": None})
        else:
            prev = prev_map[name]
            if skill.get("description") != prev.get("description"):
                changes.append({"skill_name": name, "action": "MODIFIED", "detail": "description_changed"})
            elif skill.get("type") != prev.get("type"):
                changes.append({"skill_name": name, "action": "MODIFIED", "detail": "type_changed"})


    for name in prev_map:
        if name not in curr_map:
            changes.append({"skill_name": name, "action": "DELETED", "detail": None})

    return changes



def main():
    parser = argparse.ArgumentParser(description="Ingest Cortex Code CLI skills")
    parser.add_argument("--beta", action="store_true", help="Ingest from beta channel (writes to data/beta/)")
    args = parser.parse_args()

    data_dir = BASE_DATA_DIR / "beta" if args.beta else BASE_DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    channel = "beta" if args.beta else "stable"
    print(f"Channel: {channel}")

    cli_version = get_cli_version()
    print(f"Cortex CLI version: {cli_version}")

    skills = parse_skill_list()
    print(f"Discovered {len(skills)} skills")

    for skill in skills:
        desc = read_skill_description(skill["path"])
        skill["description"] = desc

    bundled_count = sum(1 for s in skills if s["type"] == "BUNDLED")
    remote_count = sum(1 for s in skills if s["type"] == "REMOTE")
    external_count = sum(1 for s in skills if s["type"] == "EXTERNAL")
    print(f"  BUNDLED: {bundled_count}, REMOTE: {remote_count}, EXTERNAL: {external_count}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    previous = get_previous_snapshot(data_dir, today)
    if previous is None:
        print("WARNING: No previous snapshot found — CDC will mark everything as NEW.")
        print("  Ensure a baseline skills_*.json exists in the data directory before running.")
    cdc = compute_cdc(skills, previous)

    snapshot = {
        "cli_version": cli_version,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "ingestion_date": today,
        "skill_count": len(skills),
        "channel": channel,
        "skills": skills,
    }

    snapshot_path = data_dir / f"skills_{today}.json"
    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"Wrote snapshot to {snapshot_path}")

    if cdc:
        cdc_path = data_dir / f"cdc_{today}.json"
        cdc_payload = {
            "detected_date": today,
            "cli_version": cli_version,
            "channel": channel,
            "changes": cdc,
        }
        with open(cdc_path, "w") as f:
            json.dump(cdc_payload, f, indent=2)
        print(f"CDC: {len(cdc)} changes written to {cdc_path}")
        for c in cdc:
            print(f"  {c['action']}: {c['skill_name']} {c['detail'] or ''}")

    else:
        print("CDC: No changes detected")

    new_skills_week = [s for s in cdc if s["action"] == "NEW"] if cdc else []
    skills_map = {s["name"]: s for s in skills}
    weekly_path = data_dir / f"new_skills_week_{today}.json"
    weekly_payload = {
        "week_of": today,
        "cli_version": cli_version,
        "channel": channel,
        "new_skills": [
            {
                "name": s["skill_name"],
                "description": skills_map.get(s["skill_name"], {}).get("description") or "",
            }
            for s in new_skills_week
        ],
        "count": len(new_skills_week),
    }
    with open(weekly_path, "w") as f:
        json.dump(weekly_payload, f, indent=2)
    print(f"Weekly new skills JSON written to {weekly_path}")


if __name__ == "__main__":
    main()
