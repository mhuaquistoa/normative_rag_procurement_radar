# Pipelines (used in the video)

Shown before any code: what happens once (offline) and what happens on every question (online).

## Task 1 · Normative RAG

The page number is metadata attached when each PDF page is read; the abstention decision is the diamond "best similarity ≥ 0.82", before the LLM.

```mermaid
flowchart LR
  subgraph OFFLINE["Offline · build_index.py (once, or when a document changes)"]
    A[Official PDFs<br/>data/raw] --> B[Source check<br/>pages · chars · order]
    B --> C[Extract page by page<br/>page number attached here]
    C --> D[Clean R1-R4<br/>header · other norm · lines]
    D --> E[Fragments 1200/200<br/>never cross a page<br/>+ norm · article header]
    E --> F[Local embeddings<br/>multilingual-e5-large]
    F --> G[(ChromaDB<br/>vectors + metadata:<br/>documento · version · pagina · articulo)]
  end
  subgraph ONLINE["Online · engine.responder(pregunta)"]
    Q[Question] --> H[Embed query<br/>'query: ' prefix]
    H --> I[Top-5 fragments]
    G -.-> I
    I --> J{best similarity<br/>≥ 0.82?}
    J -- no --> K[Abstain · umbral<br/>LLM not called · USD 0]
    J -- yes --> L[DeepSeek, JSON mode<br/>only from fragments F1..F5]
    L --> M{abstener?}
    M -- yes --> N[Abstain · fuera_de_corpus<br/>or reglamento]
    M -- no --> O{valid citations?}
    O -- no --> P[Abstain · sin_citas]
    O -- yes --> R[Answer + sources<br/>doc · page · article · similarity<br/>+ version note + cost]
  end
  R & K & N & P --> S[Streamlit app.py<br/>and any other interface]
```

## Task 2 · Procurement Radar

The department is metadata (from the buyer address, normalized to 25 departments); numbers and places become exact filters, only the topic is semantic.

```mermaid
flowchart LR
  subgraph OFFLINE["Offline · build_index.py"]
    A[OECE bulk files<br/>monthly OCDS JSON<br/>2026-08..10] --> B[sha check<br/>skip if present]
    API[OECE API /releases<br/>recent updates only<br/>throttle · retry · cache] -.-> B
    B --> C[records → 1 row per ocid<br/>from compiledRelease]
    C --> D[Validation V1-V5<br/>duplicates · amount · description<br/>province vs department · accents]
    D --> E[(procesos.parquet<br/>+ quality report)]
    E --> F[Local embeddings of descriptions<br/>same e5-large as Task 1]
    F --> G[(ChromaDB<br/>vector = description<br/>metadata = departamento · monto ·<br/>fecha · categoria · comprador · ocid)]
    E --> H[Risk + aggregates<br/>data/outputs/*.csv]
  end
  subgraph ONLINE["Online · radar_engine.responder(pregunta)"]
    Q[Question] --> P[Rule parser]
    P -->|departamento · monto · categoría · mes| W[Exact filters 'where']
    P -->|remaining topic| S[Semantic query]
    W & S --> R[Top-8 inside the filters]
    G -.-> R
    R --> T{best ≥ 0.835?}
    T -- no --> X[Abstain · no LLM]
    T -- yes --> L[DeepSeek · cites every process by ocid]
  end
  E & H & G --> DASH[Streamlit dashboard<br/>KPIs · map · question box ·<br/>table · distribution · risk · quality]
  L --> DASH
```
