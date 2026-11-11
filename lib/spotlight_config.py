"""Spotlight settings and data-only themes shared by Bash and Python views."""
import json
import os
from pathlib import Path
import re
import shlex
import sys
if sys.version_info < (3, 11):
    sys.exit("Spotlight requires Python 3.11 or newer; upgrade python3 before launching it.")
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = dict(background='#161b22', foreground='#d5dce4', selection='#283747',
               selected_foreground='#ffffff', accent='#7dd3a8', muted='#8093a8',
               border='#485463', hint='245', command='114', tab_foreground='#161b22', error='#ff7b72')
CATEGORIES = dict(WINDOWS='81', PANES='114', SESSIONS='221', NAVIGATION='177',
                  CLIPBOARD='216', CONFIGURATION='110', PERSISTENCE='150',
                  ACTIONS='81', SYSTEM='81', DOCKER='114')
IDENTIFIER = re.compile(r'[a-z][a-z0-9_-]*\Z')


def config_dir():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'spotlight'


def settings():
    path = config_dir() / 'settings.json'
    data = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(data, dict) or any(not isinstance(v, dict) for v in data.values()):
        raise ValueError('settings.json must contain namespace objects')
    return data


def get(namespace, key, default=''):
    value = settings().get(namespace, {}).get(key, default)
    if not isinstance(value, str):
        raise ValueError(f'{namespace}.{key} must be a string')
    return value


def save(namespace, key, value):
    if not IDENTIFIER.fullmatch(namespace) or not IDENTIFIER.fullmatch(key):
        raise ValueError('Invalid setting namespace or key')
    if namespace == 'core' and key == 'theme':
        load_theme(value)  # Never persist an unusable theme.
    if namespace == 'core' and key == 'fzf_info' and value not in ('inline-right', 'inline'):
        raise ValueError('core.fzf_info must be inline-right or inline')
    if namespace == 'core' and key == 'history_limit':
        from history import history_limit
        value = str(history_limit(value))
    data = settings()
    data.setdefault(namespace, {})[key] = value
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=directory, prefix='.settings-', delete=False) as output:
            temporary = Path(output.name)
            json.dump(data, output, indent=2)
            output.write('\n')
        os.replace(temporary, directory / 'settings.json')
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def theme_paths():
    paths = {}
    for directory in (ROOT / 'themes', config_dir() / 'themes'):
        for path in sorted(directory.glob('*.toml')):
            if not IDENTIFIER.fullmatch(path.stem):
                raise ValueError(f'Invalid theme name: {path.name}')
            paths[path.stem] = path
    return paths


def valid_color(color):
    return isinstance(color, str) and (color == 'default' or bool(re.fullmatch(r'#[0-9a-fA-F]{6}', color)) or (color.isascii() and color.isdigit() and 0 <= int(color) <= 255))


def load_theme(name=None):
    name = name if name is not None else get('core', 'theme', 'default')
    path = theme_paths().get(name)
    if path is None:
        raise ValueError(f'Unknown Spotlight theme: {name}')
    with path.open('rb') as source:
        data = tomllib.load(source)
    if set(data) - {'colors', 'categories'}:
        raise ValueError(f'{path}: expected colors and categories tables')
    colors, categories = data.get('colors', {}), data.get('categories', {})
    if not isinstance(colors, dict) or not isinstance(categories, dict) or set(colors) - DEFAULT.keys():
        raise ValueError(f'{path}: invalid theme color keys')
    if any(not k or any(ord(c) < 32 for c in k) for k in categories):
        raise ValueError(f'{path}: invalid category name')
    if not all(valid_color(v) for v in [*colors.values(), *categories.values()]):
        raise ValueError(f'{path}: colors must be #RRGGBB, 0–255 strings, or default')
    return dict(name=name, colors=DEFAULT | colors, categories=CATEGORIES | {k.upper(): v for k, v in categories.items()})


def current_theme():
    snapshot = os.environ.get('SPOTLIGHT_THEME_DATA')
    return json.loads(snapshot) if snapshot else load_theme()


def ansi(color, background=False):
    if color == 'default':
        return '\033[49m' if background else '\033[39m'
    prefix = 48 if background else 38
    if color.startswith('#'):
        r, g, b = (int(color[i:i+2], 16) for i in (1, 3, 5))
        return f'\033[{prefix};2;{r};{g};{b}m'
    return f'\033[{prefix};5;{color}m'


def color_rgb(color):
    if color.startswith('#'):
        return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    if color.isdigit():
        index = int(color)
        ansi_palette = ((0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
                        (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
                        (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
                        (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255))
        if index < 16:
            return ansi_palette[index]
        if index < 232:
            value = index - 16
            levels = (0, 95, 135, 175, 215, 255)
            return levels[value // 36], levels[(value // 6) % 6], levels[value % 6]
        value = 8 + (index - 232) * 10
        return value, value, value
    return None


def theme_variant(theme):
    background = theme['colors']['background']
    rgb = color_rgb(background)
    if background == 'default':
        colorfgbg = os.environ.get('COLORFGBG', '').replace(':', ';').split(';')
        if colorfgbg and colorfgbg[-1].isdigit():
            rgb = color_rgb(colorfgbg[-1])
    if rgb is None:
        foreground = color_rgb(theme['colors']['foreground'])
        if foreground is None:
            return 'dark'
        rgb = foreground
        return 'dark' if color_luminance(rgb) >= 0.5 else 'light'
    luminance = color_luminance(rgb)
    return 'light' if luminance >= 0.5 else 'dark'


def color_luminance(rgb):
    linear = [channel / 255 for channel in rgb]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
              for value in linear]
    return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def fzf_colors(theme):
    c = theme['colors']
    roles = dict(bg='background', **{'bg+':'selection'}, fg='foreground',
                 **{'fg+':'selected_foreground'}, hl='accent', **{'hl+':'accent'},
                 header='muted', prompt='accent', pointer='accent', marker='accent',
                 border='border', info='muted', **{'preview-bg':'background', 'preview-fg':'foreground'})
    return ','.join(f'{key}:{"-1" if c[value] == "default" else c[value]}' for key, value in roles.items())


def fzf_info():
    value = get('core', 'fzf_info', 'inline-right')
    if value not in ('inline-right', 'inline'):
        raise ValueError('core.fzf_info must be inline-right or inline')
    return value


def fzf_error(message, info):
    if info != 'inline-right' or 'invalid info style' not in message.lower():
        return message.strip()
    # Check the version only after fzf rejects the configured style.
    import subprocess
    try:
        result = subprocess.run(['fzf', '--version'], capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return message.strip()
    version = re.match(r'^(\d+)\.(\d+)', result.stdout)
    if result.returncode != 0 or not version or tuple(map(int, version.groups())) >= (0, 42):
        return message.strip()
    save('core', 'fzf_info', 'inline')
    return (f"fzf {result.stdout.strip()} does not support inline-right.\n"
            "Updated Result count position (core.fzf_info) to inline in Spotlight settings.\n"
            "Reopen Spotlight; the next launch will use the saved compatible mode.")


def shell_theme(include_action_cache=False):
    from history import history_limit, history_path

    theme = load_theme()
    values = dict(SPOTLIGHT_THEME_DATA=json.dumps(theme), SPOTLIGHT_THEME_NAME=theme['name'],
                  SPOTLIGHT_THEME_VARIANT=theme_variant(theme),
                  SPOTLIGHT_FZF_INFO=fzf_info(),
                  SPOTLIGHT_FZF_COLORS=fzf_colors(theme),
                  SPOTLIGHT_HISTORY_LIMIT=str(history_limit(get('core', 'history_limit', '5'))),
                  SPOTLIGHT_HISTORY_FILE=str(history_path(inherited=False)))
    if include_action_cache:
        from actions import cache_path
        values['SPOTLIGHT_ACTION_CACHE_FILE'] = str(cache_path())
    def tmux_color(color):
        return 'colour' + color if color.isdigit() else color
    c = theme['colors']
    values['SPOTLIGHT_POPUP_STYLE'] = f"bg={tmux_color(c['background'])},fg={tmux_color(c['foreground'])}"
    values['SPOTLIGHT_POPUP_BORDER'] = f"fg={tmux_color(c['accent'])}"
    for key, color in theme['colors'].items():
        values['SPOTLIGHT_ANSI_' + key.upper()] = ansi(color)
    values['SPOTLIGHT_ANSI_TAB'] = ansi(theme['colors']['accent'], True) + ansi(theme['colors']['tab_foreground']) + '\033[1m'
    for key, value in values.items():
        print(f'export {key}={shlex.quote(value)}')
    print('declare -gA spotlight_category_colors=()')
    for key, color in theme['categories'].items():
        print(f'spotlight_category_colors[{shlex.quote(key)}]={shlex.quote(ansi(color))}')


def main():
    operation, *args = sys.argv[1:]
    if operation == 'shell':
        if args not in ([], ['--action-cache']):
            raise ValueError('Usage: spotlight_config.py shell [--action-cache]')
        shell_theme(include_action_cache=bool(args))
    elif operation == 'fzf-error':
        print(fzf_error(sys.stdin.read(), *args), file=sys.stderr)
    elif operation == 'themes':
        for name in sorted(theme_paths()):
            print(name)
    elif operation == 'get':
        print(get(*args))
    elif operation == 'set':
        save(*args)
    else:
        raise ValueError(f'Unknown configuration operation: {operation}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, TypeError) as error:
        print(f'Spotlight configuration: {error}', file=sys.stderr)
        sys.exit(1)
