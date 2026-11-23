# Changelog

All notable changes to this project are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## 0.2.0 (2026-11-23)

- `compose` can attach local files (`attachments`: a list of absolute paths). Attachments are off until you list folders in the new `[compose] attachment_dirs` setting. Even inside those folders, hidden files and folders, the Thunderbird profile and the server's own files (config, index and log) are refused, and links are resolved before the check.
- Configurations written for 0.1.0 keep working: without a `[compose]` section, attachments stay off.

## 0.1.0 (2026-11-21)

First public release.

- Six tools: `list_folders`, `search`, `get_message`, `get_thread`, `read_attachment` and `compose`.
- Reads Thunderbird's mbox files and `.msf` summaries (own Mork reader) without writing to the profile.
- Privacy filter by folder, sender, subject, body and whole conversation, applied before indexing.
- SQLite FTS5 index with accent-insensitive search and incremental refresh.
- Text extraction from PDF, DOCX, XLSX and plain-text attachments.
- `--init`, `--report`, `--rebuild` and `--version` on the command line.
- Profile, executable, configuration and data locations for Windows, Linux and macOS.
