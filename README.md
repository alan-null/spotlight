# Spotlight

A terminal command palette with fuzzy command and file search, tmux navigation, configurable actions, themes, and recent-command history.

Explore the [Spotlight website](docs/) and build a custom palette in the [theme studio](docs/theme-studio/).

## Installation

Requires Linux, Bash 4+, Python 3.11+, fzf, POSIX awk, and standard GNU command-line utilities. Tmux 3.2+ is needed for popups and tmux navigation. Git enables repository-aware file search; `file` enables text previews. No third-party Python packages are required. The default result count style requires fzf 0.42+; Settings offers `inline` for older versions.

Clone this repository to a directory of your choice and run `./bin/spotlight` from the checkout. Keep the repository layout intact: the executable loads its libraries and bundled resources relative to its location. For a command on PATH, use a wrapper that executes the actual checkout path rather than a symlink to the executable.

For a Zsh integration, capture the executable's output in a ZLE widget and append it to `LBUFFER`. For tmux, bind your preferred shortcut to `/absolute/path/to/spotlight/bin/spotlight --popup`, with `--files` for file search. The [.sh repository](https://github.com/alan-null/.sh) provides shell and tmux bindings.

Personal actions, modules, themes, settings, history, and caches use XDG directories outside this checkout. Updating the application does not require copying personal configuration.

The tmux Reload configuration action uses `~/.tmux.conf`, falling back to `$XDG_CONFIG_HOME/tmux/tmux.conf` (default `~/.config/tmux/tmux.conf`).

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s benchmarks -v
python3 tests/smoke_terminal.py
```

See [the benchmark guide](benchmarks/README.md) for performance measurements and [the module guide](MODULES.md) for provider callbacks and architecture entry points.

## Usage

Run `./bin/spotlight` for Commands, `./bin/spotlight --files` for Files, or `./bin/spotlight --settings` for Settings. With the .sh bindings, `Ctrl+Space` opens Commands and `Ctrl+P` opens Files.

Inside tmux, the bundled module adds Windows, Sessions, and Panes between Commands and Files. Outside tmux, the tabs are Commands, Files, and Settings. Available modules can add tabs.

| Key | Behavior |
| --- | --- |
| Left / Right | Switch tabs, wrapping at either end. |
| Enter | Select an item. |
| Escape | Close without inserting anything. |
| `Ctrl+/` | Toggle the preview. |
| `Ctrl+R` | Refresh the active tab; Commands also reloads action definitions. |

Each tab retains its query while Spotlight is open. Command and file selections insert text at the current shell cursor without pressing Enter. File paths are shell quoted and relative to the active shell or pane directory. Built-in tmux operations run immediately; close operations ask for confirmation.

After manually adding, changing, or removing action files, press `Ctrl+R` on Commands to rebuild its persistent cache. Reloading zsh does not clear this cache. You can also select **Clear Spotlight actions cache**, execute the inserted command, and reopen Spotlight. This removes cached action definitions for all source combinations while keeping installed action files and command history.

The launcher lives under `bin/`, helpers under `lib/`, bundled actions under `actions/`, and file search settings under `config/`. Spotlight also reads `~/.config/spotlight/actions/` recursively for per-machine actions, or `$XDG_CONFIG_HOME/spotlight/actions/` when that variable is set. Add another local repository with the colon-separated `SPOTLIGHT_EXTRA_ACTION_PATH` environment variable. `SPOTLIGHT_ACTION_PATH` replaces the default bundled and user action paths for a fully custom setup.

**Settings → Result count position** chooses `inline-right` (default, requires fzf 0.42+) or `inline` (compatible with older fzf). The preference is stored as `core.fzf_info` and applies to the main view and parameter pickers. If an older fzf rejects `inline-right`, Spotlight saves `inline` and asks you to reopen. Failed tmux popups remain open so you can read the error; press Escape to close them.

Spotlight also supports local modules that contribute commands and tabs, with an availability check for their context. Tmux is a bundled module. See the [module guide](MODULES.md) for the provider interface and an optional Git branches example. Modules use Bash functions, lazy tab loading, and the existing action cache to keep launch overhead small.

Commands shows your last five distinct invocations first, marked `↺`, so reopening Spotlight and pressing Enter reuses the most recent command. Typing a query ranks results by fuzzy relevance across the title, category, and description; recent entries have no priority while filtering. Change **Settings → Recent command count** (0–100, default 5), or set `core.history_limit` to a string such as `"10"` in your Spotlight settings. Zero disables recording and display; **Clear recent commands** removes existing history.

Recent TOML invocations reuse the exact previously inserted command, including parameter values. The generic parameterized action remains below them for choosing new values. Module operations run through their provider again. History only promotes currently available Commands rows; changed action definitions still require refresh and are validated before reuse. Successful palette installations promote Install action file into Recents; selecting it opens a fresh URL prompt. Files, Settings, canceled choices, and failed selections are not recorded. Private history lives under `$XDG_STATE_HOME/spotlight/history-v1.tsv`, defaulting to `~/.local/state/spotlight/history-v1.tsv`.

Select **Install action file...** in Commands or run `./bin/spotlight --install https://example.com/actions.toml` to download an HTTPS TOML or Navi `.cheat` file into your user config directory. GitHub `/blob/` file links are also accepted. Spotlight validates the file and rejects duplicate action IDs before saving it. The installer never runs downloaded commands. Commands use a shared cache under `$XDG_CACHE_HOME/spotlight/`, or `~/.cache/spotlight/` by default, across tmux and plain shell sessions. Installation invalidates the cache; press `Ctrl+R` on Commands to reload other edits.

In the palette, installation opens a dedicated empty URL input with instructions. Paste a link and press Enter; Escape returns to Commands. Progress and the result use the same palette surface. Errors use the theme’s `error` color (red by default). After an error, **Back to Commands** is the default; explicitly choose **Edit URL** to correct the retained link. After success, return to Commands with its search preserved and actions refreshed automatically. Arrow keys edit text in the URL step and select options in result pickers.

To install a Navi cheatsheet, use a raw URL or its GitHub file link:

```sh
./bin/spotlight --install https://github.com/denisidoro/cheats/blob/master/security/gpg.cheat
```

The original `.cheat` file is kept under `$XDG_CONFIG_HOME/spotlight/actions/` (default `~/.config/spotlight/actions/`). You can also put your own `.cheat` files there, or point `SPOTLIGHT_EXTRA_ACTION_PATH` at a local cheatsheet repository. Both TOML and `.cheat` files are discovered recursively. Imported commands appear in Commands and work offline; launching Spotlight never fetches updates. Installation does not overwrite existing files. Recent Navi invocations reuse parameter values just like TOML actions.

Navi support covers `%` tags (first tag becomes the category), `#` descriptions, `;` comments, single-line commands, unquoted `<name>` placeholders, and simple `$ name: command` suggestion sources. Names must start with a letter or underscore and contain only ASCII letters, digits, or underscores. Repeated placeholders ask once; missing suggestion sources use a typed prompt. Suggestion sources use Spotlight's existing POSIX shell and picker behavior. Review third-party sources: they run when selecting a parameterized action, although the final command is only inserted.

This is a basic Navi importer, not full Navi compatibility. Multiline or Markdown snippets, inheritance (`@`), dependent variables, advanced picker options (`---`), and quoted or escaped placeholders are rejected with a file-and-line error. An unsupported local cheatsheet prevents Commands refresh until corrected or removed; an invalid download is not installed. Parsed rows share Spotlight's disposable cache; deleting the cache does not delete downloaded cheatsheets.

Each `[[actions]]` table needs a unique `id`, `title`, `category`, and `command`. `description` and `keywords` improve search. `mode` defaults to `shell-insert`, the only supported mode: selecting an action inserts its command at the current cursor without running it. Optional context rules go in `[actions.context]`. For example:

```toml
[[actions]]
id = "git.pull"
title = "Pull repository changes"
description = "Pull changes from the remote repository"
keywords = ["git", "pull", "update", "sync"]
category = "Git"
command = "git pull"

[actions.context]
requires_git_repo = true
```

Tmux actions are available only inside tmux. Set `requires_tmux = true` under `[actions.context]` for a custom action that needs tmux. Built-in tmux actions run when selected; TOML actions always insert text. Action IDs must be unique across all sources.

Actions can contain placeholders such as `<image_id>`. Define each placeholder under `[actions.parameters.NAME]`. A parameter with `source` runs that POSIX shell command only after you select the action and offers its output in a picker. Sources run in the active shell or pane directory with a 30-second timeout. Each output line is a value, optionally followed by a tab and a display label; Spotlight inserts the first field with shell quoting. Without `source`, Spotlight asks you to type a value. Repeated placeholders reuse the same answer. Keep placeholders unquoted in the command. Canceling a parameter picker or entering an empty value leaves the shell line unchanged. For example, a custom Docker action file can contain:

```toml
[[actions]]
id = "docker.image-remove"
title = "Remove Docker image"
category = "Docker Images"
command = "docker image rm <image_id>"

[actions.parameters.image_id]
prompt = "Docker image"
source = "docker image ls --format '{{.ID}}\t{{.Repository}}:{{.Tag}}'"
```

Selecting a parameterized action runs its `source` command, so review action files downloaded from others before using them.

Outside Git repositories, Files skips directories named in [config/file-prune.conf](config/file-prune.conf). The default is `.git`. Add one directory name per line to skip others such as `node_modules`, `target`, or `.cargo`; remove a name to include it again. Git repositories use `git ls-files` and Git's ignore rules instead. Press `Ctrl+R` on Files to refresh its current listing.

Files with tabs or newlines in their names appear with escaped characters and can still be selected. The preview shows up to 160 lines or 64 KiB of text. Binary and empty files show a short placeholder. Content previews use the optional `file` command; file search and insertion still work without it.

### Spotlight settings and themes

Open the **Settings** tab with Left/Right, or launch `./bin/spotlight --settings`. Settings lists core preferences and controls contributed by available modules, showing their owner and current value with details in the preview. Enter opens a chooser or runs the control; Escape from a chooser returns without saving. Changes return to Settings and retain your search query.

**Theme** is a core preference. `default` uses a dark background with mint accents. `terminal` uses your terminal's ANSI palette. The selected theme is saved in `$XDG_CONFIG_HOME/spotlight/settings.json` (default `~/.config/spotlight/settings.json`) and applies immediately to the main view, tabs, category labels, previews and parameter pickers. The tmux popup frame picks up changes the next time it opens.

Create your own theme as `$XDG_CONFIG_HOME/spotlight/themes/NAME.toml`, or `~/.config/spotlight/themes/NAME.toml`. Names use lowercase letters, digits, underscores or hyphens and must start with a letter. Reopen the Theme chooser to discover new files. A user theme with the same name as a bundled theme overrides it. Missing entries inherit the default palette. Invalid themes report an error; an invalid selection is not saved.

```toml
[colors]
background = "#161b22"
foreground = "#d5dce4"
selection = "#283747"
selected_foreground = "#ffffff"
accent = "#7dd3a8"
muted = "#8093a8"
border = "#485463"
hint = "245"
command = "114"
tab_foreground = "#161b22"

[categories]
Git = "6"
Docker = "2"
```

Save the example as `my-theme.toml` in your user themes directory, then open **Settings → Theme → my-theme** to select it. You can include only the entries you want to change; omitted entries inherit the default palette.

#### Color values

Every color value must be a quoted TOML string. You can mix these formats in one theme:

| Format | Example | Meaning |
| --- | --- | --- |
| RGB hex | `accent = "#7dd3a8"` | An explicit RGB shade, independent of the terminal palette. Use six hexadecimal digits. |
| Palette index | `accent = "2"` | A color from the terminal's 256-color palette. This example uses its green slot. |
| Terminal default | `background = "default"` | The terminal's default background for `background` and `selection`; its default foreground for the other roles. |

Indices `"0"`–`"15"` are the standard ANSI palette slots. Your terminal's color scheme determines their actual shades, so using them helps Spotlight match your shell prompt:

| Normal index | Standard color | Bright index | Standard color |
| --- | --- | --- | --- |
| `"0"` | Black | `"8"` | Bright black / dark gray |
| `"1"` | Red | `"9"` | Bright red |
| `"2"` | Green | `"10"` | Bright green |
| `"3"` | Yellow | `"11"` | Bright yellow |
| `"4"` | Blue | `"12"` | Bright blue |
| `"5"` | Magenta | `"13"` | Bright magenta |
| `"6"` | Cyan | `"14"` | Bright cyan |
| `"7"` | White / light gray | `"15"` | Bright white |

Indices `"16"`–`"231"` normally form a 6×6×6 RGB color cube; `"232"`–`"255"` normally form a grayscale ramp from dark to light. Values such as `"114"` and `"245"` in the example are palette indices, not RGB values. Use explicit hex colors when you want to specify the shade directly.

#### Color roles and categories

| Role | Controls |
| --- | --- |
| `background` | Main and preview backgrounds, plus the tmux popup background. |
| `foreground` | Ordinary result and preview text, plus the tmux popup foreground. |
| `selection` | Background of the highlighted result. |
| `selected_foreground` | Text of the highlighted result. |
| `accent` | Search prompt, matching text, pointer, marker, active tab background, popup frame and otherwise unmapped categories. |
| `muted` | Inactive tabs, parameter breadcrumbs and search information. |
| `border` | The fzf preview divider. The outer tmux frame uses `accent`. |
| `hint` | Command hints, current setting values and parameter suggestion values. |
| `command` | Command text in the main action preview. |
| `error` | Error headings and diagnostic text; red by default. |
| `tab_foreground` | Text on the active tab and parameter breadcrumb badge. |

Under `[categories]`, map a category name to any supported color value. Names are case-insensitive, so `Git = "6"` colors the Git category cyan. Unspecified built-in categories retain their default colors; other categories use `accent`. Docker categories, including labels beginning with Docker, share the `Docker` color. Choose contrasting pairs for `background`/`foreground`, `selection`/`selected_foreground` and `accent`/`tab_foreground` so text stays readable.

The terminal preset is in [themes/terminal.toml](themes/terminal.toml). The Settings contribution API and preference helpers are documented in [MODULES.md](MODULES.md#settings-contributions).
