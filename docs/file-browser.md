# In-app file browser (pkg144)

**Why:** the browser's native file chooser backgrounds the app on Android and the OS kills it (the import freeze). The picker browses the filesystem from the Flask process instead, so the page stays in the foreground, and imports read the chosen paths straight from disk.

## Pieces
| File | Role |
|---|---|
| `src/web/BEJSON_CMS_FileBrowser.py` | Blueprint `/fb`: `/api/roots`, `/api/list`, `/api/thumb`, static assets; helpers `resolve_pick(s)`, `copy_file_chunked`, `PickedFile`, `parse_path_list` |
| `src/web/fb_assets/becss-filepicker.js/.css` | Modal picker (`CMSFilePicker.open`) + declarative `data-fb-pick` binder |
| Registered in | `BEJSON_CMS_Admin.py`, `BEJSON_CMS_PageEditor.py`, `BEJSON_CMS_PageEditorV2.py` (separate Flask apps) |

## Using it
```js
CMSFilePicker.open({kind: 'image', multiple: true}).then(r => r && CMSFilePicker.postJSON('/assets/import_server', {paths: r.paths, kind: 'image'}));
```
```html
<button type="button" data-fb-pick data-fb-kind="html" data-fb-multiple="1" data-fb-target="#htmlPaths" data-fb-summary="#fileList">Browse</button>
```
Server side: `resolve_pick(path, kind)` / `resolve_picks(paths, kind)` — never open a client-supplied path without it.

Kinds: `image video audio document media html zip app code markdown keys any`.

## Roots
Resolved at runtime (no hard-coded paths): `paths.json` (`INTERNAL_STORAGE`, `SD_CARD`, `ADMIN`, `PROJECT_ROOT`), `$EXTERNAL_STORAGE`, `$BEJSON_STORAGE_ROOT`, removable volumes under the OS mount boundary (`CMS_FILEBROWSER_STORAGE_MOUNTS`, default `/storage`), `$HOME`, the CMS project, and optional `config.json` row `filebrowser_roots`. In Termux run `termux-setup-storage` once.

## Env switches
`CMS_FILEBROWSER_ALLOW_REMOTE=1` (allow non-loopback clients), `CMS_FILEBROWSER_STORAGE_MOUNTS`, `BEJSON_PATHS_JSON`.

## Media Library sections
`/assets?type=images|video|audio|docs|youtube|links`.
