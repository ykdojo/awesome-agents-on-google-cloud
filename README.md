# Awesome Agents on Google Cloud

> A curated list of tools, docs, and resources for building AI agents on Google Cloud.

Start with the companion guide: **[The anatomy of an AI agent on Google Cloud: a complete guide](anatomy-of-an-ai-agent-on-google-cloud.md)**, a map of the whole landscape with diagrams and a decision guide.

Then: **[Google GenAI SDK vs ADK: which one to use and when](google-genai-sdk-vs-adk.md)**, seven runnable situations comparing the plain SDK against the framework.

Also:

- **[Skills vs MCP: when to use which](skills-vs-mcp.md)**, a five-situation decision guide for the two ways to extend an agent.
- **[I built the same agent three ways: Interactions API, ADK, and the Antigravity SDK](same-agent-three-ways.md)**, the same Hacker News opinion agent on the API, the framework, and the harness, all served on Cloud Run.
- **[Turning Hacker News into a daily podcast with ADK 2, Gemini TTS, and Cloud Run jobs](hn-daily-podcast.md)**, a NotebookLM-style show that fact-checks every claim against its sources.
- **[From prototype to production: a self-hosted voice agent on a single Cloud Run GPU](gemma-voice-agent.md)**, three open-weights models (Whisper, Gemma 4, Kokoro) sharing one GPU, with ADK for orchestration.

## Contents

- [Frameworks](#frameworks)
- [Runtimes](#runtimes)
- [Models](#models)
- [Protocols: MCP and A2A](#protocols-mcp-and-a2a)
- [Knowledge and RAG](#knowledge-and-rag)
- [Memory and state](#memory-and-state)
- [Observability, evals, and security](#observability-evals-and-security)
- [Starter kits and samples](#starter-kits-and-samples)
- [Codelabs and courses](#codelabs-and-courses)
- [Videos and podcasts](#videos-and-podcasts)
- [Community](#community)

## Frameworks

- [Agent Development Kit (ADK)](https://adk.dev/) - Google's open-source, code-first agent framework; Python, Go, Java, TypeScript, and Kotlin.
- [adk-python](https://github.com/google/adk-python) - The Python SDK; the most mature of the five.
- [ADK 2.0](https://adk.dev/2.0/) - The current generation: graph-based execution engine, parallel workflows, retries, human-in-the-loop pauses.
- [Agent Runtime framework support](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime) - LangGraph, LangChain, LlamaIndex, and AG2 deploy to the managed runtime too.

## Runtimes

- [Agent Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime) - Managed agent runtime (formerly Vertex AI Agent Engine): sessions, memory, code sandbox, tracing, evals.
- [Cloud Run](https://cloud.google.com/run) - Serverless containers; services, worker pools, jobs, and GPUs.
- [Cloud Run GPUs](https://docs.cloud.google.com/run/docs/configuring/services/gpu) - NVIDIA L4 and RTX PRO 6000 Blackwell with scale-to-zero billing.
- [Agentic AI on GKE](https://cloud.google.com/blog/products/containers-kubernetes/agentic-ai-on-kubernetes-and-gke) - The Kubernetes path for agent fleets and self-hosted models.
- [Agent Sandbox on GKE](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/agent-sandbox) - Kernel-level isolation (gVisor) for agent-executed code.

## Models

- [Gemini API models](https://ai.google.dev/gemini-api/docs/models) - The current Gemini lineup, Pro to Flash-Lite.
- [Model Garden](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-garden/explore-models) - 200+ models inside your Google Cloud project, including Claude, GLM, Kimi, and DeepSeek.
- [Gemma 4](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/) - Google's open model family, with function calling and structured output.
- [Gemma 4 function calling guide](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4) - How tool use works on Gemma 4.
- [Run Gemma on Cloud Run](https://docs.cloud.google.com/run/docs/run-gemma-on-cloud-run) - Official pattern: Gemma 4 served with vLLM, wired into an ADK agent.
- [Agent Arena](https://arena.ai/leaderboard/agent) - Agent-specific leaderboard: tool orchestration and task completion across a million-plus real sessions.

## Protocols: MCP and A2A

- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) - The open standard for connecting agents to tools and data.
- [Google-managed MCP servers](https://cloud.google.com/blog/products/databases/managed-mcp-servers-for-google-cloud-databases) - Fully managed MCP endpoints for Google Cloud databases and services.
- [Google MCP catalog](https://github.com/google/mcp) - Index of Google's managed and open-source MCP servers.
- [MCP Toolbox](https://github.com/googleapis/mcp-toolbox) - Open-source MCP server covering 40+ data sources.
- [Host MCP servers on Cloud Run](https://docs.cloud.google.com/run/docs/host-mcp-servers) - Run your own remote MCP server, serverless.
- [Agent2Agent protocol (A2A)](https://a2a-protocol.org/) - Agent-to-agent coordination; Linux Foundation governed, v1.0.
- [a2a-samples](https://github.com/a2aproject/a2a-samples) - Official multi-language A2A examples.

## Knowledge and RAG

- [Agent Search](https://docs.cloud.google.com/generative-ai-app-builder/docs) - Turnkey retrieval over your data (formerly Vertex AI Search).
- [RAG Engine](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/rag-engine/rag-overview) - Managed RAG pipeline with pluggable chunking, embeddings, and vector stores.
- [Vector Search](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search/overview) - Raw vector infrastructure for billions-scale retrieval.
- [AlloyDB AI](https://docs.cloud.google.com/alloydb/docs/ai/what-is-alloydb-ai) - Vector search and AI queries inside your operational database.
- [BigQuery vector search](https://docs.cloud.google.com/bigquery/docs/vector-search-intro) - Semantic search where your analytical data already lives.
- [Grounding with Google Search](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-google-search) - Fresh public-web knowledge without retrieval infrastructure.

## Memory and state

- [Sessions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sessions) - Managed conversation state, callable from agents hosted anywhere.
- [Memory Bank](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank) - Long-term memory that extracts and consolidates facts instead of storing raw transcripts.
- [ADK sessions](https://adk.dev/sessions/session/) - Session-state backends: in-memory, your own Postgres, or managed Sessions.
- [ADK memory](https://adk.dev/sessions/memory/) - Pluggable memory interface; Memory Bank is one backend among several.

## Observability, evals, and security

- [Agent observability](https://docs.cloud.google.com/stackdriver/docs/observability/agent-observability) - OpenTelemetry GenAI traces rendered in Cloud Trace.
- [adk eval](https://adk.dev/evaluate/) - Evaluate tool-call trajectories, not just final answers; runs in CI.
- [Agent Evaluation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/agent-evaluation) - Synthetic users and continuous scoring on live traffic.
- [Model Armor](https://docs.cloud.google.com/model-armor/overview) - Screens prompts and responses: prompt injection, jailbreaks, data loss.
- [Agent Identity](https://docs.cloud.google.com/iam/docs/agent-identity-overview) - IAM principal type built for agents; non-impersonable, no long-lived keys.
- [ADK tool confirmation](https://adk.dev/tools-custom/confirmation/) - Require human approval before a tool runs.
- [Secure AI Framework (SAIF)](https://www.saif.google/secure-ai-framework) - Google's risk map for agent security.

## Starter kits and samples

- [agents-cli](https://github.com/google/agents-cli) - Scaffold, evaluate, and deploy agents with Terraform and staging-then-prod CI/CD.
- [adk-samples](https://github.com/google/adk-samples) - 70+ sample agents across Python, TypeScript, Go, Java, and Kotlin.
- [agent-starter-pack](https://github.com/googlecloudplatform/agent-starter-pack) - The predecessor to agents-cli; now in maintenance mode.
- [Agent Garden](https://developers.googleblog.com/agent-garden-samples-for-learning-discovering-and-building/) - In-console gallery of agent samples with one-click deploy.

## Codelabs and courses

- [Your first agent with ADK](https://codelabs.developers.google.com/your-first-agent-with-adk) - From prototype to agent.
- [ADK agent with an MCP server on Cloud Run](https://codelabs.developers.google.com/codelabs/cloud-run/use-mcp-server-on-cloud-run-with-an-adk-agent) - Tools as their own services.
- [Multi-agent systems with ADK and A2A](https://codelabs.developers.google.com/codelabs/create-multi-agents-adk-a2a) - Build and deploy a multi-agent system.
- [Kaggle 5-day AI Agents Intensive](https://www.kaggle.com/blog/5-days-of-ai-agents-intensive-course-with-google) - Self-paced course with five whitepapers, from intro to production.
- [Build intelligent agents with ADK](https://www.skills.google/course_templates/1382) - Google Skills course.

## Videos and podcasts

- [The Agent Factory](https://www.youtube.com/playlist?list=PLIivdWyY5sqLXR1eSkiM5bE6pFlXC-OSs) - Google Cloud DevRel's agent podcast; episodes map closely to the layers above.

## Community

- [r/agentdevelopmentkit](https://www.reddit.com/r/agentdevelopmentkit/) - The ADK community subreddit.
- [awesome-adk-agents](https://github.com/Sri-Krishna-V/awesome-adk-agents) - 90+ production-ready ADK agents by domain.
- [awesome-a2a](https://github.com/ai-boost/awesome-a2a) - Curated A2A agents, tools, and servers.

## Contributing

Contributions welcome. Keep entries current (post-2025 product names), one line each, with a short description of why the resource matters.
