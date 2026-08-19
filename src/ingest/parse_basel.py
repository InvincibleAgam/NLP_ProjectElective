"""
Structure-aware parser for the BIS consolidated Basel Framework PDF.

The BIS export uses a stable visual grammar that we exploit instead of doing
naive text extraction:

    x ~  63, fs >= 13.5  -> section heading
    x ~  63, fs ~ 12     -> paragraph number in the left margin ("30.22")
    x >= 90              -> body text (indent depth encodes list nesting)
    fs < 10              -> superscript footnote marker (dropped)

Runs the PDF emits without positioning are re-inserted by ``pdf_lines`` before
any of this runs — see that module for why.

Output: one JSON record per Basel paragraph carrying the full citation path
(standard -> chapter -> heading stack -> paragraph id), so every downstream rule
can be traced back to verbatim source text.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

logging.disable(logging.CRITICAL)
from pypdf import PdfReader  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdf_lines import Line, calibrate_char_width, page_runs, reconstruct_lines, space_join  # noqa: E402

MARGIN_X_MAX = 80.0
HEADING_FS_MIN = 13.5
PARA_NUM_RE = re.compile(r"^(\d+)\.(\d+)$")
TOC_ENTRY_RE = re.compile(r"^([A-Z]{3})(\d{0,2})\s+(.*)$")
PAGE_HDR_RE = re.compile(r"^\d+\s*/\s*\d+$")
FOOTER_RE = re.compile(r"^Downloaded on |^\ufffd{6,}$")


@dataclass
class ChapterRef:
    standard: str
    standard_title: str
    chapter: str
    chapter_title: str
    start_page: int      # 0-based PDF index
    end_page: int = -1


@dataclass
class Paragraph:
    para_id: str                       # "CRE20.65"
    standard: str
    standard_title: str
    chapter: str
    chapter_title: str
    heading_path: list[str]
    text: str
    page: int                          # printed page number (1-based)
    block_type: str = "provision"      # provision | preamble | footnote | faq
    layout_lines: list[str] = field(default_factory=list)
    is_tabular: bool = False
    n_inferred_runs: int = 0           # runs re-inserted by hole-filling
    footnotes: list[str] = field(default_factory=list)
    faqs: list[str] = field(default_factory=list)


def parse_toc(reader: PdfReader, char_w: float, toc_pages=range(2, 7)) -> list[ChapterRef]:
    chapters: list[ChapterRef] = []
    cur_std = cur_std_title = ""
    for pi in toc_pages:
        if pi >= len(reader.pages):
            break
        for ln in reconstruct_lines(page_runs(reader.pages[pi]), char_w):
            page_run = max(ln.runs, key=lambda r: r.x)
            if not page_run.text.strip().isdigit() or page_run.x < 450:
                continue
            label = space_join(
                [r.text for r in sorted(ln.runs, key=lambda r: r.x)
                 if r is not page_run and set(r.text) != {"."}]
            )
            label = re.sub(r"[.\s]+$", "", label)
            m = TOC_ENTRY_RE.match(label)
            if not m:
                continue
            code, num, title = m.group(1), m.group(2), m.group(3).strip()
            if not num:
                cur_std, cur_std_title = code, title
                continue
            chapters.append(ChapterRef(
                standard=cur_std or code,
                standard_title=cur_std_title,
                chapter=f"{code}{num}",
                chapter_title=title,
                start_page=int(page_run.text) - 1,
            ))
    chapters.sort(key=lambda c: c.start_page)
    for i, c in enumerate(chapters):
        c.end_page = chapters[i + 1].start_page - 1 if i + 1 < len(chapters) else len(reader.pages) - 1
    return chapters


def _layout(runs) -> str:
    return " | ".join(f"{int(r.x)}:{r.text}" for r in sorted(runs, key=lambda r: r.x))


def _looks_tabular(layout_lines: list[str]) -> bool:
    multi = sum(1 for l in layout_lines if l.count("|") >= 2)
    return len(layout_lines) >= 3 and multi >= max(2, len(layout_lines) // 2)


def parse_chapter(reader: PdfReader, ch: ChapterRef, char_w: float) -> list[Paragraph]:
    paras: list[Paragraph] = []
    heading_stack: list[tuple[float, str]] = []
    cur: Paragraph | None = None
    block_type = "provision"
    annot: str | None = None           # collecting "Footnotes"/"FAQ" for `cur`

    def flush():
        nonlocal cur
        if cur is not None and cur.text.strip():
            cur.text = space_join([cur.text])
            cur.footnotes = [space_join([" ".join(cur.footnotes)])] if cur.footnotes else []
            cur.faqs = [space_join([" ".join(cur.faqs)])] if cur.faqs else []
            paras.append(cur)
        cur = None

    def new_para(pid, text, printed, btype):
        return Paragraph(
            para_id=pid, standard=ch.standard, standard_title=ch.standard_title,
            chapter=ch.chapter, chapter_title=ch.chapter_title,
            heading_path=[h for _, h in heading_stack],
            text=text, page=printed, block_type=btype,
        )

    for pi in range(ch.start_page, min(ch.end_page + 1, len(reader.pages))):
        printed = pi + 1
        for ln in reconstruct_lines(page_runs(reader.pages[pi]), char_w):
            body = [r for r in ln.runs if r.fs >= 10]
            if not body:
                continue
            t = space_join([r.text for r in sorted(body, key=lambda r: r.x)])
            if not t or PAGE_HDR_RE.match(t) or FOOTER_RE.match(t):
                continue
            t = t.replace("\ufffd" * 38, " ").strip()
            if not t:
                continue
            if t.startswith("©") or t.startswith("Basel Committee on"):
                continue

            first = min(body, key=lambda r: r.x)
            in_margin = first.x <= MARGIN_X_MAX
            n_inf = sum(1 for r in body if r.inferred)

            # "Footnotes"/"FAQ" head their own indented block at x~100; they
            # annotate the paragraph above rather than continuing it.
            if first.x <= 110.0 and t in ("Footnotes", "FAQ", "FAQs"):
                annot = "footnotes" if t == "Footnotes" else "faqs"
                continue

            if annot and not in_margin:
                getattr(cur, annot).append(t) if cur is not None else None
                continue

            if in_margin and ln.fs >= HEADING_FS_MIN:
                flush()
                annot = None
                while heading_stack and heading_stack[-1][0] <= ln.fs:
                    heading_stack.pop()
                heading_stack.append((ln.fs, t))
                continue

            m = PARA_NUM_RE.match(first.text.strip()) if in_margin else None
            if m:
                flush()
                annot = None
                rest_runs = [r for r in body if r is not first]
                cur = new_para(f"{ch.standard}{m.group(1)}.{m.group(2)}",
                               space_join([r.text for r in sorted(rest_runs, key=lambda r: r.x)]),
                               printed, block_type)
                cur.layout_lines.append(_layout(rest_runs))
                cur.n_inferred_runs += n_inf
                continue

            if cur is not None:
                cur.text = (cur.text + " " + t).strip()
                cur.layout_lines.append(_layout(body))
                cur.n_inferred_runs += n_inf
            else:
                cur = new_para(f"{ch.chapter}#p{printed}", t, printed,
                               block_type if block_type != "provision" else "preamble")
                cur.layout_lines.append(_layout(body))
                cur.n_inferred_runs += n_inf
    flush()

    for p in paras:
        p.is_tabular = _looks_tabular(p.layout_lines)
    return paras


def main(pdf_path: str, out_path: str) -> None:
    reader = PdfReader(pdf_path)
    char_w = calibrate_char_width(reader, range(250, 330))
    print(f"calibrated char width: {char_w:.3f} pt/char", file=sys.stderr)

    chapters = parse_toc(reader, char_w)
    print(f"chapters: {len(chapters)}", file=sys.stderr)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = ninf = 0
    with out.open("w", encoding="utf-8") as fh:
        for ch in chapters:
            ps = parse_chapter(reader, ch, char_w)
            for p in ps:
                fh.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")
            n += len(ps)
            ninf += sum(p.n_inferred_runs for p in ps)
    print(f"blocks: {n}  (re-inserted runs: {ninf}) -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
