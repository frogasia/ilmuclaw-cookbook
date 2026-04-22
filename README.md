# ILMUClaw Cookbook

Opinionated defaults and recipes for running agent workflows on [OpenClaw](https://openclaw.dev) with ILMU models.

Any agent built on any LLM can drift — tools get called in loops, answers get loosely sourced, reasoning depth is hard to calibrate. These are general properties of agent engineering, not of any one model. This cookbook is a collection of patterns that make agent behaviour more reliable, whichever model is doing the work underneath.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/frogasia/ilmuclaw-cookbook/main/install.sh | sh
```

One command. Applies to your existing OpenClaw setup. Idempotent.

## What the install does

- **Thinking mode** — sets `agents.defaults.thinkingDefault` to `adaptive` so the agent scales reasoning depth per turn.
- **Tool allowlist** — sets `agents.defaults.tools.{allow,deny}` to a curated surface (details below).
- **DeepWiki MCP** — registers the DeepWiki MCP server so your agent can query this cookbook.
- **Cookbook-helper SKILL** — installs a SKILL that routes cookbook questions through DeepWiki into this repo.

### Tool allowlist — what's enabled and why

The installer applies these defaults to `agents.defaults.tools`:

| Tool | What it lets the agent do |
|---|---|
| `read` | Read files in the workspace |
| `write` | Create new files |
| `edit` | Modify existing files |
| `exec` | Run shell commands |
| `cron` | Schedule recurring work |
| `sessions_spawn` | Delegate to a sub-agent |
| `sessions_send` / `sessions_list` / `sessions_history` | Talk to and inspect other sessions |
| `memory_search` / `memory_get` | Look things up in long-term memory |
| `message` | Send messages on configured channels |

Denied by default: `canvas`, `apply_patch` — these two overlap with `edit` / `write` and are common sources of tool-call loops on smaller models.

**Want a more conservative setup?** Drop tools you don't need with:

```sh
openclaw config set agents.defaults.tools.allow '["read","edit","write","message","memory_get","memory_search"]'
```

Good candidates to drop if you're just exploring:

- `exec` — only needed if you want the agent to run shell commands.
- `sessions_spawn` — only needed if you want multi-agent delegation.
- `cron` — only needed if you want scheduled tasks.

A note on safety: this allowlist is tuned for a **single-user laptop**. If you're running OpenClaw on a shared or untrusted machine, narrow the list before your first session — `exec` in particular gives the agent a broad reach into your shell environment.

## Local testing

The install script is testable end-to-end against a containerised OpenClaw without touching your host config. See [`test/README.md`](test/README.md).

## Recipes

- [Tool-call discipline](recipes/tool-call-discipline.md) — keep the agent from calling tools in loops.
- [Hallucination mitigation](recipes/hallucination-mitigation.md) — prompting patterns that keep answers grounded.
- [Thinking mode tuning](recipes/thinking-mode-tuning.md) — dial reasoning depth for the task at hand.

Browse the [recipes index](recipes/README.md) for the full list.

## Who this is for

Developers and power users running OpenClaw who want their agents to behave predictably on real tasks. The patterns here transfer — what you learn tuning one agent will apply to the next one you build.

## License

[MIT](LICENSE).
