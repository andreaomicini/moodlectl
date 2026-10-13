## 1.0.0 (2026-10-13)

### Features

* browse and manage course forums ([09fcbf8](https://github.com/gciatto/moodlectl/commit/09fcbf81123ac1fc4f5d26d9f9b6fd5e648bd06d))
* browser selection, headless terminal SSO login, persistent sessions ([3f89896](https://github.com/gciatto/moodlectl/commit/3f898963d568441f5740f69aeb9270f51cdcf9c0))
* cache scraped course listings per URL ([32874b3](https://github.com/gciatto/moodlectl/commit/32874b39d37796226309a6b9d5347ff881032642))
* print command results as YAML instead of JSON ([81230b0](https://github.com/gciatto/moodlectl/commit/81230b0c0aac1733573494a317a1f1c3c4377ed4))
* run the browser headless by default, except for login ([ad9c273](https://github.com/gciatto/moodlectl/commit/ad9c2732d924524ff73fa6c932874ce254e586d5))
* show academic year in courses list ([81f5f19](https://github.com/gciatto/moodlectl/commit/81f5f19ae4110b969028c236f50cd9fd549f1c80))
* split forum commands into forums, discussions and posts groups ([78dd0be](https://github.com/gciatto/moodlectl/commit/78dd0bea498922992cbff425f36f23d5c16d0c97))

### Bug Fixes

* list real course names and prefer Chrome over WebKit on macOS ([a379ada](https://github.com/gciatto/moodlectl/commit/a379adac8192474f62fa7b9896a72cbf59c5ca49))
* make static checks pass and derive __version__ from package metadata ([b8b710c](https://github.com/gciatto/moodlectl/commit/b8b710c0b7da4185fbeaee544b86e7100205339d))
* never serve cached pages when the cache TTL is zero ([615b37a](https://github.com/gciatto/moodlectl/commit/615b37a60a9f4d813050b704dcdc0681ffcff270))

### Documentation

* add AGENTS.md and document add-page, config show, MOODLE_SITE_URL ([379d037](https://github.com/gciatto/moodlectl/commit/379d03732a2971c2fd213aadd271d3307b520557))
* cover forums, YAML output and live-validation status in README ([2824ef8](https://github.com/gciatto/moodlectl/commit/2824ef8ca7bd48858e67f19f1a12de276b79571b))

### General maintenance

* first commit ([d8380f4](https://github.com/gciatto/moodlectl/commit/d8380f41ec3cd5b7e665305ed2b014619769f0be))

# Changelog

Releases are managed by semantic-release from Conventional Commit messages.
