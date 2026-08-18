# Contributing

This is a personal project (Elton Boehnen's own CMS for his BEJSON/MFDB
ecosystem), but contributions and bug reports under the terms below are
welcome.

## Bug Reports

Include: which app/route was involved (e.g. `BEJSON_CMS_Content.py:/edit/<uuid>`),
exact reproduction steps, and — where possible — whether the bug reproduces
via the real Flask test client / a real running instance, not just static
reading of the code. This project's own history shows several bugs that
looked plausible on paper but didn't reproduce under real execution, and
vice versa; a concrete repro saves a lot of back-and-forth.

## Feature Requests

Open with the specific route/entity/workflow affected and the desired
behavior. Check `docs/architecture.md` first — some apparent gaps (e.g. "no
join syntax between entities") are deliberate MFDB design choices, not
omissions.

## Noncommercial Contribution Terms

Contributions are accepted under the same PolyForm Noncommercial 1.0.0 terms
as the rest of the project. By contributing you agree your changes may be
distributed under that license.
