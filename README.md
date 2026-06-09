# interview-me

An open-source AI interview portfolio. A FastAPI + LlamaIndex Workflows backend powers an identity-grounded, RAG-augmented interview avatar with streaming responses. Qdrant for hybrid vector search, DeepSeek for generation, and a dedicated embedding microservice for vector generation. Personal data lives in a separate [interview-me-data](https://github.com/myleshk/interview-me-data) repo.

## Tech Stack

| Layer | Tech |
|-------|------|
| API | FastAPI + Uvicorn |
| Orchestration | LlamaIndex Workflows (async, event-driven) |
| Vector Store | Qdrant (hybrid search) |
| LLM | DeepSeek (via OpenAI SDK, `https://api.deepseek.com/v1`) |
| Embeddings | Embedding microservice — `BAAI/bge-small-en-v1.5` (384-dim) |
| Frontend | *(coming soon)* Next.js / React / Vue |

## Project Structure

```
interview-me/
├── .github/workflows/            # CI/CD pipelines (optional later)
├── api/                          # The FastAPI "Modulith" Backend
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes_ai.py      # /v1/chat/completions (OpenAI-compatible)
│   │   │   ├── routes_admin.py   # /v1/health, /v1/metrics
│   │   │   └── routes_cv.py      # /v1/cv/download (static PDF)
│   │   ├── core/
│   │   │   ├── config.py         # Environment variables & Pydantic settings
│   │   │   ├── identity.py       # Loads core profile from data/identity.json
│   │   │   ├── security.py       # API Key / CORS validation
│   │   │   └── rate_limit.py     # Per-IP sliding window rate limiter
│   │   ├── ai/
│   │   │   ├── workflows.py      # LlamaIndex event-driven workflow
│   │   │   ├── qdrant.py         # Vector DB connection & queries (read-only)
│   │   │   └── prompts.py        # System prompt templates
│   │   └── main.py               # Wires the routers together
│   ├── Dockerfile                # Builds ONLY the Python backend
│   └── requirements.txt
├── indexer/                      # Standalone knowledge indexer → Qdrant
├── web/                          # Frontend (Next.js/React/Vue)
│   └── src/
├── embedding/                    # Embedding microservice (FastEmbed + FastAPI)
├── docker-compose.yml            # Local dev stack (API, embedding, Qdrant)
└── README.md
```

## Quick Start

### 1. Create a virtual environment & install deps

```bash
cd api/
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file inside the `api/` directory from the template:

```bash
cp api/.env.example api/.env
```

Edit the file — the only **required** value is your DeepSeek API key:

```env
DEEPSEEK_API_KEY=sk-your-key-here
```

All other values have sensible defaults (see `api/app/core/config.py`).

### 3. Start Qdrant (local Docker)

```bash
# From the project root
docker compose up -d qdrant
```

This exposes Qdrant at `localhost:6333` (REST) and `localhost:6334` (gRPC).

### 4. Run the API

```bash
# From the api/ directory
uvicorn app.main:app --reload
```

The server starts at `http://localhost:8000`.

### Alternative: Docker Compose (full stack)

```bash
docker compose up -d
```

This starts Qdrant, the embedding service, and the API backend.

### 5. Index your knowledge data

The indexer now lives in the top-level `indexer/` directory of this repo and
reads curated Markdown files from your separate data repo clone.

```bash
# From the project root
cd indexer
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
DATA_DIR=../../data/knowledge python main.py
```

If your data repo is cloned somewhere else, point `DATA_DIR` at that
`knowledge/` directory instead.

## API Endpoints

### `POST /v1/chat/completions`

**OpenAI-compatible** — works with LobeChat, ChatGPT-Next-Web, and any OpenAI SDK client.

Streaming (SSE):

```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"interview-me","messages":[{"role":"user","content":"What are your skills?"}],"stream":true}'
```

Non-streaming (JSON):

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"interview-me","messages":[{"role":"user","content":"What is your name?"}]}'
```

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "interview-me",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "My name is Myles Fang..."},
    "finish_reason": "stop"
  }]
}
```

> **Note:** The `model` field is echoed back for frontend compatibility but is
> not used for routing — the backend always uses its configured pipeline.
> Extra fields (`temperature`, `max_tokens`, etc.) are silently ignored.
> System messages from the client are stripped — identity is injected
> server-side.

### `GET /v1/health`

Liveness probe.

```bash
curl http://localhost:8000/v1/health
```

```json
{ "status": "ok", "model": "deepseek-v4-flash", "uptime_seconds": 42.5 }
```

### `GET /v1/metrics`

Basic usage metrics.

```bash
curl http://localhost:8000/v1/metrics
```

```json
{ "total_requests": 17, "uptime_seconds": 120.3, "model": "deepseek-v4-flash" }
```

### `POST /v1/debug/retrieve`

Run only the RAG retrieve step — see exactly which chunks Qdrant returns for a query, without calling the LLM.

```bash
curl -X POST http://localhost:8000/v1/debug/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query":"What projects have you worked on?","limit":5}'
```

```json
{
  "query": "What projects have you worked on?",
  "total_results": 3,
  "chunks": [
    {"source": "Professional_Profile.md", "text": "Myles operates on the principle..."},
    ...
  ]
}
```

### `GET /v1/cv/download`

Download the owner's CV as a PDF file. Place your PDF at `data/static/cv.pdf` (mounted from the [interview-me-data](https://github.com/myleshk/interview-me-data) repo).

```bash
curl -O http://localhost:8000/v1/cv/download
```

## How It Works

The RAG pipeline is an async LlamaIndex Workflow with two steps:

```
StartEvent → [retrieve] → RetrievedEvent → [synthesize] → StopEvent
```

| Step | What it does | Current status |
|------|-------------|----------------|
| **retrieve** | Embeds the query via the embedding service, searches Qdrant via hybrid search, returns relevant context chunks | Live |
| **synthesize** | Calls DeepSeek with identity-grounded system prompt + context, streams tokens | Live |

The **core identity** from ``data/identity.json`` (name, role, company, location) is loaded by ``app/core/identity.py`` and injected into the system prompt on every request — the model always knows who it represents and never fabricates personal details. In Docker, the file is mounted from the [data repo](https://github.com/myleshk/interview-me-data); for local dev, set ``DATA_DIR`` to point at your data repo clone.

The **rich knowledge base** lives in ``data/knowledge/*.md`` files (in the [interview-me-data](https://github.com/myleshk/interview-me-data) repo). The top-level ``indexer/`` component in this repo refreshes Qdrant from those files on every deploy without dropping the whole collection first — the workflow then retrieves relevant chunks at query time for skills, projects, experience, and bio.

## Configuration

All settings live in `api/app/core/config.py` and can be overridden via `.env` or environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | *(empty)* | **Required.** Your DeepSeek API key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI-compatible base URL |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | Model name |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant REST endpoint |
| `QDRANT_COLLECTION_NAME` | `interview_me` | Collection name |
| `QDRANT_API_KEY` | *(none)* | Qdrant API key (if auth is enabled) |
| `EMBEDDING_SERVICE_URL` | `http://embedding:8080` | Embedding service URL |
| `EMBEDDING_DIM` | `384` | Embedding dimension |
| `DATA_DIR` | *(auto)* | Path to data repo (identity.json + static/) |
| `API_KEY` | *(none)* | Optional bearer-token gate (leave empty to disable) |
| `ALLOWED_ORIGINS` | `["*"]` | CORS allowed origins |
| `RATE_LIMIT_REQUESTS` | `30` | Max requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window in seconds |
| `DEBUG` | `false` | Enable debug logging (shows chunk content + full system prompt) |

## Development Notes

### LlamaIndex Workflows: avoid `@property` on the Workflow class

The `llama-index-workflows` library validates steps by calling `inspect.getmembers()`, which eagerly evaluates Python `@property` descriptors. If you put a property (e.g., a lazy OpenAI client) on the `Workflow` subclass, it will be triggered during validation — potentially before credentials are loaded. Use a plain method (e.g., `_get_llm_client()`) instead.

```python
# DON'T — property triggers during inspect.getmembers
@property
def llm_client(self) -> AsyncOpenAI: ...

# DO — only called when explicitly invoked
def _get_llm_client(self) -> AsyncOpenAI: ...
```

## Roadmap

- [x] Wire Qdrant hybrid search into the `retrieve` step
- [x] Move identity to `data/identity.json` (core facts only)
- [x] Keep personal data in separate [interview-me-data](https://github.com/myleshk/interview-me-data) repo
- [x] Move indexing logic into top-level `indexer/`
- [ ] Add dense + sparse vector indexing via embedding service
- [ ] Conversation memory (session history)
- [ ] Frontend (Next.js / React / Vue)
- [ ] Kubernetes manifests for production deployment
- [ ] GitHub Actions CI/CD pipeline
