# License Policy

## Project License

Invoice Sorter source code and project documentation are licensed under the
**BSD 2-Clause License**. The complete terms are in [LICENSE](LICENSE).

The SPDX identifier is:

```text
BSD-2-Clause
```

The license applies to repository content unless a file or directory contains a
more specific notice.

## Third-Party Software

Third-party packages retain their own copyright and license terms. Direct
dependencies and optional extras are summarized in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Installed environments may
contain additional transitive dependencies; their package metadata and upstream
license files remain authoritative.

The project does not vendor dependency source code or model weights in this
repository. Docling and OCR/model components can download or install separate
artifacts whose terms must be reviewed by distributors of bundled applications.

## Distribution Responsibilities

When redistributing source code, retain the BSD-2-Clause notice in `LICENSE`.
When distributing binaries, applications, or bundled environments:

1. Include the project license.
2. Include applicable third-party notices and license texts.
3. Review the exact resolved dependency set, including transitive packages.
4. Review optional GUI, OCR, Docling, and model licenses for the distributed
   configuration.
5. Regenerate dependency/SBOM evidence for each release.

## Contributions and AI Assistance

Unless a separate written agreement says otherwise, contributions intentionally
submitted for inclusion in this project are provided under the project's
BSD-2-Clause license. Contributors must submit only material they are authorized
to contribute and must preserve applicable notices.

AI-assisted development does not remove the requirement to review code for
correctness, security, public-code similarity, and license obligations.
Repository-specific provenance notes are in
[CONTENT_PROVENANCE.md](CONTENT_PROVENANCE.md).

This document describes repository policy and is not legal advice.
