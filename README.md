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
| `save_attachment` | Saves an attachment as a file in the folder you set (see [Saving attachments](#saving-attachments)) | writes a file |
| `compose` | Opens a pre-filled Thunderbird compose window for a new message, with attachments from folders you allow. Nothing is sent: you review it and press Send | opens a window |
| `reply` | Opens a reply to a message with the assistant's text already in it: same conversation, original quoted, everyone in copy by default (see [Replies and forwards](#replies-and-forwards)) | opens a window (with attachments, also sets the clipboard) |
| `forward` | Opens Thunderbird's forward window with the original attached as an `.eml` file, its attachments inside, plus your text and any files from allowed folders | opens a window |

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

1. Install the command, pinned to a release:

   ```
   uv tool install git+https://github.com/DanielGP121/thunderbird-local-mcp@v0.6.0
   ```

   With pipx: `pipx install git+https://github.com/DanielGP121/thunderbird-local-mcp@v0.6.0`

   Keep the `@v0.6.0`. Without it you install whatever the main branch holds that day, and an update reaches you only when you choose to install it. The [releases page](https://github.com/DanielGP121/thunderbird-local-mcp/releases) lists the versions.

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

   If you prefer not to install anything, `uvx` can run it straight from the repository. Use it as the command, with these arguments, and keep the release tag in the URL: without it, every start of your MCP client would fetch and run the latest code from the main branch.

   ```json
   {
     "mcpServers": {
       "thunderbird": {
         "command": "uvx",
         "args": ["--from", "git+https://github.com/DanielGP121/thunderbird-local-mcp@v0.6.0", "thunderbird-local-mcp"]
       }
     }
   }
   ```

Then ask things like "what arrived from the university this week?", "summarise the thread with Marta about the samples" or "what does the PDF in that message say?".

## Configuration

`config.toml` has two general settings, the filter and the attachment folders:

| Setting | Meaning | When empty |
| --- | --- | --- |
| `profile` | Thunderbird profile folder | The profile named in Thunderbird's `profiles.ini` |
| `thunderbird_exe` | Thunderbird executable, used only by `compose` | Looked up on `PATH` and in the standard install folders |
| `[exclude]` | The privacy filter | Ships excluding the Trash, Spam and Junk folders |
| `[compose] attachment_dirs` | Folders `compose`, `reply` and `forward` may attach files from (see [Attachments](#attachments)) | Attachments are refused, unless `allow_any_path` is on |
| `[compose] allow_any_path` | `true` lets them attach files from any folder, minus what is always refused | `false` |
| `[compose] never_attach` | Folders never attached from, in either mode | Only the built-in refusals apply |
| `[attachments] save_dir` | Folder `save_attachment` writes to (see [Saving attachments](#saving-attachments)) | Saving is refused |

Where things live:

| | Windows | macOS | Linux |
| --- | --- | --- | --- |
| `config.toml` | `%APPDATA%\thunderbird-local-mcp\` | `~/Library/Application Support/thunderbird-local-mcp/` | `~/.config/thunderbird-local-mcp/` |
| Index and call log | `%LOCALAPPDATA%\thunderbird-local-mcp\` | `~/Library/Application Support/thunderbird-local-mcp/` | `~/.local/share/thunderbird-local-mcp/` |

On Linux `XDG_CONFIG_HOME` and `XDG_DATA_HOME` are honoured. Two environment variables override the defaults on any system: `TB_CONFIG` (path to the config file) and `TB_DATA_DIR` (folder for the index and the log).

The index contains the text of your mail. Keep its folder out of anything that syncs to the cloud. On Linux and macOS the server makes the data folder readable by your account only (`700`), and the config file it creates with `--init` too (`600`).

## Privacy filter

The `[exclude]` section of `config.toml` has five kinds of rule:

| Rule | What it excludes | Example |
| --- | --- | --- |
| `folders` | Folders that are never opened, with their subfolders | `["Trash", "Spam", "Junk"]` |
| `senders` | Full addresses, or `@domain` including its subdomains. Also checked on messages forwarded as attachments | `["@bank.example"]` |
| `subject_regex` | Regular expressions on the subject, case-insensitive. Also checked on messages forwarded as attachments | `['payslip', 'invitation to review']` |
| `body_regex` | Regular expressions on every text part of the message (forwarded ones included) and on attachment names. When an attachment is read, also on its text | `['confidential.{0,200}manuscript']` |
| `whole_thread` | If one message is excluded, so is its whole conversation | `true` |

How it behaves:

- The filter runs before indexing. An excluded message keeps only what is needed to recognise it again (folder, position and message ids). Its sender, subject, text and attachments are never stored.
- A message that carries an excluded one inside it (a colleague forwarding it as an attachment) is excluded as a whole.
- `get_message`, `get_thread` and `read_attachment` refuse an excluded message even when asked for it by id. `read_attachment` reads the message again from the mailbox, checks it is the one that was indexed and runs the filter on it once more before extracting anything. If the text it extracts matches a body rule, it is not shown.
- `list_folders` tells the assistant how many folders are excluded, never their names: a folder name can say what it holds.
- Changing any rule rebuilds the whole index on the next call, because the text of what used to be excluded was never kept.
- `thunderbird-local-mcp --report` shows how many messages each rule removes, per folder and per rule, without printing any mail text. Use it while you tune the rules.

Three practical notes. Write regular expressions between single quotes: inside double quotes TOML turns `\b` into a backspace character and the rule stops matching without any warning. Do not rely on subject rules alone for mail that must stay out: confidential messages often arrive under unrelated subjects, which is what body rules and `whole_thread` are for. And sender rules look at the `From` address of the message and of anything forwarded as an attachment, not at text pasted into a reply: a forward written inline ("---------- Forwarded message ----------") is caught only by subject and body rules.

Folder names differ between providers and languages ("Deleted Items", "Papelera", "[Gmail]/Trash"). The report lists the names your accounts use.

## Attachments

`compose`, `reply` and `forward` can attach local files to the window they open. This is off until you choose one of two modes in the `[compose]` section of `config.toml`:

```toml
[compose]
# Only from some folders (and their subfolders):
attachment_dirs = ['C:\Users\me\Documents\To send']
# Or from anywhere:
allow_any_path = true
# Never from these folders, in either mode:
never_attach = ['C:\Users\me\Documents\Confidential']
```

The assistant passes absolute paths in `attachments`, and the server checks each one before anything opens. Links are resolved first, so a link cannot point somewhere else. Whatever the mode, these are always refused:

- **Hidden files and folders** (names starting with a dot, such as `.ssh`, `.git` or `.env`): below the listed folders, or anywhere in the path when any path is allowed.
- **The Thunderbird profile and the server's own files** (`config.toml`, the index and the log). The profile holds the mail your filter keeps out, and the config says what you consider confidential.
- **Credential stores and browser profiles**: rclone's configuration, Firefox, Chrome, Edge, Brave and Vivaldi profiles, the Windows credential and key folders, and the macOS keychains.
- **Key and password files**: `.pem`, `.p12`, `.pfx`, `.ppk`, `.kdbx`, `.kdb`, `.jks` and `.keystore` files, SSH keys such as `id_ed25519`, and any file whose beginning holds a private key block. (`.key` files are judged by their content, because Keynote presentations use that extension too.)
- **Anything inside a folder listed in `never_attach`.**
- **Files over 50 MB.**

If any file fails a check, no window opens, and the error says what to change. Edits to `config.toml` apply on the next call without restarting the server; if the file has a mistake, the server keeps the last settings that worked and tells you so.

Choose the mode with this in mind: an email can contain instructions aimed at the assistant. With `allow_any_path`, what stands between such an email and a private file is the list above, your approval of each call (keep these tools on "ask") and your look at the window before pressing Send. With `attachment_dirs`, keep the list to folders whose contents you would not mind attaching by mistake. In both modes the server cannot stop the assistant from first copying a file somewhere else with its other tools.

## Replies and forwards

`reply` and `forward` take the id of a message from `search`. How each window is built depends on what Thunderbird accepts when a window is opened from outside (checked on Thunderbird 160):

- **A reply opens with the assistant's text already in it**, followed by a line such as "On 25/11/2026 13:07, Ana wrote:" and the original quoted the way Thunderbird's Reply button quotes it: a coloured bar, with one more bar inside it for each earlier quote level in the text. The server sets the `In-Reply-To` and `References` headers, so the reply stays in the same conversation for you and for the people you write to. It answers the sender, or the `Reply-To` address when there is one, and by default also everyone in To and Cc minus your own addresses (read from Thunderbird's settings); ask for "sender only" to reply just to the sender. The window opens in HTML mode, the only one in which a quote can be passed to Thunderbird from outside. Two differences from Thunderbird's Reply button: an original that only has an HTML version is quoted as its text, without its formatting or the bars of earlier quotes, and the original is not marked as replied when you send.
- **A reply with attachments opens Thunderbird's own reply window**, the only one that takes attachments. That window keeps the conversation and marks the original as replied, but it drops any text passed to it, so the assistant's text goes to the clipboard and you paste it above the quote with Ctrl+V (Cmd+V on a Mac). This replaces whatever the clipboard held. On Linux it needs `wl-copy`, `xclip` or `xsel`; without them the assistant gives you the text instead.
- **Forwards carry the original as an attachment.** An inline forward opened this way comes out empty, so `forward` attaches the original message as an `.eml` file, which keeps its own attachments. Your text goes in the body.

The line above the quote is set by `reply_header` in the `[compose]` section of `config.toml`, with `{date}`, `{time}` and `{sender}` as placeholders. In Spanish, for example: `reply_header = 'El {date} a las {time}, {sender} escribió:'`. When the original is long, the quote is shortened so the window still opens; your text is never cut.

Neither tool works on a message the privacy filter excludes. A message that has only a provisional id (`INBOX#o...`) has to wait until Thunderbird saves its folder summary, which happens within moments of opening the folder.

## Saving attachments

`save_attachment` writes an attachment, as the original file, into one folder you choose. It is off until you set that folder:

```toml
[attachments]
save_dir = 'C:\Users\me\Downloads\From mail'
```

The folder is created if it does not exist. What the server does with each file:

- **Never overwrites.** If `informe.pdf` is already there, the new one is saved as `informe (1).pdf`.
- **Cleans the name.** The file name comes from the sender, so folders, characters Windows rejects, reserved names such as `CON`, leading dots and the invisible right-to-left characters that make `factura‮fdp.exe` look like a PDF are removed.
- **Marks it as downloaded.** On Windows the file gets the "downloaded from the Internet" mark, so Word and Excel open it in Protected View.
- **Keeps the privacy filter.** It refuses excluded messages, and a PDF, Word, Excel or text attachment whose text matches a body rule is not saved, the same as with `read_attachment`. Images and archives cannot be checked.
- **Stays in its folder.** `save_dir` cannot point into the Thunderbird profile or the server's own folders.

The assistant gets back the path and nothing of the content. Treat the file like any other attachment: open it only if you trust the sender. Keep `save_dir` out of folders whose contents you don't want the assistant to be able to read with its other tools.

## Security model

| Risk | What covers it |
| --- | --- |
| The assistant reads mail it should not | The filter runs before the index, and excluded mail is not stored. It also looks inside forwarded messages and at attachment names, and checks attachment text when it is read |
| The assistant goes around the filter by reading the profile or the index as plain files | Not something this server can prevent: deny your client's file tools access to both folders (example below) |
| An email carries instructions aimed at the assistant (prompt injection) | No tool can send, delete or move mail. Headers, bodies and attachment text come inside markers with a random tag that changes on every call, so an email cannot fake the end of its own block. Control characters and bidirectional overrides are removed. `compose`, `reply` and `forward` only open a window and you press Send |
| `compose`, `reply` or `forward` smuggle extra fields through quotes or commas in the text | Every field is percent-encoded and addresses are validated; a test tries to inject a recipient through the body |
| An email gets the assistant to reply to or forward a message you keep out | `reply` and `forward` refuse messages the privacy filter excludes, like the reading tools |
| A program called `thunderbird` planted in a folder runs instead of Thunderbird | `compose` takes the executable from `thunderbird_exe`, from absolute `PATH` entries or from the standard install folders, never from the current folder; on Windows only a real `thunderbird.exe` |
| An email gets the assistant to attach a private file | Attachments are off by default; on, they come from the folders you list or, with `allow_any_path`, from anywhere. Hidden files, the Thunderbird profile, the server's own files, credential stores, browser profiles, key and password files and your `never_attach` folders are always refused; you approve each call and see the attachments before sending |
| A saved attachment overwrites a file, escapes its folder or passes for something else | `save_attachment` writes only into `save_dir`, never overwrites, reduces the sender's file name to a plain one (no folders, no disguised extensions) and marks the file as downloaded from the Internet on Windows |
| Another account on the same computer reads the index | On Linux and macOS the data folder is `700`; on Windows it sits in your own profile |
| A malformed attachment exhausts memory | Office files that would inflate past 200 MB and PDF pages beyond 2,000 are not read; very long HTML is cut before parsing |
| The server damages the Thunderbird profile | Files are opened read-only; a test checks that no profile file changes |
| No trace of what the assistant looked at | `audit.log` next to the index records time, tool, query and returned ids, never mail text nor the text of a message being written |

Keep in mind that whatever the assistant reads through these tools is sent to your model provider like the rest of the conversation. The filter is the place to keep out what must not leave your computer.

Be careful with what else your assistant may do without asking. If the reading tools run freely and so does a tool that reaches the internet (a web fetch, a browser, a shell), an email with hidden instructions could get the assistant to read another message and send it out, with no step for you to approve. Keep network tools on "ask", or the reading tools on "ask", but not both on "allow". And keep Python up to date: the server parses mail written by strangers with the standard library's email, HTML and zip modules, which receive security fixes in each patch release.

Suggested permission rules for Claude Code (`~/.claude/settings.json`). They let the five reading tools run freely, ask before every compose, reply or forward window and before saving an attachment, and stop Claude's own file tools from opening the profile or the index. Adjust the paths to your system; the ones shown are for Windows:

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
    "ask": [
      "mcp__thunderbird__compose",
      "mcp__thunderbird__reply",
      "mcp__thunderbird__forward",
      "mcp__thunderbird__save_attachment"
    ],
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
- `compose` passes the whole message on the command line, so it is limited to roughly 5,000 to 10,000 characters of text. It always starts a new conversation; use `reply` to answer.
- `compose`, `reply` and `forward` need to find the Thunderbird executable. With Flatpak or an unusual install location, set `thunderbird_exe` in `config.toml`.
- `forward`, and `reply` with attachments, build Thunderbird's internal address of the message from the account settings in `prefs.js` and the folder's name on disk. Folders whose name Thunderbird stores differently on disk (some non-ASCII IMAP names) may not be found; tested with INBOX and with folder names that contain spaces.
- Attachment text is extracted from PDF, DOCX, XLSX and plain-text formats only. Scanned PDFs yield no text (there is no OCR).

## Status

Version 0.6.0. The test suite (34 cases on a synthetic profile, no real mail involved) runs on Windows, Linux and macOS with Python 3.12 and 3.13.

To report a security problem, see [SECURITY.md](SECURITY.md); please do not open a public issue for it.

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

## Contact

Bugs and feature requests: open an issue. Security problems: report them privately as [SECURITY.md](SECURITY.md) explains. For anything else, such as proposals or using it in your own work, write to dgonzalez@eead.csic.es.

## Licence

MIT. See [LICENSE](LICENSE).

Written by Daniel González Palazón.
