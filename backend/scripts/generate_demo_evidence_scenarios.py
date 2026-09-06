"""Generate deterministic synthetic PDF assets for Evidence quality demos."""

from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "app/data/demo_files"

SCENARIOS = {
    "recent_revenue_summary_point_in_time_invalid_v1.pdf": [
        "CredAble Synthetic Demo Evidence",
        "Scenario: Point-in-time mismatch",
        "Business: Dodam Store (synthetic)",
        "Observed at: 2026-09-05",
        "Quality reference at: 2026-08-31",
        "This document is intentionally later than the policy cutoff.",
        "Demo only - not for an actual financial application.",
    ],
    "recent_revenue_summary_incomplete_v1.pdf": [
        "CredAble Synthetic Demo Evidence",
        "Scenario: Required item missing",
        "Business: Dodam Store (synthetic)",
        "Period: 2026-03 through 2026-08",
        "Monthly sales are present, but the required totals are omitted.",
        "Demo only - not for an actual financial application.",
    ],
    "recent_revenue_summary_tampered_v1.pdf": [
        "CredAble Synthetic Demo Evidence",
        "Scenario: Altered copy",
        "Business: Dodam Store (synthetic)",
        "The content differs from the trusted server reference hash.",
        "The server should stop automatic reassessment and request review.",
        "Demo only - not for an actual financial application.",
    ],
}


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 18 Tf", "72 760 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -34 Td")
            commands.append("/F1 12 Tf")
        commands.append(f"({_escape(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    content = bytearray(b"%PDF-1.4\n% CredAble synthetic demo\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode())
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(content)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for file_name, lines in SCENARIOS.items():
        (OUTPUT_DIR / file_name).write_bytes(_pdf(lines))


if __name__ == "__main__":
    main()
