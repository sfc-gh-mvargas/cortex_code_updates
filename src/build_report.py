import argparse
import difflib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DATA_DIR = Path(__file__).parent.parent / "data"
BASE_OUTPUT_DIR = Path(__file__).parent.parent / "docs"

_B = '<span style="color:#29B5E8;">\u2588</span>'
_O = '<span style="color:#FF9F36;">\u2588</span>'
_W = '<span style="color:#FFFFFF;">\u2588</span>'
_E = '<span style="background:#29B5E8;color:#000000;">\u2584</span>'
_S = " "
COCO_ICON = (
    '<pre style="margin:0;font-family:monospace;font-size:10px;line-height:1.2;display:inline-block;vertical-align:middle;">'
    f'{_S}{_S}{_B}{_E}{_B}{_E}{_B}\n'
    f'{_S}{_B}{_B}{_B}{_O}{_B}{_B}{_B}\n'
    f'{_B}{_B}{_B}{_W}{_W}{_W}{_B}{_B}{_B}\n'
    f'{_S}{_B}{_O}{_B}{_B}{_B}{_O}{_B}\n'
    '</pre>'
)

STYLES = {
    "add": "#71D3DC",
    "remove": "#D45B90",
    "modify": "#FF9F36",
    "heading": "#11567F",
    "accent": "#29B5E8",
    "muted": "#717171",
    "text": "#262626",
    "border": "#C8C8C8",
    "bg": "#F5F5F5",
    "card": "#FFFFFF",
    "header_bg": "#11567F",
}


SNAPSHOT_PATTERN = re.compile(r"^skills_v([\d.]+)\.json$")


def load_change_history(data_dir: Path) -> list[dict]:
    snapshots = sorted(f for f in data_dir.glob("skills_v*.json") if SNAPSHOT_PATTERN.match(f.name))
    if not snapshots:
        return []

    ### first tracked version v1.0.58
    base_path = snapshots[0]
    with open(base_path) as f:
        base_data = json.load(f)
    base_skills = base_data.get("skills", [])

    history = []
    if base_skills:
        history.append({
            "date": base_data.get("ingestion_date", ""),
            "version": base_data.get("cli_version", "1.0.58"),
            "skill_count_before": 0,
            "skill_count_after": len(base_skills),
            "added": [{"name": s["name"], "description": s.get("description", "")} for s in base_skills],
            "removed": [],
            "modified": [],
        })

    cdc_files = sorted(data_dir.glob("cdc_v*_v*.json"))
    for cdc_path in cdc_files:
        with open(cdc_path) as f:
            cdc = json.load(f)
        changes = cdc.get("changes", [])
        if not changes:
            continue
        added = [c for c in changes if c["action"] == "NEW"]
        removed = [c for c in changes if c["action"] == "DELETED"]
        modified = [c for c in changes if c["action"] == "MODIFIED"]

        to_version = cdc.get("to_version", "")
        to_snapshot_path = data_dir / f"skills_v{to_version}.json"
        skills_map = {}
        if to_snapshot_path.exists():
            with open(to_snapshot_path) as f:
                skills_map = {s["name"]: s for s in json.load(f).get("skills", [])}

        from_version = cdc.get("from_version", "")
        from_snapshot_path = data_dir / f"skills_v{from_version}.json"
        prev_count = 0
        if from_snapshot_path.exists():
            with open(from_snapshot_path) as f:
                prev_count = json.load(f).get("skill_count", 0)

        history.append({
            "date": cdc.get("detected_date", ""),
            "version": to_version,
            "skill_count_before": prev_count,
            "skill_count_after": len(skills_map),
            "added": [{"name": c["skill_name"], "description": skills_map.get(c["skill_name"], {}).get("description", "")} for c in added],
            "removed": [{"name": c["skill_name"], "description": ""} for c in removed],
            "modified": [{"name": c["skill_name"], "description": c.get("detail", "")} for c in modified],
        })

    return history



def _load_latest_snapshot(data_dir: Path) -> list[dict] | None:
    snapshots = sorted((f for f in data_dir.glob("skills_v*.json") if SNAPSHOT_PATTERN.match(f.name)), reverse=True)
    if not snapshots:
        return None
    with open(snapshots[0]) as f:
        return json.load(f).get("skills", [])


def load_weekly_json(data_dir: Path) -> dict:
    candidates = sorted(data_dir.glob("new_skills_v*.json"), reverse=True)
    if not candidates:
        snapshot = _load_latest_snapshot(data_dir)
        cli_version = ""
        if snapshot:
            snapshots = sorted((f for f in data_dir.glob("skills_v*.json") if SNAPSHOT_PATTERN.match(f.name)), reverse=True)
            if snapshots:
                with open(snapshots[0]) as f:
                    cli_version = json.load(f).get("cli_version", "")
        return {"new_skills": [], "deleted_skills": [], "modified_skills": [], "count": 0, "cli_version": cli_version, "date_of": ""}
    path = candidates[0]
    if not path.exists():
        print(f"ERROR: {path} not found. Run src/ingest_skills.py first.")
        sys.exit(1)
    with open(path) as f:
        data = json.load(f)

    cdc_changes = load_cdc_changes(data.get("date_of", ""), data_dir)
    if cdc_changes["deleted"]:
        data["deleted_skills"] = cdc_changes["deleted"]
    if cdc_changes["modified"]:
        data["modified_skills"] = cdc_changes["modified"]
    if cdc_changes["new"] and not data.get("new_skills"):
        snapshot = _load_latest_snapshot(data_dir)
        skills_map = {s["name"]: s for s in snapshot} if snapshot else {}
        data["new_skills"] = [
            {"name": s["name"], "description": skills_map.get(s["name"], {}).get("description", "")}
            for s in cdc_changes["new"]
        ]
        data["count"] = len(cdc_changes["new"])
    return data


def _build_description_map(data_dir: Path) -> dict[str, str]:
    desc_map = {}
    for f in data_dir.glob("new_skills_v*.json"):
        with open(f) as fh:
            week_data = json.load(fh)
        for skill in week_data.get("new_skills", []):
            if skill.get("name") and skill.get("description"):
                desc_map[skill["name"]] = skill["description"]
    return desc_map


def _load_snapshot_map(path: Path) -> dict[str, str]:
    with open(path) as f:
        data = json.load(f)
    return {s["name"]: s.get("description", "") for s in data.get("skills", [])}


def _build_diff_map(data_dir: Path) -> dict[str, dict[str, tuple[str, str]]]:
    snapshots = sorted(f for f in data_dir.glob("skills_v*.json") if SNAPSHOT_PATTERN.match(f.name))
    diff_map: dict[str, dict[str, tuple[str, str]]] = {}
    for i in range(1, len(snapshots)):
        m = SNAPSHOT_PATTERN.match(snapshots[i].name)
        version_str = m.group(1) if m else snapshots[i].stem
        old_map = _load_snapshot_map(snapshots[i - 1])
        new_map = _load_snapshot_map(snapshots[i])
        changes = {}
        for name in set(old_map) | set(new_map):
            old_desc = old_map.get(name, "")
            new_desc = new_map.get(name, "")
            if old_desc != new_desc:
                changes[name] = (old_desc, new_desc)
        if changes:
            diff_map[version_str] = changes
    return diff_map


def load_cdc_changes(date_of: str, data_dir: Path) -> dict:
    result = {"new": [], "modified": [], "deleted": []}
    desc_map = _build_description_map(data_dir)
    for cdc_file in sorted(data_dir.glob("cdc_v*.json"), reverse=True):
        with open(cdc_file) as f:
            cdc = json.load(f)
        for change in cdc.get("changes", []):
            action = change.get("action")
            entry = {"name": change["skill_name"], "detail": change.get("detail"), "description": desc_map.get(change["skill_name"], "")}
            if action == "DELETED":
                result["deleted"].append(entry)
            elif action in ("MODIFIED", "UPDATED"):
                result["modified"].append(entry)
            elif action == "NEW":
                result["new"].append(entry)
    return result


def load_cdc_entries(data_dir: Path) -> list[dict]:
    entries = []
    desc_map = _build_description_map(data_dir)
    diff_map = _build_diff_map(data_dir)
    for cdc_file in sorted(data_dir.glob("cdc_v*.json"), reverse=True):
        with open(cdc_file) as f:
            cdc = json.load(f)
        cdc_date = cdc.get("detected_date", "")
        to_version = cdc.get("to_version", "")
        added = []
        removed = []
        modified = []
        for change in cdc.get("changes", []):
            action = change.get("action")
            skill_name = change["skill_name"]
            entry = {"name": skill_name, "detail": change.get("detail"), "description": desc_map.get(skill_name, "")}
            if change.get("detail") == "description_changed" and to_version in diff_map:
                pair = diff_map[to_version].get(skill_name)
                if pair:
                    entry["old_description"] = pair[0]
                    entry["new_description"] = pair[1]
            if action == "DELETED":
                removed.append(entry)
            elif action in ("MODIFIED", "UPDATED"):
                modified.append(entry)
            elif action == "NEW":
                added.append(entry)
        if added or removed or modified:
            entries.append({
                "date": cdc_date,
                "version": cdc.get("cli_version", ""),
                "added": added,
                "removed": removed,
                "modified": modified,
            })
    return entries


def _is_beta_entry(entry: dict) -> bool:
    msg = entry.get("commit_message", "").lower()
    if "beta" in msg:
        return True
    for field in ("added", "removed", "modified"):
        for item in entry.get(field, []):
            name = item["name"] if isinstance(item, dict) else item
            if "beta" in name.lower():
                return True
            if isinstance(item, dict):
                for change in item.get("changes", []):
                    if "beta" in change.lower():
                        return True
    return False


def _bullet(color: str, text: str) -> str:
    return (
        f'<li style="margin:4px 0;padding-left:4px;font-family:Arial,sans-serif;font-size:12px;color:{STYLES["text"]};">'
        f'<span style="color:{color};font-weight:bold;margin-right:4px;">&#x2022;</span> {text}</li>'
    )


def _expandable_desc(desc: str) -> str:
    short = (desc[:80] + "\u2026") if len(desc) > 80 else desc
    if len(desc) <= 80:
        return f' <span style="color:{STYLES["muted"]};font-size:11px;">{short}</span>'
    return (
        f'<details style="display:inline;margin-left:6px;" class="skill-desc">'
        f'<summary style="cursor:pointer;color:{STYLES["muted"]};font-size:11px;display:inline;list-style:none;">'
        f'<span class="sd-short">{short}</span>'
        f' <span class="sd-plus" style="color:{STYLES["accent"]};font-weight:bold;font-size:14px;">+</span>'
        f'<span class="sd-full" style="display:none;">{desc}</span>'
        f'</summary>'
        f'</details>'
    )


def _expandable_diff(old_desc: str, new_desc: str) -> str:
    short = "description_changed"
    sm = difflib.SequenceMatcher(None, old_desc.split(), new_desc.split())
    diff_parts = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            diff_parts.append(" ".join(old_desc.split()[i1:i2]))
        elif op == "delete":
            diff_parts.append(f'<span style="background:#FDE8F0;text-decoration:line-through;color:{STYLES["remove"]};">{" ".join(old_desc.split()[i1:i2])}</span>')
        elif op == "insert":
            diff_parts.append(f'<span style="background:#E8F9FA;color:{STYLES["add"]};font-weight:bold;">{" ".join(new_desc.split()[j1:j2])}</span>')
        elif op == "replace":
            diff_parts.append(f'<span style="background:#FDE8F0;text-decoration:line-through;color:{STYLES["remove"]};">{" ".join(old_desc.split()[i1:i2])}</span>')
            diff_parts.append(f'<span style="background:#E8F9FA;color:{STYLES["add"]};font-weight:bold;">{" ".join(new_desc.split()[j1:j2])}</span>')
    diff_html = " ".join(diff_parts)
    return (
        f'<details style="display:inline;margin-left:6px;" class="skill-desc">'
        f'<summary style="cursor:pointer;color:{STYLES["muted"]};font-size:11px;display:inline;list-style:none;">'
        f'<span class="sd-short">{short}</span>'
        f' <span class="sd-plus" style="color:{STYLES["accent"]};font-weight:bold;font-size:14px;">+</span>'
        f'<span class="sd-full" style="display:none;font-size:11px;">{diff_html}</span>'
        f'</summary>'
        f'</details>'
    )


def _render_skill_list(added: list, removed: list, modified: list) -> str:
    items = ""
    for s in added:
        name = s["name"] if isinstance(s, dict) else s
        desc = s.get("description") or "" if isinstance(s, dict) else ""
        label = f'<code style="background:#E8F9FA;padding:1px 5px;border-radius:3px;font-size:11px;">{name}</code>'
        if desc:
            label += _expandable_desc(desc)
        items += _bullet(STYLES["add"], label)
    for s in removed:
        name = s["name"] if isinstance(s, dict) else s
        desc = s.get("description") or "" if isinstance(s, dict) else ""
        label = f'<code style="background:#FDE8F0;padding:1px 5px;border-radius:3px;font-size:11px;">{name}</code>'
        if desc:
            label += _expandable_desc(desc)
        items += _bullet(STYLES["remove"], label)
    for s in modified:
        name = s["name"] if isinstance(s, dict) else s
        detail_text = ""
        if isinstance(s, dict) and "changes" in s:
            detail_text = ", ".join(s["changes"])
        elif isinstance(s, dict) and s.get("detail"):
            detail_text = s["detail"]
        desc = s.get("description") or "" if isinstance(s, dict) else ""
        old_desc = s.get("old_description", "") if isinstance(s, dict) else ""
        new_desc = s.get("new_description", "") if isinstance(s, dict) else ""
        label = f'<code style="background:#FFF3E5;padding:1px 5px;border-radius:3px;font-size:11px;">{name}</code>'
        if old_desc and new_desc:
            label += _expandable_diff(old_desc, new_desc)
        elif detail_text:
            label += f' <span style="color:{STYLES["muted"]};font-size:11px;">{detail_text}</span>'
        elif desc:
            label += _expandable_desc(desc)
        items += _bullet(STYLES["modify"], label)
    if not items:
        return ""
    return f'<ul style="list-style:none;margin:6px 0 0 0;padding:0;">{items}</ul>'


def render_history_section(history: list[dict], is_beta: bool = False) -> str:
    if not history or is_beta:
        return ""

    base_entry = history[0]
    version = base_entry.get("version", "")
    skill_count = base_entry.get("skill_count_after", 0)
    added = base_entry.get("added", [])

    version_badge = f'<span style="color:{STYLES["accent"]};font-size:11px;font-weight:bold;">[v{version}]</span> ' if version else ""

    skill_items = "".join(
        _bullet(STYLES["add"], s["name"] + (_expandable_desc(s["description"]) if s.get("description") else ""))
        for s in added
    )
    skill_list = f'<ul style="margin:8px 0 0;padding-left:18px;list-style:none;">{skill_items}</ul>' if skill_items else ""

    section = f"""<tr><td style="padding:20px 24px 8px;">
  <h2 style="margin:0;font-family:Arial,sans-serif;color:{STYLES['heading']};font-size:16px;border-bottom:2px solid {STYLES['accent']};padding-bottom:6px;">
    Base Version (when this tracker started)
  </h2>
</td></tr>
<tr><td style="padding:8px 24px 16px;">
  <p style="margin:0;font-family:Arial,sans-serif;font-size:13px;color:{STYLES['text']};">
    {version_badge}{skill_count} bundled skills
  </p>
  {skill_list}
</td></tr>"""
    return section


def _render_summary(added_count: int, removed_count: int, modified_count: int) -> str:
    parts = []
    if added_count:
        parts.append(f'<span style="color:{STYLES["add"]};font-weight:bold;">ADDED: +{added_count}</span>')
    if removed_count:
        parts.append(f'<span style="color:{STYLES["remove"]};font-weight:bold;">REMOVED: -{removed_count}</span>')
    if modified_count:
        parts.append(f'<span style="color:{STYLES["modify"]};font-weight:bold;">MODIFIED: ~{modified_count}</span>')
    if not parts:
        return ""
    joined = ' &nbsp;&nbsp; '.join(parts)
    return (
        f'<div style="margin:6px 0 2px 0;padding:6px 10px;background:#F8F9FA;border-radius:4px;'
        f'font-family:Arial,sans-serif;font-size:12px;">'
        f'{joined}</div>'
    )


def render_current_entry(data: dict, is_beta: bool = False, data_dir: Path | None = None) -> str:
    if data_dir:
        cdc_entries = load_cdc_entries(data_dir)
        if not cdc_entries:
            return ""
        rows = ""
        for entry in cdc_entries:
            version = entry.get("version", "")
            date = entry.get("date", "")
            added = entry.get("added", [])
            removed = entry.get("removed", [])
            modified = entry.get("modified", [])
            version_suffix = "-beta" if is_beta else ""
            version_badge = f'<span style="color:{STYLES["accent"]};font-size:11px;font-weight:bold;">[v{version}{version_suffix}]</span> ' if version else ""
            date_span = f'<span style="color:{STYLES["heading"]};font-family:Arial,sans-serif;font-size:12px;font-weight:bold;">{date}</span>'
            summary = _render_summary(len(added), len(removed), len(modified))
            skill_list = _render_skill_list(added, removed, modified)
            rows += (
                f'<tr><td style="padding:10px 12px;border-bottom:1px solid {STYLES["border"]};">' 
                f'{version_badge}{date_span}'
                f'{summary}'
                f'{skill_list}'
                f'</td></tr>'
            )
        heading = "Latest changes (Beta versions)" if is_beta else "Latest Changes"
        tracking_note = f'<p style="margin:4px 0 0;font-family:Arial,sans-serif;font-size:10px;color:{STYLES["muted"]};">Tracking started on v1.0.76</p>' if is_beta else ""
        section = f"""<tr><td style="padding:20px 24px 8px;">
  <h2 style="margin:0;font-family:Arial,sans-serif;color:{STYLES['heading']};font-size:16px;border-bottom:2px solid {STYLES['accent']};padding-bottom:6px;">
    {heading}
  </h2>
  {tracking_note}
</td></tr>
<tr><td style="padding:8px 24px 16px;">
  <table style="width:100%;border-collapse:collapse;">{rows}</table>
</td></tr>"""
        return section

    return ""


def render_email_html(data: dict, history: list[dict] | None = None, is_beta: bool = False, data_dir: Path | None = None) -> str:
    skills = data.get("new_skills", [])
    deleted_skills = data.get("deleted_skills", [])
    modified_skills = data.get("modified_skills", [])
    date_of = data.get("date_of", "unknown")
    cli_version = data.get("cli_version", "?")
    count = data.get("count", len(skills))
    deleted_count = len(deleted_skills)
    modified_count = len(modified_skills)

    changes_section = render_current_entry(data, is_beta=is_beta, data_dir=data_dir)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>
.skill-desc[open] .sd-short{{display:none}}
.skill-desc[open] .sd-full{{display:inline !important}}
.skill-desc[open] .sd-plus{{display:none}}
.skill-desc summary::marker,.skill-desc summary::-webkit-details-marker{{display:none}}
</style>
</head>
<body style="margin:0;padding:0;background:{STYLES['bg']};">
<table width="100%" cellpadding="0" cellspacing="0" style="background:{STYLES['bg']};">
<tr><td align="center" style="padding:20px;">
<table width="640" cellpadding="0" cellspacing="0" style="background:{STYLES['card']};border:1px solid {STYLES['border']};border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">

<tr><td style="padding:24px 24px 14px;border-bottom:3px solid {STYLES['accent']};background:{STYLES['header_bg']};border-radius:6px 6px 0 0;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <h1 style="margin:0;font-family:Arial,sans-serif;color:#FFFFFF;font-size:22px;letter-spacing:1px;display:flex;align-items:center;gap:10px;">
      {COCO_ICON} CoCo Skills Pulse
    </h1>
    <div style="display:inline-flex;border-radius:4px;overflow:hidden;border:1px solid #71D3DC;">
      <a href="index.html" style="padding:4px 10px;font-family:Arial,sans-serif;font-size:11px;font-weight:bold;text-decoration:none;{'background:#71D3DC;color:#11567F;' if not is_beta else 'background:transparent;color:#71D3DC;'}">Stable</a>
      <a href="beta.html" style="padding:4px 10px;font-family:Arial,sans-serif;font-size:11px;font-weight:bold;text-decoration:none;{'background:#71D3DC;color:#11567F;' if is_beta else 'background:transparent;color:#71D3DC;'}">Beta</a>
    </div>
  </div>
  <p style="margin:6px 0 0;font-family:Arial,sans-serif;color:#FFFFFFCC;font-size:12px;">
    Tracking skills shipped in the public <a href="https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli" style="color:#71D3DC;">Cortex Code CLI</a> installed via <code style="background:#ffffff22;padding:1px 4px;border-radius:3px;font-size:11px;">curl -LsS https://ai.snowflake.com/static/cc-scripts/install.sh</code>
  </p>
</td></tr>

{changes_section}

{render_history_section(history or [], is_beta=is_beta)}

<tr><td style="padding:20px 24px 8px;">
  <h2 style="margin:0;font-family:Arial,sans-serif;color:{STYLES['heading']};font-size:16px;border-bottom:2px solid {STYLES['accent']};padding-bottom:6px;">
    Latest Version
  </h2>
</td></tr>
<tr><td style="padding:8px 24px 20px;">
  <p style="margin:0;font-family:Arial,sans-serif;color:{STYLES['text']};font-size:14px;">
    Today's version <strong style="color:{STYLES['accent']};">v{cli_version}</strong>
  </p>
</td></tr>

<tr><td style="padding:12px 24px 20px;border-top:1px solid {STYLES['border']};">
  <p style="margin:0;font-family:Arial,sans-serif;color:{STYLES['muted']};font-size:11px;">
    Latest change {date_of} &nbsp;|&nbsp; +{count} new &nbsp;|&nbsp; -{deleted_count} deleted &nbsp;|&nbsp; ~{modified_count} modified &nbsp;|&nbsp;
    Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
  </p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Build CoCo Skills Pulse report")
    parser.add_argument("--beta", action="store_true", help="Build report from beta channel data (reads data/beta/, writes docs/beta.html)")
    args = parser.parse_args()

    data_dir = BASE_DATA_DIR / "beta" if args.beta else BASE_DATA_DIR
    output_dir = BASE_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    out_filename = "beta.html" if args.beta else "index.html"

    data = load_weekly_json(data_dir)
    history = load_change_history(data_dir)
    html = render_email_html(data, history, is_beta=args.beta, data_dir=data_dir)
    out_path = output_dir / out_filename
    out_path.write_text(html, encoding="utf-8")
    print(f"Webpage status updated to {out_path}")


if __name__ == "__main__":
    main()
