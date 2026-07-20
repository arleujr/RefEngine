# Optional portable Tesseract

RefEngine searches this folder for `tesseract.exe` before the standard Windows installation paths.

Expected structure:

```text
tools/
└── tesseract/
    ├── tesseract.exe
    └── tessdata/
        ├── eng.traineddata
        └── por.traineddata
```

Do not commit or redistribute third-party binaries without checking their license and source.
The standard Windows installation is also supported automatically.
