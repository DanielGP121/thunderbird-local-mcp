# thunderbird-local-mcp

[![tests](https://github.com/DanielGP121/thunderbird-local-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/DanielGP121/thunderbird-local-mcp/actions/workflows/tests.yml)

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant search and read the mail Thunderbird has already downloaded to your computer.

It reads Thunderbird's own files on disk. That means no add-on inside Thunderbird, no mail password and no network connection. A privacy filter decides what may be indexed before anything is stored, and the server has no tool that sends, deletes, moves or flags a message.

It was written for Claude Code and should work with any MCP client that can start a local (stdio) server.

## What the assistant can do

| Tool | What it does | Effect |
| --- | --- | --- |
| `list_folders` | Folders with message counts, how many the filter excludes, unread count and newest date | reads |
| `search` | Full-text search: words, `"exact phrases"`, `OR`, `NOT` and `prefix*`. Accents are ignored. Filters for folder, sender, recipient, dates, attachments, unread and starred | reads |
| `get_message` | Headers, flags, tags, attachment list and body text of one message | reads |
| `get_thread` | Every readable message of a conversation, oldest first | reads |
| `read_attachment` | Text of a PDF, DOCX, XLSX or plain-text attachment | reads |
| `compose` | Opens a pre-filled Thunderbird compose window. Nothing is sent: you review it and press Send | opens a window |

There is no tool to send, delete, move, flag or mark mail as read, so a malicious email cannot talk the assistant into doing any of that.

## Why another Thunderbird MCP server

The usual routes are an extension running inside Thunderbird, or a direct IMAP connection that needs the account password in a file. This server takes a third one and reads the profile folder:

- Nothing is installed in Thunderbird, and Thunderbird does not have to be running to search and read.
- No credentials are stored or used.
- The profile is only ever opened for reading. A test compares the size and date of every profile file before and after a full run.
- Mail you exclude is never copied into the index, so the assistant cannot reach it even by asking for its id.

The price of that design: only mail with an offline copy on this computer is visible, and the server cannot act on the mailbox.

## Requirements

- Thunderbird with a local copy of your mail. IMAP accounts need message synchronisation switched on (Account Settings, Synchronisation & Storage). POP accounts and Local Folders are stored locally already.
- Folders stored as mbox ("File per folder"), which is Thunderbird's default. Maildir storage is not supported.
- Python 3.12 or later.
- [uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/) to install the command.

## Quick start

1. Install the command:

   ```
   uv tool install git+https://github.com/DanielGP121/thunderbird-local-mcp
   ```

   With pipx: `pipx install git+https://github.com/DanielGP121/thunderbird-local-mcp`

2. Create the configuration file. The command prints where it put it:

   ```
   thunderbird-local-mcp --init
   ```

3. Open that `config.toml` and write your exclusion rules (see [Privacy filter](#privacy-filter)). Without this file the tools refuse to work, so nothing is ever indexed unfiltered.

4. Build the index and look at the result. This prints counts only, never mail text:

   ```
   thunderbird-local-mcp --report
   ```

5. Register the server in your MCP client.

   Claude Code (add `--scope user` to have it in every project):

   ```
   claude mcp add thunderbird -- thunderbird-local-mcp
   ```

   Claude Desktop and other clients configured with a JSON file:

   ```json
   {
     "mcpServers": {
       "thunderbird": {
         "command": "thunderbird-local-mcp"
       }
     }
   }
   ```

   If you prefer not to install anything, `uvx` can run it straight from the repository. Use it as the command, with these arguments:

   ```json
   {
     "mcpServers": {
       "thunderbird": {
         "command": "uvx",
         "args": ["--from", "git+https://github.com/DanielGP121/thunderbird-local-mcp", "thunderbird-local-mcp"]
       }
     }
   }
   ```

Then ask things like "what arrived from the university this week?", "summarise the thread with Marta about the samples" or "what does the PDF in that message say?".

## Configuration

`config.toml` has two general settings and the filter:

| Setting | Meaning | When empty |
| --- | --- | --- |
| `profile` | Thunderbird profile folder | The profile named in Thunderbird's `profiles.ini` |
| `thunderbird_exe` | Thunderbird executable, used only by `compose` | Looked up on `PATH` and in the standard install folders |
| `[exclude]` | The privacy filter | Ships excluding the Trash, Spam and Junk folders |

Where things live:

| | Windows | macOS | Linux |
| --- | --- | --- | --- |
| `config.toml` | `%APPDATA%\thunderbird-local-mcp\` | `~/Library/Application Support/thunderbird-local-mcp/` | `~/.config/thunderbird-local-mcp/` |
| Index and call log | `%LOCALAPPDATA%\thunderbird-local-mcp\` | `~/Library/Application Support/thunderbird-local-mcp/` | `~/.local/share/thunderbird-local-mcp/` |

On Linux `XDG_CONFIG_HOME` and `XDG_DATA_HOME` are honoured. Two environment variables override the defaults on any system: `TB_CONFIG` (path to the config file) and `TB_DATA_DIR` (folder for the index and the log).

The index contains the text of your mail. Keep its folder out of anything that syncs to the cloud.

## Privacy filter

The `[exclude]` section of `config.toml` has five kinds of rule:

| Rule | What it excludes | Example |
| --- | --- | --- |
| `folders` | Folders that are never opened, with their subfolders | `["Trash", "Spam", "Junk"]` |
| `senders` | Full addresses, or `@domain` including its subdomains | `["@bank.example"]` |
| `subject_regex` | Regular expressions on the subject, case-insensitive | `['payslip', 'invitation to review']` |
| `body_regex` | Regular expressions on the body text | `['confidential.{0,200}manuscript']` |
| `whole_thread` | If one message is excluded, so is its whole conversation | `true` |

How it behaves:

- The filter runs before indexing. An excluded message keeps only what is needed to recognise it again (folder, position and message ids). Its sender, subject, text and attachments are never stored.
- `get_message`, `get_thread` and `read_attachment` refuse an excluded message even when asked for it by id.
- Changing any rule rebuilds the whole index on the next call, because the text of what used to be excluded was never kept.
- `thunderbird-local-mcp --report` shows how many messages each rule removes, per folder and per rule, without printing any mail text. Use it while you tune the rules.

Two practical notes. Write regular expressions between single quotes: inside double quotes TOML turns `\b` into a backspace character and the rule stops matching without any warning. And do not rely on subject rules alone for mail that must stay out: confidential messages often arrive under unrelated subjects, which is what body rules and `whole_thread` are for.

Folder names differ between providers and languages ("Deleted Items", "Papelera", "[Gmail]/Trash"). The report lists the names your accounts use.

## Security model

| Risk | What covers it |
| --- | --- |
| The assistant reads mail it should not | The filter runs before the index, and excluded mail is not stored |
| The assistant goes around the filter by reading the profile or the index as plain files | Not something this server can prevent: deny your client's file tools access to both folders (example below) |
| An email carries instructions aimed at the assistant (prompt injection) | No tool can send, delete, move or forward. Everything returned from an email is labelled as third-party content. `compose` only opens a window and you press Send |
| `compose` smuggles extra fields through quotes or commas in the text | Every field is percent-encoded and addresses are validated; a test tries to inject a recipient through the body |
| The server damages the Thunderbird profile | Files are opened read-only; a test checks that no profile file changes |
| No trace of what the assistant looked at | `audit.log` next to the index records time, tool, query and returned ids, never mail text |

Keep in mind that whatever the assistant reads through these tools is sent to your model provider like the rest of the conversation. The filter is the place to keep out what must not leave your computer.

Suggested permission rules for Claude Code (`~/.claude/settings.json`). They let the five reading tools run freely, ask before every compose window, and stop Claude's own file tools from opening the profile or the index. Adjust the paths to your system; the ones shown are for Windows:

```json
{
  "permissions": {
    "allow": [
      "mcp__thunderbird__list_folders",
      "mcp__thunderbird__search",
      "mcp__thunderbird__get_message",
      "mcp__thunderbird__get_thread",
      "mcp__thunderbird__read_attachment"
    ],
    "ask": ["mcp__thunderbird__compose"],
    "deny": [
      "Read(//c/Users/YOUR_USER/AppData/Roaming/Thunderbird/**)",
      "Read(//c/Users/YOUR_USER/AppData/Local/thunderbird-local-mcp/**)"
    ]
  }
}
```

Those two `deny` rules stop the client's file-reading tools. They do not stop a shell command, so treat them as a guard rail and not as a sandbox.

## How it works

Thunderbird keeps each folder as two files in the profile: an mbox with the messages one after another, and a `.msf` summary in Mork format that lists the messages the folder really contains, where each one starts in the mbox, and its flags and tags.

The mbox alone is misleading, because it keeps messages that were moved or deleted until Thunderbird compacts the folder. So the server reads the `.msf` to know which messages are live and the mbox to get their content. The Mork reader is its own code and handles committed, aborted and unfinished transaction groups the way Thunderbird does.

On every call the server compares the size and date of each mbox and `.msf` with what it indexed last time. Unchanged folders cost one `stat` each. Changed folders are compared with their summary: messages that are gone are dropped and only new ones are parsed. Thunderbird writes the mbox before the summary, so a message that has just arrived shows up first with a provisional id (`INBOX#o<position>`) and gets its final one (`INBOX#<key>`) once the summary is saved.

The index is a single SQLite file with an FTS5 full-text table. It stores headers, body text (HTML is converted to text) and the list of attachments. Attachments themselves are not stored; their text is extracted from the mbox when asked for.

## Limitations

- Only mail Thunderbird has downloaded is visible. If a recent message is missing, open Thunderbird and let it sync.
- Maildir accounts are not supported.
- `compose` passes the whole message on the command line, so it is limited to roughly 5,000 to 10,000 characters of text. Replies written this way are not linked to the original thread.
- `compose` needs to find the Thunderbird executable. With Flatpak or an unusual install location, set `thunderbird_exe` in `config.toml`.
- Attachment text is extracted from PDF, DOCX, XLSX and plain-text formats only. Scanned PDFs yield no text (there is no OCR).

## Status

Version 0.1.0. The test suite (18 cases on a synthetic profile, no real mail involved) runs on Windows, Linux and macOS with Python 3.12 and 3.13.

With a real mailbox it has been used on Windows 10 with Thunderbird 160 and an IMAP account, where the first run indexes a couple of thousand messages in well under a minute and later calls take under a second. On Linux and macOS the profile and executable locations are implemented and unit-tested but have not been tried against a real installation yet. If you run it there, an issue saying whether it worked is welcome.

## Development

```
git clone https://github.com/DanielGP121/thunderbird-local-mcp
cd thunderbird-local-mcp
uv venv
uv pip install -e .
uv run python tests/test_server.py
```

The tests build a throwaway Thunderbird profile in a temporary folder and never touch a real one. Exit code 0 means every case passed.

The code is one module, `src/thunderbird_local_mcp/server.py`, organised in numbered sections: configuration, exclusion rules, profile and folders, Mork reader, mbox reader, index, attachments, compose, tools and command line.

## Licence

MIT. See [LICENSE](LICENSE).

Written by Daniel González Palazón.
