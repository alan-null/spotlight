# Trusted built-in provider; sourced once per launcher process.
spotlight_tmux_available() {
  [[ -n ${TMUX:-} ]] && command -v tmux >/dev/null
}

spotlight_tmux_tabs() {
  spotlight_module_tab tmux windows Windows
  spotlight_module_tab tmux sessions Sessions
  spotlight_module_tab tmux panes Panes
}

spotlight_tmux_commands() {
  spotlight_module_row tmux new-window       'New window'            'WINDOWS'       'prefix c'
  spotlight_module_row tmux rename-window    'Rename window'         'WINDOWS'       'prefix ,'
  spotlight_module_row tmux next-window      'Next window'           'WINDOWS'       'prefix n'
  spotlight_module_row tmux previous-window  'Previous window'       'WINDOWS'       'prefix p'
  spotlight_module_row tmux close-window     'Close window...'       'WINDOWS'       ''
  spotlight_module_row tmux split-right      'Split right'           'PANES'         'prefix %'
  spotlight_module_row tmux split-down       'Split below'           'PANES'         'prefix "'
  spotlight_module_row tmux zoom-pane        'Zoom / unzoom pane'    'PANES'         'prefix z'
  spotlight_module_row tmux swap-pane        'Swap with next pane'   'PANES'         ''
  spotlight_module_row tmux close-pane       'Close pane...'         'PANES'         'prefix x'
  spotlight_module_row tmux session-browser  'Browse sessions'       'SESSIONS'      'prefix s'
  spotlight_module_row tmux switch-tree      'Switch pane / window'  'NAVIGATION'    'prefix Tab'
  spotlight_module_row tmux rename-session   'Rename session'        'SESSIONS'      'prefix $'
  spotlight_module_row tmux detach           'Detach client'         'SESSIONS'      'prefix d'
  spotlight_module_row tmux copy-mode        'Enter copy mode'       'NAVIGATION'    'prefix ['
  spotlight_module_row tmux paste-buffer     'Paste tmux buffer'     'CLIPBOARD'     'prefix ]'
  spotlight_module_row tmux buffer-list      'Browse tmux buffers'   'CLIPBOARD'     ''
  spotlight_module_row tmux reload-config    'Reload configuration'  'CONFIGURATION' ''
  spotlight_module_row tmux keybindings      'Show keybindings'      'CONFIGURATION' 'prefix ?'

  if [[ -f "${HOME}/.tmux/plugins/tmux-resurrect/scripts/save.sh" ]]; then
    spotlight_module_row tmux save-session    'Save session'          'PERSISTENCE'   'prefix Ctrl+s'
    spotlight_module_row tmux restore-session 'Restore session'      'PERSISTENCE'   'prefix Ctrl+r'
  fi
}

spotlight_tmux_list() {
  case "$1" in
    windows)
      tmux list-windows -a -F $'  #{session_name}:#{window_index}  #{window_name}  (#{window_panes} panes)#{?window_active, [active],}\tmodule:tmux:window:#{session_id}:#{window_id}'
      ;;
    sessions)
      tmux list-sessions -F $'  #{session_name}  (#{session_windows} windows, #{session_attached} attached)\tmodule:tmux:session:#{session_id}'
      ;;
    panes)
      tmux list-panes -a -F $'  #{session_name}:#{window_index}.#{pane_index}  #{window_name}  #{pane_current_command}  #{pane_current_path}#{?pane_active, [active],}\tmodule:tmux:pane:#{session_id}:#{window_id}.#{pane_id}'
      ;;
  esac
}

spotlight_tmux_preview() {
  case "$1" in
    session:*)
      tmux display-message -p -t "${1#*:}" $'SESSION\n\n#{session_name}\n#{session_windows} windows\n#{session_attached} attached clients\n\nEnter to switch to this session.'
      ;;
    window:*)
      tmux display-message -p -t "${1#*:}" $'WINDOW\n\n#{session_name}:#{window_index} - #{window_name}\n#{window_panes} panes\n\nActive command: #{pane_current_command}\nDirectory: #{pane_current_path}\n\nEnter to switch to this window.'
      ;;
    pane:*)
      tmux display-message -p -t "${1#*:}" $'PANE\n\n#{session_name}:#{window_index}.#{pane_index} - #{window_name}\nCommand: #{pane_current_command}\nDirectory: #{pane_current_path}\nSize: #{pane_width} x #{pane_height}\n\nEnter to focus this pane.'
      ;;
    new-window) printf 'WINDOWS\n\nCreate a new window in the current session.\n\ntmux new-window\n' ;;
    rename-window) printf 'WINDOWS\n\nRename the currently selected window.\n\ntmux command-prompt ... rename-window\n' ;;
    next-window) printf 'WINDOWS\n\nSwitch to the next window.\n\ntmux next-window\n' ;;
    previous-window) printf 'WINDOWS\n\nSwitch to the previous window.\n\ntmux previous-window\n' ;;
    close-window) printf 'WINDOWS\n\nAsk for confirmation before closing the window and its panes.\n' ;;
    split-right) printf 'PANES\n\nCreate a new pane to the right.\n\ntmux split-window -h\n' ;;
    split-down) printf 'PANES\n\nCreate a new pane below.\n\ntmux split-window -v\n' ;;
    zoom-pane) printf 'PANES\n\nToggle maximizing the active pane.\n\ntmux resize-pane -Z\n' ;;
    swap-pane) printf 'PANES\n\nSwap active pane with the next pane.\n\ntmux swap-pane -D\n' ;;
    close-pane) printf 'PANES\n\nAsk for confirmation before closing the active pane.\n' ;;
    session-browser) printf 'SESSIONS\n\nBrowse sessions, windows, and panes using tmux tree mode.\n' ;;
    switch-tree) printf 'NAVIGATION\n\nSwitch between sessions, windows, and panes.\n\nUse the arrows to move, Enter to select, and Escape to cancel.\n' ;;
    rename-session) printf 'SESSIONS\n\nPrompt for a new session name.\n' ;;
    detach) printf 'SESSIONS\n\nDisconnect this tmux client. Your running programs stay alive.\n' ;;
    copy-mode) printf 'NAVIGATION\n\nEnter tmux copy mode to scroll/search history.\n' ;;
    paste-buffer) printf 'CLIPBOARD\n\nPaste the most recent tmux paste buffer into the active pane.\n\nThis is not necessarily your system clipboard.\n' ;;
    buffer-list) printf 'CLIPBOARD\n\nSelect a tmux paste buffer.\n' ;;
    reload-config) printf 'CONFIGURATION\n\nReload the tmux configuration without restarting tmux.\n' ;;
    keybindings) printf 'CONFIGURATION\n\nShow tmux keybindings in a scrollable list.\n' ;;
    save-session) printf 'PERSISTENCE\n\nSave the session using tmux-resurrect.\n\nRequires the tmux-resurrect plugin.\n' ;;
    restore-session) printf 'PERSISTENCE\n\nRestore the saved session using tmux-resurrect.\n\nRequires the tmux-resurrect plugin.\n' ;;
  esac
}

spotlight_tmux_select() {
  local id=$1 target session config
  case "$id" in
  session:*) tmux switch-client -t "${id#*:}" ;;
  window:*|pane:*)
    target="${id#*:}"
    session="${target%%:*}"
    tmux switch-client -t "$session" || return 1
    tmux select-window -t "$target" || return 1
    if [[ "$id" == pane:* ]]; then
      tmux select-pane -t "$target"
    fi
    ;;
  new-window)      tmux new-window ;;
  rename-window)   tmux command-prompt -I '#W' 'rename-window -- "%%"' ;;
  next-window)     tmux next-window ;;
  previous-window) tmux previous-window ;;
  close-window)    tmux confirm-before -p 'Close current window? (y/n)' 'kill-window' ;;
  split-right)     tmux split-window -h ;;
  split-down)      tmux split-window -v ;;
  zoom-pane)       tmux resize-pane -Z ;;
  swap-pane)       tmux swap-pane -D ;;
  close-pane)      tmux confirm-before -p 'Close current pane? (y/n)' 'kill-pane' ;;
  session-browser) tmux choose-tree -s ;;
  switch-tree)     tmux choose-tree -Z ;;
  rename-session)  tmux command-prompt -I '#S' 'rename-session -- "%%"' ;;
  detach)          tmux detach-client ;;
  copy-mode)       tmux copy-mode ;;
  paste-buffer)    tmux paste-buffer ;;
  buffer-list)     tmux choose-buffer ;;
  reload-config)
    config="$HOME/.tmux.conf"
    [[ -f "$config" ]] || config="${XDG_CONFIG_HOME:-$HOME/.config}/tmux/tmux.conf"
    if [[ ! -f "$config" ]]; then
      printf 'tmux configuration not found: %s\n' "$config" >&2
      return 1
    fi
    tmux source-file "$config" && tmux display-message 'tmux configuration reloaded'
    ;;
  keybindings)     tmux list-keys | less -R ;;
  save-session)    tmux run-shell -b "$HOME/.tmux/plugins/tmux-resurrect/scripts/save.sh" ;;
  restore-session) tmux run-shell -b "$HOME/.tmux/plugins/tmux-resurrect/scripts/restore.sh" ;;
  esac
}

# Settings exposes maintenance controls alongside future module preferences.
spotlight_tmux_settings() {
  spotlight_module_setting tmux reload-config 'Reload tmux configuration' 'Run…' 'Reload your tmux configuration without restarting tmux.'
}

spotlight_tmux_setting_preview() {
  spotlight_tmux_preview "$1"
}

spotlight_tmux_setting_select() {
  [[ $1 == reload-config ]] || return 1
  spotlight_tmux_select "$1"
}
