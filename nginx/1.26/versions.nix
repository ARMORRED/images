# Version metadata for nginx 1.26.x line
#
# This file documents all supported versions in this line.
# The package source is local (copied from nixpkgs).
{
  # Version line identifier
  line = "1.26";

  # Nixpkgs branch for build dependencies
  nixpkgsRef = "github:NixOS/nixpkgs/nixos-24.11";

  # Package source (local copy from nixpkgs)
  packageSource = "nixpkgs/nixos-24.11";

  # End-of-life date (nginx 1.26 is stable, EOL TBD)
  eol = null;

  # Notes about this version line
  notes = ''
    Nginx 1.26.3 stable release.
    Package source copied from nixpkgs/nixos-24.11 for local customization.
    Build dependencies from nixos-24.11 (newer toolchain).
  '';
}
