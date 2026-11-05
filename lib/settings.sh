# Shared palette prompts and core settings UI. Providers own their operations.
spotlight_theme_load() {
  local assignments
  assignments=$(python3 "$MODULE_DIR/lib/spotlight_config.py" shell "$@") || return
  unset SPOTLIGHT_ACTION_CACHE_FILE
  eval "$assignments"
  SPOTLIGHT_THEME_SHELL=$assignments
}

spotlight_setting_get() {
  python3 "$MODULE_DIR/lib/spotlight_config.py" get "$@"
}

spotlight_setting_set() {
  python3 "$MODULE_DIR/lib/spotlight_config.py" set "$@"
}

# TITLE followed by choices. Sets SPOTLIGHT_CHOICE; cancellation returns 1.
spotlight_choose() {
  local title=$1 status
  shift
  SPOTLIGHT_CHOICE=$(printf '%s\n' "$@" | fzf --no-clear --ansi --layout=reverse --border=none --no-preview --no-multi --header-first --pointer='▸' --prompt='  Choose ❯ ' --header="$title" --color="$SPOTLIGHT_FZF_COLORS")
  status=$?
  case $status in
    0) [[ -n $SPOTLIGHT_CHOICE ]] ;;
    1|130) return 1 ;;
    *) printf 'Settings picker failed (exit %s).\n' "$status" >&2; return "$status" ;;
  esac
}

# Free text uses the same full-screen handoff as pickers, without result rows.
# print-query emits only on Enter; Escape/Ctrl+C leave stdout empty.
spotlight_input() {
  local title=$1 status
  SPOTLIGHT_INPUT=$(fzf --no-clear --ansi --disabled --layout=reverse --border=none --no-preview --no-multi --info=hidden --header-first --prompt='  URL ❯ ' --header="$title" --query="${2:-}" --bind='enter:print-query+abort' --color="$SPOTLIGHT_FZF_COLORS" </dev/null)
  status=$?
  case $status in
    0|1|130) [[ -n $SPOTLIGHT_INPUT ]] ;;
    *) printf 'Input prompt failed (exit %s).\n' "$status" >&2; return "$status" ;;
  esac
}

spotlight_install_actions() {
  local title="  ${SPOTLIGHT_ANSI_TAB} Commands › Install action file "$'\033[0m' url='' message status
  SPOTLIGHT_ACTIONS_INSTALLED=0
  while :; do
    if spotlight_input "$title"$'\n\n  Paste an HTTPS URL to a TOML or Navi .cheat file. GitHub file links are accepted.\n  Enter to download · Esc to return to Commands' "$url"; then
      url=$SPOTLIGHT_INPUT
    else
      status=$?
      (( status == 1 )) && return 0
      return "$status"
    fi
    printf '\033[H\033[2J%b\n\n  Downloading and validating…\n' "$title" 2>/dev/null >/dev/tty || true
    if message=$(python3 "$MODULE_DIR/lib/actions.py" install "$url" 2>&1); then
      SPOTLIGHT_ACTIONS_INSTALLED=1
      spotlight_choose "$title"$'\n\n  '"$message" 'Back to Commands'
      status=$?
      (( status == 0 || status == 1 )) || return "$status"
      return 0
    fi
    if spotlight_choose "$title"$'\n\n  '"${SPOTLIGHT_ANSI_ERROR}Could not install action file"$'\n\n'"$message"$'\033[0m' 'Back to Commands' 'Edit URL'; then
      [[ $SPOTLIGHT_CHOICE == 'Edit URL' ]] || return 0
    else
      status=$?
      (( status == 1 )) && return 0
      return "$status"
    fi
  done
}

spotlight_module_setting() {
  local module=$1 id=$2 title=$3 value=$4 description=$5
  if [[ $module == core || ! $id =~ ^[a-z][a-z0-9_-]*$ || -z ${spotlight_module_paths[$module]:-} || -z $title || $title$value$description =~ [[:cntrl:]] ]]; then
    printf 'Invalid module setting: %s.%s\n' "$module" "$id" >&2
    return 1
  fi
  add "setting:$module:$id" "$title" "$module" "$value" "$description"
}

spotlight_settings_rows() {
  add 'setting:core:theme' Theme Core "$SPOTLIGHT_THEME_NAME" 'Choose a built-in or user theme. Applies immediately; the popup frame updates on next open.'
  add 'setting:core:fzf_info' 'Result count position' Core "$SPOTLIGHT_FZF_INFO" 'inline-right places the count on the right; inline places it beside the query and supports older fzf.'
  add 'setting:core:history_limit' 'Recent command count' Core "$SPOTLIGHT_HISTORY_LIMIT" 'Show this many recent invocations first in Commands. Zero disables history; maximum 100.'
  add 'setting:core:clear_history' 'Clear recent commands' Core 'Clear…' 'Remove saved invocations from this machine.'
  local module
  for module in "${spotlight_modules[@]}"; do
    spotlight_module_call "$module" settings || return
  done
}

spotlight_setting_preview() {
  local payload=${1#setting:} module
  module=${payload%%:*}
  if [[ $module == core ]]; then
    case ${payload#*:} in
      theme) printf 'APPEARANCE\n\nChoose a built-in or user theme.\n\nUser themes: %s/spotlight/themes/NAME.toml\n\nThe popup frame updates on next open.\n' "${XDG_CONFIG_HOME:-$HOME/.config}" ;;
      fzf_info) printf 'RESULT COUNT POSITION\n\ninline-right (default): count at the right edge; requires fzf 0.42+.\ninline: count beside the query; compatible with older fzf.\n\nAn unsupported style is corrected only after fzf reports an error. Reopen Spotlight after the correction.\n' ;;
      history_limit) printf 'RECENT COMMANDS\n\nMost recent invocations appear first when search is empty. Search results are ranked by relevance.\n\nChoose 0 to disable history. Valid limits: 0–100.\n' ;;
      clear_history) printf 'RECENT COMMANDS\n\nRemove saved invocations. Command definitions are preserved.\n\n%s\n' "$SPOTLIGHT_HISTORY_FILE" ;;
    esac
  else
    spotlight_module_preview "module:$payload" setting_preview "${2:-}"
  fi
}

spotlight_setting_select() {
  local payload=${1#setting:} module names status
  module=${payload%%:*}
  if [[ $module == core && ${payload#*:} == theme ]]; then
    names=$(python3 "$MODULE_DIR/lib/spotlight_config.py" themes) || return
    local -a choices
    mapfile -t choices <<< "$names"
    if spotlight_choose 'Settings › Theme' "${choices[@]}"; then
      spotlight_setting_set core theme "$SPOTLIGHT_CHOICE" || return
      spotlight_theme_load || return
    else
      status=$?
      (( status == 1 )) || return "$status"
    fi
  elif [[ $module == core && ${payload#*:} == fzf_info ]]; then
    if spotlight_choose 'Settings › Result count position' inline-right inline; then
      spotlight_setting_set core fzf_info "$SPOTLIGHT_CHOICE" || return
      spotlight_theme_load || return
    else
      status=$?
      (( status == 1 )) || return "$status"
    fi
  elif [[ $module == core && ${payload#*:} == history_limit ]]; then
    if spotlight_choose 'Settings › Recent command count' 0 5 10 20 50 100; then
      spotlight_setting_set core history_limit "$SPOTLIGHT_CHOICE" || return
      spotlight_theme_load || return
    else
      status=$?
      (( status == 1 )) || return "$status"
    fi
  elif [[ $module == core && ${payload#*:} == clear_history ]]; then
    python3 "$MODULE_DIR/lib/history.py" clear || return
  else
    spotlight_module_dispatch setting_select "module:$payload" || return
  fi
}
