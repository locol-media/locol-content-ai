# Third-party notices

Locol Content AI is licensed under the GNU General Public License v3.0 — see
[LICENSE](./LICENSE) for the license text and [COPYRIGHT](./COPYRIGHT) for the
project's own copyright notice. This file records the third-party components distributed
**inside this repository** (vendored, not merely declared as dependencies), the
licenses they carry, and where each one sits in the tree.

Packages fetched at build time from npm (`FrontEnd/package-lock.json`) or PyPI
(`BackEnd/uv.lock`, `Web/uv.lock`) are not listed here; their licenses travel
with them in `node_modules/` and the resolved Python environment.

## A note on duplicated paths

`BackEnd/www/` is committed build output that mirrors `FrontEnd/src/`. Every
vendored file below therefore appears twice — once in the FrontEnd source tree
and once in the built assets that `BackEnd` serves. These are the same component,
not two, and each copy carries its own license file.

## Components

| Component | Version | License | Where |
|---|---|---|---|
| [Quill](https://quilljs.com/) | 2.0.2 | BSD-3-Clause | `FrontEnd/src/includes/vendor/`, `BackEnd/www/includes/vendor/` |
| [stencil-quill](https://github.com/KillerCodeMonkey/stencil-quill) | 11.0.0 | MIT | `FrontEnd/` — `src/components/`, and the project scaffolding |
| [Intro.js](https://introjs.com) | 7.2.0 | **AGPL-3.0**, or commercial | `FrontEnd/src/includes/`, `BackEnd/www/includes/` |

---

### Quill — BSD-3-Clause

Rich-text editor, vendored as a prebuilt bundle and stylesheet.

- Files: `quill.js`, `quill.snow.css`
- In: `FrontEnd/src/includes/vendor/` and `BackEnd/www/includes/vendor/`
- License text: [`FrontEnd/src/includes/vendor/quill.LICENSE`](./FrontEnd/src/includes/vendor/quill.LICENSE)
  (and the identical copy at `BackEnd/www/includes/vendor/quill.LICENSE`)

```
Copyright (c) 2017-2024, Slab
Copyright (c) 2014, Jason Chen
Copyright (c) 2013, salesforce.com
All rights reserved.
```

Redistribution in source and binary form is permitted under the three BSD
conditions; see the license file for the full terms and warranty disclaimer.

---

### stencil-quill — MIT

`FrontEnd/` began as a checkout of stencil-quill, a Stencil.js web-component
wrapper around Quill. The upstream component library under
`FrontEnd/src/components/` is unmodified, and much of the project scaffolding
(`package.json`, `.github/`, `VENDOR_README.md`) is still upstream's.

- License text: [`FrontEnd/LICENSE`](./FrontEnd/LICENSE)
- Upstream README, retained: [`FrontEnd/VENDOR_README.md`](./FrontEnd/VENDOR_README.md)

```
MIT License

Copyright (c) 2018 Bengt Weiße
```

Locol's own code in that folder — `src/index.html` and the Locol files in
`src/includes/` (`auth.js`, `dynamic-*`, `getting-started.js`, `grid-master.*`,
`prompt-window.*`, `quill-editor-window.js`) — is covered by this repository's
GPLv3 license, not by the MIT license above. The vendored Quill and Intro.js
files that also live under `src/includes/` are covered by their own licenses as
listed here.

---

### Intro.js — AGPL-3.0 (or a commercial license)

Guided product tour, used by `FrontEnd/src/includes/getting-started.js`.

- Files: `intro.min.js`, `introjs.min.css`
- In: `FrontEnd/src/includes/` and `BackEnd/www/includes/`
- License text: [`FrontEnd/src/includes/intro.LICENSE`](./FrontEnd/src/includes/intro.LICENSE)
  (and the identical copy at `BackEnd/www/includes/intro.LICENSE`) — this is
  upstream's own `license.md` from tag `v7.2.0`, verbatim: the dual-license
  statement followed by the full GNU AGPL-3.0 text.

```
Copyright (C) 2012-2023 Afshin Mehrabani (afshin.meh@gmail.com)
```

The minified bundle's banner states only the copyright, so the license is easy
to miss. It is **not** MIT. Upstream dual-licenses Intro.js from v2.0.0 onward:
AGPL-3.0, or a paid commercial license from introjs.com for projects that need
to keep their source proprietary.

**What this adds for a deployed instance.** GPLv3 §13 expressly permits
combining a GPLv3 work with AGPL-3.0 code, so this repository's license and
Intro.js are compatible and it may be distributed as it stands. But AGPL §13
then applies to the combination: users who interact with the running program
*remotely over a network* must be offered the Corresponding Source. Plain GPLv3
carries no such requirement — Intro.js is what brings it in.

In practice, for anyone hosting this application: make the source available to
your users, for example by linking this repository from the running app's UI.
Publishing the repository is not by itself enough if your users cannot find it.
If that does not suit your deployment, the alternatives are to purchase the
Intro.js commercial license, or to replace it with a permissively licensed tour
library.
