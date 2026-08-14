# Third-Party Software and Reference Register

Last reviewed: 2026-08-14

This register distinguishes incorporated software, planned runtime integrations, and design-only references. It is an engineering inventory, not legal advice. Platform terms of service, data rights, privacy, account authorization, robots policies, and rate limits require a separate compliance review.

## 1. Incorporated code baseline

### HotPush

- Project: https://github.com/JackyST0/hotpush
- Copyright: Copyright (c) 2025 JackyST0
- License: MIT License
- Baseline commit: `c9d6fce9213637ec0515fb806230e26c955c4031`
- Use: Primary code and Git-history baseline for this repository.
- Local notice: The upstream `LICENSE` file is retained at the repository root. Modified files remain subject to the MIT notice for substantial portions originating from HotPush.
- Engineering note: Existing FastAPI, Vue, auth, settings, scheduler, cache, database, trend UI, push channel and Docker foundations are retained where suitable. New hotspot-domain code should be original and attributable through Git history.

## 2. Planned Provider integrations

These projects are approved candidates, but Phase 0 does not copy or integrate their source code.

### NewsNow

- Project: https://github.com/ourongxing/newsnow
- Copyright: ourongxing and contributors
- License: MIT License
- Intended use: Hotspot data Provider for supported platforms.
- Integration rule: Prefer a documented/self-hosted API contract or a small original adapter. Do not copy an entire source tree. If source snippets or substantial portions are incorporated later, record the exact commit, files and preserved MIT notice here.
- Operational risk: Public instances may change, rate-limit or become unavailable. Availability must be established by Phase 2 real contract tests; failed collection must never be replaced with fabricated live data.

### DailyHotApi

- Project: https://github.com/imsyy/DailyHotApi
- Copyright: imsyy and contributors
- License: MIT License
- Intended use: Primary or fallback hotspot data Provider. Its documented source list includes Bilibili, Weibo and Douyin.
- Integration rule: Prefer API consumption or an original adapter. If source is incorporated, record exact provenance and retain the MIT notice.
- Operational risk: Platform responses and public instances may fail or change. A successful empty response, a transport failure and stale cached data must remain distinguishable.

### OpenCLI

- Project: https://github.com/jackwener/opencli
- License: Apache License 2.0
- Intended use: Isolated fallback Provider for platforms or views requiring a logged-in browser session.
- Current workspace artifact: `bin/autocli.exe` existed before the HotPush baseline was imported and remains untracked in Phase 0. It reports `autocli 0.3.8` and is from the earlier `nashsu/AutoCLI` lineage rather than a current OpenCLI release.
- Artifact provenance: The local executable is byte-identical to the executable inside the official `nashsu/AutoCLI` v0.3.8 `autocli-x86_64-pc-windows-msvc.zip` release. Local executable SHA-256: `F1BF52BD7AEA43FBC984F6CAEEDA3496B3CC2E518510E7F3F668BFE477F89758`. Release tag commit: `c0969e2c83b29a7528452b1ba555085deca8e00d`. Official archive SHA-256: `CD439179091B28A0C9E373D69E93D767E2DC1E0E61DFC6C0F45607C588E7C1D1`.
- Distribution status: Not approved for repository or release packaging. Phase 2 must decide whether to replace it with a supported OpenCLI release and must add the applicable Apache-2.0 LICENSE/NOTICE materials before distribution.
- Integration rule: Run out of process behind the Provider contract. Do not expose browser cookies, tokens, profiles or personal data to application logs. Retain Apache-2.0 license and NOTICE obligations for any distributed binary or source modification; document modified files when applicable.
- Operational risk: Browser login expiry, extension/daemon availability, platform anti-automation rules, account permissions and UI/API changes.

## 3. Design-only references — source code prohibited

### TrendRadar

- Project: https://github.com/sansan0/TrendRadar
- License: GNU General Public License v3.0
- Allowed use: Study publicly described architecture, product behavior, terminology and high-level ideas.
- Prohibited use: Do not copy, translate, port, adapt or incorporate its source code, configuration, prompts, templates, tests, assets or other copyrightable implementation into this commercial repository. Do not add it as a package, submodule, service, container image or runtime dependency.
- Clean-room rule: Requirements derived from product behavior must be written in this repository's own terms, followed by an original implementation without consulting GPL source during implementation. Git review should be able to show independent provenance.

### MediaCrawler

- Project: https://github.com/NanmiCoder/MediaCrawler
- License observed: Non-Commercial Learning License 1.1
- Allowed use: General learning about collection-system concerns at an architectural level.
- Prohibited use: No code, configuration, selectors, adapters, tests or assets may be copied or integrated. It must not be packaged, deployed, imported, invoked, added as a submodule, or used as a commercial runtime dependency.
- Reason: The license limits use to non-commercial learning/research and is incompatible with this commercial project's intended use.

## 4. Existing HotPush direct dependencies

The HotPush baseline currently declares the following direct dependencies. Exact transitive versions and licenses must be generated from lock files/container manifests before a production release.

### Python

| Dependency | Current declaration | Purpose | Review note |
| --- | --- | --- | --- |
| FastAPI | `>=0.109.0` | API framework | Permissive; pin and scan transitive dependencies |
| Uvicorn | `>=0.27.0` | ASGI server | Permissive; standard extras expand dependency set |
| Pydantic / pydantic-settings | `>=2.5.0` / `>=2.1.0` | schemas/config | Pin versions |
| feedparser | `>=6.0.10` | RSS parsing | Keep attribution in generated inventory |
| httpx | `>=0.26.0` | HTTP client | Pin versions |
| APScheduler | `>=3.10.4` | scheduling | Major-version behavior must be pinned |
| PyMySQL / cryptography | `>=1.1.0` / `>=42.0.0` | MySQL/TLS | cryptography includes native components |
| redis | `>=5.0.1` | optional cache/locks | Pin versions |
| python-dotenv | `>=1.0.0` | environment config | Avoid secrets in committed files |
| PyJWT / bcrypt | `>=2.8.0` / `>=4.0.0` | authentication | Security-sensitive; pin and scan |
| LiteLLM | `>=1.30.0` | model gateway | Large changing transitive surface; AI data egress review required |
| pytest / pytest-asyncio | `>=8.0.0` / `>=0.23.0` | tests | Development-only |

### JavaScript

| Dependency | Current declaration | Purpose |
| --- | --- | --- |
| Vue | `^3.4.0` | UI framework |
| Vue Router | `^4.2.5` | client routing |
| Pinia | `^2.1.7` | client state |
| Chart.js / vue-chartjs | `^4.5.1` / `^5.3.3` | trend charts |
| Vite / plugin-vue | `^5.0.0` | build tooling |
| Tailwind CSS / PostCSS / Autoprefixer | declared in `frontend/package.json` | styling/build |

### Container/runtime images

| Image/service | Current declaration | Risk/action |
| --- | --- | --- |
| MySQL | `mysql:8.0` | Pin digest for production; review Oracle image terms and bundled components |
| Redis | `redis:alpine` | Pin version and digest |
| RSSHub | `diygod/rsshub:chromium-bundled` | Large transitive/browser surface; review RSSHub license, route-specific behavior and platform terms; pin digest |
| Backend/frontend base images | Dockerfiles | Generate SBOM after versions are pinned |

## 5. Required release controls

- Preserve the repository-root HotPush MIT `LICENSE`.
- Record exact versions, commits and checksums for every incorporated Provider implementation or distributed binary.
- Generate Python, npm and container SBOM/license reports in Phase 11 and review unknown, copyleft, non-commercial and source-available entries.
- Do not vendor TrendRadar or MediaCrawler artifacts, including into test fixtures or generated code.
- Keep Provider responses and platform evidence factual. Cached data is labeled `stale`; failed live collection is reported as failed.
- Keep login-state Provider credentials outside source control, database plaintext, reports and logs.
- Re-review this file whenever a dependency, Provider, model gateway, container image or copied snippet is added.

## 6. Phase 0 security observations

`npm audit` against the inherited `frontend/package-lock.json` reported 6 vulnerabilities: 1 moderate and 5 high. Affected packages include Vite/esbuild, PostCSS, Rollup, nanoid and picomatch. These are inherited baseline dependencies, not accepted production risk. Upgrade them in a scoped change with build and regression tests; do not use a forced major-version audit fix without review.

The inherited Python test suite passes on Python 3.14.6 but emits deprecation warnings for Pydantic class-based settings config, Python's SQLite default datetime adapter and naive `datetime.utcnow()`. Track these before their respective removals become runtime failures.
