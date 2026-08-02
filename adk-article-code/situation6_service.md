# Situation 6: make it a service

No Python file here; this situation is two commands.

Turn any agent folder in this directory's style (a package with a `root_agent`) into a REST API locally:

```bash
adk api_server   # serves on :8000
```

You get session CRUD endpoints (`POST /apps/{app}/users/{user}/sessions/{session}`), `/run` (full event stream), `/run_sse` (streaming), and Swagger docs at `/docs`, with zero server code.

Deploy that same server to Cloud Run:

```bash
adk deploy cloud_run \
  --project=$PROJECT --region=$REGION --service_name=$NAME \
  --session_service_uri="postgresql+asyncpg://..." \
  path/to/agent
```

The `--session_service_uri` flag plugs situation 3's persistence into the deployed service (any SQLAlchemy URL, or `agentengine://<id>` for Google's managed session store). Docs: https://adk.dev/runtime/api-server/ and https://adk.dev/deploy/cloud-run/
