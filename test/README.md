# Test harness

End-to-end test for [`install.sh`](../install.sh) against `ghcr.io/openclaw/openclaw:latest`. Never touches your host `~/.openclaw`.

## Quick start

```sh
make test-e2e
# or:
docker compose -f test/docker-compose.yml run --rm cookbook-test
```

Expected final line:

```
all assertions passed
```

## What it does

1. Spins up the OpenClaw container with a fresh, ephemeral `~/.openclaw` volume.
2. Runs `install.sh` (with `COOKBOOK_ACCEPT_RISK=1` so the consent prompt is bypassed in the non-interactive container). The script itself invokes `openclaw onboard --non-interactive --accept-risk` because the workspace is missing on first boot.
3. Runs `install.sh` a second time — the idempotency check.
4. Asserts the expected state:
   - `openclaw config get agents.defaults.thinkingDefault` contains `adaptive`
   - `openclaw config get tools.deny` contains `canvas` and `apply_patch`
   - `openclaw config get tools.allow` contains `read`, `edit`, `web_search`
   - `openclaw mcp show deepwiki` includes the DeepWiki MCP URL
   - `~/.openclaw/workspace/skills/cookbook-helper/SKILL.md` exists
5. Invokes one atomic sub-command (`install.sh apply deepwiki-mcp`) to confirm targeted dispatch works.

## Using a different image

```sh
COOKBOOK_TEST_IMAGE=<other-tag> make test-e2e
```

## Testing a different branch

By default the SKILL is fetched from the `main` branch. To test a feature branch:

```sh
COOKBOOK_REF=feat/install-script make test-e2e
```
