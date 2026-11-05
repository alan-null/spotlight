# Small in-process provider API. Module files are trusted Bash code.
spotlight_modules_loaded=0
spotlight_modules=()
declare -A spotlight_module_paths=() spotlight_module_actions=() spotlight_tab_owners=()

spotlight_module_call() {
  local callback="spotlight_${1}_${2}"
  shift 2
  if declare -F "$callback" >/dev/null; then
    "$callback" "$@"
  fi
}

spotlight_module_require_callback() {
  local callback="spotlight_${1}_${2}"
  if ! declare -F "$callback" >/dev/null; then
    printf 'Module %s requires callback %s.\n' "$1" "$callback" >&2
    return 1
  fi
}

spotlight_module_tab() {
  local module=$1 id="$1.$2" label=$3
  if [[ ! $2 =~ ^[a-z][a-z0-9_-]*$ || -z $label || $label =~ [[:cntrl:]] || -n ${spotlight_tab_owners[$id]:-} || -z ${spotlight_module_paths[$module]:-} ]]; then
    printf 'Invalid or duplicate module tab: %s\n' "$id" >&2
    return 1
  fi
  spotlight_module_require_callback "$module" list || return
  spotlight_module_require_callback "$module" select || return
  tab_ids+=("$id") tabs+=("$label")
  spotlight_tab_owners[$id]=$module
}

spotlight_load_modules() {
  (( spotlight_modules_loaded == 0 )) || return 0
  local roots="${SPOTLIGHT_MODULE_PATH:-$MODULE_DIR/modules:${XDG_CONFIG_HOME:-$HOME/.config}/spotlight/modules}"
  local root path module actions status
  local -a module_roots
  IFS=: read -r -a module_roots <<< "$roots${SPOTLIGHT_EXTRA_MODULE_PATH:+:$SPOTLIGHT_EXTRA_MODULE_PATH}"
  tabs=(Commands) tab_ids=(Commands)
  for root in "${module_roots[@]}"; do
    [[ -n $root ]] || continue
    for path in "$root"/*/module.sh; do
      [[ -f $path ]] || continue
      module=${path%/module.sh} module=${module##*/}
      if [[ $module == core || ! $module =~ ^[a-z][a-z0-9_]*$ || -n ${spotlight_module_paths[$module]:-} ]]; then
        printf 'Invalid or duplicate module: %s\n' "$module" >&2
        return 1
      fi
      spotlight_module_paths[$module]=$path
      source "$path" || return
      spotlight_module_call "$module" available
      status=$?
      if (( status == 1 )); then continue; fi
      if (( status != 0 )); then
        printf 'Module %s availability check failed (exit %s).\n' "$module" "$status" >&2
        return "$status"
      fi
      spotlight_modules+=("$module")
      export "SPOTLIGHT_PROVIDER_${module}=$path"
      if declare -F "spotlight_${module}_commands" >/dev/null; then
        spotlight_module_require_callback "$module" select || return
      fi
      if declare -F "spotlight_${module}_settings" >/dev/null; then
        spotlight_module_require_callback "$module" setting_select || return
      fi
      spotlight_module_call "$module" tabs || return
      actions=${path%/module.sh}/actions.toml
      if [[ -f $actions ]]; then
        spotlight_module_actions[$module]=$actions
        SPOTLIGHT_EXTRA_ACTION_PATH="${SPOTLIGHT_EXTRA_ACTION_PATH:+$SPOTLIGHT_EXTRA_ACTION_PATH:}$actions"
        export SPOTLIGHT_EXTRA_ACTION_PATH
      fi
    done
  done
  spotlight_files_index=${#tabs[@]}
  tabs+=(Files) tab_ids+=(Files)
  spotlight_settings_index=${#tabs[@]}
  tabs+=(Settings) tab_ids+=(Settings)
  spotlight_modules_loaded=1
}

spotlight_module_tab_load() {
  local module=${spotlight_tab_owners[$1]:-}
  [[ -n $module ]] || return 1
  spotlight_module_call "$module" list "${1#*.}"
}

# Reuse core formatting; IDs route to their owner without per-row processes.
spotlight_module_row() {
  local module=$1 id=$2
  shift 2
  add "module:$module:$id" "$@"
}

spotlight_module_dispatch() {
  local operation=$1 payload=${2#module:} module callback active found=0
  module=${payload%%:*} payload=${payload#*:}
  for active in "${spotlight_modules[@]}"; do
    [[ $active != "$module" ]] || found=1
  done
  callback="spotlight_${module}_${operation}"
  if (( found == 0 )) || ! declare -F "$callback" >/dev/null; then
    printf 'Unavailable module operation: %s\n' "$module.$operation" >&2
    return 1
  fi
  # Recheck before acting; context or targets can disappear while fzf is open.
  if [[ $operation == select || $operation == setting_select ]]; then
    spotlight_module_require_available "$module" || return
  fi
  "$callback" "$payload"
}

spotlight_module_require_available() {
  if ! spotlight_module_call "$1" available; then
    printf 'Module is no longer available: %s\n' "$1" >&2
    return 1
  fi
}

# Ownership is separate from globally unique action IDs and cached TOML rows.
spotlight_action_require_available() {
  local module
  for module in "${!spotlight_module_actions[@]}"; do
    if [[ $1 -ef ${spotlight_module_actions[$module]} ]]; then
      spotlight_module_require_available "$module" || return
    fi
  done
}

spotlight_module_preview() {
  local module=${1#module:} variable path
  module=${module%%:*}
  [[ $module =~ ^[a-z][a-z0-9_]*$ ]] || return 1
  variable=SPOTLIGHT_PROVIDER_$module
  path=${!variable:-}
  if [[ -n $path ]]; then
    # fzf inherits the active provider path: no discovery or context probes here.
    source "$path" || return
    spotlight_modules=("$module")
  else
    spotlight_load_modules || return
  fi
  if [[ ${2:-preview} == setting_preview ]] && ! declare -F "spotlight_${module}_setting_preview" >/dev/null; then
    printf '%s\n' "${3:-}"
    return
  fi
  if [[ ${2:-preview} == preview ]] && ! declare -F "spotlight_${module}_preview" >/dev/null; then
    printf 'No preview available.\n'
    return
  fi
  spotlight_module_dispatch "${2:-preview}" "$1"
}

spotlight_cwd() {
  if [[ -n ${TMUX:-} ]]; then pane_cwd; else printf '%s\n' "$PWD"; fi
}

spotlight_in_git_repo() {
  local cwd=${1:-}
  if [[ -z $cwd ]]; then cwd=$(spotlight_cwd) || return 2; fi
  git -C "$cwd" rev-parse --show-toplevel >/dev/null 2>&1 && return 0
  return 1
}

spotlight_insert() {
  local target
  if [[ -n ${TMUX:-} ]]; then
    target=$(pane_target) || return
    tmux send-keys -t "$target" -l -- "$1"
  else
    printf '%s' "$1"
  fi
}
