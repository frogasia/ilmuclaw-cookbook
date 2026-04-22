# ILMUClaw Cookbook

Opinionated defaults and recipes for running agent workflows on [OpenClaw](https://openclaw.dev) with ILMU models.

Any agent built on any LLM can drift — tools get called in loops, answers get loosely sourced, reasoning depth is hard to calibrate. These are general properties of agent engineering, not of any one model. This cookbook is a collection of patterns that make agent behaviour more reliable, whichever model is doing the work underneath.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/frogasia/ilmuclaw-cookbook/main/install.sh | sh
```

One command. Applies to your existing OpenClaw setup. Idempotent.

## What the install does

- **Thinking mode** — reasoning defaults tuned for reliable multi-step work.
- **Tool allowlist** — a curated tool surface that reduces tool-call loops.
- **DeepWiki MCP** — wires up the DeepWiki MCP server so your agent can query this cookbook.
- **Cookbook-helper SKILL** — installs a SKILL that routes cookbook questions through DeepWiki into this repo.

## Recipes

- [Tool-call discipline](recipes/tool-call-discipline.md) — keep the agent from calling tools in loops.
- [Hallucination mitigation](recipes/hallucination-mitigation.md) — prompting patterns that keep answers grounded.
- [Thinking mode tuning](recipes/thinking-mode-tuning.md) — dial reasoning depth for the task at hand.

Browse the [recipes index](recipes/README.md) for the full list.

## Who this is for

Developers and power users running OpenClaw who want their agents to behave predictably on real tasks. The patterns here transfer — what you learn tuning one agent will apply to the next one you build.

## License

[MIT](LICENSE).
