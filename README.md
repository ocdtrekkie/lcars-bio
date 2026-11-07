# LCARS Bio

This is a basic concept app for a Sandstorm-based roleplaying platform. Instead of a single
monolith, each player would own their own character sheets, which are individual grains and
use static web publishing to publish both a readable character page as well as a JSON version
of their character sheet. The JSON version could be pulled into a simm's roster or a fleet
management system, or multiple at the same time. Since the publicly-available web content is
static, this model isn't vulnerable to things like PHP exploits which move faster than the
roleplaying community can chase, and individual players can more easily retain and manage their
own work, even when it's part of a larger whole.

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

## Disclaimers

This is vibe coded AI slop. Buyer beware.

Unofficial fan project; no affiliation with Star Trek rights holders. No proprietary
LCARS graphics, logos or fonts are bundled. Ensure you can use any images you upload.
