# Cairo — the Arabic font used for PDF export

## Why this file is tracked

Every PDF export in this application contains Arabic: patient names, service
names, and the report titles themselves. reportlab embeds only the fonts it is
given, so without an Arabic-capable font here, exports come back as valid PDFs
with blank glyphs where the data should be — a silent failure (FE-016).

None of the font files that were already under `static/` contains a single
codepoint in the Arabic block. That included a `sourcesanspro/Cairo-Regular.ttf`
which, despite its name, was a **Latin-only subset of 215 codepoints** and could
not render Arabic. It and the dead `utils/export_pdf.py` that referenced it have
since been removed, so this directory is now the only Cairo in the repository —
there is no longer a same-named file to confuse it with.

## Provenance

| | |
|---|---|
| Family | Cairo |
| Source | <https://github.com/google/fonts/tree/main/ofl/cairo> (the canonical Google Fonts repository) |
| Upstream file | `Cairo[slnt,wght].ttf` — the variable font |
| Retrieved | 2026-09-09 |
| Size | 599,548 bytes |
| SHA-256 | `667c987182391c91f4e57a2f455b1794fb5e3ee6ca4ef3383e86bb690fa9c964` |
| Licence | SIL Open Font License 1.1 — see `OFL.txt` (SHA-256 `a4554e1799d42e1405924b61eb0e0722ae1623b1f1f07f995348f96c496362a9`) |
| Copyright | 2009 The Cairo Project Authors — <https://github.com/Gue3bara/Cairo> |

Renamed to `Cairo.ttf` rather than kept as `Cairo[slnt,wght].ttf`, because square
brackets in a filename are awkward in URLs and static paths. It is **not** renamed
to `Cairo-Regular.ttf`, even though reportlab reports that family name for the
default instance, because that would repeat exactly the naming confusion
described above.

Google Fonts publishes no static instances for Cairo — only the variable font.
reportlab registers it and embeds the default instance (weight 400, slant 0),
which is the Regular face.

Cairo was chosen over Noto Naskh Arabic because six templates already declare
`font-family: 'Cairo'`, so this keeps PDF and on-screen typography consistent.

## Verified coverage

`dashboard/test_exports.py` asserts this at test time rather than trusting it.
The check that matters is not "does the font have Arabic" but **"does it have a
glyph for every codepoint the shaping step actually emits"** — those are
different questions, and the second one failed at first.

`arabic_reshaper` maps letters onto Arabic Presentation Forms-B (U+FE70–FEFF).
Cairo covers 89 of those, but modern fonts implement *isolated* forms through
the base codepoint plus OpenType GSUB rather than duplicating them, so 17
codepoints the reshaper emitted by default had no glyph — `أ`, `ا`, `ب`, `ة`,
`ت`, `ج`, `د`, `ذ`, `ر`, `ط`, `ع`, `ل`, `م`, `ن`, `و`, `ي` in isolated position.
Configuring the reshaper with `use_unshaped_instead_of_isolated` leaves those as
their base codepoints, which Cairo does have, bringing missing glyphs to zero
across every string this application exports.

## Updating it

Replace both files from the same upstream path, update the size and hashes
above, and run `python manage.py test dashboard.test_exports`. The coverage test
will fail if the replacement cannot render the shaped output.
