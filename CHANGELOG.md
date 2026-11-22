# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-11-22

### Added

- In the focus mode the chat also steps aside for a page the assistant takes you to, and a button (or Ctrl+G) brings it back by @danilogco
- In the focus mode the Settings still open: the chat steps aside while they are open and is back when they are left by @danilogco
- Gabi has a focus mode: while the chat is open it takes the place of the side menu and the pages, and the top bar and the footer stay; the chat is always open, with the look of the pages of the app; it is set in the header of the chat or in the Settings of Gabi, and kept by @danilogco
- A new session button in the header of the chat starts the conversation of the context from nothing by @danilogco
- The header shows the tokens of the session (input, output and the share read from the cache), and its tip tells the cache reads and writes, the last answer and the cost, for Claude Code and Codex by @danilogco

## [1.0.1] - 2026-11-20

### Fixed

- Update the locked dependencies and the pre-commit hooks by @danilogco

## [1.0.0] - 2026-11-19

### Added

- Gabi as an extension of her own project, written against the KubeScope SDK only: the chat in the corner of the window, her section of the Settings, her shortcut and the terminal commands `chat` and `assistant`

[Unreleased]: https://github.com/dcotecnologia/kubescope-ai-gabi/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/dcotecnologia/kubescope-ai-gabi/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/dcotecnologia/kubescope-ai-gabi/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/dcotecnologia/kubescope-ai-gabi/releases/tag/v1.0.0
