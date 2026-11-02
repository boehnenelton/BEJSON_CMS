# UI & Layout Preferences (dev/UIPref.md)

## Editor V2 & BKS-1 Blog Job Studio

- **Zero Horizontal Overflow Principle**:
  - No element or button bar may exceed `window.innerWidth`. Form and workflow button bars must wrap on mobile devices rather than overflowing horizontally or forcing horizontal scroll bars on the parent body.
- **Responsive Breakpoint Standards**:
  - Desktop: Standard 3-column layouts for template / provider / model selectors (`.editor-grid-3`), 2-column layouts for saved jobs / target pages (`.editor-grid-2`).
  - Tablet (`<= 860px`): `.editor-grid-3` collapses to single-column stacked format.
  - Mobile (`<= 640px`): `.editor-grid-2` collapses to single-column format. Workflow action buttons expand to full width (`width: 100%`) for easy touch accessibility. Container padding scales down to 10px-14px to maximize available space for textareas and content editors.
- **Drawer Navigation**:
  - Switching tabs via `showTab(id)` must strictly close the side menu drawer (`closeMenu()`), ensuring the drawer never covers the active editing surface.
- **Plan Card Headers**:
  - Part title inputs must maintain a `min-width: 200px` and wrap with status badges and action buttons across narrow viewports.
- **Merged Article Preview Containers**:
  - Any rendered HTML preview container must enforce `overflow-x: auto; max-width: 100%;` alongside `overflow-y: auto` to contain tables and code blocks cleanly.
