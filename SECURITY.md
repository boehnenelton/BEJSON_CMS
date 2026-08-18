# Security Policy

## Reporting a Vulnerability

Report vulnerabilities to boehnenelton2024@gmail.com. Do not open a public
issue for unpatched security problems.

## Known operational hardening notes

- All admin routes require authentication via `CMS_PASSWORD`. It defaults to
  `changeme` — set a real value via the `CMS_SECRET_KEY`/`CMS_PASSWORD`
  environment variables before exposing any service beyond `127.0.0.1`. A
  startup banner and a persistent dashboard alert both fire whenever the
  default is still in use.
- Standalone-app ZIP imports are guarded against decompression-bomb style
  attacks: total uncompressed size is checked from the ZIP's own central
  directory (`zipfile.ZipInfo.file_size`) before any extraction happens,
  capped at 300MB.
- `pydroid_start.py` invokes `termux-open-url` via `subprocess.run()` with an
  argument list (no shell string interpolation) — do not reintroduce
  `os.system()`/shell-string patterns for any subprocess call that could ever
  carry user-influenced input.
- Path handling for asset/app serving routes goes through
  `lib_bejson_Core_bejson_path_guard.py` — do not bypass it with raw
  `open()`/`send_file()` calls built from unvalidated request input.
