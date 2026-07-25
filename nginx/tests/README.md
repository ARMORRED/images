# Nginx Image Tests

Complete pytest test suite for Armorred Nginx images.

## Requirements

- Python 3.11+
- podman (running)
- uv (Python package manager)

## Installation

The test suite uses inline script metadata, so dependencies are automatically managed by `uv`:

```bash
cd nginx/tests
uv sync
```

## Running Tests

Test the hardened tier:
```bash
uv run pytest --image=armorred/nginx:hardened --tier=hardened -v
```

Test the locked tier:
```bash
uv run pytest --image=armorred/nginx:locked --tier=locked -v
```

Test a specific version:
```bash
uv run pytest --image=armorred/nginx:1.26.3-hardened --tier=hardened -v
```

Run specific test file:
```bash
uv run pytest test_core.py --image=armorred/nginx:hardened --tier=hardened -v
```

Run specific test:
```bash
uv run pytest test_core.py::TestContainerStartup::test_container_starts \
  --image=armorred/nginx:hardened --tier=hardened -v
```

## Test Structure

### `conftest.py`
- Pytest configuration and fixtures
- `podman_client`: Session-scoped Podman client
- `container`: Module-scoped container fixture (auto-cleanup)
- `image`, `tier`: Command-line option fixtures
- `get_container_host_port()`: Helper to extract mapped ports

### `test_core.py`
Core functionality tests:
- **TestContainerStartup**: Container lifecycle and process checks
- **TestHTTPEndpoints**: HTTP serving, health endpoint, default page
- **TestSecurityHeaders**: X-Content-Type-Options, X-Frame-Options, server tokens
- **TestContainerBehavior**: Logging, concurrent requests, graceful shutdown
- **TestConfiguration**: Nginx config validation, worker processes

### `test_security.py`
Security hardening tests:
- **TestSecurityHardening**: Non-root user, minimal packages, read-only rootfs
- **TestTierDifferences**: Shell availability (hardened vs locked)
- **TestBinaryHardening**: PIE, RELRO, stack canary, NX bit
- **TestNetworkSecurity**: Non-privileged ports
- **TestContainerSecurity**: no-new-privileges, dropped capabilities
- **TestBuildInformation**: Compiler flags, nginx modules

## Linting and Type Checking

```bash
# Format check
uv run --extra dev ruff format --check .

# Lint
uv run --extra dev ruff check .

# Type check
uv run --extra dev mypy .
```

## CI/CD Integration

The test suite is designed for integration with GitHub Actions and GitLab CI:

```yaml
- name: Test nginx image
  run: |
    cd nginx/tests
    uv run pytest --image=armorred/nginx:hardened --tier=hardened -v
```

## Test Coverage

The test suite verifies:
- ✅ Container starts and runs nginx process
- ✅ HTTP endpoints serve content (/, /health)
- ✅ Security headers present (X-Content-Type-Options, X-Frame-Options)
- ✅ Server tokens hidden (no version disclosure)
- ✅ Non-root user (uid != 0)
- ✅ Read-only root filesystem
- ✅ Minimal packages (no curl, wget, nc)
- ✅ Binary hardening (PIE, RELRO, stack canary, NX)
- ✅ Container security (no-new-privileges, dropped caps)
- ✅ Tier differences (bash in hardened, no shells in locked)
- ✅ Graceful shutdown (SIGQUIT)
- ✅ Concurrent request handling

## Notes

- Tests use podman Python API (not Docker)
- Containers are automatically cleaned up after tests
- Random high ports are used to avoid conflicts
- Tests require the image to be built or pulled first
- Binary hardening tests require `readelf` in the container (may be skipped for minimal images)
