"""Pytest fixtures for Nginx image testing."""

import time
from typing import Generator

import podman
import pytest
import requests
from podman.domain.containers import Container


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command line options."""
    parser.addoption(
        "--image",
        action="store",
        default="armorred/nginx:hardened",
        help="Nginx image to test",
    )
    parser.addoption(
        "--tier",
        action="store",
        default="hardened",
        help="Security tier (hardened or locked)",
    )


@pytest.fixture(scope="session")
def podman_client() -> Generator[podman.PodmanClient, None, None]:
    """Create a Podman client for the test session."""
    client = podman.PodmanClient(base_url="unix:///run/user/1000/podman/podman.sock")
    yield client
    client.close()


@pytest.fixture
def image(request: pytest.FixtureRequest) -> str:
    """Get the image name from command line options."""
    return request.config.getoption("--image")


@pytest.fixture
def tier(request: pytest.FixtureRequest) -> str:
    """Get the tier name from command line options."""
    return request.config.getoption("--tier")


@pytest.fixture(scope="module")
def container(
    podman_client: podman.PodmanClient,
    request: pytest.FixtureRequest,
) -> Generator[Container, None, None]:
    """
    Start an Nginx container for testing.

    The container is created with:
    - Random high port mapping for port 8080
    - tmpfs mounts for writable paths
    - Security hardening (read-only root, no new privileges, dropped caps)
    """
    image = request.config.getoption("--image")
    tier = request.config.getoption("--tier")

    print(f"\n[*] Starting Nginx container: {image} (tier: {tier})")

    try:
        # Pull image if not present
        try:
            podman_client.images.get(image)
            print(f"[*] Image {image} already present")
        except podman.errors.exceptions.ImageNotFound:
            print(f"[*] Pulling image {image}...")
            podman_client.images.pull(image)
            print(f"[+] Image {image} pulled successfully")

        # Start container with security hardening
        nginx_container = podman_client.containers.run(
            image=image,
            name=f"nginx_test_{int(time.time() * 1000)}",
            detach=True,
            remove=False,
            read_only=True,
            ports={"8080/tcp": None},  # Random host port
            tmpfs={
                "/tmp": "rw,noexec,nosuid,size=64m",
                "/var/cache/nginx": "rw,noexec,nosuid,size=64m",
            },
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
        )

        # Wait for container to be ready
        print("[*] Waiting for Nginx to be ready...")
        max_wait = 30  # seconds
        start_time = time.time()

        while time.time() - start_time < max_wait:
            nginx_container.reload()
            if nginx_container.status == "running":
                # Try to hit the health endpoint
                try:
                    host_port = get_container_host_port(nginx_container)
                    response = requests.get(
                        f"http://localhost:{host_port}/health", timeout=2
                    )
                    if response.status_code == 200:
                        print("[+] Nginx ready and responding")
                        break
                except requests.RequestException:
                    pass
            time.sleep(1)
        else:
            # Dump logs if failed to start
            logs = nginx_container.logs().decode()
            pytest.fail(
                f"Nginx container failed to start within {max_wait}s.\nLogs:\n{logs}"
            )

        # Attach tier information to container for tests
        nginx_container.tier = tier  # type: ignore

        yield nginx_container

    finally:
        # Cleanup
        print("[*] Stopping and removing container...")
        try:
            nginx_container.stop(timeout=10)
            nginx_container.remove()
            print("[+] Container cleaned up")
        except Exception as e:
            print(f"[-] Error during cleanup: {e}")


def get_container_host_port(container: Container, container_port: str = "8080") -> int:
    """Extract the host port for a given container port."""
    return int(container.ports[f"{container_port}/tcp"][0]["hostPort"])
