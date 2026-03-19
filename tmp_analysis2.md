# Analysis of the failure:
1. The user's screenshot shows the original text "쌍용어린이집" (top) is thinner / different font than the new text "쌍용어가린이집" (bottom).
2. Look at the logs:
```
INFO:text_edit:old='쌍용어린이집'  new='쌍용어가린이집'  same=False
INFO:text_edit:extract_font xref=697: basename='DEVEXP+ËÀ´' fname='DEVEXP+ËÀ´' sname='F1' real_family='ËÀ´' content_len=386324
INFO:text_edit:matched system font: {'fontname': 'malgun', 'fontfile': 'C:\\WINDOWS\\Fonts\\malgun.ttf'}
INFO:text_edit:font='\x14Õ´' flags=4 kwargs={'fontname': 'malgun', 'fontfile': 'C:\\WINDOWS\\Fonts\\malgun.ttf'}
```

3. `real_family='ËÀ´'` : The font name extracted from the PDF binary `name` table is corrupted or using an unknown encoding ('ËÀ´'). 
Consequently, `real_family` is not matched because it's garbage.
4. It falls back to `font='\x14Õ´'` (also garbage) with `flags=4` (bit 2 = 4, wait, bit 1 is 2, bit 2 is 4, bit 4 is 16).
Actually, `flags=4` means: 
Bit 0 (1): FixedPitch 
Bit 1 (2): Serif 
Bit 2 (4): Symbolic 
Bit 3 (8): Script 
Bit 5 (32): Nonsymbolic 
Bit 6 (64): Italic 
Bit 18 (262144): ForceBold 
Wait, I used `flags & 16` for bold! 
Let me check the PyMuPDF documentation for `flags`! 

I ran: `python -c "import fitz; ..."` but I didn't check `flags`.
According to PyMuPDF `font.flags`:
Bit 0: FixedPitch (1)
Bit 1: Serif (2)
Bit 2: Symbolic (4)
Bit 3: Script (8)
Bit 5: Nonsymbolic (32)
Bit 6: Italic (64)
Bit 18: ForceBold (262144) (wait, `2**18` is `262144`)
Wait! I previously used `flags & 16` and `flags & 2` for bold and italic! 
Where did I get `16` and `2`? 
TextSpan flags in PyMuPDF for `get_text("rawdict")` `span["flags"]`:
Wait... PyMuPDF span flags are DIFFERENT from font flags! 
Span flags are:
bit 0: superscript (1)
bit 1: italic (2)
bit 2: serifed (4)
bit 3: monospaced (8)
bit 4: bold (16)

The log says: `flags=4`. So it's serifed (4), NOT bold (16).
So `is_bold = bool(4 & 16) = False`, `is_italic = bool(4 & 2) = False`.
So the fallback `_map_to_fitz_font` is called with `is_bold=False`.
Inside `_map_to_fitz_font`, it determines it has Korean characters (`has_korean=True`), so it looks for a Korean fallback font since the original font name `'\x14Õ´'` is unrecognized.
Fallback Korean logic in `_map_to_fitz_font`:
```python
            # Default: Malgun Gothic with weight matching
            if is_bold:
                default_file = "malgunbd.ttf"
            elif is_light:
                default_file = "malgunsl.ttf"
            else:
                default_file = "malgun.ttf"
```
So it selects `malgun.ttf` (Malgun Gothic Regular).

Wait, "Malgun Gothic Regular" (`malgun.ttf`) IS What we used!
But the user's screenshot original document uses a SERIF font (e.g. 바탕체 Batang, 명조체 Myeongjo). 
Look closely at the screenshot! 
"①법인명(상호)" and "어린이집" in the top image have serifs (the little tails on strokes, especially noticeable on '법', '인', '상', '호').
The bottom image "쌍용어가린이집" uses Malgun Gothic (a sans-serif font, 맑은 고딕).
So the problem is NOT boldting! The problem is SANS-SERIF vs SERIF!

The font in the PDF has `flags=4` (bit 2: serifed = True).
But my fallback logic in `_map_to_fitz_font` defaults to Malgun Gothic (Sans-serif) for ALL Korean fonts if the name is unrecognized!

```python
            # Default: Malgun Gothic with weight matching
            if is_bold: ...
            else: default_file = "malgun.ttf"
```

To fix this, `_map_to_fitz_font` needs to know if the font `is_serif`, and if so, fallback to a SERIF Korean font like `batang.ttc` or `batang.ttf` (Batang = 바탕체) or `myeongjo` instead of `malgun.ttf`.

Let's double check if my `is_serif` reasoning is correct:
PyMuPDF span flags:
https://pymupdf.readthedocs.io/en/latest/recipes-text.html#how-to-analyze-font-characteristics
> flags: Bit 0 = superscript, Bit 1 = italic, Bit 2 = serifed, Bit 3 = monspaced, Bit 4 = bold.

Yes! `flags=4` means it IS serifed!

And how did I determine `is_bold`? `is_bold = bool(flags & 16)`.
And `is_serif = bool(flags & 4)`.

So I need to modify `pdf_viewer.py` again:
1. `is_serif = bool(flags & 4)`
2. Add `is_serif` to `_extract_embedded_font` and `_map_to_fitz_font` kwargs.
3. In `_map_to_fitz_font` fallback logic for CJK:
If `is_serif`: fallback to `batang.ttc`
Else: fallback to `malgun.ttf`

Also, look at `is_bold` fallback for Serif.
If `is_serif` and `is_bold`: unfortunately, standard Windows `batang.ttc` contains Batang, BatangChe, Gungsuh, GungsuhChe, but there is no explicit bold file for Batang (it uses algorithmic bold or maybe malgunbd?). Actually, `batang.ttc` usually includes regular only, but let's check. Defaulting to `batang.ttc` is still 100x better than Malgun.

Wait, the `real_family` extraction failed because of encoding.
`DEVEXP+ËÀ´` -> `ËÀ´` which is EUC-KR or CP949 decoded incorrectly as mac-roman or utf-16-be!
PDF binary `name` table:
Often pid=3, eid=1 (Windows, UCS-2).
But sometimes pid=1, eid=0 (Mac, MacRoman).
If the string `ËÀ´` actually represents "바탕" or something in EUC-KR... we can't easily guess. 
But using the `is_serif = bool(flags & 4)` fallback is a perfect heuristic!

Let's check `_commit_text_edit` line 2012:
```python
        flags = line_info.get("flags", 0)

        # PyMuPDF font flags: bit 4 (16) = bold, bit 1 (2) = italic, bit 2 (4) = serif
        is_bold = bool(flags & 16)
        is_italic = bool(flags & 2)
        is_serif = bool(flags & 4)
```

And in `_map_to_fitz_font` (line 2096):
```python
    @staticmethod
    def _map_to_fitz_font(original_font: str, text: str, is_bold: bool = False, is_italic: bool = False, is_serif: bool = False) -> dict:
```
```python
            # Default: Malgun Gothic or Batang with weight matching
            if is_serif:
                default_file = "batang.ttc"
                default_name = "batang"
            elif is_bold:
                default_file = "malgunbd.ttf"
                default_name = "malgunbd"
            elif is_light:
                default_file = "malgunsl.ttf"
                default_name = "malgunsl"
            else:
                default_file = "malgun.ttf"
                default_name = "malgun"

            path = os.path.join(fonts_dir, default_file)
            if os.path.exists(path):
                return {"fontname": default_name, "fontfile": path}

            # If the specific one wasn't found, try the fallback
            path = os.path.join(fonts_dir, "malgun.ttf")
            if os.path.exists(path):
                return {"fontname": "malgun", "fontfile": path}
```
