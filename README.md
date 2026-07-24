# Local-RAG

**Chat with your documents, entirely offline.**

Local-RAG lets you upload files and ask questions about them. The system automatically prepares and indexes your documents so you can start asking right away. Because everything — from embeddings to retrieval to LLM inference — runs locally on your machine, your data never leaves it. Every answer includes inline citations so you can verify it against the source.

> **Status:** Early, functional prototype. It works, but it's a work in progress and not yet production-ready.

![Local-RAG Preview](preview.png)

## Features

- **Broad file support** — ingest PDF, DOCX, PPTX, XLSX, TXT, and images (PNG, JPEG, TIFF, BMP, GIF).
- **Structure-aware chunking** — convert with Docling, then split markdown with a custom heading- and table-aware chunker.
- **Automatic summaries** — generate document summaries on ingest via a map-reduce pipeline.
- **Streaming answers with citations** — stream responses token-by-token with inline `(filename)` citations, then extract and display the cited sources in a structured UI.
- **Safe re-ingestion** — detect filename conflicts and offer an overwrite/re-ingest workflow; re-ingesting creates fresh chunks and automatically removes stale vectors from earlier generations.
- **Async ingestion** — process uploads on a background job queue with heartbeat logging.
- **Prompt-injection hardening** — enforce a strict instruction hierarchy with angle-bracket neutralization and source-tag isolation.
- **Fully local** — no external API calls; all LLM inference, embeddings, and vector storage run on Ollama and Qdrant.

## Tech Stack

| Layer | Choice |
| --- | --- |
| Document processing | Docling conversion + custom markdown-aware chunking (PDF, DOCX, PPTX, XLSX, TXT, images) |
| LLM & embeddings | Ollama (local) — `gemma4:e4b` for chat, `bge-m3` for embeddings |
| Vector store | Qdrant (similarity search over document embeddings) |
| Metadata store | SQLite (async) for document state |
| Backend | Python 3.11, FastAPI (async), Uvicorn |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, TanStack React-Query |
| Deployment | Docker Compose (backend, frontend, Qdrant); Ollama runs separately as a local or reachable service |

## Architecture

**Ingestion flow**

```
Upload → Sanitize → Docling Conversion → Markdown Chunking
   ├→ Embed Chunks (Ollama) → Qdrant (Vector Store)
   └→ Summarize (LLM Map-Reduce) → SQLite (State Store)
```

**Chat flow**

```
User Query
    ↓
Embed Query (Ollama) → Vector Search (Qdrant, Top-K chunks)
    ↓
Build RAG Prompt (system prompt + retrieved chunks)
    ↓
Stream Tokens from LLM (Ollama) → SSE → Client
    ↓
[After all tokens streamed]
    ↓
Filter Cited Sources (validate which chunks were actually cited)
    ↓
Send Citations → SSE → Client (attaches to the completed answer)
    ↓
DONE
```

## Getting Started

### Prerequisites

Make sure you have the following installed:

- **Docker & Docker Compose** — runs Qdrant, the backend, and the frontend.
- **Ollama** — running locally or on a reachable network (models are pulled separately).
- **Python 3.11** — only if running the backend natively.
- **Node.js 18+ & npm** — only if running the frontend natively.

### 1. Pull the Ollama models

```bash
ollama pull bge-m3:latest
ollama pull gemma4:e4b
```

### 2. Start Ollama

Ensure the Ollama service is running (default `http://localhost:11434`):

```bash
ollama serve
```

### 3. Run Qdrant, backend & frontend with Docker (recommended)

```bash
# Clone the repo
git clone https://github.com/SirajSpark/local-rag.git
cd local-rag

# Configure environment
cp .env.example .env
# Edit .env if needed — defaults work for most setups.
# Ollama must be reachable at the URL in OLLAMA_BASE_URL.

# Build and start Qdrant + backend + frontend
docker compose up -d --build
```

Once it's up:

| Service | URL |
| --- | --- |
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

> **Note:** Ollama must be running on your host machine. The backend connects to it via `host.docker.internal`.

## Configuration

All options live in [`backend/app/core/config.py`](backend/app/core/config.py) and can be overridden via environment variables or a `.env` file.

| Variable | Default | Description |
| --- | --- | --- |
| `QDRANT_HOST` | `qdrant` | Qdrant host |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `QDRANT_COLLECTION` | `documents` | Qdrant collection |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama base URL (use `http://localhost:11434` when running the backend outside Docker) |
| `EMBEDDING_MODEL` | `bge-m3:latest` | Embedding model |
| `EMBEDDING_DIMENSIONS` | `1024` | Embedding vector size |
| `LLM_MODEL` | `gemma4:e4b` | LLM model |
| `LLM_TEMPERATURE` | `0.1` | Sampling temperature |
| `LLM_TOP_P` | `0.9` | Top-p sampling |
| `LLM_NUM_PREDICT` | `1024` | Max tokens to generate |
| `LLM_NUM_CTX` | `65536` | Model context window |
| `LLM_THINK` | `False` | Enable Ollama thinking mode |
| `CHUNK_MAX_TOKENS` | `512` | Max tokens per chunk |
| `CHUNK_MIN_CONTENT_LENGTH` | `120` | Minimum chunk content length |
| `TOP_K` | `8` | Number of nearest neighbours |
| `MIN_SCORE` | `0.35` | Minimum similarity score |
| `MAX_FILE_SIZE_MB` | `100` | Max upload size (MB) |
| `DB_PATH` | `data/state.db` | SQLite DB path |
| `TEMP_DIR` | `data/tmp` | Temporary files directory |
| `LLM_TIMEOUT` | `900` | LLM request timeout (seconds) |
| `EMBEDDING_TIMEOUT` | `600` | Embedding request timeout (seconds) |
| `SUMMARY_MAP_BATCH_SIZE` | `10` | Batch size for map-reduce summarisation |

## Backend Structure

```text
backend/
└─ app/
   ├─ main.py                 # FastAPI entry point; wires routers and dependencies
   ├─ deps.py                 # Shared dependency providers
   ├─ core/
   │   ├─ config.py           # Application settings (env vars / .env)
   │   ├─ exceptions.py       # Custom exception types
   │   └─ logging.py          # Logging configuration
   ├─ api/
   │   └─ routes/
   │       ├─ chat.py         # Chat query endpoint (SSE streaming)
   │       └─ ingest.py       # Upload, re-ingest, list, status, delete
   ├─ jobs/
   │   └─ queue.py            # Background ingestion job queue
   ├─ models/                 # Pydantic request/response schemas
   └─ services/
       ├─ rag_service.py         # Retrieval-augmented generation orchestration
       ├─ ingestion_service.py   # Parsing, chunking, summarisation
       ├─ docling_service.py     # Docling integration for parsing file types
       ├─ embedding_service.py   # Generate embeddings via Ollama
       ├─ llm_service.py         # LLM interaction via Ollama, streaming responses
       ├─ qdrant_service.py      # Qdrant vector store CRUD
       ├─ citation_service.py    # Extract and deduplicate citations
       └─ state.py               # Persistent document state (SQLite)
```

## API Endpoints

### Documents

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/documents/upload` | Upload a new document for ingestion |
| PUT | `/api/documents/{document_id}/reingest` | Replace and re-ingest an existing document |
| GET | `/api/documents` | List all documents with status |
| DELETE | `/api/documents/{document_id}` | Delete a document and its vector data |
| GET | `/api/documents/{document_id}/status` | Retrieve processing status of a document |

### Chat

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/chat/query` | Submit a question; returns SSE streaming tokens and citations |

## License

[MIT](LICENSE)
