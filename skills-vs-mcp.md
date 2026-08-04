# Skills vs MCP: when to use which

In October 2025, Simon Willison wrote that Claude Skills are "[awesome, maybe a bigger deal than MCP](https://simonwillison.net/2025/Oct/16/claude-skills/)." Nine months later he published "[Stateless MCP has recaptured my interest](https://simonwillison.net/2026/Jul/31/stateless-mcp/)" and spent that week shipping MCP tooling. When someone so heavily identified with the skills-are-bigger take shifts like that, "which one wins" is the wrong question.

The right question is the one you face for each capability you add to an agent: do I write a skill, or set up an MCP server? This post is a decision guide: a short primer on each, five situations ending in verdicts, and a decision table. tl;dr: they solve different problems, and mature setups use both.

## What are skills?

A skill is a folder with a `SKILL.md` in it: YAML frontmatter with a `name` and `description`, then Markdown instructions, optionally alongside scripts and reference files. That's the whole format. [Anthropic launched it](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) in October 2025 and published it as an [open standard](https://agentskills.io/) that December. Adoption raced ahead: the spec's site lists 44 supporting clients, including OpenAI's Codex, GitHub Copilot, VS Code, Cursor, and Google's Antigravity.

The interesting part is the loading model, progressive disclosure. At rest, only each skill's name and description sit in context: a name plus a sentence or two of description comes out to roughly 100 tokens, the figure [the spec itself uses](https://agentskills.io/specification#progressive-disclosure). When a task matches, the agent reads the full `SKILL.md`; bundled files load only if needed. An agent can carry hundreds of skills while paying almost nothing for the ones it isn't using.

## What is MCP?

The [Model Context Protocol](https://modelcontextprotocol.io/) is an open protocol, launched by Anthropic in November 2024 and donated to the Linux Foundation a year later, for connecting agents to external systems. A server exposes tools (functions with JSON Schemas); any MCP-speaking client can discover and call them. Locally, servers run as subprocesses over stdio; remotely, over HTTP with OAuth 2.1. Write the server once and every client can use it. Think of it as the Language Server Protocol, but instead of editors talking to programming languages, it's agents talking to the outside world.

MCP won its bet on adoption (the official SDKs see close to half a billion downloads a month), and it just went through the [2026-07-28 spec revision](https://blog.modelcontextprotocol.io/posts/2026-07-28/), the biggest rewrite since launch, which made the protocol stateless.

## Situation 1: teach the agent how you do things

Your team has a way of writing postmortems. A release checklist. A house style for SQL. That's procedure, not an API call, and today it lives in a wiki the agent never reads. This is what skills are for:

```markdown
---
name: postmortem-writer
description: Write incident postmortems following our team's format and tone
---

# Writing a postmortem

Use the template in references/template.md. Sections in this order:
impact, timeline, root cause, what went well, action items.
Blameless tone: name systems, not people. Action items must have owners.
Verify the timeline against the incident channel before writing it.
```

Anthropic's launch post calls this "like putting together an onboarding guide for a new hire," which also captures who can write one: the domain expert who owns the procedure.

MCP has nothing for procedural knowledge. Its closest feature, `prompts`, is a menu of fill-in-the-blank templates a human picks from (most clients show them as slash commands); the agent never discovers one mid-task and decides to follow it, which is exactly what skills do.

**Verdict: skills.**

## Situation 2: give the agent live access to an external system

A different case: the agent needs your production database, your CRM, a ticketing system behind SSO. That's a connection, with credentials, freshness, and access control attached.

Skills can reach external systems too, but indirectly. A skill that teaches `gh` gives a coding agent real access to GitHub, no server in sight; that argument is [much of why Willison liked skills](https://simonwillison.net/2025/Oct/16/claude-skills/) in the first place. But the skill is borrowing tools the environment already has: a CLI that's already installed and logged in, the agent acting as you, reaching whatever your shell reaches. MCP provides the access itself: the server owns the connection, auth is scoped per client via OAuth, the model never touches a credential, and it works from environments with no shell at all, for example a web chat.

When a great CLI exists and the agent runs as a trusted user, the indirect path is genuinely fine. When there's no CLI, no shell, or a need to scope what the agent specifically may do, that's what MCP is for.

**Verdict: MCP.**

## Situation 3: lots of capabilities, small context

The complaint that launched the debate: connect several MCP servers, say ten or twenty, and your context window is gone before the first user message, because every server eagerly loads every tool's full JSON Schema. GitHub's official server became famous for consuming tens of thousands of tokens at rest. Skills cost only their name and description until used, [typically around a hundred tokens each](https://agentskills.io/specification#progressive-disclosure).

The MCP side has answered, mostly outside the protocol. Deferred tool loading (Anthropic's Tool Search Tool reports ~85% context reduction) is a client feature: schemas stay in a client-side index, and only the tools the agent searches for get loaded. Progressive disclosure remains something built on top of MCP, not into it.

**Verdict: skills, with MCP catching up.**

## Situation 4: production trust, security, and governance

Here the pendulum swings toward MCP. A skill that's only instructions is just text to read. But skills can bundle scripts and direct the agent to run commands, and the agents that read them typically have a shell and internet access, so a malicious skill can do real damage; the mitigation, sandboxing, is real operational work. Anthropic's guidance is blunt: install only from trusted sources, audit what they bundle. The data backs the caution: [Snyk scanned nearly 4,000 skills](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/) from two public registries and found over a third had at least one security flaw, including 76 confirmed malicious payloads built for credential theft, backdoors, and data exfiltration.

MCP has real risks of its own: it's a supply chain of servers, with real CVEs on record. But it's easier to govern: tool calls are structured requests a gateway can log, allow, or deny per tool. The new spec also lets an organization put its identity provider inside the OAuth flow, so the company can decide centrally which servers its agents may use. That auditability is why Willison, [in his July post](https://simonwillison.net/2026/Jul/31/stateless-mcp/), calls MCP the easier option to control for sensitive applications.

**Verdict: MCP.**

## Situation 5: use them together

The combination was in [Anthropic's launch post](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) from day one: MCP supplies the connections, and skills supply the judgment about using them. For example, an MCP server exposes your data warehouse; a skill teaches which tables matter and what "active user" means here. Without the skill, the agent queries the warehouse naively. Without the server, it can't query at all.

**Verdict: use both when it makes sense.** Skills teach the agent; MCP lets it act.

## The decision guide

| Situation | Reach for |
|---|---|
| 1. Teach the agent how you do things | Skills |
| 2. Give the agent live access to an external system | MCP |
| 3. Lots of capabilities, small context | Skills, with MCP catching up |
| 4. Production trust, security, and governance | MCP |
| 5. Use them together | Both, when it makes sense |

The shortest honest version: **skills are knowledge, MCP is access.** Start with a skill when what's missing is know-how; a Markdown file is the cheapest thing to try. Reach for MCP the moment a credential, a no-shell client, or an auditor enters the picture. And plan on both: the choice is per capability, not per architecture.

## Related reading

Karl Weinmeister's [Why I write skills instead of agents for knowledge work](https://medium.com/google-cloud/why-i-write-skills-instead-of-agents-for-knowledge-work-f5a08d1dc3e7) looks at skills from a different angle (skills versus building more agents) and pairs well with this piece.
