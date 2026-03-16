#!/usr/bin/env bash
set -euo pipefail

found_clients=()
configured_clients=()
skipped_clients=()
error_clients=()

detect_python() {
  if command -v python >/dev/null 2>&1; then
    PYTHON_CMD=(python)
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=(python3)
    return 0
  fi

  echo "Python 3.10+ was not found. Install Python and rerun this script." >&2
  exit 1
}

ensure_umi_installed() {
  if "${PYTHON_CMD[@]}" -c "from importlib import metadata; print(metadata.version('umi-mcp'))" >/dev/null 2>&1; then
    return 0
  fi

  echo "umi-mcp is not installed for the detected Python. Installing with pip..."
  "${PYTHON_CMD[@]}" -m pip install umi-mcp
}

merge_config() {
  local kind="$1"
  local path="$2"

  "${PYTHON_CMD[@]}" - "$kind" "$path" <<'PY'
import json
import os
import re
import sys
import tempfile

ENTRY = {"command": "python", "args": ["-m", "umi_mcp"]}


def read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8-sig") as handle:
        return handle.read()


def atomic_write(path: str, text: str) -> None:
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".umi-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def update_json(path: str) -> str:
    raw = read_text(path)
    if raw.strip():
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise TypeError("JSON config root must be an object.")
    else:
        data = {}

    mcp_servers = data.get("mcpServers")
    if mcp_servers is None:
        mcp_servers = {}
        data["mcpServers"] = mcp_servers
    elif not isinstance(mcp_servers, dict):
        raise TypeError('JSON config field "mcpServers" must be an object.')

    if "umi" in mcp_servers:
        print("already configured")
        return

    mcp_servers["umi"] = ENTRY
    atomic_write(path, json.dumps(data, indent=2) + "\n")
    print("configured")


def load_toml_module():
    try:
        import tomllib  # type: ignore
        return tomllib
    except ModuleNotFoundError:
        try:
            import tomli  # type: ignore
            return tomli
        except ModuleNotFoundError:
            return None


def update_toml(path: str) -> None:
    raw = read_text(path)
    if re.search(r"(?m)^\s*\[\s*mcp_servers\.umi\s*\]\s*$", raw):
        print("already configured")
        return

    toml_module = load_toml_module()
    if toml_module and raw.strip():
        toml_module.loads(raw)

    block = '[mcp_servers.umi]\ncommand = "python"\nargs = ["-m", "umi_mcp"]'
    merged = f"{raw.rstrip()}\n\n{block}\n" if raw.strip() else f"{block}\n"

    if toml_module:
        toml_module.loads(merged)

    atomic_write(path, merged)
    print("configured")


def main() -> int:
    kind = sys.argv[1]
    path = sys.argv[2]
    if kind == "json":
        update_json(path)
    elif kind == "toml":
        update_toml(path)
    else:
        raise ValueError(f"Unsupported config kind: {kind}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
PY
}

add_found_client() {
  found_clients+=("$1")
}

add_configured_client() {
  configured_clients+=("$1")
}

add_skipped_client() {
  skipped_clients+=("$1")
}

add_error_client() {
  error_clients+=("$1")
}

detect_python
ensure_umi_installed

uname_value="$(uname -s)"
json_names=()
json_paths=()
json_dirs=()
toml_names=()
toml_paths=()
toml_dirs=()

case "$uname_value" in
  Darwin)
    json_names+=("Claude Desktop")
    json_paths+=("$HOME/Library/Application Support/Claude/claude_desktop_config.json")
    json_dirs+=("$HOME/Library/Application Support/Claude")
    ;;
  Linux)
    json_names+=("Claude Desktop")
    json_paths+=("$HOME/.config/Claude/claude_desktop_config.json")
    json_dirs+=("$HOME/.config/Claude")
    ;;
esac

json_names+=("Cursor" "Windsurf" "Cline")
json_paths+=(
  "$HOME/.cursor/mcp.json"
  "$HOME/.codeium/windsurf/mcp_config.json"
  "$HOME/.vscode/globalStorage/saoudrizwan.claude-dev/cline_mcp_settings.json"
)
json_dirs+=(
  "$HOME/.cursor"
  "$HOME/.codeium/windsurf"
  "$HOME/.vscode/globalStorage/saoudrizwan.claude-dev"
)

toml_names+=("Codex CLI")
toml_paths+=("$HOME/.codex/config.toml")
toml_dirs+=("$HOME/.codex")

for i in "${!json_names[@]}"; do
  name="${json_names[$i]}"
  config_path="${json_paths[$i]}"
  client_dir="${json_dirs[$i]}"

  if [[ ! -f "$config_path" && ! -d "$client_dir" ]]; then
    continue
  fi

  add_found_client "$name"
  if output="$(merge_config json "$config_path" 2>&1)"; then
    status="$(printf '%s\n' "$output" | tail -n 1)"
    if [[ "$status" == "configured" ]]; then
      add_configured_client "$name"
    else
      add_skipped_client "$name (already configured)"
    fi
  else
    add_error_client "$name: $output"
  fi
done

for i in "${!toml_names[@]}"; do
  name="${toml_names[$i]}"
  config_path="${toml_paths[$i]}"
  client_dir="${toml_dirs[$i]}"

  if [[ ! -f "$config_path" && ! -d "$client_dir" ]]; then
    continue
  fi

  add_found_client "$name"
  if output="$(merge_config toml "$config_path" 2>&1)"; then
    status="$(printf '%s\n' "$output" | tail -n 1)"
    if [[ "$status" == "configured" ]]; then
      add_configured_client "$name"
    else
      add_skipped_client "$name (already configured)"
    fi
  else
    add_error_client "$name: $output"
  fi
done

echo
echo "UMI installer summary"
echo "Found clients: ${#found_clients[@]}"
for item in "${found_clients[@]}"; do
  echo "  - $item"
done

echo "Configured: ${#configured_clients[@]}"
for item in "${configured_clients[@]}"; do
  echo "  - $item"
done

echo "Skipped: ${#skipped_clients[@]}"
for item in "${skipped_clients[@]}"; do
  echo "  - $item"
done

if [[ "${#error_clients[@]}" -gt 0 ]]; then
  echo "Errors: ${#error_clients[@]}"
  for item in "${error_clients[@]}"; do
    echo "  - $item"
  done
  echo
  echo "Restart any configured clients to load UMI."
  exit 1
fi

echo
echo "Restart any configured clients to load UMI."
