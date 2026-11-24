# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-11-24

### Added

- A notice of the system when she is done with what you asked (the start of the answer, or why there is none) and you are not looking: another window is in front, or the chat is put away. Clicking it brings the chat forward by @danilogco

## [1.2.1] - 2026-11-22

### Fixed

- Remove the focus-mode checkbox from Settings; the chat header controls the mode, which stays saved between runs by @danilogco
- Keep the focused chat attached and show a button in Settings that returns to the chat by @danilogco

## [1.2.0] - 2026-11-22

### Changed

- Gabi no longer has a made-up birth date, age and hometown: she is an AI assistant, and speaks of herself in the feminine in the languages that mark gender by @danilogco
- The instructions of Gabi are about a third shorter (the lists of kinds and views are said once, and the text is tighter), so every conversation starts with about 3,200 tokens instead of 4,400; she still refuses changes in the read-only mode, asks which container, keeps to Kubernetes and asks for the same actions by @danilogco

### Added

- Claude Code is kept running for the chat, so each question sends only what is new and not the whole conversation again: the conversation stays in the memory of that program and is never saved to disk, the cache is reused and a long chat costs much less (about 60% less input in six long questions); it is started again, with the conversation, when the model, the language or the mode change, when an answer is stopped or when it dies by @danilogco
- The conversation is compacted into a summary made by the assistant: by hand with `/compact`, and by itself before a question when it has grown (100,000 tokens in the context of Claude Code, or when the oldest messages were about to be left out) by @danilogco

### Fixed

- Claude Code is run with none of your own MCP servers, skills or user settings, which were sent with every question: a simple greeting went from about 10,000 tokens to about 4,400 by @danilogco
- The tokens and the cache of the session are shown under the box of the question, in the panel as in the focus mode, and no longer in the header by @danilogco
- The Settings button in Gabi's focus-mode header now hides the chat page before opening Settings and returns to the chat when Settings are closed by @danilogco

## [1.1.0] - 2026-11-22

### Added

- The manifest says that Gabi needs KubeScope 2.4.0 or later (`min_app`), so a KubeScope that offers or installs her checks it, and an older one keeps the version that works with it by @danilogco

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

[Unreleased]: https://github.com/dcotecnologia/kubescope-ai-gabi/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/dcotecnologia/kubescope-ai-gabi/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/dcotecnologia/kubescope-ai-gabi/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/dcotecnologia/kubescope-ai-gabi/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/dcotecnologia/kubescope-ai-gabi/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/dcotecnologia/kubescope-ai-gabi/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/dcotecnologia/kubescope-ai-gabi/releases/tag/v1.0.0
