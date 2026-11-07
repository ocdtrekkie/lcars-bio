import io
import json
import os
import secrets
import tempfile
import warnings
from contextlib import contextmanager
from pathlib import Path
import fcntl
from flask import Flask, abort, flash, redirect, render_template, request, send_file, send_from_directory, session, url_for
from PIL import Image, ImageOps, UnidentifiedImageError
import subprocess
from urllib.parse import urlsplit

FIELDS = {
    "Identity": [
        ("name", "Full name"),
        ("rank", "Rank"),
        ("position", "Position / department"),
        ("assignment", "Ship / station / simm"),
        ("species", "Species"),
        ("pronouns", "Pronouns"),
        ("age", "Age"),
        ("birthplace", "Birthplace"),
        ("height", "Height (include units)"),
        ("weight", "Weight (include units)"),
        ("hair_color", "Hair color"),
        ("eye_color", "Eye color"),
    ],
    "Biography": [
        ("physical_description", "Physical description"),
        ("family", "Family members"),
        ("personality", "Personality"),
        ("history", "Personal history"),
        ("service_record", "Service record"),
        ("notes", "Simming notes"),
    ],
}
KEYS = [key for group in FIELDS.values() for key, _ in group]
DATA = Path(os.environ.get("BIO_DATA_DIR", "./data")).resolve()
DATA.mkdir(parents=True, exist_ok=True)
UPLOADS = DATA / "images"
UPLOADS.mkdir(exist_ok=True)
SECRET = DATA / "session-secret"
APP_DIR = Path(__file__).resolve().parent

PUBLIC_DIR = Path(
    os.environ.get("BIO_PUBLIC_DIR", "/var/www")
)
PUBLIC_URL_FILE = DATA / "public-url"

GET_PUBLIC_ID = Path(
    os.environ.get(
        "GET_PUBLIC_ID",
        str(APP_DIR / "sandstorm-integration" / "getPublicId"),
    )
)
try:
    fd = os.open(SECRET, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    pass
else:
    with os.fdopen(fd, 'w') as out:
        out.write(secrets.token_hex(32))
app = Flask(__name__)
app.config.update(SECRET_KEY=SECRET.read_text(), MAX_CONTENT_LENGTH=12 * 1024 * 1024,
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
Image.MAX_IMAGE_PIXELS = 20_000_000
SANDSTORM = os.environ.get('SANDSTORM') == '1'

@contextmanager
def locked():
    with (DATA / 'character.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield

def load():
    path = DATA / 'character.json'
    if not path.exists():
        return dict(version=1, revision=0, character={k: '' for k in KEYS}, images=[])
    return json.loads(path.read_text(encoding='utf-8'))

def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}-",
    )
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())

        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def save(doc):
    current = DATA / "character.json"

    # Preserve the exact previous file before replacing it.
    if current.exists():
        previous_bytes = current.read_bytes()
        previous = json.loads(previous_bytes.decode("utf-8"))
        revision = previous["revision"]
        archive = DATA / f"character.rev-{revision:06d}.json"

        if archive.exists():
            # A previous attempt may have archived successfully but failed
            # before replacing character.json. Allow that retry, but never
            # overwrite an archive containing different data.
            if archive.read_bytes() != previous_bytes:
                raise RuntimeError(
                    f"Refusing to overwrite a different archive: {archive.name}"
                )
        else:
            atomic_write(archive, previous_bytes)

    updated = {**doc, "revision": doc["revision"] + 1}
    payload = json.dumps(
        updated,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    atomic_write(current, payload)
    doc["revision"] = updated["revision"]

def public_url():
    if not PUBLIC_URL_FILE.exists():
        return None

    return PUBLIC_URL_FILE.read_text(encoding="utf-8").strip() or None


def publish_snapshot(doc):
    """Caller must hold locked(). Publish only explicitly allowed files."""
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    public_images = PUBLIC_DIR / "images"
    public_images.mkdir(exist_ok=True)

    # Prepare everything before changing the published snapshot.
    image_payloads = {}

    for image in doc["images"]:
        filename = image["filename"]

        # Never allow JSON filenames to escape the image directory.
        if (
            not filename
            or Path(filename).name != filename
            or "/" in filename
            or "\\" in filename
            or not filename.endswith(".jpg")
        ):
            raise ValueError("Invalid image filename in character record.")

        image_payloads[filename] = (UPLOADS / filename).read_bytes()

    stylesheet = (APP_DIR / "static" / "lcars.css").read_bytes()

    json_payload = json.dumps(
        doc,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    html_payload = render_template(
        "public.html",
        doc=doc,
        fields=FIELDS,
    ).encode("utf-8")

    # Publish assets first, then the documents referring to them.
    for filename, content in image_payloads.items():
        atomic_write(public_images / filename, content)

    atomic_write(PUBLIC_DIR / "lcars.css", stylesheet)
    atomic_write(PUBLIC_DIR / "character.json", json_payload)
    atomic_write(PUBLIC_DIR / "index.html", html_payload)

    # Remove previously published images no longer in the current record.
    for path in public_images.iterdir():
        if path.is_file() and path.name not in image_payloads:
            path.unlink()

def editable():
    return not SANDSTORM or 'edit' in {p.strip() for p in request.headers.get('X-Sandstorm-Permissions', '').split(',')}

def token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(32)
    return session['csrf']
app.jinja_env.globals['csrf_token'] = token

@app.before_request
def protect():
    if request.method == 'POST':
        if not editable():
            abort(403)
        actual = request.form.get('csrf', '')
        if not actual or not secrets.compare_digest(actual, session.get('csrf', '')):
            abort(400, 'Invalid form token. Reload the page and try again.')

@app.after_request
def headers(response):
    if request.method == "POST" and response.status_code < 400:
        try:
            with locked():
                if public_url():
                    publish_snapshot(load())
        except Exception:
            app.logger.exception(
                "The change was saved, but static publishing failed"
            )
            response = app.make_response((
                render_template(
                    "error.html",
                    message=(
                        "Your change was saved, but the public biography "
                        "could not be refreshed. The public page may still "
                        "show an older version. Return to the record and "
                        "save again to retry."
                    ),
                ),
                503,
            ))

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self'; style-src 'self'; "
        "script-src 'none'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'"
    )
    response.headers["Cache-Control"] = "no-store"
    return response

@app.get("/")
def index():
    with locked():
        doc = load()
        published_url = public_url()

    return render_template(
        "index.html",
        doc=doc,
        fields=FIELDS,
        can_edit=editable(),
        published_url=published_url,
    )

@app.post('/save')
def update():
    with locked():
        doc = load()
        if request.form.get('revision') != str(doc['revision']):
            abort(409, 'This biography changed in another tab. Copy your changes, reload, and try again.')
        for key in KEYS:
            value = request.form.get(key, '').strip()
            if len(value) > 50000:
                abort(400, 'A field exceeds 50,000 characters.')
            doc['character'][key] = value
        save(doc)
    flash('Personnel record saved.')
    return redirect(url_for('index'))

@app.post('/images')
def upload():
    photo = request.files.get('photo')
    if not photo or not photo.filename:
        abort(400, 'Choose an image first.')
    caption = request.form.get('caption', '').strip()
    if len(caption) > 200:
        abort(400, 'Caption must be at most 200 characters.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(photo.stream) as original:
                if original.format not in {'JPEG', 'PNG', 'WEBP'}:
                    abort(400, 'Use a JPEG, PNG, or WebP image.')
                original.load()
                image = ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((2400, 2400))
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=90)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        abort(400, 'Invalid image or image exceeds the 20-megapixel safety limit.')
    filename = secrets.token_hex(16) + '.jpg'
    with locked():
        doc = load()
        if len(doc['images']) >= 24:
            abort(400, 'Maximum 24 images per character. Remove an image first.')
        path = UPLOADS / filename
        path.write_bytes(output.getvalue())
        doc['images'].append({'filename': filename, 'caption': caption})
        try:
            save(doc)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    flash('Image added. Biography fields are saved separately.')
    return redirect(url_for('index', _anchor='gallery'))

@app.get('/images/<filename>')
def image_file(filename):
    with locked():
        if filename not in {i['filename'] for i in load()['images']}:
            abort(404)
    return send_from_directory(UPLOADS, filename, mimetype='image/jpeg')

@app.post('/images/<filename>/delete')
def delete_image(filename):
    with locked():
        doc = load()
        if filename not in {i['filename'] for i in doc['images']}:
            abort(404)
        doc['images'] = [i for i in doc['images'] if i['filename'] != filename]
        save(doc)
        (UPLOADS / filename).unlink(missing_ok=True)
    flash('Image removed.')
    return redirect(url_for('index', _anchor='gallery'))

@app.get('/export')
def export():
    with locked():
        payload = json.dumps(load(), ensure_ascii=False, indent=2).encode('utf-8')
    return send_file(io.BytesIO(payload), mimetype='application/json', as_attachment=True, download_name='character.json')

@app.post("/publish")
def enable_publishing():
    if not SANDSTORM:
        abort(400, "Static publishing must be enabled from a Sandstorm grain.")

    session_id = request.headers.get("X-Sandstorm-Session-Id")
    if not session_id:
        abort(400, "Sandstorm did not provide a session ID.")

    try:
        result = subprocess.run(
            [str(GET_PUBLIC_ID), session_id],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (
        OSError,
        subprocess.SubprocessError,
        UnicodeError,
    ):
        app.logger.exception("Could not obtain the public URL")
        abort(503, "Could not enable publishing. Please try again.")

    lines = result.stdout.splitlines()
    if len(lines) < 3:
        abort(503, "The publishing helper returned an unexpected response.")

    url = lines[2].strip()
    parsed = urlsplit(url)

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        abort(503, "The publishing helper returned an invalid public URL.")

    # Persist the URL only after the first snapshot has been generated.
    with locked():
        publish_snapshot(load())
        atomic_write(PUBLIC_URL_FILE, url.encode("utf-8"))

    flash("Publishing enabled. Future changes will update the public biography.")
    return redirect(url_for("index"))

@app.errorhandler(413)
def too_large(error):
    return render_template('error.html', message='Request too large. Upload one image smaller than 12 MiB.'), 413

@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(409)
def expected_error(error):
    return render_template('error.html', message=error.description), error.code

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8000)
