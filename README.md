# ILMUClaw Cookbook

Opinionated defaults and recipes for running agent workflows on [OpenClaw](https://openclaw.dev) with ILMU models.

Any agent built on any LLM can drift — tools get called in loops, answers get loosely sourced, reasoning depth is hard to calibrate. These are general properties of agent engineering, not of any one model. This cookbook is a collection of patterns that make agent behaviour more reliable, whichever model is doing the work underneath.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/frogasia/ilmuclaw-cookbook/main/install.sh | sh
```

One command. Applies to your existing OpenClaw setup. Idempotent.

If you've never run `openclaw onboard`, the installer will pause, show you what OpenClaw's `--accept-risk` means, and ask for a y/n before running onboarding on your behalf. You can also pass `COOKBOOK_ACCEPT_RISK=1` to skip the prompt for reruns or CI.

## Platform support

| Platform | Status | Notes |
|---|---|---|
| macOS (Darwin) | ✅ supported | Works out of the box. |
| Linux | ✅ supported | Works out of the box. |
| Windows (WSL2) | ✅ supported | Detected as Linux — install OpenClaw inside WSL2 and run the one-liner there. |
| Windows (Git Bash / MSYS2 / Cygwin) | ⚠️ best-effort | Runs, but the `/dev/tty` consent read can hang. Set `COOKBOOK_ACCEPT_RISK=1` if the prompt stalls. |
| Windows (native `cmd` / PowerShell) | ❌ unsupported | No bash interpreter — use WSL2. |

If you're on native Windows, install WSL2 first (`wsl --install`), then run the cookbook one-liner inside your WSL shell. There is no plan to ship a PowerShell port.

## How to run it

Three situations cover almost everyone. Pick the one that sounds like you:

### A. Brand-new to OpenClaw

Run the one-liner above in a terminal. The installer will onboard OpenClaw for you, then apply the cookbook. When you start the gateway afterwards, everything is already in place — nothing else to do.

### B. Already using OpenClaw on this machine

Run the one-liner in a terminal, then restart the gateway so it loads the new DeepWiki MCP server:

```sh
openclaw gateway restart
```

That's it. Your existing conversations and workspace stay intact.

### C. All you have is the OpenClaw chat UI (no terminal access)

This comes up when someone else runs OpenClaw for you — for example, a shared instance, a hosted deployment, or a Docker container you connect to through the web UI.

Paste the install command into the chat. The agent will run it, and most of the cookbook takes effect right away:

- ✅ The **cookbook-helper skill** is available on your next message.
- ✅ **Thinking mode** and the **tool allowlist** apply the next time you start a fresh conversation.
- ⚠️ **DeepWiki MCP** needs the gateway to be restarted, and the agent can't restart the process it's running inside. Ask whoever operates that OpenClaw to run `openclaw gateway restart` — or skip this one piece and install it later.

> A caveat worth checking with your operator: the cookbook's changes live in `~/.openclaw/openclaw.json`. Restarting the gateway re-reads that file, so the patch survives — **unless** the host reseeds the config on every gateway boot (some container setups do). If you're on a shared deployment and DeepWiki keeps disappearing after restarts, that's where to look.

If you'd rather skip DeepWiki cleanly and avoid the restart issue altogether, ask the agent to run these instead of the full installer:

```sh
install.sh apply cookbook-helper-skill
install.sh apply tool-allowlist
install.sh apply thinking-mode
```

You (or your operator) can add DeepWiki later with `install.sh apply deepwiki-mcp` followed by a gateway restart.

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
- [Within-turn trust](recipes/within-turn-trust.md) — stop the agent from re-reading the same file within a single turn.

Browse the [recipes index](recipes/README.md) for the full list.

## Who this is for

Developers and power users running OpenClaw who want their agents to behave predictably on real tasks. The patterns here transfer — what you learn tuning one agent will apply to the next one you build.

## License

[MIT](LICENSE).
