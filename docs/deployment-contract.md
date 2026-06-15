# Deployment Contract Draft

This document translates the current local runtime into a GitOps-oriented
production deployment plan. The actual ArgoCD/config repo lives elsewhere, so
the YAML examples here define the contract that repo should implement.

Actual current config location:

- local checkout: `/Users/myles/projects/k0s-config/jp-3/interview-me`
- repo-relative target path: `jp-3/interview-me`

## Goals

- Keep the code repo public and the `data` repo private.
- Let the config repo be the single source of truth for deployed code and data versions.
- Reindex only when reindexing inputs change.
- Keep the API available even if indexing is delayed.
- Avoid giving GitHub Actions direct access to the VPS or cluster.

## Locked Decisions

- Config repo stores image tags only.
- Each image tag should match the source git commit hash.
- Config repo also stores the exact `data` repo commit hash.
- Qdrant stays as a single persistent collection for now.
- API availability is preferred over immediate freshness.
- Initial rollout should not block API deployment on indexer completion.

## Current Runtime Mapping

Local `docker-compose` currently maps cleanly to these production components:

- `api`: FastAPI app on port `8000`
- `embedding`: FastAPI embedding service on port `8080`
- `qdrant`: persistent vector database on ports `6333` and `6334`
- `indexer`: one-shot batch process that reads `knowledge/*.md` and writes to Qdrant

## Current ArgoCD Baseline

The existing config repo path `jp-3/interview-me` already contains flat manifest
files for the current deployment:

- `namespace.yaml`
- `configmap.yaml`
- `secret.yaml`
- `ssh-deploy-key.yaml`
- `api.yaml`
- `embedding.yaml`
- `qdrant.yaml`

Observed current behavior from that config:

- `api` is deployed as a Deployment + Service.
- `embedding` is deployed as a Deployment + Service with a PVC-backed model cache.
- `qdrant` is deployed as a StatefulSet + Service with `ReadWriteOncePod`.
- API receives `identity.json` via ConfigMap mount (no longer clones data repo).
- All images use git-hash tags (no `:latest`).
- `indexer` Job manifest exists with versioned naming.
- Cloudflare Tunnel ingress points to `interview.myles.hk`.

Migration from "API pulls data repo" layout is complete.

Important environment values already used by the code:

- API:
  - `DEEPSEEK_API_KEY`
  - `DEEPSEEK_BASE_URL`
  - `DEEPSEEK_MODEL`
  - `QDRANT_URL`
  - `QDRANT_API_KEY`
  - `QDRANT_COLLECTION_NAME`
  - `EMBEDDING_SERVICE_URL`
  - `EMBEDDING_DIM`
  - `DATA_DIR`
  - `API_KEY`
  - `ALLOWED_ORIGINS`
- Embedding:
  - `EMBEDDING_MODEL_NAME`
  - `PORT`
  - `FASTEMBED_CACHE_DIR`
- Indexer:
  - `QDRANT_URL`
  - `QDRANT_COLLECTION_NAME`
  - `EMBEDDING_SERVICE_URL`
  - `EMBEDDING_DIM`
  - `DATA_DIR`

## Config Repo Contract

The config repo should carry four versioned deployment inputs:

- `api` image tag
- `embedding` image tag
- `indexer` image tag
- `data` repo commit hash

An example contract shape:

```yaml
interviewMe:
  images:
    api:
      repository: ghcr.io/myleshk/interview-me-api
      tag: 4f2c8d1
    embedding:
      repository: ghcr.io/myleshk/interview-me-embedding
      tag: 4f2c8d1
    indexer:
      repository: ghcr.io/myleshk/interview-me-indexer
      tag: 4f2c8d1
  dataRepo:
    url: github.com/myleshk/interview-me-data.git
    commit: a18d0e9
  app:
    qdrantCollectionName: interview_me
    embeddingModelName: BAAI/bge-small-en-v1.5
```

Notes:

- The config repo should store the real target app path, not dummy placeholders.
- The real target app path is currently `jp-3/interview-me`.
- Tags are enough because you want them to match git commit hashes.
- The data commit is the deployed knowledge version and must be explicit.
- Image repository names can vary, but the shape above should stay stable.

## Recommended Config Repo Shape

The current config path is a flat manifest directory at
`jp-3/interview-me`. The key deployment inputs are in these files:

- `api.yaml` — API image tag (git hash)
- `embedding.yaml` — Embedding service image tag
- `indexer.yaml` — Indexer Job image tag + data commit in job name
- `configmap.yaml` — `DATA_REPO_COMMIT` and other runtime config

No Helm or Kustomize is needed at this scale.

## Manifest Set

Current production manifests:

- `api` Deployment + Service
- `embedding` Deployment + Service
- `qdrant` StatefulSet + Service + PVC
- Ingress for the public API/chat entrypoint
- One dedicated `indexer` Job
- Secrets/ConfigMaps for runtime settings and credentials

## Indexer Job Strategy

The indexer should be a normal declarative `Job`, not a hook-based Job.

Why:

- ArgoCD hooks would rerun on every sync unless carefully constrained.
- A standard Job with a deterministic name only changes when its inputs change.
- That matches the desired behavior: rerun on `data` commit change or `indexer` tag change only.

Recommended Job identity rule:

- Include short `data` commit in the Job name.
- Include short `indexer` image tag in the Job name.

Example:

```yaml
metadata:
  name: interview-me-indexer-a18d0e9-4f2c8d1
```

That gives these behaviors:

- `data` commit changes -> new Job name -> ArgoCD creates a new Job
- `indexer` tag changes -> new Job name -> ArgoCD creates a new Job
- unrelated manifest change -> same Job name -> no rerun

The Job should also include:

- `ttlSecondsAfterFinished`
- `restartPolicy: Never`
- a shared `emptyDir`
- one init container for cloning the private repo
- one main container for running the Python indexer

## Private Data Repo Access

The `data` repo stays private and should be fetched inside the cluster.

Recommended flow:

1. Init container receives repo URL and target commit from manifest values.
2. Init container authenticates using a K8S Secret.
3. Init container clones the private repo into a shared `emptyDir`.
4. Init container checks out the exact configured commit.
5. Main indexer container reads `/work/data/knowledge` from that shared volume.

Two viable auth options:

- GitHub deploy key mounted as SSH key
- GitHub token mounted as env var or file

Deploy key is usually cleaner because it is repo-scoped and read-only.

## Service Wiring

Recommended in-cluster service URLs:

- API -> `http://embedding:8080`
- API -> `http://qdrant:6333`
- Indexer -> `http://embedding:8080`
- Indexer -> `http://qdrant:6333`

Recommended storage:

- Qdrant: persistent volume
- Embedding model cache: optional persistent volume
- Indexer clone workspace: `emptyDir`

## Rollout Behavior

Initial rollout behavior should optimize for availability:

- Deploy API independently from indexer completion.
- Allow API to continue serving old indexed content while the new index runs later.
- Do not make API readiness depend on the indexer Job.

This fits your stated preference: stale data is acceptable, downtime is not.

## Migration Plan From Current Config

Migration complete:

- Git-hash image tags for `api`, `embedding`, and `indexer`. ✅
- Dedicated `indexer` Job with deterministic naming (`data-commit` + `indexer-tag`). ✅
- Private data repo cloning moved from `api` init container into `indexer` Job. ✅
- Identity delivered via ConfigMap mount (no data repo clone in API pod). ✅
- Qdrant on StatefulSet + `ReadWriteOncePod` with persistent storage. ✅

## Important Risk

The indexer should preserve the Qdrant collection itself and refresh managed
points in place instead of dropping the whole collection before each run.

That keeps Qdrant storage meaningfully persistent across deploys and avoids
turning every reindex into a full collection reset.

Current preferred behavior:

- keep the collection and its storage volume intact
- delete points for managed Markdown sources before reinserting them
- remove points for sources that disappeared from `knowledge/*.md`
- use stable point ids so upserts stay deterministic across reruns

Future improvement options still remain open:

- build into a staging collection and switch readers later
- support finer-grained incremental updates instead of per-source replacement

## Suggested Manifest Inputs

These values are likely enough for a first implementation:

```yaml
interviewMe:
  images:
    api:
      repository: ghcr.io/myleshk/interview-me-api
      tag: 4f2c8d1
    embedding:
      repository: ghcr.io/myleshk/interview-me-embedding
      tag: 4f2c8d1
    indexer:
      repository: ghcr.io/myleshk/interview-me-indexer
      tag: 4f2c8d1
  dataRepo:
    url: git@github.com:myleshk/interview-me-data.git
    commit: a18d0e9
    secretName: interview-me-data-repo
  api:
    replicas: 2
    allowedOrigins: ["*"]
    deepseekBaseUrl: https://api.deepseek.com/v1
    deepseekModel: deepseek-v4-flash
    apiKeySecretName: interview-me-api-secrets
  embedding:
    replicas: 1
    modelName: BAAI/bge-small-en-v1.5
  qdrant:
    storageSize: 10Gi
    collectionName: interview_me
  ingress:
    host: your-real-domain.example
```

## Near-Term Execution Order

All items below are now completed:

1. ✅ Config repo schema locked for four deployment inputs.
2. ✅ Private repo auth via deploy key in init container.
3. ✅ `indexer` Job manifest with deterministic naming.
4. ✅ Runtime manifests for `api`, `embedding`, `qdrant`, and ingress.
5. ✅ Non-destructive collection rebuild (upsert, not drop-and-recreate).
6. ✅ CI auto-updates config repo with image tags and data commit.
