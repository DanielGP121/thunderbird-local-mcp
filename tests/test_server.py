"""Offline tests of the server on a synthetic Thunderbird profile: no real mail is read.

The fixture is an IMAP-style account with an mbox and a hand-written .msf summary in a temporary
folder. The cases cover what the server promises: only the messages the summary lists are visible,
excluded mail leaves no text behind, search ignores accents, attachments yield their text, new
arrivals and compaction are picked up, rule changes rebuild the index, and the profile is never
written. A last group checks the per-platform locations (config, data, profile, executable) and
--init. Run it with "python tests/test_server.py"; exit code 0 means every case passed.
"""

import io
import os
import shutil
import sys
import tempfile
import traceback
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="tbmcp_test_"))
os.environ["TB_DATA_DIR"] = str(TMP / "data")
os.environ["TB_CONFIG"] = str(TMP / "config.toml")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # test the checkout, not an installed copy
import thunderbird_local_mcp.server as s  # noqa: E402

PROFILE = TMP / "Profiles" / "test.default"
INBOX = PROFILE / "ImapMail" / "imap.example.org" / "INBOX"
TRASH = PROFILE / "ImapMail" / "imap.example.org" / "Trash"
OFFSETS: dict[str, int] = {}

CONFIG = """
profile = '{profile}'
thunderbird_exe = ""
[exclude]
folders = ["Trash"]
senders = {senders}
subject_regex = {subjects}
body_regex = []
whole_thread = true
[compose]
attachment_dirs = {dirs}
"""


# --- § 1 — Fixture: messages, mbox and .msf ----------------------------------------------------

def crlf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def headers(m, mid, frm, to, subject, date, refs=""):
    m["From"], m["To"], m["Date"], m["Message-ID"] = frm, to, date, f"<{mid}>"
    m["Subject"] = Header(subject, "utf-8")
    if refs:
        m["References"] = refs
    return m


def tiny_pdf(text: str) -> bytes:
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = f"BT /F1 18 Tf 20 60 Td ({text}) Tj ET".encode()
    objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offs = b"%PDF-1.4\n", []
    for n, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % n + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offs:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def office_files() -> tuple[bytes, bytes]:
    import docx
    import openpyxl

    d = docx.Document()
    d.add_paragraph("Informe de prueba sobre la floración")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "CP50", "812"
    b1 = io.BytesIO()
    d.save(b1)
    wb = openpyxl.Workbook()
    wb.active.append(["gene", "log2FC"])
    wb.active.append(["Gene_1", 2.5])
    b2 = io.BytesIO()
    wb.save(b2)
    return b1.getvalue(), b2.getvalue()


def attach(container, part, filename, disposition="attachment"):
    part.add_header("Content-Disposition", disposition, filename=filename)
    container.attach(part)


def messages() -> dict[str, bytes]:
    m1 = crlf(
        b"From: =?utf-8?q?Ana_Mart=C3=ADnez?= <ana@example.org>\n"
        b"To: alex@example.org\n"
        b"Subject: =?utf-8?q?Revisi=C3=B3n_del_informe?=\n"
        b"Date: Mon, 17 Nov 2026 10:00:00 +0100\n"
        b"Message-ID: <m1@test>\n"
        b"Content-Type: text/plain; charset=utf-8\n"
        b"Content-Transfer-Encoding: 8bit\n\n"
        + "Hola Alex, te paso la revisión del informe.\n\n"
          "From here on the text continues\nwithout a header line.\n>From an escaped line.\n".encode()
    )
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(
        "<html><head><style>p {color: red}</style></head><body><p>Plazo&nbsp;abierto.</p>"
        "<p>Información de la convocatoria</p><script>alert(1)</script></body></html>", "html", "iso-8859-1"))
    m2 = crlf(headers(alt, "m2@test", "University <noreply@university.example>", "alex@example.org", "Convocatoria",
                      "Mon, 17 Nov 2026 11:00:00 +0100").as_bytes())
    docx_bytes, xlsx_bytes = office_files()
    mixed = MIMEMultipart("mixed")
    mixed.attach(MIMEText("Adjunto los ficheros del experimento.", "plain", "utf-8"))
    attach(mixed, MIMEText("nota de campo: floración 12 de marzo", "plain", "utf-8"), "notes.txt")
    attach(mixed, MIMEApplication(xlsx_bytes, "vnd.openxmlformats-officedocument.spreadsheetml.sheet"), "table.xlsx")
    attach(mixed, MIMEApplication(docx_bytes, "vnd.openxmlformats-officedocument.wordprocessingml.document"), "informe.docx")
    attach(mixed, MIMEApplication(tiny_pdf("Dormancy release"), "pdf"), "paper.pdf")
    attach(mixed, MIMEImage(b"\x89PNG\r\n\x1a\n" + b"0" * 200, "png"), "logo.png", "inline")
    m3 = crlf(headers(mixed, "m3@test", "Luis <luis@example.org>", "alex@example.org", "Re: Revisión del informe",
                      "Tue, 18 Nov 2026 09:00:00 +0100", refs="<m1@test>").as_bytes())
    m4 = crlf(headers(MIMEText("Dear Dr, would you review MS-2026-001?", "plain", "utf-8"), "m4@test",
                      "Journal Office <office@journal.example>", "alex@example.org",
                      "Invitation to review manuscript", "Mon, 17 Nov 2026 12:00:00 +0100").as_bytes())
    m5 = crlf(headers(MIMEText("Accepted, confidential manuscript.", "plain", "utf-8"), "m5@test",
                      "Alex <alex@example.org>", "luis@example.org", "Re: question",
                      "Mon, 17 Nov 2026 13:00:00 +0100", refs="<m4@test>").as_bytes())
    m6 = crlf(headers(MIMEText("This copy was moved away.", "plain", "utf-8"), "m6@test",
                      "Old <old@example.org>", "alex@example.org", "Stale copy", "Sun, 16 Nov 2026 08:00:00 +0100").as_bytes())
    m7 = crlf(headers(MIMEText("New arrival about pollination.", "plain", "utf-8"), "m7@test",
                      "Marta <marta@example.org>", "alex@example.org", "Pollination", "Tue, 18 Nov 2026 10:00:00 +0100").as_bytes())
    trash = crlf(headers(MIMEText("Deleted secret text.", "plain", "utf-8"), "t1@test",
                         "X <x@example.org>", "alex@example.org", "Secret", "Sun, 16 Nov 2026 08:00:00 +0100").as_bytes())
    return {"m1": m1, "m2": m2, "m3": m3, "m4": m4, "m5": m5, "m6": m6, "m7": m7, "trash": trash}


MSGS = messages()


def write_mbox(path: Path, names: list[str]) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    out, offs = bytearray(), {}
    for name in names:
        offs[name] = len(out)
        out += b"From - Mon Nov 17 10:00:00 2026\r\n" + MSGS[name].rstrip(b"\r\n") + b"\r\n\r\n"
    path.write_bytes(bytes(out))
    return offs


def msf_text(rows: list[tuple[int, str, int, int]], extra: str = "") -> str:
    lines = [
        '// <!-- <mdb:mork:z v="1.4"/> -->',
        "< <(a=c)> // (f=iso-8859-1)",
        "  (80=ns:msg:db:row:scope:msgs:all)(81=subject)(82=message-id)(83=flags)",
        "  (84=storeToken)(85=ns:msg:db:table:kind:msgs)(86=keywords)>",
        "<(A1=important)>",
        "{1:^80 {(k^85:c)(s=9)}",
    ]
    for key, mid, flags, off in rows:
        lines.append(f"  [{key:X}(^82={mid})(^83={flags:X})(^84={off})" + ("(^86^A1)" if key == 1 else "") + "]")
    lines.append("  }")
    return "\n".join(lines) + "\n" + extra


# Group 1 (committed) removes the stale copy from the table; group 2 is aborted (its flag change
# must not apply); group 3 never commits (Thunderbird was writing) and must be ignored.
GROUPS = (
    "@$${1{@\n{1:^80 -9 }\n@$$}1}@\n"
    "@$${2{@\n[1:^80(^83=0)]\n@$$}~~}@\n"
    "@$${3{@\n{1:^80 -1 }\n"
)


def write_config(senders='["@journal.example"]', subjects='["invitation to review"]', dirs="[]"):
    Path(os.environ["TB_CONFIG"]).write_text(
        CONFIG.format(profile=PROFILE.as_posix(), senders=senders, subjects=subjects, dirs=dirs), encoding="utf-8")


def setup_fixture() -> None:
    OFFSETS.update(write_mbox(INBOX, ["m1", "m2", "m6", "m3", "m4", "m5"]))
    o = OFFSETS
    rows = [(1, "m1@test", 0x81, o["m1"]), (2, "m2@test", 0x80, o["m2"]), (3, "m3@test", 0x80, o["m3"]),
            (4, "m4@test", 0x80, o["m4"]), (5, "m5@test", 0x80, o["m5"]), (9, "m6@test", 0x80, o["m6"]),
            (6, "m8@test", 0x0, 999999)]  # row 6: headers only, no offline copy
    INBOX.with_name("INBOX.msf").write_text(msf_text(rows, GROUPS), encoding="latin-1")
    write_mbox(TRASH, ["trash"])
    TRASH.with_name("Trash.msf").write_text(msf_text([(1, "t1@test", 0x80, 0)]), encoding="latin-1")
    write_config()


def fresh_index() -> s.Index:
    if s._index is not None:
        s._index.db.close()
    s._index = None
    idx = s.get_index()
    idx.refresh(force=True)
    return idx


def snapshot() -> dict:
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in PROFILE.rglob("*") if p.is_file()}


def raises(fn, text: str) -> None:
    try:
        fn()
    except s.ToolError as exc:
        assert text in str(exc), f"error {exc!r} does not mention {text!r}"
        return
    raise AssertionError(f"expected ToolError mentioning {text!r}")


# --- § 2 — Cases -------------------------------------------------------------------------------

def test_mork_groups_and_removals():
    m = s.Mork(INBOX.with_name("INBOX.msf").read_text(encoding="latin-1"))
    rows = {r["_id"]: r for r in m.table_rows("ns:msg:db:table:kind:msgs")}
    assert sorted(rows) == ["1", "2", "3", "4", "5", "6"], sorted(rows)
    assert rows["1"]["flags"] == "81", "aborted group was applied"
    assert rows["1"]["keywords"] == "important"


def test_visible_set_follows_summary():
    idx = fresh_index()
    q = idx.db.execute
    assert q("SELECT COUNT(*) FROM messages WHERE excluded IS NULL").fetchone()[0] == 3
    assert q("SELECT COUNT(*) FROM messages WHERE offset = ?", (OFFSETS["m6"],)).fetchone()[0] == 0, "stale copy indexed"
    rules = dict(q("SELECT msg_key, excluded FROM messages WHERE excluded IS NOT NULL").fetchall())
    assert rules == {"4": "sender:@journal.example", "5": "thread"}, rules
    assert q("SELECT not_offline FROM folders WHERE name='INBOX'").fetchone()[0] == 1
    assert q("SELECT excluded FROM folders WHERE name='Trash'").fetchone()[0] == "folder:trash"
    assert q("SELECT COUNT(*) FROM messages m JOIN folders f ON f.id=m.folder_id WHERE f.name='Trash'").fetchone()[0] == 0


def test_excluded_mail_leaves_no_text():
    idx = fresh_index()
    row = idx.db.execute("SELECT sender, subject, body, recipients FROM messages WHERE msg_key IN ('4','5')").fetchall()
    assert all(v is None for r in row for v in r), row
    assert idx.db.execute("SELECT COUNT(*) FROM fts WHERE fts MATCH 'accepted OR invitation OR secret'").fetchone()[0] == 0
    assert s.search(query="confidential") == "No messages match."
    raises(lambda: s.get_message(id="INBOX#4"), "privacy filter")
    raises(lambda: s.get_message(id="INBOX#5"), "privacy filter")
    raises(lambda: s.read_attachment(id="INBOX#5"), "privacy filter")


def test_search_ignores_accents_and_filters():
    fresh_index()
    assert "[INBOX#1]" in s.search(query="revision informe")
    assert "[INBOX#2]" in s.search(query="informacion convocatoria")
    assert "[INBOX#3]" in s.search(query="dormancy OR paper")  # attachment name
    out = s.search(unread=True)
    assert "[INBOX#1]" not in out and "[INBOX#2]" in out
    out = s.search(has_attachment=True)
    assert "[INBOX#3]" in out and "[INBOX#1]" not in out and "4 attachments" in out
    assert "[INBOX#1]" in s.search(sender="martínez")
    assert "1 messages match" in s.search(date_from="2026-11-18")


def test_message_text_and_html():
    fresh_index()
    out = s.get_message(id="INBOX#1")
    assert "Ana Martínez <ana@example.org>" in out and "revisión del informe" in out and "Flags: read" in out
    assert "From here on the text continues" in out, "an unescaped From line split the message"
    assert "Tags: important" in out
    out = s.get_message(id="INBOX#2")
    assert "Plazo abierto." in out and "Información de la convocatoria" in out
    assert "alert(1)" not in out and "color: red" not in out
    raises(lambda: s.get_message(id="INBOX#99"), "no message")
    raises(lambda: s.get_message(id="INBOX-1"), "must look like")


def test_thread():
    fresh_index()
    out = s.get_thread(id="INBOX#3")
    assert out.startswith("Conversation with 2 readable messages") and "INBOX#1" in out and "INBOX#3" in out


def test_attachments():
    fresh_index()
    out = s.get_message(id="INBOX#3")
    assert "1. notes.txt" in out and "4. paper.pdf" in out and "logo.png" not in out
    assert "floración 12 de marzo" in s.read_attachment(id="INBOX#3", attachment="notes.txt")
    xlsx = s.read_attachment(id="INBOX#3", attachment="2")
    assert "Gene_1\t2.5" in xlsx, xlsx
    docx = s.read_attachment(id="INBOX#3", attachment="informe.docx")
    assert "Informe de prueba sobre la floración" in docx and "CP50\t812" in docx
    assert "Dormancy release" in s.read_attachment(id="INBOX#3", attachment="4")
    raises(lambda: s.read_attachment(id="INBOX#3", attachment="7"), "pick 1-4")
    raises(lambda: s.read_attachment(id="INBOX#1"), "no attachments")


def test_new_arrival_then_summary_update():
    fresh_index()
    with INBOX.open("ab") as fh:
        OFFSETS["m7"] = fh.tell()
        fh.write(b"From - Tue Nov 18 10:00:00 2026\r\n" + MSGS["m7"].rstrip(b"\r\n") + b"\r\n\r\n")
    idx = s.get_index()
    idx.refresh(force=True)
    assert f"[INBOX#o{OFFSETS['m7']}]" in s.search(query="pollination"), "provisional arrival not visible"
    o = OFFSETS
    rows = [(1, "m1@test", 0x81, o["m1"]), (2, "m2@test", 0x80, o["m2"]), (3, "m3@test", 0x80, o["m3"]),
            (4, "m4@test", 0x80, o["m4"]), (5, "m5@test", 0x80, o["m5"]), (7, "m7@test", 0x80, o["m7"])]
    INBOX.with_name("INBOX.msf").write_text(msf_text(rows), encoding="latin-1")
    idx.refresh(force=True)
    assert "[INBOX#7]" in s.search(query="pollination")
    raises(lambda: s.get_message(id=f"INBOX#o{OFFSETS['m7']}"), "no message")


def test_compaction_moves_offsets():
    offs = write_mbox(INBOX, ["m1", "m2", "m3", "m4", "m5", "m7"])  # m6 squeezed out
    rows = [(1, "m1@test", 0x81, offs["m1"]), (2, "m2@test", 0x80, offs["m2"]), (3, "m3@test", 0x80, offs["m3"]),
            (4, "m4@test", 0x80, offs["m4"]), (5, "m5@test", 0x80, offs["m5"]), (7, "m7@test", 0x80, offs["m7"])]
    INBOX.with_name("INBOX.msf").write_text(msf_text(rows), encoding="latin-1")
    idx = s.get_index()
    idx.refresh(force=True)
    assert idx.db.execute("SELECT COUNT(*) FROM messages WHERE excluded IS NULL").fetchone()[0] == 4
    assert "Dormancy release" in s.read_attachment(id="INBOX#3", attachment="paper.pdf")
    assert "Hola Alex" in s.get_message(id="INBOX#1")


def test_rule_change_rebuilds_index():
    write_config(senders="[]", subjects="[]")
    try:
        fresh_index()
        assert "would you review" in s.get_message(id="INBOX#4")
        assert "Accepted" in s.get_message(id="INBOX#5")
    finally:
        write_config()
    fresh_index()
    raises(lambda: s.get_message(id="INBOX#4"), "privacy filter")


def test_query_sanitising():
    assert s.fts_query('foo-bar "baz qux" OR') == '"foo" "bar" "baz qux"'
    assert s.fts_query("revis*") == '"revis"*'
    assert s.fts_query("a NOT b") == '"a" NOT "b"'
    raises(lambda: s.fts_query('"" ()'), "no searchable words")
    assert isinstance(s.search(query='"unclosed (paren) AND: NEAR('), str)


def test_compose_arguments():
    from urllib.parse import unquote

    body = "Línea 1, con coma y 'comillas'.\n\nfrom=x,to='evil@x.org'"
    spec = s.build_compose_spec(["a@b.org", "e@f.org"], ["c@d.es"], [], "Alex's note", body)
    fields = dict(f.split("=", 1) for f in spec.split(","))  # no raw comma or quote survives encoding
    assert set(fields) == {"to", "cc", "subject", "body"}, fields
    assert unquote(fields["to"]) == "a@b.org,e@f.org" and unquote(fields["cc"]) == "c@d.es"
    assert unquote(fields["subject"]) == "Alex's note" and unquote(fields["body"]) == body
    raises(lambda: s.build_compose_spec(["a@b.org"], [], [], "x", "á" * 6000), "too long")
    assert s.split_addresses("a@b.org; c@d.es") == ["a@b.org", "c@d.es"]
    raises(lambda: s.split_addresses("a@b.org',subject='x"), "not a plain email address")
    raises(lambda: s.split_addresses("Name <a@b.org>"), "not a plain email address")


def test_compose_attachment_rules():
    from urllib.parse import unquote

    outbox = TMP / "outbox"
    (outbox / "sub").mkdir(parents=True)
    (outbox / ".git").mkdir()
    report, notes = outbox / "informe final.pdf", outbox / "sub" / "año, notas.txt"
    for f in (report, notes, outbox / ".env", outbox / ".git" / "config", TMP / "elsewhere.txt"):
        f.write_text("x", encoding="utf-8")
    allowed, blocked = [str(outbox)], s.private_paths(PROFILE)

    files = s.check_attachments([str(report), str(notes), str(report)], allowed, blocked)
    assert files == [report.resolve(), notes.resolve()], files  # duplicates dropped, order kept
    spec = s.build_compose_spec(["a@b.org"], [], [], "x", "", files)
    fields = dict(f.split("=", 1) for f in spec.split(","))
    urls = unquote(fields["attachment"]).split(",")  # what Thunderbird does with the field
    assert urls == [p.as_uri() for p in files], urls  # the comma in "año, notas.txt" stays encoded
    assert "attachment" not in s.build_compose_spec(["a@b.org"], [], [], "x", "")

    raises(lambda: s.check_attachments([str(report)], [], blocked), "switched off")
    raises(lambda: s.check_attachments(["informe final.pdf"], allowed, blocked), "must be absolute")
    raises(lambda: s.check_attachments([str(outbox / "missing.pdf")], allowed, blocked), "not found")
    raises(lambda: s.check_attachments([str(outbox / "sub")], allowed, blocked), "not a file")
    raises(lambda: s.check_attachments([str(TMP / "elsewhere.txt")], allowed, blocked), "outside the folders")
    raises(lambda: s.check_attachments([str(outbox / "sub" / ".." / ".." / "elsewhere.txt")], allowed, blocked),
           "outside the folders")
    raises(lambda: s.check_attachments([str(outbox / ".env")], allowed, blocked), "hidden")
    raises(lambda: s.check_attachments([str(outbox / ".git" / "config")], allowed, blocked), "hidden")
    # Allowing a parent folder does not open the mail store or the server's own files.
    raises(lambda: s.check_attachments([str(INBOX)], [str(TMP)], blocked), "Thunderbird profile")
    raises(lambda: s.check_attachments([os.environ["TB_CONFIG"]], [str(TMP)], blocked), "own files")
    limit = s.MAX_ATTACHMENT
    s.MAX_ATTACHMENT = 0
    try:
        raises(lambda: s.check_attachments([str(report)], allowed, blocked), "MB limit")
    finally:
        s.MAX_ATTACHMENT = limit
    link = outbox / "link.txt"
    try:
        link.symlink_to(TMP / "elsewhere.txt")
    except OSError:
        pass  # creating links needs extra rights on Windows; the CI runners on Linux and macOS cover it
    else:
        raises(lambda: s.check_attachments([str(link)], allowed, blocked), "outside the folders")


def test_compose_tool_with_attachments():
    from urllib.parse import unquote

    report = TMP / "outbox" / "informe final.pdf"
    launched: list[list[str]] = []
    real_popen, real_exe = s.subprocess.Popen, s.thunderbird_exe
    s.subprocess.Popen = lambda args, **kw: launched.append(args)
    s.thunderbird_exe = lambda cfg: Path("thunderbird")
    try:
        write_config()
        fresh_index()
        raises(lambda: s.compose(to="a@b.org", attachments=[str(report)]), "switched off")
        write_config(dirs=f"['{(TMP / 'outbox').as_posix()}']")
        fresh_index()
        out = s.compose(to="a@b.org", subject="Datos", attachments=[str(report)])
        assert "attaching informe final.pdf" in out and "Nothing has been sent" in out, out
        assert len(launched) == 1 and launched[0][1] == "-compose"
        fields = dict(f.split("=", 1) for f in launched[0][2].split(","))
        assert unquote(fields["attachment"]) == report.resolve().as_uri()
        raises(lambda: s.compose(to="a@b.org", attachments=[str(INBOX)]), "outside the folders")
        assert len(launched) == 1, "a refused attachment must not open a window"
    finally:
        s.subprocess.Popen, s.thunderbird_exe = real_popen, real_exe
        write_config()
    log = (Path(os.environ["TB_DATA_DIR"]) / "audit.log").read_text(encoding="utf-8")
    assert "informe final.pdf" in log and "window opened" in log


def test_audit_log_has_no_mail_text():
    log = (Path(os.environ["TB_DATA_DIR"]) / "audit.log").read_text(encoding="utf-8")
    for phrase in ("Adjunto los ficheros", "Plazo abierto", "floración 12", "would you review", "Dormancy release"):
        assert phrase not in log, f"audit.log contains mail text: {phrase!r}"


def exits(fn, text: str) -> None:
    try:
        fn()
    except SystemExit as exc:
        assert text in str(exc), f"exit message {exc!r} does not mention {text!r}"
        return
    raise AssertionError(f"expected SystemExit mentioning {text!r}")


def test_user_dirs_per_platform():
    home = Path("/home/u")
    cfg, data = s.user_dirs("linux", {}, home)
    assert cfg == home / ".config" / s.APP_NAME and data == home / ".local" / "share" / s.APP_NAME
    cfg, data = s.user_dirs("linux", {"XDG_CONFIG_HOME": "/x/c", "XDG_DATA_HOME": "/x/d"}, home)
    assert cfg == Path("/x/c") / s.APP_NAME and data == Path("/x/d") / s.APP_NAME
    cfg, data = s.user_dirs("darwin", {}, home)
    assert cfg == data == home / "Library" / "Application Support" / s.APP_NAME
    cfg, data = s.user_dirs("win32", {"APPDATA": "C:/R", "LOCALAPPDATA": "C:/L"}, home)
    assert cfg == Path("C:/R") / s.APP_NAME and data == Path("C:/L") / s.APP_NAME


def test_profile_discovery():
    empty, root = TMP / "roots" / "empty", TMP / "roots" / "tb"
    empty.mkdir(parents=True)
    for name in ("old.default", "new.default-release"):
        (root / "Profiles" / name).mkdir(parents=True)
    legacy = (
        "[Profile0]\nName=old\nIsRelative=1\nPath=Profiles/old.default\nDefault=1\n\n"
        "[Profile1]\nName=new\nIsRelative=1\nPath=Profiles/new.default-release\n\n"
    )
    (root / "profiles.ini").write_text(legacy, encoding="utf-8")
    assert s.find_profile("", [empty, root]) == root / "Profiles" / "old.default"
    # The Install section names the profile this installation opens and wins over Default=1.
    (root / "profiles.ini").write_text(
        legacy + "[InstallABC123]\nDefault=Profiles/new.default-release\nLocked=1\n", encoding="utf-8")
    assert s.find_profile("", [empty, root]) == root / "Profiles" / "new.default-release"
    assert s.find_profile(str(PROFILE)) == PROFILE, "a configured profile must be used as given"
    exits(lambda: s.find_profile("", [empty]), "no Thunderbird profile")
    exits(lambda: s.find_profile(str(TMP / "missing")), "not found")
    home = Path("/home/u")
    linux = s.profile_roots("linux", {}, home)
    assert linux[0] == home / ".thunderbird" and len(linux) == 3
    assert s.profile_roots("darwin", {}, home) == [home / "Library" / "Thunderbird"]
    assert s.profile_roots("win32", {"APPDATA": "C:/R"}, home) == [Path("C:/R") / "Thunderbird"]


def test_init_and_bundled_example():
    target = TMP / "fresh" / "config.toml"
    exits(lambda: s.load_config(target), "--init")
    assert s.init_config(target) == (target, True) and target.is_file()
    target.write_text(target.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    assert s.init_config(target) == (target, False), "--init must not replace an existing config"
    assert "# edited" in target.read_text(encoding="utf-8")
    cfg = s.load_config(target)
    assert cfg["exclude"]["folders"][:3] == ["trash", "spam", "junk"] and cfg["exclude"]["whole_thread"] is True
    assert cfg["profile"] == "" and cfg["thunderbird_exe"] == ""
    assert cfg["attachment_dirs"] == [], "attachments must ship switched off"
    s.Exclusions(cfg["exclude"])  # every pattern in the bundled example compiles


def test_executable_lookup():
    exe = TMP / "bin" / ("thunderbird.exe" if sys.platform == "win32" else "thunderbird")
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    exe.chmod(0o755)
    assert s.thunderbird_exe({"thunderbird_exe": str(exe)}) == exe
    raises(lambda: s.thunderbird_exe({"thunderbird_exe": str(TMP / "bin" / "absent")}), "not found")
    home = Path("/home/u")
    assert s.exe_candidates(sys.platform, {"PATH": str(exe.parent)}, home)[0] == exe, "PATH must come first"
    assert Path("/usr/bin/thunderbird") in s.exe_candidates("linux", {}, home)
    assert home / "Applications" / "Thunderbird.app" / "Contents" / "MacOS" / "thunderbird" in s.exe_candidates("darwin", {}, home)
    win = s.exe_candidates("win32", {"ProgramFiles": "D:/Apps"}, home)
    assert win[0] == Path("D:/Apps") / "Mozilla Thunderbird" / "thunderbird.exe" and len(win) == 2


READ_ONLY = [
    test_mork_groups_and_removals,
    test_visible_set_follows_summary,
    test_excluded_mail_leaves_no_text,
    test_search_ignores_accents_and_filters,
    test_message_text_and_html,
    test_thread,
    test_attachments,
]
MUTATING = [
    test_new_arrival_then_summary_update,
    test_compaction_moves_offsets,
    test_rule_change_rebuilds_index,
    test_query_sanitising,
    test_compose_arguments,
    test_compose_attachment_rules,
    test_compose_tool_with_attachments,
    test_audit_log_has_no_mail_text,
]
PLATFORM = [
    test_user_dirs_per_platform,
    test_profile_discovery,
    test_init_and_bundled_example,
    test_executable_lookup,
]


def run(test) -> bool:
    try:
        test()
        print(f"PASS {test.__name__}")
        return True
    except Exception:
        print(f"FAIL {test.__name__}")
        traceback.print_exc()
        return False


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    setup_fixture()
    before = snapshot()
    results = [run(t) for t in READ_ONLY]
    untouched = snapshot() == before
    print(f"{'PASS' if untouched else 'FAIL'} test_profile_never_written")
    results.append(untouched)
    results += [run(t) for t in MUTATING]
    results += [run(t) for t in PLATFORM]
    if s._index is not None:
        s._index.db.close()
    shutil.rmtree(TMP, ignore_errors=True)
    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
