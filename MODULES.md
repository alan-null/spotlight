# Spotlight modules

Modules contribute commands, tabs, settings, or a combination of these. The launcher owns fzf, navigation, query state, caching, and text insertion. The [tmux module](modules/tmux/module.sh) owns tmux command rows, Windows/Sessions/Panes listings, previews, and operations. Finding the originating pane and inserting text remain launcher responsibilities because ordinary commands and Files also use them.

Providers are sourced Bash functions; registration starts no provider processes, and each tab loads only when first opened or explicitly refreshed. Static TOML actions reuse the existing shared cache. Module previews source only their owning provider using a path inherited from the launcher; they do not rediscover modules or repeat availability checks. Avoid slow work at file scope, during tab registration, and in availability checks.

For normal launches, module discovery precedes the Python theme/bootstrap call. Launching Commands requests action-cache metadata in that same call; launching Files or Settings defers it to avoid loading action infrastructure unnecessarily. Bash reads warm cache files directly when the bootstrap supplied a path; cold loads, deferred Commands loads, and explicit refresh still use Python validation. The popup wrapper passes generated theme assignments explicitly through tmux to an internal `--popup-child` handoff, avoiding a second theme process. If the child discovers module TOML actions, it falls back to the Python cache loader because the wrapper bootstrap preceded discovery. This keeps cache keys correct without adding another bootstrap stage. These handoff details are internal; modules should use the public helpers below.

## Discovery and context

Spotlight discovers `MODULE_ID/module.sh` under its bundled `modules/` directory and `$XDG_CONFIG_HOME/spotlight/modules/` (default `~/.config/spotlight/modules/`). `SPOTLIGHT_MODULE_PATH` replaces these roots; `SPOTLIGHT_EXTRA_MODULE_PATH` adds roots. Both are colon-separated directory lists. Discovery follows root order and filename order within each root. Module IDs must match `[a-z][a-z0-9_]*`; duplicates fail rather than override another provider.

Module files are trusted local Bash code, sourced into Spotlight's process. Define functions at file scope; do not print output, execute operations, change shell options, or overwrite launcher variables there. Use module-prefixed function names and local variables. The HTTPS action installer installs TOML actions or basic Navi `.cheat` files, not executable modules. Navi imports belong to the shared action loader and require no Bash module.

An optional `spotlight_ID_available` function returns 0 when available, 1 when unavailable, or a higher status for an error. It runs once during launch and again before a module operation is selected. An unavailable module contributes no tabs, commands, or TOML actions. Registration stays fixed while the launcher is open; reopen to discover modules or change their availability. `Ctrl+R` reloads the active tab's rows, not the module registry. Item-level requirements and target validation belong in the provider.

`spotlight_cwd` returns the originating pane directory inside tmux and `$PWD` outside it. `spotlight_in_git_repo` checks that directory with Git, including worktrees and subdirectories. These helpers perform work only when called. Modules should check required executables in their availability function. Module callbacks must report failures on stderr and return nonzero; an unavailable module is different from a failed listing.

## Provider interface

Capabilities are optional, but contributions must have the callbacks they need. Registering a tab requires `list` and `select`; defining `commands` requires `select`; defining `settings` requires `setting_select`. The launcher validates these at registration and reports the missing callback before opening fzf. TOML-only modules do not need selection callbacks. Command previews are optional and show a placeholder when absent; settings previews default to the row description. The module ID `core` is reserved and rejected during discovery.

| Callback | Contract |
| --- | --- |
| `spotlight_ID_available` | Check module context and dependencies. |
| `spotlight_ID_tabs` | Call `spotlight_module_tab ID TAB_ID LABEL` for each tab. Tab IDs match `[a-z][a-z0-9_-]*` and are namespaced internally as `ID.TAB_ID`. Labels are display text, not routing keys. |
| `spotlight_ID_commands` | Emit rows for the shared Commands tab using `spotlight_module_row ID ITEM_ID TITLE CATEGORY HINT`. |
| `spotlight_ID_list TAB_ID` | Emit rows for one tab. The same row helper works here. Each row is TSV: display text, hidden `module:ID:ITEM_ID`, then optional preview metadata. |
| `spotlight_ID_preview ITEM_ID` | Print a preview. Treat the item ID as data; never evaluate it as shell code. |
| `spotlight_ID_select ITEM_ID` | Validate the item and perform the operation, or call `spotlight_insert TEXT` to insert shell text without pressing Enter. |

IDs and row fields must not contain tabs or newlines. Encode unusual values before putting them in IDs, as Files does. List and command callbacks run in command-substitution subshells; keep persistent state in the launcher rather than assigning globals in those callbacks. A successful selection closes the launcher. Callbacks returning shell text must use `spotlight_insert`, which handles both tmux and zsh insertion; raw stdout is not a portable insertion mechanism inside tmux.

An optional `actions.toml` alongside `module.sh` contributes ordinary shell-insert actions while the module is available. It uses the [existing action format](README.md#usage), parameter chooser, action-level context rules, and globally unique action IDs. Dynamic module rows use namespaced IDs instead. The launcher retains ownership of module action files independently of action IDs and rechecks availability before resolving an action or running its parameter sources. Module source paths participate in the shared action-cache key, so different active module sets do not reuse each other's action listings. Installation invalidates all action-cache variants because user actions are shared between module contexts. Changes to TOML actions still require `Ctrl+R` on Commands.

## Example: contextual Git branches

Create `~/.config/spotlight/modules/git/module.sh`:

```bash
spotlight_git_available() {
  command -v git >/dev/null && spotlight_in_git_repo
}

spotlight_git_tabs() {
  spotlight_module_tab git branches Branches
}

spotlight_git_list() {
  local cwd
  cwd=$(spotlight_cwd) || return
  git -C "$cwd" for-each-ref --format='  %(refname:short)%09module:git:%(refname:short)' refs/heads/
}

spotlight_git_preview() {
  printf 'Insert git switch for branch: %s\n' "$1"
}

spotlight_git_select() {
  local cwd branch
  cwd=$(spotlight_cwd) || return
  git -C "$cwd" show-ref --verify --quiet "refs/heads/$1" || return 1
  printf -v branch '%q' "$1"
  spotlight_insert "git switch -- $branch"
}
```

Optionally add `actions.toml` in the same directory:

```toml
[[actions]]
id = "git.status"
title = "Git status"
category = "Git"
command = "git status --short"
```

This example inserts commands for review. The built-in tmux module instead performs its navigation operations immediately and retains confirmation for close operations. No Git module is enabled by default.

## Scope

There is no module dependency graph, remote module installer, hot reload, or tab paging. Commands, Files, and Settings remain built in, tab state is sized dynamically, and Files has a stable shortcut independent of contributed tabs. Modules run as trusted code without sandboxing.

## Architecture entry points

| Entry point | Responsibility |
| --- | --- |
| [bin/spotlight](bin/spotlight) | CLI and popup entry, fzf loop, built-in tabs, row formatting, selection routing |
| [lib/modules.sh](lib/modules.sh) | Discovery, registration validation, module ownership, availability, provider dispatch, shell insertion |
| [lib/actions.py](lib/actions.py) | TOML validation, shared action cache, installation, parameter resolution |
| [lib/settings.sh](lib/settings.sh) | Settings tab, interactive choices, provider settings routing |
| [lib/spotlight_config.py](lib/spotlight_config.py) | Persistent configuration and data-only theme parsing |
| [lib/history.sh](lib/history.sh) and [lib/history.awk](lib/history.awk) | Lazy history snapshots and one native catalog-index pass for recent-row promotion |
| [lib/history.py](lib/history.py) | Bounded, private, atomic history persistence and limit validation |
| [modules/tmux/module.sh](modules/tmux/module.sh) | Tmux capabilities and their operations |

Add capabilities by defining provider callbacks, not by adding module-specific branches to the fzf loop. Add ordinary command bundles through TOML, not executable providers, when commands are sufficient.

Successful module operations selected from Commands participate in invocation history automatically; no history callback is needed. Stable namespaced item IDs let recent entries match current contributions, so unavailable or removed commands are not replayed. Module selections still pass through availability and provider dispatch on reuse. Module tabs and Settings operations do not enter Commands history.

## Settings contributions

Settings is a built-in tab after Files, also accessible with `spotlight --settings`. It presents one searchable list of setting names, their owning core/module section, and current values. Descriptions appear in the preview. Selecting a setting opens its chooser or performs its maintenance operation, then returns to Settings without inserting shell text or closing Spotlight. Only available modules contribute rows. Theme rendering is core functionality because it spans every view and the popup frame; themes themselves are data, not executable modules.

| Callback | Contract |
| --- | --- |
| `spotlight_ID_settings` | Emit rows with `spotlight_module_setting ID KEY TITLE CURRENT_VALUE DESCRIPTION`. This callback runs lazily in a subshell like other listings. Keys match `[a-z][a-z0-9_-]*`; `core` is reserved as a settings namespace. |
| `spotlight_ID_setting_preview KEY` | Optional custom preview; otherwise the row description is shown. Preview children source only the owning module, as for command previews. |
| `spotlight_ID_setting_select KEY` | Validate the key and change a preference or perform a maintenance operation. Availability is checked again first. Return 0 after success or cancellation; other statuses report failure. This callback runs in the launcher process. Its stdout is routed to stderr to preserve the shell insertion contract. |

`spotlight_setting_get ID KEY DEFAULT` reads a string preference; `spotlight_setting_set ID KEY VALUE` atomically saves one. Values live in `$XDG_CONFIG_HOME/spotlight/settings.json`, defaulting to `~/.config/spotlight/settings.json`, under the module ID. Writes preserve other namespaces and keys. These helpers start Python only when called; do not use them at module file scope or during tab registration. Reads and writes are intended for occasional interactive configuration, not concurrent high-frequency state updates. Concurrent writers use last-write-wins behavior.

`spotlight_choose TITLE CHOICE...` opens a themed choice list and sets `SPOTLIGHT_CHOICE`. Return 0 means a selection, 1 means cancellation, and other statuses mean failure. Do not invoke it in command substitution: its result variable belongs to the callback process. Persist only after a successful selection. Settings refreshes rows after the callback, retaining the current query. Module settings do not change module registration or tab layout until Spotlight is reopened.

```bash
spotlight_demo_settings() {
  local value
  value=$(spotlight_setting_get demo mode compact) || return
  spotlight_module_setting demo mode 'Display mode' "$value" 'Choose how the Demo module presents its results.'
}

spotlight_demo_setting_select() {
  [[ $1 == mode ]] || return 1
  local status
  if spotlight_choose 'Settings › Demo › Display mode' compact detailed; then
    spotlight_setting_set demo mode "$SPOTLIGHT_CHOICE"
  else
    status=$?
    [[ $status == 1 ]] || return "$status"
  fi
}
```

The module must also read its preference when rendering its own results. Core does not interpret module-specific values. The bundled tmux provider contributes **Reload tmux configuration** as an example of a maintenance control; existing command shortcuts remain available.
