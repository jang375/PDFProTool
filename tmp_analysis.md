# 1. Understanding the problem
- User reported that editing text in a PDF makes it bold and lose its original formatting.
- `pdf_viewer.py` handles text edit via `_commit_text_edit`.
- `_commit_text_edit` extracts the font via `_extract_embedded_font` which falls back to `_map_to_fitz_font`.
- Formatting (bold/italic) is determined entirely by parsing the font name string `line_info["font"]` or `real_family` using string matching (e.g., `"bold" in lower`).
- `apply_redactions` is used to remove the old text before `insert_text` is called.

# 2. Hypothesis for "Bold" issue
A. **Double rendering (Overlay)**: If `page.apply_redactions(...)` fails to remove the original text (e.g., due to slight bbox mismatch or font rendering issues), drawing the new text over the exact same spot will create an anti-aliased overlap that looks "bold" and messy.
B. **Incorrect Weight via System Font**: If `_extract_embedded_font` returns `None` (or returns a generic name), `_map_to_fitz_font` is called. If the fallback logic incorrectly defaults to `malgunbd.ttf` (Malgun Gothic Bold) or another bold font due to a logic flaw (for instance, failing to parse weight properly), the text will legitimately be bold.
C. **Loss of Original Formatting**: `_get_text_lines_for_page` strictly queries `first_span.get("font", "")` but Ignores `first_span.get("flags", 0)`. The `flags` attribute contains the true bitmask for superscipt, italic, monospace, serifed, and BOLD. Ignoring this means we rely purely on the font name, which might just be "MalgunGothic" without weight suffix!

# 3. Code Inspection (`pdf_viewer.py`)
In `_get_text_lines_for_page`:
```python
                    "font": first_span.get("font", ""),
                    "size": first_span.get("size", 12),
                    "color": first_span.get("color", 0),
                    "flags": first_span.get("flags", 0), # We should ADD this
```
And in `_commit_text_edit`:
```python
            font_size = line_info["size"]
            flags = line_info.get("flags", 0)
            is_bold = bool(flags & 16)
            is_italic = bool(flags & 2)
```
Then pass `is_bold` and `is_italic` to `_extract_embedded_font` and `_map_to_fitz_font` so that even if the font name doesn't contain "bold", the text is correctly matched to a bold system font.

Wait, if it DEFAULTS to bold, maybe we are mistakenly assuming it's bold? 
No, the user complains: "볼드처리 되고" which implies it *becomes* bold, meaning it *wasn't* bold originally, but our code makes it bold.
If our code makes it bold incorrectly, it must be because A) duplicate overlay, OR B) `_map_to_fitz_font` mistakenly selects `malgunbd.ttf`.

Look at `_map_to_fitz_font` in `pdf_viewer.py`:
```python
            is_bold = "bold" in lower or "heavy" in lower or "black" in lower
```
If `is_bold` is False, it falls back to `default_file = "malgun.ttf"`.
So it shouldn't mathematically select bold unless the word "bold" is in the name. Thus, B) is unlikely to cause an *incorrect* bolding trend.

The most probable culprit for "becomes bold" is A) the old text is NOT being removed by `apply_redactions`.
Let's check `apply_redactions`:
```python
            cover_rect = fitz.Rect(
                bbox.x0 - 0.5, bbox.y0 - 0.5,
                bbox.x1 + 0.5, bbox.y1 + 0.5,
            )
            page.add_redact_annot(cover_rect)
            page.apply_redactions(images=0, graphics=0, text=0)
```
Wait, PyMuPDF documentation for `apply_redactions`:
If `apply_redactions` removes the text, does it work reliably? Yes, usually.
But wait! What if the bbox is slightly off? `apply_redactions` only removes text that intersects the redaction rect. `cover_rect` is expanded by 0.5.
What if `text=0` is default?
Actually, wait:
```python
page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_IMAGE_NONE)
```
Wait, `text=0`? PyMuPDF enum for `fitz.PDF_REDACT_TEXT_REMOVE` is actually 0. Wait, `PDF_REDACT_TEXT_REMOVE` = ? We should not pass undocumented integers if we can avoid it.
Actually, if the text isn't removed, it's overlay.

Let's test this in Python.
