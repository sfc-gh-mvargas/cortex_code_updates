# Cortex Code Updates

[![Website Status](https://github.com/sfc-gh-mvargas/cortex_code_updates/actions/workflows/cortex_version_monitor.yml/badge.svg)](https://github.com/sfc-gh-mvargas/cortex_code_updates/actions/workflows/cortex_version_monitor.yml)
[![Ingest Cortex CLI Skills](https://github.com/sfc-gh-mvargas/cortex_code_updates/actions/workflows/cortex_code_docs_updated.yml/badge.svg)](https://github.com/sfc-gh-mvargas/cortex_code_updates/actions/workflows/cortex_code_docs_updated.yml)

Documentation and monitoring tools for Snowflake Cortex Code Skills.

## Overview

This repository provides documentation, version monitoring, and automated skill ingestion for Snowflake's Cortex Code capabilities. It maintains up-to-date records of available CLI tools and generates comprehensive documentation for developers.

## Features

- 🔍 **Version Monitoring**: Automatically tracks Cortex CLI version changes
- 📚 **Skill Documentation**: Ingests and catalogs all available Cortex Code Skills
- 🤖 **Automated Updates**: GitHub Actions workflows keep documentation in sync
- 📊 **Comprehensive Reporting**: Generates detailed skill reports and snapshots

## GitHub Workflows

### Cortex Version Monitor
**File**: `.github/workflows/cortex_version_monitor.yml`  
**Schedule**: Every 6 hours (can be triggered manually)

This workflow:
- Monitors the current Cortex CLI version
- Compares with stored version in `data/cortex_code_cli_version`
- Automatically commits version updates when changes are detected
- Triggers the documentation update workflow on version changes
- Runs integration tests via `tests/test_monitor.sh`

**Key Steps**:
1. Sets up Python 3.13 and installs the Cortex Code CLI
2. Runs version checks and comparison logic
3. Commits changes if version differs
4. Triggers the `cortex_code_docs_updated` workflow

### Ingest Cortex CLI Skills
**File**: `.github/workflows/cortex_code_docs_updated.yml`  
**Trigger**: Manual dispatch (automatically triggered by version monitor)

This workflow:
- Installs Cortex CLI and Python dependencies
- Runs skill ingestion script (`src/ingest_skills.py`)
- Generates documentation report (`src/build_report.py`)
- Commits updated skill data and documentation to `data/` and `docs/` directories

**Key Steps**:
1. Sets up Python 3.13 environment with `uv`
2. Installs Cortex Code CLI
3. Ingests current available skills
4. Generates comprehensive documentation
5. Commits changes with timestamped commit messages

## Project Structure

```
cortex_code_updates/
├── .github/workflows/          # GitHub Actions workflows
│   ├── cortex_version_monitor.yml
│   └── cortex_code_docs_updated.yml
├── data/                       # Data snapshots
│   └── cortex_code_cli_version # Current CLI version
├── docs/                       # Generated documentation
├── src/                        # Python scripts
│   ├── ingest_skills.py       # Skill ingestion script
│   └── build_report.py        # Report generation script
├── tests/                      # Test scripts
│   └── test_monitor.sh        # Version monitor tests
└── README.md                  # This file
```

## Technology Stack

- **Language**: Python
- **CI/CD**: GitHub Actions
- **Dependencies**: 
  - `uv` - Python package installer
  - `pyyaml` - YAML parsing
  - Cortex Code CLI

## Getting Started

### Prerequisites

- Python 3.13+
- GitHub account with repository access
- Cortex Code CLI credentials
- `uv` package manager

### Installation

1. Clone the repository:
```bash
git clone https://github.com/sfc-gh-mvargas/cortex_code_updates.git
cd cortex_code_updates
```

2. Install dependencies:
```bash
uv pip install -r requirements.txt
```

3. Install Cortex CLI:
```bash
curl -LsS https://ai.snowflake.com/static/cc-scripts/install.sh | sh
```

## Usage

### Manual Workflow Trigger

You can manually trigger workflows via GitHub Actions:

1. Go to **Actions** tab in the repository
2. Select the workflow to run:
   - `Cortex Code Version Monitor`
   - `Ingest Cortex CLI Skills`
3. Click **Run workflow**

### Local Development

To run scripts locally:

```bash
# Ingest skills
uv run python src/ingest_skills.py

# Generate documentation
uv run python src/build_report.py

# Run tests
bash tests/test_monitor.sh
```

## Automated Schedule

- **Version Monitoring**: Every 6 hours
- **Documentation Updates**: Triggered automatically when version changes are detected
- **Manual Triggers**: Available anytime via GitHub Actions UI

## Contributing

Contributions are welcome! Please:

1. Create a feature branch
2. Make your changes
3. Submit a pull request

## License

This project is open source and available under the MIT License.

## Support

For issues or questions:
- Check [GitHub Issues](https://github.com/sfc-gh-mvargas/cortex_code_updates/issues)
- Review workflow logs in [GitHub Actions](https://github.com/sfc-gh-mvargas/cortex_code_updates/actions)

## Related Resources

- [Snowflake Cortex Code Documentation](https://docs.snowflake.com/en/user-guide/cortex-code)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

---

**Last Updated**: 2026-05-01  
**Repository**: [sfc-gh-mvargas/cortex_code_updates](https://github.com/sfc-gh-mvargas/cortex_code_updates)
