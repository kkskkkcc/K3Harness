# Self-Learning AI Agent

A local memory-augmented conversational agent built as an AI engineering learning
project. It learns by creating and retrieving durable memories; it does not
retrain or modify model weights during a conversation.

No OpenAI or Mem0 cloud API key is required. All model and memory processing runs
on your machine.

## Architecture

```text
User message
  -> Mem0 searches relevant long-term memories in Qdrant
  -> Ollama combines those memories with recent messages
  -> PostgreSQL stores the raw user and assistant messages

Finalize conversation
  -> Ollama summarizes the complete transcript as structured data
  -> PostgreSQL stores the validated summary for auditing
  -> only then is the summary sent to Mem0
  -> Mem0 stores the source-validated durable memory candidates
  -> Ollama creates local embeddings and Qdrant stores the vectors
```

The strict ordering matters: long-term memory is written only after the complete
conversation has been summarized. Raw messages and summaries remain separate
because summaries are useful but lossy.

## Technology choices

- FastAPI: HTTP API
- Ollama + Qwen: local answers and structured summaries
- Ollama + Nomic Embed Text: local embeddings
- Mem0 OSS: local vector-backed memory storage and retrieval
- Qdrant: Mem0's vector database
- PostgreSQL: conversations and auditable structured summaries
- Pydantic: validation of typed, structured LLM summaries
- SQLAlchemy + Alembic: persistence and migrations

## What is implemented

- Conversation creation, chat, and explicit finalization
- Retrieval of user-specific memories before each answer
- Complete-conversation summary generation before any memory write
- Exact message-ID provenance validation for summary candidates
- Source-validated memory addition plus user-scoped listing and deletion
- Local models and local persistence with no paid API calls

## Prerequisites

- Python 3.11+
- Docker Desktop
- [Ollama](https://ollama.com/download)

You do not need to clone another Git repository. Install Ollama, then download the
two free local models:

```powershell
ollama pull qwen3:1.7b
ollama pull nomic-embed-text:latest
```

qwen3:1.7b handles both chat and structured summaries for this learning project.
Qwen thinking is disabled, generation lengths are bounded, and Ollama releases
idle model memory after two minutes to keep laptop resource usage reasonable.

## Run the API locally

Install dependencies and create the environment file:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Start PostgreSQL and Qdrant:

```powershell
docker compose up -d db qdrant
```

Keep Ollama running, then migrate and start the API:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn self_learning_agent.api:app --reload
```

Open `http://localhost:8000` for the chat and memory interface. The API's interactive
documentation remains available at `http://localhost:8000/docs`.

The interface lets you create conversations, inspect recalled memories under each
answer, finalize a transcript so the agent can learn from its summary, list all
memories for the current identity, and delete memories you no longer want stored.

## Run the API in Docker

Ollama still runs on the Windows host; the Compose configuration connects to it
through host.docker.internal:

```powershell
docker compose up --build
```

## API walkthrough

Create a conversation:

```powershell
$conversation = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/v1/conversations `
  -ContentType application/json `
  -Body '{"user_id":"demo-user"}'
```

Send a message:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/v1/conversations/$($conversation.id)/messages" `
  -ContentType application/json `
  -Body '{"content":"I prefer science-fiction books and concise answers."}'
```

Finalize it. This creates the summary first and then stores validated long-term
memory candidates:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/v1/conversations/$($conversation.id)/finalize"
```

Start another conversation with the same user_id. Mem0 will retrieve relevant
preferences before Ollama generates the answer.

List or delete memories:

```powershell
Invoke-RestMethod http://localhost:8000/v1/users/demo-user/memories

Invoke-RestMethod `
  -Method Delete `
  -Uri http://localhost:8000/v1/users/demo-user/memories/MEM0_MEMORY_ID
```

## Tests and quality checks

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m pytest
```

Unit tests do not call Ollama or Mem0. An end-to-end chat test requires Ollama,
PostgreSQL, and Qdrant to be running.

## Known limitations

- The agent has no live web-search tool and should not be treated as a source of
  current facts.
- The lightweight local model can still make factual mistakes.
- Response and finalization speed depend on available CPU and RAM.

## Production boundaries

This is a development and portfolio baseline. Before exposing it publicly, add
authentication, derive user_id from the authenticated identity, introduce rate
limits and tracing, define retention/export controls, and build a retrieval
evaluation dataset. Pin the Qdrant container image to a tested version before a
production deployment.
