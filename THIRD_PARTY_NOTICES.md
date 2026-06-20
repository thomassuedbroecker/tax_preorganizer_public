# Third-Party Notices

This project uses third-party Python packages. Each dependency remains governed
by its own license. This inventory covers direct dependencies declared in
`pyproject.toml`; it does not replace the license files distributed with those
packages.

Last reviewed: 2026-06-20.

| Dependency | Use | Declared license | Installation |
|---|---|---|---|
| PyYAML | YAML configuration | MIT | Core |
| python-dateutil | Date parsing | Apache-2.0 OR BSD-3-Clause | Core |
| Rich | CLI tables and formatting | MIT | Core |
| pdfplumber | PDF text extraction | MIT | `light` extra |
| pypdf | PDF text extraction | BSD-3-Clause | `light` extra |
| pytesseract | Tesseract integration | Apache-2.0 | `light` extra |
| Pillow | Image loading | MIT-CMU | `light` extra |
| Docling | Document extraction | MIT | `docling` extra |
| PySide6 | Desktop GUI | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only (community wheel metadata) | `gui` extra |
| python-docx | Planned DOCX output | MIT | `docx` extra |
| langgraph | In-app agent orchestration | MIT | `agent` extra |
| langchain-core | Agent message/model abstractions | MIT | `agent` extra |
| pydantic | Agent data validation | MIT | `agent` extra |
| pytest | Tests | MIT | `test` extra |

## Important Packaging Notes

- **PySide6 / Qt:** binary redistribution can trigger LGPL obligations, including
  notice, license-text, relinking/replacement, and source-offer considerations
  depending on how Qt is packaged. Commercial Qt for Python packages are a
  separately obtained distribution; installing the community `PySide6` wheel
  does not itself grant commercial-license terms. Review the exact Qt
  distribution before shipping a bundled desktop application. See the
  [official Qt licensing overview](https://doc.qt.io/qt-6/licensing.html) and
  [Qt for Python licensing details](https://doc.qt.io/qtforpython-6.8/licenses.html).
- **Docling and models:** Docling has transitive dependencies and can obtain
  model artifacts separately. Model and dataset terms are not implied by the
  Docling package license and must be reviewed independently before redistribution.
- **Ollama and local models:** Ollama is accessed as an external local service;
  neither its executable nor model weights are bundled by this project. Review
  the Ollama distribution and each selected model's separate terms before
  redistributing either one.
- **Tesseract:** the external Tesseract executable and language data are system
  components, not vendored here. Their own notices apply when bundled.
- **Pillow:** current upstream licensing identifies the PIL/Pillow terms as
  `MIT-CMU`; retain Pillow's complete upstream license text when bundling its
  wheel or native components.
- **Transitive dependencies:** create an SBOM or resolved license report from the
  release environment. This file intentionally does not claim completeness for
  packages introduced transitively.

Upstream package metadata and included license files are authoritative if this
summary conflicts with a dependency release.
