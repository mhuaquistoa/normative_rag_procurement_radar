"""Phase 2 - fragments. A fragment never crosses a page, so its citation is exact.

Paragraphs of one page are packed up to `size` characters; a paragraph longer than that is split at
sentence ends. Consecutive fragments of a page share `overlap` characters (whole sentences).
Each fragment knows the article it belongs to (the last "Artículo N." heading seen so far in the
document, also across page breaks), which is shown in citations and used by the version logic.
ID = <documento>:p<page>:c<n> - unique across documents and stable between runs; `hash` detects a
changed text under the same ID.
"""
import hashlib
import json
import re

from config import path, sources

ARTICLE = re.compile(r"^[\"“]?Art[ií]culo\s+(\d{1,3}(?:-[A-Z])?)\s*\.\s*([^\n]{0,90})", re.M)
SENTENCE_END = re.compile(r"(?<=[.;:])\s+(?=[A-ZÁÉÍÓÚÑ“\"(\d])")


def load_pages(doc_id: str) -> list:
    with open(path("processed") / f"{doc_id}.jsonl", encoding="utf-8") as f:
        return [r for r in map(json.loads, f) if not r["descartada"]]


def _pieces(paragraph: str, size: int) -> list:
    if len(paragraph) <= size:
        return [paragraph]
    out, cur = [], ""
    for s in SENTENCE_END.split(paragraph):
        while len(s) > size:  # a single sentence longer than size: hard cut
            out.append(s[:size]); s = s[size:]
        if cur and len(cur) + 1 + len(s) > size:
            out.append(cur); cur = s
        else:
            cur = f"{cur} {s}".strip()
    return out + ([cur] if cur else [])


def _tail(text: str, overlap: int) -> str:
    """Last whole sentences of `text` adding up to at most `overlap` characters."""
    if overlap <= 0:
        return ""
    keep = ""
    for s in reversed(SENTENCE_END.split(text)):
        if len(keep) + len(s) + 1 > overlap:
            break
        keep = f"{s} {keep}".strip()
    return keep


def chunk_document(source: dict, size: int, overlap: int) -> list:
    chunks, article = [], None
    for page in load_pages(source["id"]):
        paragraphs = [p.strip() for p in page["texto"].split("\n") if p.strip()]
        pieces = [x for p in paragraphs for x in _pieces(p, size)]
        packs, cur, starts = [], "", []
        art_at = []
        for x in pieces:
            m = ARTICLE.match(x)
            if cur and len(cur) + 1 + len(x) > size:
                packs.append(cur); art_at.append(starts)
                cur = (_tail(cur, overlap) + " " + x).strip() if overlap else x
                starts = []
            else:
                cur = f"{cur}\n{x}".strip()
            if m:
                starts.append(f"{m.group(1)}. {m.group(2).strip()}".strip(" .") if m.group(2) else m.group(1))
        if cur:
            packs.append(cur); art_at.append(starts)
        for n, (text, arts) in enumerate(zip(packs, art_at)):
            # the fragment belongs to the article in force where it starts: its own heading if it opens
            # with one, else the last heading seen before it (possibly on an earlier page)
            current = arts[0] if arts and ARTICLE.match(text) else article
            article = arts[-1] if arts else article
            chunks.append({
                "id": f"{source['id']}:p{page['pagina']}:c{n}",
                "texto": text,
                "documento": source["id"], "titulo": source["titulo"], "tipo": source["tipo"],
                "version": source["version"], "fecha_version": source["fecha_version"],
                "pagina": page["pagina"], "pagina_diario": page["pagina_diario"] or 0,
                "articulo": current or "", "articulos_en_fragmento": "; ".join(arts),
                "ambito": "reglamento" if source["tipo"] == "decreto_modificatorio" else "ley",
                "chars": len(text), "hash": hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]})
    return chunks


def chunk_all(size: int, overlap: int) -> list:
    return [c for s in sources() for c in chunk_document(s, size, overlap)]
