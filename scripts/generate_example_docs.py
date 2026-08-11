"""Generates docs/handbook.pdf from plain text, using only pypdf (already a
project dependency) — no extra PDF-authoring library needed.

    uv run python scripts/generate_example_docs.py

Re-run any time HANDBOOK_PAGES below is edited; the output is checked in so a
fresh clone has example RAG content without running this first.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "handbook.pdf"

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN = 72
FONT_SIZE = 11
LEADING = 16
WRAP_WIDTH = 92  # characters; Helvetica 11pt fits ~92 chars in a 612pt page with 72pt margins

# Each entry is one PDF page. Blank strings render as blank lines, which is
# what gives the "Section" headings visual breathing room.
HANDBOOK_PAGES: list[list[str]] = [
    [
        "Acme Robotics — Support Handbook",
        "",
        "This handbook is the source of truth for support policy. Front Desk",
        "associates do not have access to this document; the Support Manager",
        "tier and above do, via the RAG knowledge base.",
        "",
        "Section 1: Returns & Refunds",
        "",
        "- Standard return window: 30 days from the delivery date, for all",
        "  hardware purchased directly from acme.com.",
        "- Acme Pro subscribers (see Section on subscriptions) receive an",
        "  extended 45-day return window on hardware purchases.",
        "- Returns require an RMA number. Request one by emailing",
        "  returns@acme.com or through the RMA tool at acme.com/returns.",
        "- Refunds are issued to the original payment method within 5-7",
        "  business days of the warehouse receiving the returned item.",
        "- Custom-configured RoboArm X9 units are FINAL SALE once assembled",
        "  and are not eligible for return.",
    ],
    [
        "Section 2: Warranty Coverage",
        "",
        "- All Acme Robotics hardware ships with a 2-year limited warranty",
        "  covering manufacturing defects.",
        "- The RoboArm X9 and RoboArm X9 Pro extend to a 3-year warranty",
        "  when registered within 30 days of purchase at acme.com/register.",
        "- Warranty claims require a claim code in the format ARW-#####",
        "  (five digits). Claim codes are issued after a diagnostic call",
        "  with support — customers cannot self-issue one.",
        "- Water damage, drops, and unauthorized firmware modifications",
        "  void the warranty immediately.",
        "- Battery packs are covered for 1 year only, regardless of the",
        "  hardware's warranty term.",
    ],
    [
        "Section 3: Hardware Troubleshooting Codes",
        "",
        "- Error E-101 (Motor calibration failure): hold the RESET button",
        "  for 10 seconds until the LED blinks blue, then re-run calibration",
        "  from the companion app. Front Desk and Manager can both walk a",
        "  customer through this.",
        "- Error E-204 (Battery communication fault): reseat the battery",
        "  pack. If the code persists after 3 attempts, the battery",
        "  requires replacement under warranty.",
        "- Error E-317 (Firmware checksum mismatch): reflash firmware via",
        "  USB-C using the Acme Recovery Tool. Do not attempt this over",
        "  Wi-Fi — an interrupted OTA update is what causes this error in",
        "  the first place.",
        "- Error E-450 (Joint overcurrent protection tripped): power cycle",
        "  the unit. If it recurs within 24 hours, stop use and contact",
        "  support — this can indicate a mechanical obstruction.",
    ],
    [
        "Section 4: When to Escalate",
        "",
        "- Front Desk associates handle order status, general policy",
        "  questions, and basic troubleshooting (E-101, E-204).",
        "- Support Managers have access to the order and RMA systems and",
        "  additionally handle E-317 and E-450 codes, plus policy",
        "  exceptions up to $200.",
        "- The VP of Customer Success can authorize policy exceptions",
        "  above $200, coordinate with engineering on recurring hardware",
        "  faults, and search the live web for parts availability and",
        "  compatibility questions.",
        "- Escalations reaching the CEO's office are reserved for cases",
        "  requiring executive judgment, PR-sensitive situations, or a",
        "  problem that has already failed to resolve at every lower tier.",
    ],
]


def _wrap(line: str, width: int) -> list[str]:
    if not line:
        return [""]
    words = line.split(" ")
    wrapped: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            wrapped.append(current)
            current = word
        else:
            current = candidate
    if current:
        wrapped.append(current)
    return wrapped


def _escape(text: str) -> str:
    # Base-14 Helvetica with the PDF default encoding only covers Latin-1;
    # normalize the handful of typographic characters used above (em dash) to
    # plain ASCII rather than letting them silently become "?" at encode time.
    ascii_safe = text.replace("—", "--").replace("–", "-")
    return ascii_safe.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(lines: list[str]) -> bytes:
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(_wrap(line, WRAP_WIDTH))

    top = PAGE_HEIGHT - MARGIN
    ops = ["BT", f"/F1 {FONT_SIZE} Tf", f"{LEADING} TL", f"{MARGIN} {top} Td"]
    for i, line in enumerate(wrapped):
        if i > 0:
            ops.append("T*")
        ops.append(f"({_escape(line)}) Tj")
    ops.append("ET")
    return "\n".join(ops).encode("latin-1", errors="replace")


def _add_text_page(writer: PdfWriter, lines: list[str]) -> None:
    page = writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)  # noqa: SLF001 - pypdf has no public "add raw object" API

    resources = page.get(NameObject("/Resources"))
    if resources is None:
        resources = DictionaryObject()
        page[NameObject("/Resources")] = resources
    resources[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): font_ref})

    writer._merge_content_stream_to_page(page, _content_stream(lines))  # noqa: SLF001


def main() -> None:
    writer = PdfWriter()
    for page_lines in HANDBOOK_PAGES:
        _add_text_page(writer, page_lines)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("wb") as f:
        writer.write(f)

    print(f"Wrote {OUTPUT_PATH} ({len(HANDBOOK_PAGES)} pages)")


if __name__ == "__main__":
    main()
