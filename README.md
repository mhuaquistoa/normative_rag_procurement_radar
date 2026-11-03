# Normative RAG and Public Procurement Radar

Two connected tools for a Peruvian small business (MYPE) that wants to sell to the State:

- **Task 1 — Normative RAG** (`tarea1_rag_normativo/`): answers "what does the law say?" only from the
  official texts, cites document and page, and abstains when the answer is not in the corpus.
- **Task 2 — Procurement Radar** (`tarea2_radar/`): "what is the State buying, and where?" over OECE
  open contracting data.

Work in progress — this README is completed as each phase lands.

## Task 1 · Phase 1 · Source check

Run before building anything (`python tarea1_rag_normativo/src/source_check.py`):

| Document | Pages | Characters | Chars/page (median, min–max) | Pages without text | Reading order | Usable as is |
|---|---|---|---|---|---|---|
| Ley N.° 32069 (text with amendments up to 2026-07-19) | 63 | 220,096 | 3,551 (1,238–4,273) | 0 | 0.990 | yes |
| DS N.° 001-2026-EF (modifies the Reglamento) | 16 | 112,477 | 6,977 (6,444–8,033) | 0 | 0.974 | yes |

*Reading order* = share of consecutive article headings that appear in ascending order. The few
backward steps are structural, not column-order errors: the Ley's final provisions cite "artículo 5"
of other norms; the decree's own articles 3–5 follow the Reglamento articles it quotes; page 16 of the
decree continues with an unrelated norm (cut during cleaning, see Phase 1).

Sources (official only, downloaded 2026-11-03, sha256 in `tarea1_rag_normativo/data/raw/sources.json`):
the Ley from the OECE collection on gob.pe; the decree from the MEF page on gob.pe, because
`busquedas.elperuano.pe` refused connections on 2026-11-03 (the gob.pe file is the El Peruano edition
of 8 January 2026, pages 33–48).
