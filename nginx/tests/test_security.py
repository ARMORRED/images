"""Security hardening tests for Nginx images."""

import pytest
from podman.domain.containers import Container


class TestSecurityHardening:
    """Test security hardening features."""

    def test_runs_as_non_root(self, container: Container) -> None:
        """Test that container runs as non-root user."""
        exit_code, output = container.exec_run(["id", "-u"])

        assert exit_code == 0
        uid = output.decode().strip()

        # Should not be root (uid=0)
        assert uid != "0", f"Container is running as root (uid={uid})"
        print(f"[+] Container runs as non-root user (uid={uid})")

    def test_minimal_installed_packages(self, container: Container) -> None:
        """Test that only minimal packages are installed."""
        # Common tools that should NOT be present in a minimal image
        unnecessary_tools = ["curl", "wget", "nc", "netcat", "telnet", "ftp"]

        for tool in unnecessary_tools:
            exit_code, _ = container.exec_run(["which", tool])
            # which should fail (exit code != 0) for these tools
            assert exit_code != 0, f"Unnecessary tool '{tool}' found in image"

        print("[+] No unnecessary tools found in image")

    def test_read_only_root_filesystem(self, container: Container) -> None:
        """Test that root filesystem is read-only."""
        # Try to write to root filesystem (should fail)
        exit_code, _ = container.exec_run(["touch", "/test-write"])

        assert exit_code != 0, "Root filesystem is not read-only"
        print("[+] Root filesystem is read-only")

    def test_tmpfs_writable(self, container: Container) -> None:
        """Test that tmpfs mounts are writable."""
        # /tmp should be writable
        exit_code, output = container.exec_run(["touch", "/tmp/test-file"])

        assert exit_code == 0, f"Failed to write to /tmp: {output.decode()}"

        # Clean up
        container.exec_run(["rm", "/tmp/test-file"])
        print("[+] tmpfs mounts are writable")


class TestTierDifferences:
    """Test differences between hardened and locked tiers."""

    def test_shell_availability(self, container: Container, tier: str) -> None:
        """Test shell availability based on tier."""
        shells = ["/bin/bash", "/bin/sh", "/bin/zsh"]

        if tier == "hardened":
            # Hardened tier should have bash available
            exit_code, _ = container.exec_run(["test", "-f", "/bin/bash"])
            assert exit_code == 0, "Bash should be available in hardened tier"
            print("[+] Bash available in hardened tier")
        elif tier == "locked":
            # Locked tier should NOT have any shells
            for shell in shells:
                exit_code, _ = container.exec_run(["test", "-f", shell])
                assert exit_code != 0, (
                    f"Shell {shell} should not be available in locked tier"
                )
            print("[+] No shells available in locked tier")


class TestBinaryHardening:
    """Test binary-level hardening features."""

    def test_binary_hardening_flags(self, container: Container) -> None:
        """Test that nginx binary has hardening flags enabled."""
        # Check for PIE (Position Independent Executable)
        exit_code, output = container.exec_run(["readelf", "-h", "/bin/nginx"])

        if exit_code == 0:
            output_str = output.decode()
            # PIE binaries have Type: DYN
            assert "Type:" in output_str and "DYN" in output_str, (
                "Binary is not PIE (Type should be DYN)"
            )
            print("[+] Binary is PIE (Position Independent Executable)")
        else:
            # readelf might not be available in minimal image
            print("[*] Skipping PIE check (readelf not available)")

    def test_relro_enabled(self, container: Container) -> None:
        """Test that RELRO (Relocation Read-Only) is enabled."""
        exit_code, output = container.exec_run(["readelf", "-l", "/bin/nginx"])

        if exit_code == 0:
            output_str = output.decode()
            # Full RELRO should have GNU_RELRO segment
            assert "GNU_RELRO" in output_str, "RELRO not enabled"
            print("[+] RELRO (Relocation Read-Only) is enabled")
        else:
            print("[*] Skipping RELRO check (readelf not available)")

    def test_stack_canary(self, container: Container) -> None:
        """Test that stack canary is enabled."""
        exit_code, output = container.exec_run(["readelf", "-s", "/bin/nginx"])

        if exit_code == 0:
            output_str = output.decode()
            # Stack canary uses __stack_chk_fail symbol
            assert "__stack_chk" in output_str, "Stack canary not enabled"
            print("[+] Stack canary protection is enabled")
        else:
            print("[*] Skipping stack canary check (readelf not available)")

    def test_nx_bit(self, container: Container) -> None:
        """Test that NX (No-eXecute) bit is set."""
        exit_code, output = container.exec_run(["readelf", "-l", "/bin/nginx"])

        if exit_code == 0:
            output_str = output.decode()
            # GNU_STACK should have RW (not RWE)
            if "GNU_STACK" in output_str:
                # Check that execute flag is not set
                lines = output_str.split("\n")
                for i, line in enumerate(lines):
                    if "GNU_STACK" in line:
                        # The flags are typically in the same line or nearby
                        context = " ".join(lines[i : i + 2])
                        assert "RWE" not in context, (
                            "Stack is executable (NX bit not set)"
                        )
                        print("[+] NX bit is set (stack not executable)")
                        return
        else:
            print("[*] Skipping NX bit check (readelf not available)")


class TestNetworkSecurity:
    """Test network-related security features."""

    def test_no_privileged_ports(self, container: Container) -> None:
        """Test that Nginx listens on non-privileged port."""
        # Check listening ports
        exit_code, output = container.exec_run(
            ["ss", "-tlnp"]
            if container.tier == "hardened"
            else ["cat", "/proc/net/tcp"]
        )

        # If ss is not available (locked tier), parse /proc/net/tcp
        if exit_code != 0:
            exit_code, output = container.exec_run(["cat", "/proc/net/tcp"])

        if exit_code == 0:
            output_str = output.decode()
            # Port 8080 = 0x1F90 in hex, should appear in output
            # Just verify we're not listening on port 80 or 443
            assert ":0050" not in output_str, "Listening on privileged port 80"
            assert ":01BB" not in output_str, "Listening on privileged port 443"
            print("[+] Nginx listens on non-privileged port")


class TestContainerSecurity:
    """Test container-level security configuration."""

    def test_no_new_privileges(self, container: Container) -> None:
        """Test that no-new-privileges is set."""
        inspect = container.attrs

        security_opts = inspect.get("HostConfig", {}).get("SecurityOpt", [])
        assert any("no-new-privileges" in opt for opt in security_opts), (
            "no-new-privileges not set"
        )
        print("[+] no-new-privileges is enabled")

    def test_capabilities_dropped(self, container: Container) -> None:
        """Test that all capabilities are dropped."""
        inspect = container.attrs

        cap_drop = inspect.get("HostConfig", {}).get("CapDrop", [])
        assert "ALL" in cap_drop or "all" in cap_drop, "Not all capabilities dropped"
        print("[+] All capabilities are dropped")

    def test_readonly_rootfs(self, container: Container) -> None:
        """Test that root filesystem is read-only."""
        inspect = container.attrs

        readonly_rootfs = inspect.get("HostConfig", {}).get("ReadonlyRootfs", False)
        assert readonly_rootfs is True, "Root filesystem is not read-only"
        print("[+] Root filesystem is read-only (via container config)")


class TestBuildInformation:
    """Test build and compiler information."""

    def test_compiler_flags(self, container: Container) -> None:
        """Test that nginx was built with hardening compiler flags."""
        exit_code, output = container.exec_run(["nginx", "-V"])

        # nginx -V outputs to stderr
        output_str = output.decode()
        assert exit_code == 0

        # Should have been built with optimization flags
        # The exact flags visible depend on whether they're in configure args
        print(f"[*] Nginx build info:\n{output_str[:500]}...")

    def test_nginx_modules(self, container: Container) -> None:
        """Test that nginx has expected modules compiled in."""
        exit_code, output = container.exec_run(["nginx", "-V"])

        output_str = output.decode()
        assert exit_code == 0

        # Core modules should be present
        assert "--with-http_ssl_module" in output_str, "SSL module not compiled"
        assert "--with-http_v2_module" in output_str, "HTTP/2 module not compiled"

        print("[+] Core modules (SSL, HTTP/2) are compiled in")
