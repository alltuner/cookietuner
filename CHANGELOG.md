# Changelog

## [0.1.6](https://github.com/alltuner/cookietuner/compare/v0.1.5...v0.1.6) (2026-10-06)


### Miscellaneous Chores

* keep uv.lock version in sync on release ([#42](https://github.com/alltuner/cookietuner/issues/42)) ([2419aac](https://github.com/alltuner/cookietuner/commit/2419aac95eef66d0f13ccd346848e2b68c516776))

## [0.1.5](https://github.com/alltuner/cookietuner/compare/v0.1.4...v0.1.5) (2026-10-06)


### Features

* **site:** publish through the fleet's registry instead of GitHub Pages ([#36](https://github.com/alltuner/cookietuner/issues/36)) ([d77ceee](https://github.com/alltuner/cookietuner/commit/d77ceee87e52f4c4230e79249292fe25b733aa66))


### Miscellaneous Chores

* **deps:** update actions/checkout action to v7 ([#31](https://github.com/alltuner/cookietuner/issues/31)) ([bc460b0](https://github.com/alltuner/cookietuner/commit/bc460b097d7851f187b5c5f027af57d8bda19351))
* **deps:** update astral-sh/setup-uv action to v10 ([#35](https://github.com/alltuner/cookietuner/issues/35)) ([f976cb8](https://github.com/alltuner/cookietuner/commit/f976cb8654268a805b0812b5c5a05d4546eb126a))
* **deps:** update dependency uv_build to &gt;=0.12.23,&lt;0.13.0 ([#34](https://github.com/alltuner/cookietuner/issues/34)) ([8b45241](https://github.com/alltuner/cookietuner/commit/8b4524199b839162a26ced8c78b6d810ca580e2d))
* drop the GitHub Pages jobs from the release workflow ([#38](https://github.com/alltuner/cookietuner/issues/38)) ([9577649](https://github.com/alltuner/cookietuner/commit/9577649b590d2f344b9c78fc067c5caea6a569a1))
* refresh stale uv.lock ([#41](https://github.com/alltuner/cookietuner/issues/41)) ([7afd563](https://github.com/alltuner/cookietuner/commit/7afd563adb7c94fb7e7702a58fb878f276a9830d))
* use hello@alltuner.com as author email ([#39](https://github.com/alltuner/cookietuner/issues/39)) ([a2ea259](https://github.com/alltuner/cookietuner/commit/a2ea259dd3fde3f034b3af6a9a6c8e1ec7e81e90))


### CI/CD Changes

* skip claude-review on bot PRs ([#40](https://github.com/alltuner/cookietuner/issues/40)) ([3deb1f0](https://github.com/alltuner/cookietuner/commit/3deb1f0c48a315fe5ecae064c7609b6a721c6c9c))

## [0.1.4](https://github.com/alltuner/cookietuner/compare/v0.1.3...v0.1.4) (2026-05-04)


### Miscellaneous Chores

* **deps:** update actions/configure-pages action to v6 ([#20](https://github.com/alltuner/cookietuner/issues/20)) ([de4d61d](https://github.com/alltuner/cookietuner/commit/de4d61d725f40e1e69c2238b3c18fe78e7250b00))
* **deps:** update actions/deploy-pages action to v5 ([#19](https://github.com/alltuner/cookietuner/issues/19)) ([7249723](https://github.com/alltuner/cookietuner/commit/72497237aa444ed580c0736301647fac475bf95e))
* **deps:** update actions/upload-pages-artifact action to v5 ([#21](https://github.com/alltuner/cookietuner/issues/21)) ([f249453](https://github.com/alltuner/cookietuner/commit/f24945353383a84aeda0fb532221d2ce609e8604))
* **deps:** update astral-sh/setup-uv action to v8 ([#22](https://github.com/alltuner/cookietuner/issues/22)) ([9d62f2f](https://github.com/alltuner/cookietuner/commit/9d62f2f43b541dc8f13cfb047f93ef289e944972))
* **deps:** update dependency uv_build to &gt;=0.11.2,&lt;0.12.0 ([#18](https://github.com/alltuner/cookietuner/issues/18)) ([38464ad](https://github.com/alltuner/cookietuner/commit/38464ad49db8a185494dea8fe57aba6d48ae77f3))
* **deps:** update github artifact actions ([#14](https://github.com/alltuner/cookietuner/issues/14)) ([8ef33aa](https://github.com/alltuner/cookietuner/commit/8ef33aaa7a7541ca7381f081998f7276d3be7247))
* **deps:** update googleapis/release-please-action action to v5 ([#24](https://github.com/alltuner/cookietuner/issues/24)) ([75dd0fb](https://github.com/alltuner/cookietuner/commit/75dd0fb2b1d94858febb8de5425a4897c4afa48b))


### Documentation Updates

* add support section and FUNDING.yml ([#15](https://github.com/alltuner/cookietuner/issues/15)) ([6f036f2](https://github.com/alltuner/cookietuner/commit/6f036f297cac3b403658e79c73d7d7a693a8a867))
* move License above Support so Support sits next to the footer ([#29](https://github.com/alltuner/cookietuner/issues/29)) ([c7a56d5](https://github.com/alltuner/cookietuner/commit/c7a56d5de34b1e7fbdcb75410b6484696712e134))
* standardize README to alltuner brand structure ([#28](https://github.com/alltuner/cookietuner/issues/28)) ([56c61e4](https://github.com/alltuner/cookietuner/commit/56c61e4e14a85786fd9e6a443c09cb89afa96ca8))


### CI/CD Changes

* allow revert as a conventional PR title type ([#27](https://github.com/alltuner/cookietuner/issues/27)) ([b059e5f](https://github.com/alltuner/cookietuner/commit/b059e5fbf21dbd71594d7f7530805aa2758675af))
* validate PR titles as conventional commits ([#26](https://github.com/alltuner/cookietuner/issues/26)) ([ee8b40f](https://github.com/alltuner/cookietuner/commit/ee8b40f2fdaa2358c238e3e8c26b429945c0798c))

## [0.1.3](https://github.com/alltuner/cookietuner/compare/v0.1.2...v0.1.3) (2026-02-06)


### Miscellaneous Chores

* **deps:** update dependency uv_build to &gt;=0.10.0,&lt;0.11.0 ([#11](https://github.com/alltuner/cookietuner/issues/11)) ([01bb51d](https://github.com/alltuner/cookietuner/commit/01bb51d8924ccd283da69ee07c8e49b1d31a4d8e))


### Documentation Updates

* apply All Tuner Labs corporate MkDocs style ([#12](https://github.com/alltuner/cookietuner/issues/12)) ([1ef9b56](https://github.com/alltuner/cookietuner/commit/1ef9b568263c6aa76be5a8b253ce0b322fa66ced))

## [0.1.2](https://github.com/alltuner/cookietuner/compare/v0.1.1...v0.1.2) (2026-02-04)


### Miscellaneous Chores

* **deps:** update astral-sh/setup-uv action to v7 ([#8](https://github.com/alltuner/cookietuner/issues/8)) ([192ff96](https://github.com/alltuner/cookietuner/commit/192ff96931618749a17b74baf66059838c30b76c))
* **deps:** update github artifact actions ([#9](https://github.com/alltuner/cookietuner/issues/9)) ([02dee87](https://github.com/alltuner/cookietuner/commit/02dee87ab7d442bd9a940f7323e313acb75cfccf))

## [0.1.1](https://github.com/alltuner/cookietuner/compare/v0.1.0...v0.1.1) (2026-01-27)


### Miscellaneous Chores

* Add Claude Code GitHub Workflow ([#3](https://github.com/alltuner/cookietuner/issues/3)) ([8a9f149](https://github.com/alltuner/cookietuner/commit/8a9f14939f2c6584d0718b2ef8bd32c605d358b3))
* **deps:** update actions/checkout action to v6 ([#5](https://github.com/alltuner/cookietuner/issues/5)) ([fb54581](https://github.com/alltuner/cookietuner/commit/fb545815a8bdd5f6d2321968a8ffb6edd7a8d138))
* **deps:** update actions/upload-pages-artifact action to v4 ([#6](https://github.com/alltuner/cookietuner/issues/6)) ([6604784](https://github.com/alltuner/cookietuner/commit/6604784b01413f1503e0b6166a5e082ae4073f17))


### CI/CD Changes

* Add release-please for automated releases ([#2](https://github.com/alltuner/cookietuner/issues/2)) ([9a09f19](https://github.com/alltuner/cookietuner/commit/9a09f19d7e301c874a1cbf1eed1ebb4419e7d270))
