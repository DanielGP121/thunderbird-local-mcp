# Changelog

All notable changes to this project are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## 0.4.0 (2026-11-25)

- New `reply` tool: opens Thunderbird's own reply window for a message id, so the reply stays in the same conversation, quotes the original and is marked as replied once sent. Reply-all by default, sender only on request, attachments from allowed folders. Thunderbird drops text passed to a reply window, so the reply text is copied to the clipboard for the user to paste.
- New `forward` tool: opens Thunderbird's forward window with the original attached as an `.eml` file (its attachments inside), the user's text in the body, and extra files from allowed folders.
- Both refuse messages excluded by the privacy filter and messages that only have a provisional id.
- A refused call no longer writes the text of the message being written to `audit.log`; only its length is logged.
- Add `mcp__thunderbird__reply` and `mcp__thunderbird__forward` to your client's "ask" rules, next to `compose`.

## 0.3.0 (2026-11-25)

Security release, from a review of 0.2.0. Upgrade recommended. The index is rebuilt once on the first call, because the filter now excludes more.

- Privacy filter: sender and subject rules also apply to messages forwarded as attachments, and a message carrying an excluded one is excluded as a whole. Body rules also apply to every text part (forwarded ones included) and to attachment names. In 0.2.0 an excluded invitation forwarded by a colleague, or a confidential text sent only as an attachment, could be read with `read_attachment`.
- `read_attachment` checks that the message it reads from the mailbox is the one that was indexed (exact Message-ID, or sender, subject and date when there is none), runs the filter on it again, and refuses to show attachment text that matches a body rule. In 0.2.0, after a compaction, an excluded message could be read through the id of another one that had no Message-ID.
- `compose` no longer takes `thunderbird` from the current folder or from a relative `PATH` entry, and on Windows accepts only `thunderbird.exe`. In 0.2.0, with an MCP client that does not set `NoDefaultCurrentDirectoryInExePath`, a `thunderbird.bat` in the folder the client started from ran on the first `compose`.
- Output: headers, bodies and attachment text sit between markers with a random tag that changes on every call, so an email cannot fake the end of its own block. Control characters and bidirectional overrides are removed from everything returned.
- `list_folders` gives the number of excluded folders, not their names.
- On Linux and macOS the data folder (index and log) is made `700` and the config created by `--init` `600`.
- Limits against malformed attachments: Office files that would inflate past 200 MB are refused, PDFs are read up to 2,000 pages, and HTML is cut at one million characters before parsing.
- The reading tools are annotated `openWorldHint: true`, since they return text written by others.
- README: install pinned to a release tag; a warning about letting reading tools and internet tools both run without asking; `SECURITY.md` with how to report a vulnerability. CI actions pinned by commit and Dependabot configured.

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
