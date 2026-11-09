'use strict';

// Static, inert fixtures based on Spotlight's tmux provider and the supplied screenshots.
const row = (title, category, hint, description, command = '') => ({ title, category, hint, description, command });
const commands = [
  row('Install action file...', 'ACTIONS', 'HTTPS URL', 'Download an HTTPS TOML or Navi .cheat file to your user configuration. GitHub file links are accepted.'),
  row('New window', 'WINDOWS', 'prefix c', 'Create a new window in the current session.', 'tmux new-window'),
  row('Rename window', 'WINDOWS', 'prefix ,', 'Rename the currently selected window.', 'tmux command-prompt ... rename-window'),
  row('Next window', 'WINDOWS', 'prefix n', 'Switch to the next window.', 'tmux next-window'),
  row('Previous window', 'WINDOWS', 'prefix p', 'Switch to the previous window.', 'tmux previous-window'),
  row('Close window...', 'WINDOWS', '', 'Ask for confirmation before closing the window and its panes.'),
  row('Split right', 'PANES', 'prefix %', 'Create a new pane to the right.', 'tmux split-window -h'),
  row('Split below', 'PANES', 'prefix "', 'Create a new pane below.', 'tmux split-window -v'),
  row('Zoom / unzoom pane', 'PANES', 'prefix z', 'Toggle maximizing the active pane.', 'tmux resize-pane -Z'),
  row('Swap with next pane', 'PANES', '', 'Swap the active pane with the next pane.', 'tmux swap-pane -D'),
  row('Close pane...', 'PANES', 'prefix x', 'Ask for confirmation before closing the active pane.'),
  row('Browse sessions', 'SESSIONS', 'prefix s', 'Browse sessions, windows, and panes using tmux tree mode.'),
  row('Switch pane / window', 'NAVIGATION', 'prefix Tab', 'Switch between sessions, windows, and panes.'),
  row('Rename session', 'SESSIONS', 'prefix $', 'Prompt for a new session name.'),
  row('Detach client', 'SESSIONS', 'prefix d', 'Disconnect this tmux client. Running programs stay alive.'),
  row('Enter copy mode', 'NAVIGATION', 'prefix [', 'Enter tmux copy mode to scroll or search terminal history.'),
  row('Paste tmux buffer', 'CLIPBOARD', 'prefix ]', 'Paste the most recent tmux paste buffer into the active pane.'),
  row('Browse tmux buffers', 'CLIPBOARD', '', 'Select a tmux paste buffer.'),
  row('Reload configuration', 'CONFIGURATION', '', 'Reload the tmux configuration without restarting tmux.'),
  row('Show keybindings', 'CONFIGURATION', 'prefix ?', 'Show tmux keybindings in a scrollable list.'),
  row('Save session', 'PERSISTENCE', 'prefix Ctrl+s', 'Save the session using tmux-resurrect.'),
  row('Restore session', 'PERSISTENCE', 'prefix Ctrl+r', 'Restore the saved session using tmux-resurrect.'),
  row('Update system', 'System', 'Refresh package lists and upgrade installed packages ...', 'Refresh package lists and upgrade installed packages.', 'sudo apt update && sudo apt upgrade'),
  row('Clear Spotlight actions cache', 'Spotlight', 'Delete cached action definitions; reopen Spotlight to...', 'Delete cached action definitions. Reopen Spotlight to load added, changed, or removed actions.'),
  row('List cron jobs', 'crontab', 'List cron jobs crontab schedule', 'Example of a locally installed action that lists scheduled jobs.', 'crontab -l'),
  row('Edit cron job', 'crontab', 'Edit cron job crontab schedule', 'Example of a locally installed action that edits scheduled jobs.', 'crontab -e')
];
const tabs = {
  Commands: commands,
  Windows: [row('work:1  zsh  (2 panes) [active]', 'WINDOWS', 'work:1', 'Active window in the work session. Enter would switch to it.'), row('work:2  editor  (1 pane)', 'WINDOWS', 'work:2', 'Editor window in the work session. Enter would switch to it.')],
  Sessions: [row('work  (2 windows, 1 attached)', 'SESSIONS', 'active', 'Two windows in the work session. Enter would switch to it.'), row('notes  (1 window, 0 attached)', 'SESSIONS', '', 'One window in the notes session. Enter would switch to it.')],
  Panes: [row('work:1.0  zsh  ~/projects', 'PANES', 'active', 'Shell pane in the work session. Enter would focus it.'), row('work:1.1  vim  ~/projects', 'PANES', '', 'Editor pane in the work session. Enter would focus it.')],
  Files: [row('README.md', 'FILE', './README.md', 'Project overview and usage instructions.'), row('bin/spotlight', 'FILE', './bin/spotlight', 'Spotlight launcher.'), row('themes/default.toml', 'FILE', './themes/default.toml', 'Bundled default theme.')],
  Settings: [row('Theme', 'Core', 'default', 'Choose a built-in or user theme. Changes apply immediately.'), row('Recent command count', 'Core', '5', 'Choose how many recent commands appear first.'), row('Result count position', 'Core', 'inline-right', 'Choose where fzf displays the result count.')]
};
const terminal = document.querySelector('.demo-terminal');
const list = document.getElementById('demo-list');
const detail = document.getElementById('demo-detail');
const search = document.getElementById('demo-search');
let activeTab = 'Commands';
let selected = 0;
let visible = [];

function render() {
  const source = tabs[activeTab];
  const query = search.value.trim().toLowerCase();
  visible = source.filter(item => `${item.title} ${item.category} ${item.hint} ${item.description}`.toLowerCase().includes(query));
  selected = Math.min(selected, Math.max(0, visible.length - 1));
  document.getElementById('demo-count').textContent = `${visible.length}/${source.length}`;
  list.replaceChildren();
  visible.forEach((item, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'demo-row';
    button.setAttribute('role', 'option');
    button.setAttribute('aria-selected', String(index === selected));
    const pointer = document.createElement('span');
    pointer.className = 'demo-pointer';
    pointer.textContent = index === selected ? '▸' : '';
    const title = document.createElement('span');
    title.className = 'demo-title';
    title.textContent = item.title;
    const category = document.createElement('span');
    category.className = 'demo-category';
    category.dataset.kind = item.category.toLowerCase();
    category.textContent = item.category;
    const hint = document.createElement('span');
    hint.className = 'demo-hint';
    hint.textContent = item.hint;
    button.append(pointer, title, category, hint);
    button.addEventListener('click', () => { selected = index; render(); });
    list.append(button);
  });
  if (!visible.length) {
    const empty = document.createElement('p');
    empty.className = 'demo-empty';
    empty.textContent = 'No matching results';
    list.append(empty);
  }
  detail.replaceChildren();
  const item = visible[selected];
  if (item) {
    const heading = document.createElement('strong');
    heading.textContent = item.category.toUpperCase();
    const description = document.createElement('p');
    description.textContent = item.description;
    detail.append(heading, description);
    if (item.command) {
      const command = document.createElement('code');
      command.textContent = item.command;
      detail.append(command);
    }
  }
}

search.addEventListener('input', () => { selected = 0; render(); });
list.addEventListener('keydown', event => {
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
  event.preventDefault();
  selected = Math.max(0, Math.min(visible.length - 1, selected + (event.key === 'ArrowDown' ? 1 : -1)));
  render();
  list.focus({ preventScroll: true });
  list.querySelector('[aria-selected=true]')?.scrollIntoView({ block: 'nearest' });
});
document.querySelectorAll('[data-demo-tab]').forEach(button => button.addEventListener('click', () => {
  activeTab = button.dataset.demoTab;
  selected = 0;
  search.value = '';
  document.querySelectorAll('[data-demo-tab]').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
  render();
}));
document.querySelectorAll('[data-demo-palette]').forEach(button => button.addEventListener('click', () => {
  terminal.dataset.palette = button.dataset.demoPalette;
  document.querySelectorAll('[data-demo-palette]').forEach(choice => choice.setAttribute('aria-pressed', String(choice === button)));
  document.querySelector('.demo-note').textContent = button.dataset.demoPalette === 'terminal' ? 'Terminal ANSI uses sample terminal shades. Your terminal controls the actual colors. Preview only.' : 'Built-in tmux commands and illustrative local actions. Preview only.';
}));
render();
