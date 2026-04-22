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

## Inspecting the resulting config

The container's `~/.openclaw` is bind-mounted to `test/.state/` on your host, so the config is readable without entering the container:

```sh
cat test/.state/openclaw.json
ls  test/.state/workspace/skills/
```

Or drop into a shell in the container with the same state mounted:

```sh
make shell
# inside:
openclaw config get tools.allow
openclaw mcp show deepwiki
```

### Connecting to a live gateway from the host

The container's gateway port (`18789`) is published to the host at `28789` — chosen to avoid colliding with a real local OpenClaw gateway on `18789`.

The quickest way: **`make run`**. It applies the cookbook config, then keeps the gateway running in the foreground with the port already mapped. From another terminal on the host:

```sh
openclaw tui --gateway ws://127.0.0.1:28789
# or:
wscat -c ws://127.0.0.1:28789
```

Ctrl-C in the `make run` terminal stops the gateway and tears the container down.

For hand-driven inspection without the gateway running, use `make shell` and drive things yourself inside the container.

If `28789` is also taken on your host:

```sh
COOKBOOK_HOST_GATEWAY_PORT=38789 make run
```

Reset state between runs:

```sh
make clean-state
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
