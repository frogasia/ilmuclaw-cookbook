# ILMUClaw Cookbook

Opinionated defaults and recipes for running agent workflows on [OpenClaw](https://openclaw.dev) with ILMU models.

Any agent built on any LLM can drift — tools get called in loops, answers get loosely sourced, reasoning depth is hard to calibrate. These are general properties of agent engineering, not of any one model. This cookbook is a collection of patterns that make agent behaviour more reliable, whichever model is doing the work underneath.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/frogasia/ilmuclaw-cookbook/main/install.sh | sh
```

One command. Applies to your existing OpenClaw setup. Idempotent.

If you've never run `openclaw onboard`, the installer will pause, show you what OpenClaw's `--accept-risk` means, and ask for a y/n before running onboarding on your behalf. You can also pass `COOKBOOK_ACCEPT_RISK=1` to skip the prompt for reruns or CI.

## What the install does

- **Thinking mode** — sets `agents.defaults.thinkingDefault` to `adaptive` so the agent scales reasoning depth per turn.
- **Tool allowlist** — sets `agents.defaults.tools.{allow,deny}` to a curated surface (details below).
- **DeepWiki MCP** — registers the DeepWiki MCP server so your agent can query this cookbook.
- **Cookbook-helper SKILL** — installs a SKILL that routes cookbook questions through DeepWiki into this repo.

### Tool allowlist — the `beginner` profile

The installer applies a **`beginner` profile** to OpenClaw's top-level `tools.allow` / `tools.deny` — a useful, friendly default for someone running OpenClaw on their laptop for the first time.

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
| `web_search` | Search the web using the configured provider |
| `web_fetch` | Fetch the contents of a URL |

Denied by default: `canvas`, `apply_patch` — these two overlap with `edit` / `write` and are common sources of tool-call loops on smaller models.

**Want a stricter setup?** Drop tools you don't need. Reviewing your agent's tool surface periodically is a good habit — tight tool allowlists age better than broad ones.

```sh
openclaw config set tools.allow '["read","edit","write","message","memory_get","memory_search"]'
openclaw gateway restart
```

Good candidates to drop if you don't need them:

- `exec` — only needed if you want the agent to run shell commands.
- `web_search` / `web_fetch` — network-facing tools; omit if you want the agent fully local.
- `sessions_spawn` — only needed if you want multi-agent delegation.
- `cron` — only needed if you want scheduled tasks.

`web_search` and `web_fetch` are worth calling out: they give the agent reach to arbitrary URLs and search results, which is where most real work happens but also where prompt-injection and data-exfiltration risks enter. If you're handling sensitive material, consider dropping them.

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
