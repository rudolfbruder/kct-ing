"""MsgFactory: a fake Outlook email (.msg) as it arrives as evidence (Laravel: a model factory).

    MsgFactory().create(folder)       writes EV-04_..._SAMPLE.msg into folder, returns the path
    MsgFactory().make()               the .msg as bytes

What evidence emails tend to contain, with made-up data:
    - sender, To and Cc recipients, date, subject
    - a plain-text and an HTML body with a list, bold and red text
    - a thread of earlier emails quoted below the newest one (history=N), each
      with its Outlook From / Sent / To / Subject block
    - links to ServiceNow tickets, the audit portal and SharePoint (links=True)
    - inline screenshots spread over the thread (images=N, image001.png, ...)
    - attachments: a Word document (DocxFactory), an Excel workbook (ExcelFactory)
      and an approval email forwarded as an attachment (an .msg inside the .msg)

.msg is Outlook's binary format (an OLE compound file holding MAPI properties,
[MS-OXMSG]). It is written with extract-msg's OleWriter. Needs extract-msg,
python-docx, openpyxl and Pillow.
"""
from __future__ import annotations

import re
import struct
from html import escape as html_escape
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Union

from factories.docx_factory import DocxFactory
from factories.excel_factory import ExcelFactory
from factories.images import audit_log_screenshot, ticket_screenshot

# MAPI property types
PT_LONG, PT_SYSTIME, PT_UNICODE, PT_BINARY, PT_OBJECT = 0x0003, 0x0040, 0x001F, 0x0102, 0x000D
TO, CC = 1, 2


@dataclass
class Attachment:
    name: str = ""
    mime: str = "application/octet-stream"
    data: bytes = b""
    content_id: Optional[str] = None      # set for images shown inside the HTML body
    message: Optional["Email"] = None     # set for an email attached as an email


@dataclass
class Email:
    subject: str
    sender: Tuple[str, str]                         # (name, address)
    recipients: List[Tuple[str, str, int]]          # (name, address, TO or CC)
    date: datetime
    body: str
    html: Optional[str] = None
    attachments: List[Attachment] = field(default_factory=list)


SNOW = "https://servicenow.example.com/nav_to.do?uri=incident.do?sysparm_query=number="
PORTAL = "https://audit-portal.example.com/requests/CTL-IAM-0472"
SHAREPOINT = "https://example.sharepoint.com/sites/iam-ops/Evidence/2026-Q1"

AUDITOR = ("Auditor", "auditor@example.com")
ANNA = ("Anna Bak", "anna.bak@example.com")
MARK = ("Mark Pol", "mark.pol@example.com")
DESK = ("Service Desk", "servicedesk@example.com")
OPS = ("IAM Operations", "iam.ops@example.com")


@dataclass
class ThreadMessage:
    """One message of a thread, as quoted below the newest one."""
    sender: Tuple[str, str]
    to: List[Tuple[str, str]]
    date: datetime
    subject: str
    paragraphs: List[str]                 # HTML allowed: <b>, <a href>, <span style>
    images: List[str] = field(default_factory=list)   # content ids of inline images, in order


# Earlier messages, oldest first: (sender, to, subject, paragraphs). {link:...} marks are filled in below.
HISTORY = [
    (AUDITOR, [ANNA], "Evidence request CTL-IAM-0472",
     ["Hi Anna,", "Please send the evidence for the password resets of privileged accounts in 2026 Q1 "
      "(control CTL-IAM-0472). The request is in the {link:audit portal|PORTAL}.", "Thanks,<br>Auditor"]),
    (ANNA, [AUDITOR], "RE: Evidence request CTL-IAM-0472",
     ["Hi,", "We are pulling the ADX audit log extract and the ticket list from ServiceNow. "
      "You will get it by the end of the week.", "Anna"]),
    (AUDITOR, [ANNA], "RE: Evidence request CTL-IAM-0472",
     ["Thanks. Please also include the approval for emergency resets, for example "
      "{link:SD-105112|SNOW:SD-105112}.", "Auditor"]),
    (ANNA, [MARK], "FW: Evidence request CTL-IAM-0472",
     ["Mark, can you confirm you approved the emergency reset {link:SD-105112|SNOW:SD-105112}? "
      "Screenshot of the ticket below.", "Anna"]),
    (MARK, [ANNA, AUDITOR], "RE: Evidence request CTL-IAM-0472",
     ["Yes, approved on 19 February by email, I will forward it. "
      "<span style='color:red'>The reset was done before the verification call</span>, "
      "we are looking into that.", "Mark"]),
    (ANNA, [DESK], "Verification log for SD-105112",
     ["Hi Service Desk, please export the verification log for {link:SD-105112|SNOW:SD-105112} "
      "and {link:SD-104871|SNOW:SD-104871} to {link:the evidence folder|SHAREPOINT}.", "Thanks, Anna"]),
    (DESK, [ANNA], "RE: Verification log for SD-105112",
     ["Done, both logs are in the folder. SD-105112 shows the callback at 08:05, the reset at 08:04.",
      "Service Desk"]),
    (AUDITOR, [ANNA], "RE: Evidence request CTL-IAM-0472",
     ["Reminder: the deadline is 31 March.", "Auditor"]),
]


class MsgFactory:
    """A fake evidence email with a thread of earlier emails quoted below it.

        MsgFactory()                                  newest reply + 2 earlier emails, 1 image, links
        MsgFactory(history=6, images=4)               longer thread, screenshots spread over it
        MsgFactory(history=0, links=False, attachments=False)   a single plain email

    history:     number of earlier emails quoted below the newest one (0 to any number;
                 beyond the 8 written ones, reminders are added)
    images:      number of inline screenshots; the first sits in the newest email, the
                 others in earlier ones (Outlook names them image001.png, image002.png, ...)
    links:       ServiceNow ticket, audit portal and SharePoint links in the bodies
    attachments: attach the Word evidence, an Excel extract and a forwarded approval email
    """

    name = "EV-04_evidence_email_SAMPLE.msg"

    def __init__(self, history: int = 2, images: int = 1, links: bool = True, attachments: bool = True) -> None:
        self.history = max(0, history)
        self.images = max(0, images)
        self.links = links
        self.attachments = attachments

    def email(self) -> Email:
        """The fake email. Override or change it to vary the sample."""
        newest = datetime(2026, 3, 31, 14, 5, tzinfo=timezone.utc)
        earlier = self._earlier(newest)
        latest = ThreadMessage(
            sender=ANNA, to=[AUDITOR], date=newest,
            subject="RE: Evidence request CTL-IAM-0472 (SAMPLE)",
            paragraphs=[
                "Hi,",
                "As requested for control <b>CTL-IAM-0472</b> (password resets of privileged accounts, 2026 Q1), "
                "please find the evidence attached:",
                "<ul><li>EV-01: service desk tickets (Word)</li><li>EV-03: ADX audit log extract (Excel)</li>"
                "<li>the approval for the emergency reset of {link:SD-105112|SNOW:SD-105112} (attached email)</li></ul>",
                "<span style='color:red'><b>Note:</b> SD-105112 was executed one minute before verification</span>, "
                "see the screenshot below. All files are also in {link:the evidence folder|SHAREPOINT}.",
                "Kind regards,<br>Anna Bak<br>IAM Operations",
            ],
        )
        thread = [latest] + earlier                      # newest first, as in Outlook

        inline: List[Attachment] = []
        for number, message in zip(range(1, self.images + 1), self._image_slots(thread)):
            cid = f"image{number:03d}.png@01DB0000.SAMPLE"
            message.images.append(cid)
            ticket = "SD-105112" if number % 2 == 0 else "SD-104871"
            data = (audit_log_screenshot() if number == 1 else ticket_screenshot(ticket)).getvalue()
            inline.append(Attachment(f"image{number:03d}.png", "image/png", data, content_id=cid))

        attachments: List[Attachment] = []
        if self.attachments:
            attachments = [
                Attachment(DocxFactory.name, "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           DocxFactory().make()),
                Attachment(ExcelFactory.name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           ExcelFactory(rows=15).make()),
                Attachment(message=self._approval()),
            ]
        recipients = [(n, a, TO) for n, a in latest.to] + [(OPS[0], OPS[1], CC)]
        return Email(
            subject=latest.subject, sender=latest.sender, recipients=recipients, date=latest.date,
            body=self._plain(thread), html=self._html(thread), attachments=attachments + inline,
        )

    # --- thread --------------------------------------------------------------------

    def _earlier(self, newest: datetime) -> List[ThreadMessage]:
        """The first self.history messages of the conversation, returned newest first.

        The conversation is HISTORY in order, followed by reminders when more are asked for.
        Each message is about a day before the next one.
        """
        from datetime import timedelta

        conversation = list(HISTORY)
        for number in range(1, self.history - len(HISTORY) + 1):
            conversation.append((AUDITOR, [ANNA], "RE: Evidence request CTL-IAM-0472",
                                 [f"Reminder {number}: can you send the evidence?", "Auditor"]))
        chosen = conversation[:self.history]
        messages = []
        for age, (sender, to, subject, paragraphs) in enumerate(reversed(chosen), start=1):
            messages.append(ThreadMessage(
                sender=sender, to=list(to), subject=subject, paragraphs=list(paragraphs),
                date=newest - timedelta(days=age, hours=(age * 3) % 7, minutes=(age * 17) % 60),
            ))
        return messages

    @staticmethod
    def _image_slots(thread: List[ThreadMessage]):
        """Where the inline images go: newest message first, then each earlier one, round robin."""
        index = 0
        while True:
            yield thread[index % len(thread)]
            index += 1

    def _approval(self) -> Email:
        return Email(
            subject="Approval: emergency password reset SD-105112",
            sender=MARK, recipients=[(DESK[0], DESK[1], TO)],
            date=datetime(2026, 2, 19, 7, 58, tzinfo=timezone.utc),
            body="Hi,\n\nApproved. Please reset the password of adm_kvan, the user is locked out "
                 "before the quarter-end batch.\n\nMark Pol\nHead of IAM Operations",
        )

    def _link(self, text: str, html: bool) -> str:
        """Fill {link:label|TARGET} marks: an <a> in HTML, 'label <url>' in plain text (as Outlook does)."""
        def url(target: str) -> str:
            if target.startswith("SNOW:"):
                return SNOW + target[5:]
            return {"PORTAL": PORTAL, "SHAREPOINT": SHAREPOINT}[target]

        def replace(match) -> str:
            label, target = match.group(1), match.group(2)
            if not self.links:
                return label
            return f'<a href="{url(target)}">{label}</a>' if html else f"{label} <{url(target)}>"

        return re.sub(r"\{link:([^|}]+)\|([^}]+)\}", replace, text)

    @staticmethod
    def _who(people: List[Tuple[str, str]]) -> str:
        return "; ".join(f"{n} <{a}>" for n, a in people)

    def _html(self, thread: List[ThreadMessage]) -> str:
        parts = ["<html><body>"]
        for position, message in enumerate(thread):
            if position:
                # Outlook's reply separator and quoted header block.
                parts.append(
                    "<div style='border:none;border-top:solid #E1E1E1 1.0pt;padding:3.0pt 0 0 0'><p>"
                    f"<b>From:</b> {html_escape(self._who([message.sender]))}<br>"
                    f"<b>Sent:</b> {message.date.strftime('%A, %B %d, %Y %H:%M')}<br>"
                    f"<b>To:</b> {html_escape(self._who(message.to))}<br>"
                    f"<b>Subject:</b> {html_escape(message.subject)}</p></div>"
                )
            for paragraph in message.paragraphs:
                body = self._link(paragraph, html=True)
                parts.append(body if body.startswith("<ul>") else f"<p>{body}</p>")
            for cid in message.images:
                parts.append(f"<p><img src='cid:{cid}' width='600'></p>")
        parts.append("</body></html>")
        return "".join(parts)

    def _plain(self, thread: List[ThreadMessage]) -> str:
        lines: List[str] = []
        for position, message in enumerate(thread):
            if position:
                lines += ["", "________________________________",
                          f"From: {self._who([message.sender])}",
                          f"Sent: {message.date.strftime('%A, %B %d, %Y %H:%M')}",
                          f"To: {self._who(message.to)}",
                          f"Subject: {message.subject}", ""]
            for paragraph in message.paragraphs:
                text = re.sub(r"<li>", "- ", paragraph)
                text = re.sub(r"<br\s*/?>|</li>", "\n", text)
                text = re.sub(r"<[^>]+>", "", text)
                lines += [self._link(text, html=False).strip(), ""]   # links after tags are gone
            for cid in message.images:
                lines += [f"[cid:{cid}]", ""]
        return "\n".join(lines).strip() + "\n"

    def make(self, email: Optional[Email] = None) -> bytes:
        from io import BytesIO

        from extract_msg.ole_writer import OleWriter

        writer = OleWriter()
        # Named-property mapping; required by readers even when empty.
        writer.addEntry(["__nameid_version1.0"], storage=True)
        for stream in ("00020102", "00030102", "00040102"):
            writer.addEntry(["__nameid_version1.0", f"__substg1.0_{stream}"], data=b"")
        self._message(writer, [], email or self.email())
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def create(self, target: Union[str, Path], email: Optional[Email] = None) -> Path:
        """Write the email. target is a folder (the default name is used) or a file path."""
        path = Path(target)
        if path.suffix.lower() != ".msg":
            path = path / self.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.make(email))
        return path

    # --- MS-OXMSG writing ------------------------------------------------------------

    def _message(self, writer, base: list, email: Email) -> None:
        props = _Properties()
        to = [(n, a) for n, a, kind in email.recipients if kind == TO]
        cc = [(n, a) for n, a, kind in email.recipients if kind == CC]
        props.string(0x001A, "IPM.Note")
        props.string(0x0037, email.subject)
        props.string(0x0042, email.sender[0])
        props.string(0x0065, email.sender[1])
        props.string(0x0C1A, email.sender[0])
        props.string(0x0C1F, email.sender[1])
        props.string(0x5D01, email.sender[1])
        props.string(0x0E04, "; ".join(n for n, _ in to))
        props.string(0x0E03, "; ".join(n for n, _ in cc))
        props.string(0x1000, email.body)
        if email.html:
            props.binary(0x1013, email.html.encode("utf-8"))
        props.time(0x0039, email.date)
        props.time(0x0E06, email.date)
        headers = (
            f"From: {email.sender[0]} <{email.sender[1]}>\r\n"
            f"To: {', '.join(f'{n} <{a}>' for n, a in to)}\r\n"
            + (f"Cc: {', '.join(f'{n} <{a}>' for n, a in cc)}\r\n" if cc else "")
            + f"Subject: {email.subject}\r\n"
            f"Date: {email.date.strftime('%a, %d %b %Y %H:%M:%S %z')}\r\n"
            "MIME-Version: 1.0\r\n\r\n"
        )
        props.string(0x007D, headers)
        props.write(writer, base)

        for index, (name, address, kind) in enumerate(email.recipients):
            storage = base + [f"__recip_version1.0_#{index:08X}"]
            writer.addEntry(storage, storage=True)
            recipient = _Properties()
            recipient.string(0x3001, name)
            recipient.string(0x3002, "SMTP")
            recipient.string(0x3003, address)
            recipient.string(0x39FE, address)
            recipient.long(0x0C15, kind)
            recipient.write(writer, storage, header=b"\0" * 8)

        for index, attachment in enumerate(email.attachments):
            storage = base + [f"__attach_version1.0_#{index:08X}"]
            writer.addEntry(storage, storage=True)
            item = _Properties()
            item.long(0x0E21, index)
            if attachment.message is not None:
                item.long(0x3705, 5)  # ATTACH_EMBEDDED_MSG
                item.string(0x3001, attachment.message.subject)
                inner = storage + ["__substg1.0_3701000D"]
                writer.addEntry(inner, storage=True)
                self._message(writer, inner, attachment.message)
                item.fixed.append(((0x3701 << 16) | PT_OBJECT, struct.pack("<II", 0xFFFFFFFF, 4)))
            else:
                item.long(0x3705, 1)  # ATTACH_BY_VALUE
                item.string(0x3001, attachment.name)
                item.string(0x3704, attachment.name[:12])
                item.string(0x3707, attachment.name)
                item.string(0x370E, attachment.mime)
                if attachment.content_id:
                    item.string(0x3712, attachment.content_id)
                item.binary(0x3701, attachment.data)
            item.write(writer, storage, header=b"\0" * 8)

        counts = struct.pack("<IIII", len(email.recipients), len(email.attachments),
                             len(email.recipients), len(email.attachments))
        # Top-level message: 32-byte header; embedded message: 24 bytes.
        header = b"\0" * 8 + counts + (b"\0" * 8 if not base else b"")
        props.write_header(writer, base, header)


class _Properties:
    """One MAPI property set: fixed values go in __properties_version1.0, the rest in __substg1.0_ streams."""

    def __init__(self) -> None:
        self.fixed: List[Tuple[int, bytes]] = []
        self.streams: dict = {}

    def string(self, pid: int, text: str) -> None:
        data = text.encode("utf-16-le")
        self.streams[f"__substg1.0_{pid:04X}{PT_UNICODE:04X}"] = data
        self.fixed.append(((pid << 16) | PT_UNICODE, struct.pack("<II", len(data) + 2, 0)))

    def binary(self, pid: int, data: bytes) -> None:
        self.streams[f"__substg1.0_{pid:04X}{PT_BINARY:04X}"] = data
        self.fixed.append(((pid << 16) | PT_BINARY, struct.pack("<II", len(data), 0)))

    def long(self, pid: int, value: int) -> None:
        self.fixed.append(((pid << 16) | PT_LONG, struct.pack("<II", value, 0)))

    def time(self, pid: int, moment: datetime) -> None:
        ticks = int((moment - datetime(1601, 1, 1, tzinfo=timezone.utc)).total_seconds() * 10_000_000)
        self.fixed.append(((pid << 16) | PT_SYSTIME, struct.pack("<Q", ticks)))

    def write(self, writer, base: list, header: Optional[bytes] = None) -> None:
        for name, data in self.streams.items():
            writer.addEntry(base + [name], data=data)
        if header is not None:
            self.write_header(writer, base, header)

    def write_header(self, writer, base: list, header: bytes) -> None:
        entries = b"".join(struct.pack("<II", tag, 6) + value for tag, value in self.fixed)
        writer.addEntry(base + ["__properties_version1.0"], data=header + entries)
