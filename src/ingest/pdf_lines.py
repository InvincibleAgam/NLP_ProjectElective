"""
Line reconstruction for the BIS consolidated Basel Framework PDF.

The BIS export emits ~8% of its text runs with an identity text matrix, i.e. at
(0, 0) with no positioning.  These are not junk: they are the *bodies of
numbered sub-items* and the *second half of cross-reference ranges* — precisely
the operative text of the rules.  Naive extraction drops them to the end of the
page, which silently corrupts provisions such as CRE20.65.

They are, however, emitted in document order.  We therefore:

  1. attach every unpositioned run to the line of the most recent positioned run;
  2. estimate each positioned run's rendered width from a calibrated
     characters-per-point factor;
  3. locate the horizontal holes the missing runs were meant to occupy and drop
     them back in, left to right.

`calibrate_char_width` fits the factor on lines that have no unpositioned runs,
where consecutive runs are known to be truly adjacent.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

Y_TOL = 2.5
RIGHT_MARGIN = 522.0
MIN_HOLE_PT = 12.0


@dataclass
class Run:
    x: float
    y: float
    fs: float
    text: str
    positioned: bool = True
    inferred: bool = False


@dataclass
class Line:
    y: float
    runs: list[Run] = field(default_factory=list)

    @property
    def x0(self) -> float:
        return min(r.x for r in self.runs)

    @property
    def fs(self) -> float:
        return max(r.fs for r in self.runs)

    @property
    def first(self) -> Run:
        return min(self.runs, key=lambda r: r.x)

    def text(self) -> str:
        return space_join([r.text for r in sorted(self.runs, key=lambda r: r.x)])


def space_join(parts: list[str]) -> str:
    s = " ".join(p for p in parts if p)
    s = re.sub(r"\s+([.,;:%\)\]])", r"\1", s)
    s = re.sub(r"([\(\[])\s+", r"\1", s)
    s = re.sub(r"\s+’", "’", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def page_runs(page) -> list[Run]:
    """Text runs in PDF emission order (== document order)."""
    out: list[Run] = []

    def visitor(text, cm, tm, font_dict, font_size):
        t = text.strip()
        if not t:
            return
        x, y = round(tm[4], 1), round(tm[5], 1)
        out.append(Run(x, y, round(font_size or 0, 1), t, positioned=not (x == 0.0 and y == 0.0)))

    page.extract_text(visitor_text=visitor)
    return out


def calibrate_char_width(reader, sample_pages) -> float:
    """Points-per-character for 12pt body text, fitted on clean lines."""
    ratios: list[float] = []
    for pi in sample_pages:
        runs = page_runs(reader.pages[pi])
        if any(not r.positioned for r in runs):
            continue
        by_y: dict[float, list[Run]] = {}
        for r in runs:
            if r.fs < 10:
                continue
            key = next((k for k in by_y if abs(k - r.y) <= Y_TOL), r.y)
            by_y.setdefault(key, []).append(r)
        for ys, group in by_y.items():
            if len(group) < 2:
                continue
            group.sort(key=lambda r: r.x)
            for a, b in zip(group, group[1:]):
                span = b.x - a.x
                if span <= 0:
                    continue
                ratios.append(span / (len(a.text) + 1))
    return statistics.median(ratios) if ratios else 5.35


def reconstruct_lines(runs: list[Run], char_w: float) -> list[Line]:
    """Group runs into lines, re-inserting unpositioned runs into their holes."""
    lines: list[Line] = []
    index: dict[float, Line] = {}
    pending: dict[int, list[Run]] = {}
    last_line: Line | None = None

    def line_for(y: float) -> Line:
        for k, ln in index.items():
            if abs(k - y) <= Y_TOL:
                return ln
        ln = Line(y=y)
        index[y] = ln
        lines.append(ln)
        return ln

    for r in runs:
        if r.positioned:
            ln = line_for(r.y)
            ln.runs.append(r)
            last_line = ln
        else:
            if last_line is None:
                last_line = line_for(0.0)
            pending.setdefault(id(last_line), []).append(r)

    for ln in lines:
        orphans = pending.get(id(ln), [])
        if orphans:
            _fill_holes(ln, orphans, char_w)

    lines.sort(key=lambda l: -l.y)
    return lines


def _fill_holes(line: Line, orphans: list[Run], char_w: float) -> None:
    placed = sorted([r for r in line.runs if r.fs >= 10], key=lambda r: r.x)
    if not placed:
        for i, o in enumerate(orphans):
            o.x, o.y, o.inferred = 100.0 + i * 0.01, line.y, True
            line.runs.append(o)
        return

    # candidate holes: (gap_size, insert_x)
    holes: list[tuple[float, float]] = []
    for a, b in zip(placed, placed[1:]):
        end = a.x + len(a.text) * char_w
        gap = b.x - end
        if gap >= MIN_HOLE_PT:
            holes.append((gap, end))
    last = placed[-1]
    tail = RIGHT_MARGIN - (last.x + len(last.text) * char_w)
    if tail >= MIN_HOLE_PT:
        holes.append((tail, last.x + len(last.text) * char_w))

    # keep the widest holes, then restore left-to-right reading order
    holes.sort(key=lambda h: -h[0])
    chosen = sorted(h[1] for h in holes[: len(orphans)])

    for i, o in enumerate(orphans):
        o.y = line.y
        o.inferred = True
        if i < len(chosen):
            o.x = chosen[i] + 0.01 * i
        else:  # more orphans than holes -> append at the end, preserving order
            o.x = RIGHT_MARGIN + 1.0 + i
        line.runs.append(o)
