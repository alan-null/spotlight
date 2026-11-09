# Spotlight website

The static Spotlight site lives here for GitHub Pages. Set Pages to deploy from the repository's `docs/` folder on the main branch. The homepage is [index.html](./index.html), and the [theme studio](./theme-studio/) is a subpage. No build step is required.

To preview locally from the repository root, run `python3 -m http.server 8765 --directory docs` and open `http://localhost:8765/`. The appearance switcher saves your light or dark choice in browser storage. The homepage's Monoaki, Slate, and Terminal ANSI examples are visual previews; Terminal ANSI shades vary with the terminal. The terminal palette in the studio is independent of the page appearance and is exported as TOML.
