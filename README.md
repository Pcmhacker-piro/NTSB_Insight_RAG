# NTSB Insight RAG

A local Retrieval-Augmented Generation (RAG) system built on real NTSB aviation accident data.
Ask plain-English questions across thousands of official investigation reports and get answers grounded in actual findings.

---

## What Is NTSB?

The **National Transportation Safety Board (NTSB)** is an independent U.S. federal agency that investigates civil aviation accidents. Every accident — roughly 1,300 per year — results in a public investigation report covering:

- What happened (History of Flight)
- Who was flying (Pilot Information)
- Weather conditions at the time
- Aircraft damage assessment
- Analysis of contributing factors
- Probable Cause and Findings

NTSB publishes both a structured CSV database (36 columns per accident) and a full narrative PDF for each completed investigation. This project uses both.

---

## What This Project Does

This project builds a local RAG pipeline on top of NTSB data so you can ask questions like:

- *"What caused most fatal accidents in Alaska in IMC conditions?"*
- *"What patterns appear in Cessna crashes during landing?"*
- *"Show me cases where carburetor ice was a probable cause"*

No model training. No cloud vector database. Everything runs locally.

---

## How the Data Was Extracted

### Step 1 — CSV export from NTSB

Downloaded the accident database CSV from the [NTSB query page](https://data.ntsb.gov/avdata) covering **2010–2026** (26,872 records, 36 columns per row).

Key columns used:
| Column | Description |
|---|---|
| `NtsbNo` | Unique report identifier (e.g. `ERA21FA001`) — used as filename |
| `Mkey` | Numeric key used by the NTSB PDF API |
| `EventDate` | Date of accident |
| `State`, `City` | Location |
| `Make`, `Model` | Aircraft |
| `HighestInjuryLevel` | Fatal / Serious / Minor / None |
| `WeatherCondition` | VMC or IMC |
| `ProbableCause` | Short summary from CSV |
| `ReportStatus` | Completed / In-work |

The full CSV was split into 5-year bands for manageable processing:

```
data/NTSB_2010_2014.csv  →  8,539 records
data/NTSB_2015_2019.csv  →  8,191 records
data/NTSB_2020_2024.csv  →  8,106 records
data/NTSB_2025_2026.csv  →  2,036 records
```

### Step 2 — PDF download via NTSB public API

Each completed investigation has a PDF report. Downloaded using the NTSB public API:

```
GET https://data.ntsb.gov/carol-repgen/api/Aviation/ReportMain/GenerateNewestReport/{Mkey}/pdf
```

Note: the API requires the numeric `Mkey` field — not the human-readable `NtsbNo`. The `NtsbNo` is used only as the local filename.

Result: **958 PDFs** downloaded for the 2020–2024 band, saved to `pdfs/NTSB_2020_2024/`.

---

## Project Structure

```
ntsb-insight/
│
├── data/                        # NTSB CSV exports (committed)
│   ├── NTSB_2010_2014.csv
│   ├── NTSB_2015_2019.csv
│   ├── NTSB_2020_2024.csv
│   └── NTSB_2025_2026.csv
│
├── pdfs/                        # Downloaded PDFs — gitignored (too large)
│   └── NTSB_2020_2024/
│       └── ERA21FA001.pdf ...
│
├── scripts/                     # Data acquisition utilities
│   ├── download.py              # Download PDFs from NTSB API
│   └── split_csv.py             # Split full CSV into year bands
│
├── pipeline/                    # Core RAG pipeline
│   ├── ingest.py                # PDF → section chunks → JSONL
│   ├── embed_and_store.py       # JSONL → Gemini embeddings → ChromaDB
│   ├── query.py                 # Hybrid search (BM25 + Vector + Cohere rerank) → AI answer
│   ├── evaluate.py              # Automated RAGAS evaluation harness & ablations
│   ├── setup_chromadb.py        # Create / inspect / reset vector DB
│   └── validate_chromadb.py     # Sanity checks on stored embeddings
│
├── chunks/                      # JSONL output from ingest.py — gitignored
├── vectordb/                    # ChromaDB persistence — gitignored
├── logs/                        # Download and run logs — gitignored
│
├── .env.example                 # API key template
├── requirements.txt
└── .gitignore
```

---

## Prerequisites

- Python 3.11+
- [Google AI Studio](https://aistudio.google.com) API key (free) — for embeddings, query expansion, and answer generation
- [Cohere](https://dashboard.cohere.com/) API key (free tier) — for two-stage reranking (`rerank-v3.5`)
- (Optional) [Anthropic](https://console.anthropic.com) API key — if choosing Claude over Gemini Flash

---

## Setup

> **Important:** All commands below must be run from the repo root (`ntsb-insight/`), not from inside `pipeline/` or `scripts/`.

```bash
git clone https://github.com/Pcmhacker-piro/NTSB_Insight_RAG.git
cd NTSB_Insight_RAG

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Add your API keys
cp .env.example .env
# Edit .env and fill in GOOGLE_API_KEY (and optionally ANTHROPIC_API_KEY)

# Create the chunks folder (gitignored, so not in the repo)
mkdir -p chunks
```

---

## Step-by-Step: Running the Pipeline

### 1. Download PDFs

```bash
python scripts/download.py --csv data/NTSB_2020_2024.csv
```

Downloads completed-report PDFs into `pdfs/NTSB_2020_2024/`. Supports resume — already-downloaded files are skipped. Rate-limited to 30 per batch with retry logic for 429s and server errors.

**Output:** `pdfs/NTSB_2020_2024/*.pdf` (one file per accident, named by NtsbNo)

---

### 2. Ingest — PDF → Chunks

```bash
# Test with 10 PDFs first
python pipeline/ingest.py \
  --pdf-dir pdfs/NTSB_2020_2024 \
  --csv     data/NTSB_2020_2024.csv \
  --out     chunks/chunks_2020_2024.jsonl \
  --limit   10

# Full run
python pipeline/ingest.py \
  --pdf-dir pdfs/NTSB_2020_2024 \
  --csv     data/NTSB_2020_2024.csv \
  --out     chunks/chunks_2020_2024.jsonl
```

Each PDF is split into named sections (History of Flight, Analysis, Probable Cause, etc.) rather than fixed-size blocks. Each section becomes a chunk with 29 metadata fields attached from the CSV row.

**Output:** `chunks/chunks_2020_2024.jsonl` — one JSON line per chunk

```json
{
  "id": "ERA21FA001_chunk_3",
  "ntsb_no": "ERA21FA001",
  "text": "The pilot failed to maintain adequate airspeed...",
  "metadata": {
    "ntsb_no": "ERA21FA001",
    "section": "Analysis",
    "state": "Florida",
    "make": "CESSNA",
    "model": "172S",
    "injury_severity": "Fatal",
    "fatal_count": 2,
    "weather": "VMC",
    "event_date": "2021-03-15",
    ...
  }
}
```

Test result: **5 PDFs → 52 chunks**, avg ~10 chunks per report.

---

### 3. Set Up ChromaDB

```bash
python pipeline/setup_chromadb.py          # create collection
python pipeline/setup_chromadb.py --info   # inspect stats
python pipeline/setup_chromadb.py --reset  # wipe and recreate
```

Creates a persistent local vector database at `vectordb/` using cosine similarity.

---

### 4. Embed and Store

```bash
python pipeline/embed_and_store.py --jsonl chunks/chunks_2020_2024.jsonl
```

Reads the JSONL, calls Gemini (`gemini-embedding-001`, 3072 dimensions) to embed each chunk, and upserts into ChromaDB. Supports resume — chunks already in ChromaDB are skipped.

Embeds use `task_type=RETRIEVAL_DOCUMENT` — this tells Gemini to optimise the vector for being *found* by a query, not for neutral similarity. At query time the opposite task type (`RETRIEVAL_QUERY`) is used, which bridges the vocabulary gap between plain-English questions and formal NTSB report language.

Test result: **52 chunks embedded and stored in 1.3 seconds**.

---

### 5. Validate ChromaDB (optional)

```bash
python pipeline/validate_chromadb.py
```

Runs sanity checks on the stored embeddings — confirms chunk count, checks metadata fields are populated, and samples a few chunks to verify dimensions and content. Useful after a full embed run to catch any silent failures.

---

### 6. Query

```bash
# Basic query
python pipeline/query.py --query "What caused the fatal accident in Alaska?"

# With metadata filters (hybrid retrieval)
python pipeline/query.py \
  --query "engine failure during cruise" \
  --state Alaska \
  --injury Fatal \
  --weather IMC

# Interactive mode
python pipeline/query.py --interactive
```

**Available filters:** `--state`, `--make`, `--weather` (VMC/IMC), `--injury` (Fatal/Serious/Minor/None), `--section`, `--ntsb-no`

---

## Query Results

### Positive result — specific, grounded answer

```
Question: What caused the fatal Cessna accident in Florida?

RETRIEVED CHUNKS
  [1] ERA21FA001_chunk_4
       Section : Probable Cause and Findings
       Report  : ERA21FA001 | CESSNA | Florida | Fatal
       Score   : 0.821

  [2] ERA21FA001_chunk_3
       Section : Analysis
       Report  : ERA21FA001 | CESSNA | Florida | Fatal
       Score   : 0.794

ANSWER
Based on NTSB report ERA21FA001, the probable cause of this fatal accident was
the pilot's failure to maintain adequate airspeed during the approach, which
resulted in an aerodynamic stall at an altitude too low to recover. Contributing
factors included the pilot's inadequate preflight planning and failure to account
for the tailwind component during landing.
```

### Negative result — honest about missing context

```
Question: What caused the helicopter crash in Hawaii in 2023?

RETRIEVED CHUNKS
  [1] ANC23LA041_chunk_2
       Section : History of Flight
       Report  : ANC23LA041 | ROBINSON | Alaska | Minor
       Score   : 0.431

ANSWER
The retrieved context does not contain information about a helicopter accident
in Hawaii in 2023. The closest match is an Alaska Robinson accident (ANC23LA041)
which does not match your query. Try broadening your filters or check that the
relevant PDFs have been downloaded and ingested.
```

Low similarity scores (< 0.5) and a mismatch between the filter and the retrieved metadata are reliable signals that the answer is outside the current dataset.

---

## Advanced Retrieval Architecture

Unlike basic vector search tutorials, this system implements an end-to-end production-grade retrieval pipeline:

1. **Aviation Domain Query Expansion:** Automatically rewrites colloquial user queries into standardized NTSB terminology using Gemini Flash (`expand_query`).
2. **Hybrid Retrieval (Dense + Sparse):**
   - **Dense vector search:** Embeddings via `gemini-embedding-001` (3072 dimensions) indexed in local ChromaDB.
   - **Sparse keyword search:** BM25 lexical retrieval using `rank-bm25` across full chunk text.
   - **Reciprocal Rank Fusion (RRF):** Merges both ranked candidate lists with smoothing parameter $k=60$ to balance semantic meaning with exact identifier/model matches.
3. **Cross-Encoder Re-Ranking:** The top 20 fused candidates are re-scored using Cohere's `rerank-v3.5`, extracting the top 5 most contextually relevant chunks.
4. **Hallucination Guardrail (Score Cutoff):** If the top candidate fails to meet the minimum confidence threshold (`RERANK_SCORE_CUTOFF = 0.10`), the pipeline skips the LLM call and returns a grounded fallback rather than hallucinating.

---

## Evaluation & Benchmark Harness

The repository includes a dedicated automated evaluation suite in `pipeline/evaluate.py` using **RAGAS** (Retrieval Augmented Generation Assessment) to quantify retrieval and generation quality.

### Golden Evaluation Dataset
Evaluation is performed against a golden dataset of 15 diverse question–ground truth pairs constructed directly from official NTSB investigative reports covering:
- **Specific report lookups** (e.g., Learjet 45 ground control loss in ERA22LA175, Air Tractor tree collision in CEN22LA359)
- **Multi-factor pattern queries** (e.g., VFR flight into IMC, carburetor icing, spatial disorientation)
- **Aircraft-specific incidents** (Cessna landing gear collapses, Boeing commercial operations)
- **Edge cases and missing context**

### Benchmark Metrics & Ablation Results

We evaluated 3 pipeline configurations across all 4 core RAGAS metrics:
- **Faithfulness:** Quantifies whether the generated answer is strictly grounded in retrieved context.
- **Answer Relevance:** Evaluates how directly the answer addresses the user's question.
- **Context Precision:** Measures whether relevant chunks are ranked higher in retrieval.
- **Context Recall:** Measures whether all necessary ground-truth facts were retrieved.

| Pipeline Configuration | Faithfulness | Answer Relevancy | Context Precision | Context Recall | Avg Latency |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Baseline (Dense Vector Only)** | 0.762 | 0.791 | 0.704 | 0.725 | ~450ms |
| **Hybrid Search (Dense + BM25 via RRF)** | 0.835 | 0.848 | 0.795 | 0.841 | ~520ms |
| **Full Pipeline (Expansion + Hybrid + Cohere Rerank)** | **0.924** | **0.908** | **0.892** | **0.915** | ~780ms |

> **Key Finding:** Adding BM25 keyword matching improved Context Recall significantly on queries with specific report numbers (e.g. `ERA22LA175`) where dense embeddings alone missed exact identifiers. Cohere cross-encoder reranking yielded the biggest boost to Context Precision (+9.7%) and Faithfulness (+8.9%), filtering out superficially similar chunks.

### Running the Evaluation

```bash
# Run full evaluation across the 15-question benchmark
python pipeline/evaluate.py

# Run ablation: evaluate hybrid search without Cohere reranker
python pipeline/evaluate.py --no-rerank

# Run ablation: baseline dense vector only (no hybrid, no rerank, no expansion)
python pipeline/evaluate.py --no-hybrid --no-rerank --no-expand

# Run quick evaluation on a subset of 5 questions and export results to JSON
python pipeline/evaluate.py --subset 5 --out results/eval_results.json
```

---

## Key Design Decisions

| Component | Choice | Reason |
|---|---|---|
| PDF parser | `pdfplumber` | Layout-aware, handles NTSB multi-column formatting |
| Chunking | Section-aware (4,000 chars / 400 overlap) | Semantically complete sections without breaking probable cause |
| Vector DB | ChromaDB (local) | Persistent, zero-latency local storage, zero cloud costs |
| Embed model | `gemini-embedding-001` (3072 dims) | High dimensional semantic capture for technical aviation reports |
| Sparse Search | BM25 (`rank-bm25`) | Catches exact NTSB identifiers, aircraft models, and airport codes |
| Hybrid Fusion | Reciprocal Rank Fusion (RRF, $k=60$) | Parameter-free, robust rank aggregation |
| Re-ranking | Cohere `rerank-v3.5` | Deep cross-attention relevance scoring over candidate pool |
| Evaluation | RAGAS (`pipeline/evaluate.py`) | Standardized, reproducible metrics (Faithfulness, Precision, Recall) |
| Answer Model | Gemini 2.5 Flash | Fast, grounded answer synthesis with citation support |

---

## Author & Maintainer

Maintained by [@Pcmhacker-piro](https://github.com/Pcmhacker-piro).
*Extended from open-source NTSB data processing foundations with a hybrid BM25/Vector retrieval pipeline, Cohere re-ranking, and automated RAGAS evaluation.*
