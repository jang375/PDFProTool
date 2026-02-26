# PDF Pro Tool — Windows Edition

macOS Swift/SwiftUI 버전을 **Python + PyQt6 + PyMuPDF + EasyOCR** 로 변환한 Windows 버전입니다.

---

## 기술 스택 비교

| 항목 | macOS 원본 | Windows 변환 |
|------|-----------|-------------|
| UI 프레임워크 | SwiftUI | **PyQt6** |
| PDF 렌더링/편집 | PDFKit | **PyMuPDF (fitz)** |
| OCR 엔진 | Apple Vision | **EasyOCR** |
| 파일 다이얼로그 | NSOpenPanel / NSSavePanel | **QFileDialog** |
| 커스텀 뷰 | NSViewRepresentable | **QPainter + QScrollArea** |
| 언어 | Swift | **Python 3.10+** |

---

## 설치 방법

### 1. Python 설치
Python 3.10 이상이 필요합니다: https://python.org

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

> **참고**: EasyOCR은 첫 실행 시 언어 모델을 자동 다운로드합니다 (~500MB).  
> 한국어 OCR은 `ko` 모델을 사용합니다.

### 3. 실행
```bash
python main.py
```

또는 PDF 파일을 직접 열어서 실행:
```bash
python main.py document.pdf
```

---

## 기능 목록

| 기능 | 상태 |
|------|------|
| 멀티탭 PDF 뷰어 | ✅ |
| 연속 스크롤 (Continuous Scroll) | ✅ |
| 확대/축소 (Ctrl+Scroll) | ✅ |
| 썸네일 사이드바 | ✅ |
| 북마크 | ✅ |
| 목차(Outline) | ✅ |
| 텍스트 주석 추가/편집/삭제 | ✅ |
| 이미지 직인(Stamp) 추가 | ✅ |
| 주석 드래그&리사이즈 | ✅ |
| 주석 더블클릭 인라인 편집 | ✅ |
| 텍스트 검색 | ✅ |
| 페이지 삭제/회전 | ✅ |
| PDF 합치기 | ✅ |
| PDF 분할 | ✅ |
| 페이지 삽입 | ✅ |
| 저장 / 다른 이름으로 저장 | ✅ |
| OCR (한국어, 영어, 일본어, 중국어) | ✅ |
| 드래그 앤 드롭으로 파일 열기 | ✅ |
| 다크 모드 | 🔜 (향후 추가) |

---

## OCR 언어 지원

| macOS Vision | EasyOCR |
|-------------|---------|
| `ko-KR + en-US` | `['ko', 'en']` |
| `en-US` | `['en']` |
| `ja-JP + en-US` | `['ja', 'en']` |
| `zh-Hans + en-US` | `['ch_sim', 'en']` |

---

## 파일 구조

```
PDFProTool_Windows/
├── main.py              # 앱 진입점
├── main_window.py       # 메인 윈도우 (ContentView + PDFProToolApp)
├── pdf_viewer.py        # PDF 렌더링 위젯 (EnhancedPDFView)
├── sidebar.py           # 사이드바 패널 (SidebarView)
├── panels.py            # 우측 패널 (PanelsView)
├── ocr_manager.py       # OCR 관리자 (OCRManager)
├── models.py            # 데이터 모델 (Models.swift)
├── requirements.txt     # 의존성
└── README.md
```

---

## 주요 변환 포인트

### OCR: Apple Vision → EasyOCR
```swift
// macOS Swift (Vision)
let request = VNRecognizeTextRequest { ... }
request.recognitionLanguages = ["ko-KR", "en-US"]
```
```python
# Windows Python (EasyOCR)
import easyocr
reader = easyocr.Reader(['ko', 'en'], gpu=False)
results = reader.readtext(image_bytes, detail=0, paragraph=True)
```

### PDF 렌더링: PDFKit → PyMuPDF
```swift
// macOS Swift (PDFKit)
page.draw(with: .mediaBox, to: ctx)
```
```python
# Windows Python (PyMuPDF)
mat = fitz.Matrix(zoom, zoom)
pix = page.get_pixmap(matrix=mat, alpha=False)
img = QImage(pix.samples, pix.width, pix.height, ...)
```

### 주석 추가: PDFAnnotation → fitz.Annot
```swift
// macOS Swift
let annot = PDFAnnotation(bounds: rect, forType: .freeText, ...)
annot.contents = text
page.addAnnotation(annot)
```
```python
# Windows Python (PyMuPDF)
annot = page.add_freetext_annot(
    rect=fitz.Rect(...),
    text=text,
    fontname="Helvetica",
    fontsize=14,
    text_color=(0, 0, 0)
)
```
