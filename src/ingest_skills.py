import os
import re
import subprocess
import yaml
from datetime import datetime, timezone
from pathlib import Path

import snowflake.connector


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
            return desc.strip()[:16384]
    except yaml.YAMLError:
        pass
    return None


def ensure_snowflake_objects(conn):
    cur = conn.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS PRODUCT")
    cur.execute("CREATE SCHEMA IF NOT EXISTS PRODUCT.UPDATES")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS PRODUCT.UPDATES.CORTEX_CLI_BUNDLED_SKILLS_LOG (
            SKILL_NAME          VARCHAR(256)    NOT NULL,
            SKILL_DESCRIPTION   VARCHAR(16384),
            SKILL_TYPE          VARCHAR(64)     NOT NULL,
            SKILL_PATH          VARCHAR(4096),
            CLI_VERSION         VARCHAR(64)     NOT NULL,
            CAPTURED_AT         TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
            INGESTION_DATE      DATE            NOT NULL DEFAULT CURRENT_DATE()
        )
    """)


def upload_to_snowflake(skills: list[dict], cli_version: str):
    conn = snowflake.connector.connect(
        connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"
    )
    try:
        ensure_snowflake_objects(conn)
        cur = conn.cursor()
        cur.execute("USE DATABASE PRODUCT")
        cur.execute("USE SCHEMA UPDATES")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        cur.execute(
            "DELETE FROM PRODUCT.UPDATES.CORTEX_CLI_BUNDLED_SKILLS_LOG WHERE INGESTION_DATE = %s",
            (today,),
        )

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        rows = []
        for skill in skills:
            rows.append((
                skill["name"],
                skill.get("description"),
                skill["type"],
                skill["path"],
                cli_version,
                now,
                today,
            ))

        cur.executemany(
            """
            INSERT INTO PRODUCT.UPDATES.CORTEX_CLI_BUNDLED_SKILLS_LOG
                (SKILL_NAME, SKILL_DESCRIPTION, SKILL_TYPE, SKILL_PATH, CLI_VERSION, CAPTURED_AT, INGESTION_DATE)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        print(f"Inserted {len(rows)} skill records for CLI version {cli_version} (replaced today's snapshot)")
    finally:
        conn.close()


def main():
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

    upload_to_snowflake(skills, cli_version)


if __name__ == "__main__":
    main()
