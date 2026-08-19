"""
Corpus access + hybrid retrieval over the parsed Basel Framework.

Retrieval is deliberately hybrid because regulatory language is *lexically
precise but semantically diffuse*: a query like "how much capital must be held
against undrawn credit card lines" must match both the literal term
("credit conversion factor") and paraphrases that never use it.

  - BM25            -> exact regulatory terms of art
  - TF-IDF + SVD    -> latent-semantic recall (LSA), no external model needed
  - RRF fusion      -> rank-level combination, scale-free

The dense side is pluggable: `HybridRetriever(dense=...)` accepts any object
exposing `encode(list[str]) -> np.ndarray`, so a sentence-transformer or an API
embedder can be dropped in without touching callers.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

DEFAULT_CORPUS = Path("data/basel/paragraphs.jsonl")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")


@dataclass
class Para:
    para_id: str
    standard: str
    chapter: str
    chapter_title: str
    heading_path: list[str]
    text: str
    page: int
    block_type: str
    footnotes: list[str]
    faqs: list[str]
    is_tabular: bool

    @property
    def citation(self) -> str:
        return f"{self.para_id} ({self.chapter} — {self.chapter_title}, p.{self.page})"

    def context(self, with_notes: bool = True) -> str:
        parts = [f"[{self.para_id}] {' > '.join(self.heading_path)}", self.text]
        if with_notes and self.footnotes:
            parts.append("Footnotes: " + " ".join(self.footnotes))
        if with_notes and self.faqs:
            parts.append("FAQ: " + " ".join(self.faqs))
        return "\n".join(parts)


def load_corpus(path: Path = DEFAULT_CORPUS) -> list[Para]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        out.append(Para(
            para_id=d["para_id"], standard=d["standard"], chapter=d["chapter"],
            chapter_title=d["chapter_title"], heading_path=d["heading_path"],
            text=d["text"], page=d["page"], block_type=d["block_type"],
            footnotes=d.get("footnotes", []), faqs=d.get("faqs", []),
            is_tabular=d.get("is_tabular", False),
        ))
    return out


def tokenize(s: str) -> list[str]:
    return TOKEN_RE.findall(s.lower())


class HybridRetriever:
    def __init__(self, paras: list[Para], dense=None, n_components: int = 256):
        self.paras = paras
        self._docs = [p.context() for p in paras]
        self.bm25 = BM25Okapi([tokenize(d) for d in self._docs])

        self.tfidf = TfidfVectorizer(
            lowercase=True, sublinear_tf=True, ngram_range=(1, 2),
            min_df=2, max_df=0.6, stop_words="english",
        )
        X = self.tfidf.fit_transform(self._docs)
        k = min(n_components, X.shape[1] - 1, X.shape[0] - 1)
        self.svd = TruncatedSVD(n_components=k, random_state=0)
        self.emb = normalize(self.svd.fit_transform(X))
        self.dense = dense
        if dense is not None:
            self.emb = normalize(np.asarray(dense.encode(self._docs)))

    def _dense_scores(self, query: str) -> np.ndarray:
        if self.dense is not None:
            q = normalize(np.asarray(self.dense.encode([query])))
        else:
            q = normalize(self.svd.transform(self.tfidf.transform([query])))
        return (self.emb @ q.T).ravel()

    def search(self, query: str, k: int = 12, chapters: list[str] | None = None,
               rrf_k: int = 60) -> list[tuple[Para, float, dict]]:
        """Reciprocal-rank fusion of BM25 and latent-semantic rankings."""
        lex = np.asarray(self.bm25.get_scores(tokenize(query)))
        sem = self._dense_scores(query)

        mask = np.ones(len(self.paras), dtype=bool)
        if chapters:
            allow = set(chapters)
            mask = np.array([p.chapter in allow or p.standard in allow for p in self.paras])
            lex = np.where(mask, lex, -np.inf)
            sem = np.where(mask, sem, -np.inf)

        rank_lex = _ranks(lex)
        rank_sem = _ranks(sem)
        fused = 1.0 / (rrf_k + rank_lex) + 1.0 / (rrf_k + rank_sem)
        fused = np.where(mask, fused, -np.inf)

        order = np.argsort(-fused)[:k]
        return [(self.paras[i], float(fused[i]),
                 {"bm25": float(lex[i]), "semantic": float(sem[i]),
                  "rank_bm25": int(rank_lex[i]), "rank_sem": int(rank_sem[i])})
                for i in order]


def _ranks(scores: np.ndarray) -> np.ndarray:
    order = np.argsort(-scores)
    r = np.empty(len(scores), dtype=float)
    r[order] = np.arange(1, len(scores) + 1)
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description="Query the parsed Basel corpus.")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--search")
    ap.add_argument("--chapters", help="comma-separated chapter/standard filter, eg CRE20,LCR40")
    ap.add_argument("--ids", help="comma-separated paragraph ids to dump verbatim")
    ap.add_argument("--chapter-dump", help="dump every paragraph of a chapter")
    ap.add_argument("-k", type=int, default=12)
    ap.add_argument("--full", action="store_true", help="print full text, not a preview")
    args = ap.parse_args()

    paras = load_corpus(Path(args.corpus))

    if args.ids:
        want = [s.strip() for s in args.ids.split(",")]
        idx = {p.para_id: p for p in paras}
        for w in want:
            p = idx.get(w)
            print(f"\n===== {w} =====")
            print(p.context() if p else "  NOT FOUND")
        return

    if args.chapter_dump:
        for p in paras:
            if p.chapter == args.chapter_dump:
                print(f"\n===== {p.para_id} | {' > '.join(p.heading_path)} =====")
                print(p.context())
        return

    if args.search:
        chapters = [c.strip() for c in args.chapters.split(",")] if args.chapters else None
        r = HybridRetriever(paras)
        for p, score, dbg in r.search(args.search, k=args.k, chapters=chapters):
            print(f"\n[{score:.5f}] {p.citation}  (bm25 #{dbg['rank_bm25']}, sem #{dbg['rank_sem']})")
            print("  " + (" > ".join(p.heading_path))[:100])
            print("  " + (p.text if args.full else p.text[:300]))
        return

    print(f"{len(paras)} paragraphs; standards: "
          f"{sorted({p.standard for p in paras})}")


if __name__ == "__main__":
    main()
