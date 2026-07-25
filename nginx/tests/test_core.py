"""Core functionality tests for Nginx images."""

import signal
import time

import pytest
import requests
from podman.domain.containers import Container

from conftest import get_container_host_port


class TestContainerStartup:
    """Test container startup and basic functionality."""

    def test_container_starts(self, container: Container) -> None:
        """Test that the Nginx container starts successfully."""
        assert container.status == "running"
        assert "nginx" in container.name
        print("[+] Nginx container is running")

    def test_nginx_process_running(self, container: Container) -> None:
        """Test that Nginx process is running inside container."""
        top_output = container.top()
        processes = top_output.get("Processes", [])

        # Check if nginx binary is running
        nginx_running = any("nginx" in str(proc) for proc in processes)
        assert nginx_running, "Nginx process not found in container"
        print("[+] Nginx process is running")

    def test_nginx_version(self, container: Container) -> None:
        """Test that Nginx version is correct."""
        exit_code, output = container.exec_run(["nginx", "-v"])

        # nginx -v outputs to stderr
        output_str = output.decode()
        assert exit_code == 0
        assert "nginx version:" in output_str
        assert "nginx/1.26" in output_str or "nginx/1.28" in output_str
        print(f"[+] Nginx version: {output_str.strip()}")


class TestHTTPEndpoints:
    """Test HTTP endpoint functionality."""

    def test_serves_http_200(self, container: Container) -> None:
        """Test that HTTP GET to port 8080 returns 200."""
        host_port = get_container_host_port(container)

        response = requests.get(f"http://localhost:{host_port}/", timeout=5)

        assert response.status_code == 200
        print("[+] HTTP endpoint returns 200")

    def test_health_endpoint(self, container: Container) -> None:
        """Test that /health endpoint returns 200 with OK."""
        host_port = get_container_host_port(container)

        response = requests.get(f"http://localhost:{host_port}/health", timeout=5)

        assert response.status_code == 200
        assert response.text.strip() == "OK"
        assert "text/plain" in response.headers.get("content-type", "")
        print("[+] Health endpoint returns OK")

    def test_serves_default_page(self, container: Container) -> None:
        """Test that GET / returns HTML with 'Nginx is running'."""
        host_port = get_container_host_port(container)

        response = requests.get(f"http://localhost:{host_port}/", timeout=5)

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Nginx is running" in response.text
        print("[+] Default page contains 'Nginx is running'")

    def test_health_endpoint_fast_response(self, container: Container) -> None:
        """Test that health endpoint responds quickly."""
        host_port = get_container_host_port(container)

        start_time = time.time()
        response = requests.get(f"http://localhost:{host_port}/health", timeout=5)
        response_time = time.time() - start_time

        assert response.status_code == 200
        assert response_time < 1.0, (
            f"Health check took {response_time:.2f}s (expected < 1s)"
        )
        print(f"[+] Health endpoint responded in {response_time:.3f}s")


class TestSecurityHeaders:
    """Test security headers in HTTP responses."""

    def test_security_headers(self, container: Container) -> None:
        """Test that security headers are present."""
        host_port = get_container_host_port(container)

        response = requests.get(f"http://localhost:{host_port}/", timeout=5)

        # Check for security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert "X-XSS-Protection" in response.headers
        print("[+] Security headers present")

    def test_server_tokens_off(self, container: Container) -> None:
        """Test that Server header does not reveal version."""
        host_port = get_container_host_port(container)

        response = requests.get(f"http://localhost:{host_port}/", timeout=5)

        server_header = response.headers.get("Server", "")

        # server_tokens off means no version number should be present
        # The header might be absent or just say "nginx" without version
        assert "1.26" not in server_header and "1.28" not in server_header, (
            f"Server header reveals version: {server_header}"
        )
        print(f"[+] Server tokens hidden (Server: {server_header or '(not set)'})")


class TestContainerBehavior:
    """Test container behavior and resilience."""

    def test_container_logs_available(self, container: Container) -> None:
        """Test that container logs are available."""
        logs = container.logs().decode()

        assert len(logs) > 0, "No logs available from container"
        print("[+] Container logs are available")

    def test_multiple_concurrent_requests(self, container: Container) -> None:
        """Test handling of multiple concurrent requests."""
        host_port = get_container_host_port(container)
        url = f"http://localhost:{host_port}/health"

        # Send 20 concurrent requests
        import concurrent.futures

        def make_request() -> requests.Response:
            return requests.get(url, timeout=5)

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All requests should succeed
        assert all(r.status_code == 200 for r in results)
        assert len(results) == 20
        print("[+] Handled 20 concurrent requests successfully")

    def test_graceful_shutdown(self, container: Container) -> None:
        """Test that container stops cleanly with SIGQUIT."""
        # Send SIGQUIT for graceful shutdown
        container.kill(signal=signal.SIGQUIT)

        # Wait for container to stop
        max_wait = 10
        start_time = time.time()

        while time.time() - start_time < max_wait:
            container.reload()
            if container.status in ["exited", "stopped"]:
                print("[+] Container stopped gracefully")
                return
            time.sleep(0.5)

        pytest.fail("Container did not stop gracefully within 10s")


class TestConfiguration:
    """Test Nginx configuration."""

    def test_config_syntax(self, container: Container) -> None:
        """Test that Nginx configuration syntax is valid."""
        exit_code, output = container.exec_run(["nginx", "-t"])

        output_str = output.decode()
        assert exit_code == 0, f"Config syntax check failed: {output_str}"
        assert "syntax is ok" in output_str
        assert "test is successful" in output_str
        print("[+] Nginx configuration syntax is valid")

    def test_worker_processes(self, container: Container) -> None:
        """Test that Nginx has appropriate worker processes."""
        top_output = container.top()
        processes = top_output.get("Processes", [])

        # Count nginx processes (master + workers)
        nginx_processes = [p for p in processes if "nginx" in str(p)]

        # Should have at least master process + 1 worker
        assert len(nginx_processes) >= 2, (
            f"Expected at least 2 nginx processes, found {len(nginx_processes)}"
        )
        print(f"[+] Found {len(nginx_processes)} nginx processes")
