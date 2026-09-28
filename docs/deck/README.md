# Deck generator

`docs/SAT-SA-Lens-SIH26157.pptx` is a normal, fully editable PowerPoint file —
open it and change anything. This folder only exists if you would rather edit the
deck as code and regenerate it.

```bash
cd docs/deck
npm install
npm run build          # rewrites ../SAT-SA-Lens-SIH26157.pptx
```

`build.js` holds every slide's content and coordinates (inches, 13.333 x 7.5).
`lib.js` draws each primitive twice: once into the .pptx and once into an HTML
twin at 96 px/inch. Building also writes `preview.html` plus `preview-1..6.html`,
which is how the layout was checked for text overflow and overlaps without
LibreOffice installed:

```bash
python3 -m http.server 5311      # then open http://localhost:5311/preview.html
```

Things to replace before submitting: `TEAM`, `TEAM_ID`, `INSTITUTE` and
`PS_TITLE` at the top of `build.js`, and the three `<... URL>` placeholders in
the PROJECT LINKS block on slide 6.
