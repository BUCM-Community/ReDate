"""
scripts/sync_meta.py

Syncs metadata from pixi.toml to pyproject.toml using tomlkit.

This script ensures that the Single Source of Truth (SSOT) remains pixi.toml.
It handles the conversion between Pixi's string-based authors and PEP 621 structured authors.
"""

from pathlib import Path
import re
import sys
from typing import Any, NoReturn

from redate.utils_telemetry import logger

# Ensure tomlkit is installed (provided by feature.dev)
try:
    import tomlkit
    from tomlkit import TOMLDocument
    from tomlkit.items import Table
except ImportError:
    logger.error("Critical Error: 'tomlkit' is missing. Run 'pixi install' first.")
    sys.exit(1)


def _fail(message: str) -> NoReturn:
    logger.error(f"[!] {message}", file=sys.stderr)
    sys.exit(1)


def _load_toml(path: Path) -> TOMLDocument:
    if not path.exists():
        if path.name == "pyproject.toml":
            logger.info(f"[*] Creating new: {path}")
            return tomlkit.document()
        _fail(f"File not found: {path}")

    try:
        with Path.open(path, encoding="utf-8") as f:
            return tomlkit.load(f)
    except Exception as e:
        _fail(f"_Failed to parse {path}: {e}")


def parse_author(author_str: str) -> dict[str, str]:
    """
    Parses 'Name <email>' into {'name': 'Name', 'email': 'email'}.

    Fallback to {'name': author_str} if format doesn't match.
    """
    if not isinstance(author_str, str):
        return {"name": str(author_str)}
    match = re.match(r"^(?P<name>.*?)\s*<(?P<email>.*?)>$", author_str.strip())
    if match:
        return match.groupdict()
    return {"name": author_str.strip()}


def sync_metadata() -> None:  # noqa: C901
    """Sync pyproject.toml metadata using tomlkit."""
    root_dir = Path(__file__).resolve().parent.parent
    pixi_path = root_dir / "pixi.toml"
    pyproject_path = root_dir / "pyproject.toml"

    logger.info(f"[*] Reading source: {pixi_path}")
    pixi_doc = _load_toml(pixi_path)

    # 1. Extract Workspace Metadata
    workspace = pixi_doc.get("workspace") or pixi_doc.get("project")
    if not isinstance(workspace, (dict, Table)):
        _fail("Invalid pixi.toml: Missing [workspace] or [project] table.")

    target_version = workspace.get("version")
    target_desc = workspace.get("description")
    target_name = workspace.get("name", "redate")
    target_license = workspace.get("license")
    target_authors_raw = workspace.get("authors", [])

    # Pixi doesn't enforce requires-python in [workspace], but usually in [dependencies] or features.
    # We default to 3.11+ based on the feature flags in pixi.toml if not explicitly found.
    target_requires_python = ">=3.11"

    if not target_version:
        _fail("Invalid pixi.toml: Missing 'version'.")

    # 2. Load or Init pyproject.toml
    logger.info(f"[*] Loading target: {pyproject_path}")
    pyproject_doc = _load_toml(pyproject_path)

    # 3. Ensure Basic Structure ([build-system] & [project])
    if "build-system" not in pyproject_doc:
        logger.info("[*] Init [build-system]")
        build_system = tomlkit.table()
        build_system["requires"] = ["hatchling"]
        build_system["build-backend"] = "hatchling.build"
        pyproject_doc.add("build-system", build_system)

    if "project" not in pyproject_doc:
        logger.info("[*] Init [project]")
        pyproject_doc.add("project", tomlkit.table())

    project_table: Table = pyproject_doc["project"]  # type: ignore

    # 4. Sync Fields
    changes = []

    def update_field(key: str, value: Any) -> None:
        if project_table.get(key) != value:
            project_table[key] = value
            changes.append(f"Updated '{key}'")

    update_field("name", target_name)
    update_field("version", target_version)
    update_field("description", target_desc)
    update_field("requires-python", target_requires_python)

    if target_license:
        # PEP 621 license format is {text = "..."} or {file = "..."}
        update_field("license", {"text": target_license})

    # 5. Sync Authors (Complex Type Conversion)
    # Pixi: ["Name <email>"] -> Pyproject: [{name="Name", email="email"}]
    target_authors_structured = [parse_author(a) for a in target_authors_raw]

    # Compare structure content, not just reference
    # Use explicit comparison to avoid ordering issues causing flux
    current_authors = project_table.get("authors")
    if current_authors != target_authors_structured:
        project_table["authors"] = target_authors_structured
        changes.append("Updated 'authors' list")

    # 6. Finalize
    if changes:
        logger.info("[*] Applying changes:")
        for change in changes:
            logger.info(f"    - {change}")

        try:
            with Path.open(pyproject_path, "w", encoding="utf-8") as f:
                tomlkit.dump(pyproject_doc, f)
            logger.info(f"[+] {pyproject_path.name} successfully synced.")
        except Exception as e:
            _fail(f"_Failed to write pyproject.toml: {e}")
    else:
        logger.info(f"[✓] {pyproject_path.name} is already up to date.")


if __name__ == "__main__":
    sync_metadata()
