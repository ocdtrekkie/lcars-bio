# LCARS Personnel Archive

A small Flask app for one Star Trek simming character per Sandstorm grain.
No database, JavaScript, CDNs, external fonts, remote services, or accounts.

## Features
- Rank, species, age, height, weight, name, pronouns, birthplace, position and assignment.
- Physical description, family members, personality, history, service record and notes.
- Responsive LCARS-inspired interface, labels, keyboard focus indicators and read-only sharing.
- Gallery of up to 24 character images. The first image is the primary portrait.
- JSON export (image metadata only; not image bytes).
- CSRF-protected changes, atomic JSON replacement, process file locks and stale-edit rejection.
- Actual image decoding, safe random filenames, 12 MiB request cap, 20-megapixel limit,
  resizing and JPEG re-encoding without original metadata. Animated images use their first frame;
  transparency is not retained. A caption supplies the alternative text.

## Local development (Linux / Python 3.11+)

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python app.py

Open http://127.0.0.1:8000 . Data is created in ./data. Set BIO_DATA_DIR to change it.
Local mode intentionally allows editing without authentication; bind only to loopback.
For a non-Sandstorm production deployment, add authentication and HTTPS separately.
The dependency ranges are not a lockfile: resolve, audit and pin dependencies for a release.

## Sandstorm packaging (raw spk workflow)

This archive is SOURCE, not a prebuilt or signed .spk. You need a Linux Sandstorm
build host with spk, Python 3.11+, and network access during dependency installation.
No internet access is needed by the resulting grain.

1. Place this project at /opt/lcars-bio on the build host. Do not copy local ./data.
   For example, create that directory with appropriate ownership and extract the project there.
2. From /opt/lcars-bio:

       python3 -m venv .venv
       .venv/bin/pip install -r requirements.txt
       chmod +x start.sh
       spk init -p 8000 -- /bin/sh /opt/lcars-bio/start.sh

3. Edit the generated sandstorm-pkgdef.capnp. Set the generated app title/default
   title to "LCARS Personnel Archive". Merge the viewInfo fragment from
   sandstorm-roles.capnp.txt into the existing bridgeConfig, preserving its other fields.
   This defines edit permission plus Editor and Viewer sharing roles. Without it,
   Sandstorm mode deliberately denies all writes, including owner writes.
4. In the generated sourceMap, add these package-root-relative entries to
   alwaysInclude (preserving existing entries):

       "opt/lcars-bio/app.py",
       "opt/lcars-bio/start.sh",
       "opt/lcars-bio/templates",
       "opt/lcars-bio/static",
       "opt/lcars-bio/.venv"

   Also include the base Python standard library for your installed interpreter,
   e.g. "usr/lib/python3.11" (verify the actual path on your build host).
   Inspect the generated mappings so /opt/lcars-bio resolves to the project on
   your host. Do not include data/, signing keys, caches or development secrets.
5. Run `spk dev`. Create a grain and exercise every route: save a bio, upload each
   supported image format, view images, delete an image, trigger errors, export JSON,
   and open shares as both Viewer and Editor. Check that Viewer writes get HTTP 403.
   This runtime exercise is important because spk traces dependencies.
6. Stop dev mode. Inspect sandstorm-files.list for missing dependencies or private
   host files. Then run:

       spk pack lcars-personnel.spk

7. Install through your Sandstorm server's /install page and repeat the smoke tests
   on the packed app. Keep the generated app ID and private signing key secure for updates.

start.sh sets SANDSTORM=1, HOME=/var and BIO_DATA_DIR=/var/lcars-bio, and runs
Gunicorn on loopback port 8000. Sandstorm provides the HTTP bridge and authentication.
Only trust the X-Sandstorm-Permissions header inside a Sandstorm grain; never expose
this server directly to an untrusted network with header-based permissions enabled.
The CSP intentionally allows Sandstorm embedding (it does not set frame-ancestors).

## Storage and behavior

/var/lcars-bio/character.json holds a version, revision, character field dictionary,
and images list. Uploaded bytes live in /var/lcars-bio/images/. The session signing
secret and advisory lock live alongside the JSON. There is exactly one biography.
Family and service record are free-form multiline fields, not separate relational tables.
Height, weight and age are strings so different units and fictional species are supported.

Changes are explicit: save text before adding or removing images, as either action
reloads the page. Conflicting text saves return 409 instead of overwriting a newer edit.
The error page does not retain unsaved form contents; use browser Back and copy the
text before refreshing. Invalid JSON fails loudly rather than overwriting a damaged file.
JSON replacement is atomic, but images and JSON are not one filesystem transaction;
an abrupt crash can leave an orphan image, which can be cleaned up administratively.

Use Sandstorm grain backups for a full backup including images. JSON export alone is
not a full backup and there is no JSON import feature. Do not manually modify the JSON
while the grain is running. There is no automatic history, account system or autosave.

## Tests

    .venv/bin/python -m unittest discover -s tests -v

These use Flask's test client, temporary storage, and in-memory generated images.
They do not verify Sandstorm packaging or real-browser rendering.

Unofficial fan project; no affiliation with Star Trek rights holders. No proprietary
LCARS graphics, logos or fonts are bundled. Ensure you can use any images you upload.
