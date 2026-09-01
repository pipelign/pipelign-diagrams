# Third-party software notices

The original `pipelign-diagrams` service code is licensed separately under the
Apache License 2.0; see `LICENSE` and `NOTICE`. The service contains and installs
third-party software, and those components remain under their own licenses. This
file is an inventory aid, not legal advice and not a replacement for the license
texts shipped with the components.

The exact dependency set can change when the image is rebuilt because the base
images and Debian packages are not pinned to immutable digests. Generate an SBOM
for the image being distributed and review it together with these notices.

## Direct rendering and runtime components

| Component | How it is used | License | License/source information in the image |
| --- | --- | --- | --- |
| PlantUML 1.2026.2 | The bundled, unmodified JAR renders PlantUML source. | GPL-3.0-or-later | `/app/plantuml/license.txt`, `/app/plantuml/license-GPL.txt`, and the [corresponding source tag](https://github.com/plantuml/plantuml/tree/v1.2026.2) |
| Mermaid CLI 11.16.0 | `mmdc` renders Mermaid source with Chromium. | MIT | `/opt/mermaid-cli/lib/node_modules/@mermaid-js/mermaid-cli/LICENSE` and the [source repository](https://github.com/mermaid-js/mermaid-cli) |
| Chromium | Headless browser used by Mermaid CLI. | Multiple open-source licenses | `/usr/share/doc/chromium/copyright` and the Debian package/source metadata recorded in the SBOM |
| Graphviz | Layout engine used by PlantUML diagrams that require `dot`. | EPL-1.0 and MIT-covered portions | `/usr/share/doc/graphviz/copyright` and the Debian package/source metadata recorded in the SBOM |
| OpenJDK 17 runtime | Runs the PlantUML JAR. | GPL-2.0 with the Classpath Exception, plus third-party licenses | `/usr/share/doc/openjdk-17-jre-headless/copyright` and the Debian package/source metadata recorded in the SBOM |
| Node.js 22 | Runs Mermaid CLI. | MIT, plus licenses for bundled third-party software | `/usr/share/licenses/node/LICENSE` and the [Node.js source repository](https://github.com/nodejs/node) |
| Python 3.11 | Runs the API service. | Python Software Foundation License, plus bundled third-party licenses | `/usr/local/lib/python3.11/LICENSE.txt` and the [CPython source repository](https://github.com/python/cpython) |
| uv 0.11.14 | Installs locked Python dependencies and launches the service. | Apache-2.0 OR MIT; this distribution elects the MIT option | `/usr/share/licenses/uv/LICENSE-MIT` and the [corresponding source tag](https://github.com/astral-sh/uv/tree/0.11.14) |

The bundled PlantUML JAR has this SHA-256 digest:

```text
3cdce52133c424dea22425b947ae9d47f2167b0866dfcf99e714d4ea1689975c
```

PlantUML's included notice states that images produced by PlantUML are not
covered by PlantUML's GPL merely because PlantUML rendered them. The source text
of a diagram may, of course, have its own license.

## Transitive dependencies

Python package metadata is retained under `/app/.venv/lib/python3.11/site-packages`.
Node package metadata and license files are retained under
`/opt/mermaid-cli/lib/node_modules`. Debian package copyright files are retained
under `/usr/share/doc`.

For a machine-readable inventory, build the exact image and run:

```bash
./scripts/generate-sbom.sh pipelign-diagrams:local
```

The report is written to `build/pipelign-diagrams.spdx.json` by default. Entries
reported as `NOASSERTION` or `NONE` need manual review; an automated SBOM is not
by itself a license-compliance determination.

## Distribution note

The PlantUML binary is distributed under the GNU GPL and therefore carries
source-code availability obligations when the image is distributed. The source
tag above identifies the exact upstream release bundled here. Anyone distributing
the container should ensure that their distribution method satisfies the GPL's
corresponding-source requirements rather than relying on this notice alone.
