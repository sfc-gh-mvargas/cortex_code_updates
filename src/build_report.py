import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DATA_DIR = Path(__file__).parent.parent / "data"
BASE_OUTPUT_DIR = Path(__file__).parent.parent / "docs"

COCO_ICON = "🥥"

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


def load_change_history(data_dir: Path) -> list[dict]:
    snapshots = sorted(data_dir.glob("skills_*.json"))
    if not snapshots:
        return []
    snapshot_path = snapshots[0]
    with open(snapshot_path) as f:
        data = json.load(f)
    skills = data.get("skills", [])
    if not skills:
        return []
    return [{
        "date": data.get("ingestion_date", "2026-04-30"),
        "version": data.get("cli_version", "unknown"),
        "skill_count_before": 0,
        "skill_count_after": len(skills),
        "added": [{"name": s["name"], "description": s.get("description", "")} for s in skills],
        "removed": [],
        "modified": [],
    }]


def _load_latest_snapshot(data_dir: Path) -> list[dict] | None:
    snapshots = sorted(data_dir.glob("skills_*.json"), reverse=True)
    if not snapshots:
        return None
    with open(snapshots[0]) as f:
        return json.load(f).get("skills", [])


def load_weekly_json(data_dir: Path) -> dict:
    candidates = sorted(data_dir.glob("new_skills_week_*.json"), reverse=True)
    if not candidates:
        print("ERROR: No new_skills_week_*.json found. Run src/ingest_skills.py first.")
        sys.exit(1)
    path = candidates[0]
    if not path.exists():
        print(f"ERROR: {path} not found. Run src/ingest_skills.py first.")
        sys.exit(1)
    with open(path) as f:
        data = json.load(f)

    cdc_changes = load_cdc_changes(data.get("week_of", ""), data_dir)
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


def load_cdc_changes(week_of: str, data_dir: Path) -> dict:
    result = {"new": [], "modified": [], "deleted": []}
    for cdc_file in sorted(data_dir.glob("cdc_*.json"), reverse=True):
        with open(cdc_file) as f:
            cdc = json.load(f)
        cdc_date = cdc.get("detected_date", "")
        if week_of and cdc_date < week_of:
            break
        for change in cdc.get("changes", []):
            action = change.get("action")
            entry = {"name": change["skill_name"], "detail": change.get("detail")}
            if action == "DELETED":
                result["deleted"].append(entry)
            elif action in ("MODIFIED", "UPDATED"):
                result["modified"].append(entry)
            elif action == "NEW":
                result["new"].append(entry)
    return result


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


def _render_skill_list(added: list, removed: list, modified: list) -> str:
    items = ""
    for s in added:
        name = s["name"] if isinstance(s, dict) else s
        desc = s.get("description") or "" if isinstance(s, dict) else ""
        short_desc = (desc[:80] + "\u2026") if len(desc) > 80 else desc
        label = f'<code style="background:#E8F9FA;padding:1px 5px;border-radius:3px;font-size:11px;">{name}</code>'
        if short_desc:
            label += f' <span style="color:{STYLES["muted"]};font-size:11px;">{short_desc}</span>'
        items += _bullet(STYLES["add"], label)
    for s in removed:
        name = s["name"] if isinstance(s, dict) else s
        label = f'<code style="background:#FDE8F0;padding:1px 5px;border-radius:3px;font-size:11px;">{name}</code>'
        items += _bullet(STYLES["remove"], label)
    for s in modified:
        name = s["name"] if isinstance(s, dict) else s
        detail_text = ""
        if isinstance(s, dict) and "changes" in s:
            detail_text = ", ".join(s["changes"])
        elif isinstance(s, dict) and s.get("detail"):
            detail_text = s["detail"]
        label = f'<code style="background:#FFF3E5;padding:1px 5px;border-radius:3px;font-size:11px;">{name}</code>'
        if detail_text:
            label += f' <span style="color:{STYLES["muted"]};font-size:11px;">{detail_text}</span>'
        items += _bullet(STYLES["modify"], label)
    if not items:
        return ""
    return f'<ul style="list-style:none;margin:6px 0 0 0;padding:0;">{items}</ul>'


def render_history_section(history: list[dict]) -> str:
    if not history:
        return ""

    filtered = [e for e in history if not _is_beta_entry(e)]
    recent = filtered[-10:]
    recent.reverse()

    rows = ""
    for entry in recent:
        date = entry["date"]
        version = entry.get("version", "")
        added = entry.get("added", [])
        removed = entry.get("removed", [])
        modified = entry.get("modified", [])

        version_badge = f'<span style="color:{STYLES["accent"]};font-size:11px;font-weight:bold;">[{version}]</span> ' if version else ""

        summary = _render_summary(len(added), len(removed), len(modified))
        skill_list = _render_skill_list(added, removed, modified)

        rows += (
            f'<tr><td style="padding:10px 12px;border-bottom:1px solid {STYLES["border"]};">'
            f'{version_badge}<span style="color:{STYLES["heading"]};font-family:Arial,sans-serif;font-size:12px;font-weight:bold;">{date}</span>'
            f'{summary}'
            f'{skill_list}'
            f'</td></tr>'
        )

    section = f"""<tr><td style="padding:20px 24px 8px;">
  <h2 style="margin:0;font-family:Arial,sans-serif;color:{STYLES['heading']};font-size:16px;border-bottom:2px solid {STYLES['accent']};padding-bottom:6px;">
    Base Version (when this tracker started)
  </h2>
</td></tr>
<tr><td style="padding:8px 24px 16px;">
  <table style="width:100%;border-collapse:collapse;">{rows}</table>
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


def render_current_entry(data: dict) -> str:
    skills = data.get("new_skills", [])
    deleted_skills = data.get("deleted_skills", [])
    modified_skills = data.get("modified_skills", [])
    week_of = data.get("week_of", "unknown")
    cli_version = data.get("cli_version", "?")

    if not skills and not deleted_skills and not modified_skills:
        return ""

    version_badge = f'<span style="color:{STYLES["accent"]};font-size:11px;font-weight:bold;">[v{cli_version}]</span> '
    date_span = f'<span style="color:{STYLES["heading"]};font-family:Arial,sans-serif;font-size:12px;font-weight:bold;">{week_of}</span> '

    summary = _render_summary(len(skills), len(deleted_skills), len(modified_skills))

    added_list = [s if isinstance(s, dict) else {"name": s} for s in skills]
    removed_list = [s if isinstance(s, dict) else {"name": s} for s in deleted_skills]
    modified_list = [s if isinstance(s, dict) else {"name": s} for s in modified_skills]
    skill_list = _render_skill_list(added_list, removed_list, modified_list)

    row = (
        f'<tr><td style="padding:10px 12px;border-bottom:1px solid {STYLES["border"]};">'
        f'{version_badge}{date_span}'
        f'{summary}'
        f'{skill_list}'
        f'</td></tr>'
    )

    section = f"""<tr><td style="padding:20px 24px 8px;">
  <h2 style="margin:0;font-family:Arial,sans-serif;color:{STYLES['heading']};font-size:16px;border-bottom:2px solid {STYLES['accent']};padding-bottom:6px;">
    Latest Changes
  </h2>
</td></tr>
<tr><td style="padding:8px 24px 16px;">
  <table style="width:100%;border-collapse:collapse;">{row}</table>
</td></tr>"""
    return section


def render_email_html(data: dict, history: list[dict] | None = None, is_beta: bool = False) -> str:
    skills = data.get("new_skills", [])
    deleted_skills = data.get("deleted_skills", [])
    modified_skills = data.get("modified_skills", [])
    week_of = data.get("week_of", "unknown")
    cli_version = data.get("cli_version", "?")
    count = data.get("count", len(skills))
    deleted_count = len(deleted_skills)
    modified_count = len(modified_skills)

    changes_section = render_current_entry(data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:{STYLES['bg']};">
<table width="100%" cellpadding="0" cellspacing="0" style="background:{STYLES['bg']};">
<tr><td align="center" style="padding:20px;">
<table width="640" cellpadding="0" cellspacing="0" style="background:{STYLES['card']};border:1px solid {STYLES['border']};border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">

<tr><td style="padding:24px 24px 14px;border-bottom:3px solid {STYLES['accent']};background:{STYLES['header_bg']};border-radius:6px 6px 0 0;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <h1 style="margin:0;font-family:Arial,sans-serif;color:#FFFFFF;font-size:22px;letter-spacing:1px;">
      {COCO_ICON} CoCo Skill Pulse
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

{render_history_section(history or [])}

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
    Week of {week_of} &nbsp;|&nbsp; +{count} new &nbsp;|&nbsp; -{deleted_count} deleted &nbsp;|&nbsp; ~{modified_count} modified &nbsp;|&nbsp;
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
    parser = argparse.ArgumentParser(description="Build CoCo Skill Pulse report")
    parser.add_argument("--beta", action="store_true", help="Build report from beta channel data (reads data/beta/, writes docs/beta.html)")
    args = parser.parse_args()

    data_dir = BASE_DATA_DIR / "beta" if args.beta else BASE_DATA_DIR
    output_dir = BASE_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    out_filename = "beta.html" if args.beta else "index.html"

    data = load_weekly_json(data_dir)
    history = load_change_history(data_dir)
    html = render_email_html(data, history, is_beta=args.beta)
    out_path = output_dir / out_filename
    out_path.write_text(html, encoding="utf-8")
    print(f"Webpage status updated to {out_path}")


if __name__ == "__main__":
    main()
