{
  description = "Nginx 1.28.x hardened images";

  inputs = { nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11"; };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };

      # Nginx packages with different hardening levels (using Clang for CFI/SafeStack)
      nginxHardened = pkgs.callPackage ./package {
        stdenv = pkgs.llvmPackages.stdenv;
        hardenedStdenv = pkgs.llvmPackages.stdenv;
        withHardening = true;
        withExtraHardening = false;
        # Perl module incompatible with LTO/CFI (LTO bitcode not recognized by Perl linker)
        withPerl = false;
      };

      nginxLocked = pkgs.callPackage ./package {
        stdenv = pkgs.llvmPackages.stdenv;
        hardenedStdenv = pkgs.llvmPackages.stdenv;
        withHardening = true;
        withExtraHardening = true;
        # Disable Perl module when using LTO/CFI (LTO bitcode incompatible with Perl linker)
        withPerl = false;
      };

      # Version metadata (use hardened as reference)
      versions = import ./versions.nix;
      version = nginxHardened.version;

      # Hardened nginx configuration generator
      mkNginxConf = nginx:
        pkgs.writeText "nginx.conf" ''
          worker_processes auto;
          pid /tmp/nginx.pid;
          error_log /dev/stderr warn;

          events {
              worker_connections 1024;
              use epoll;
          }

          http {
              include       ${nginx}/conf/mime.types;
              default_type  application/octet-stream;

              # Security headers
              server_tokens off;
              add_header X-Content-Type-Options nosniff always;
              add_header X-Frame-Options DENY always;
              add_header X-XSS-Protection "1; mode=block" always;

              # Logging
              access_log /dev/stdout;

              # Performance
              sendfile on;
              tcp_nopush on;
              tcp_nodelay on;
              keepalive_timeout 65;

              # Temp paths for unprivileged operation
              client_body_temp_path /tmp/client_body;
              proxy_temp_path /tmp/proxy;
              fastcgi_temp_path /tmp/fastcgi;
              uwsgi_temp_path /tmp/uwsgi;
              scgi_temp_path /tmp/scgi;

              server {
                  listen 8080;
                  server_name _;
                  root /var/www/html;
                  index index.html;

                  location / {
                      try_files $uri $uri/ =404;
                  }

                  location /health {
                      access_log off;
                      return 200 "OK\n";
                      add_header Content-Type text/plain;
                  }
              }
          }
        '';

      # Default HTML content
      defaultHtml = pkgs.writeTextDir "index.html" ''
        <!DOCTYPE html>
        <html>
        <head><title>Nginx</title></head>
        <body><h1>Nginx is running</h1></body>
        </html>
      '';

      # Build OCI image with specified security tier
      mkImage = { tier, nginx }:
        let
          isLocked = tier == "locked";
          uid = "65534";
          gid = "65534";
          nginxConf = mkNginxConf nginx;
        in pkgs.dockerTools.buildLayeredImage {
          name = "nginx";
          tag = "${version}-${tier}";

          contents = [ nginx pkgs.coreutils defaultHtml ]
            ++ pkgs.lib.optionals (!isLocked) [ pkgs.bashInteractive ];

          extraCommands = ''
            mkdir -p var/www/html tmp
            cp -r ${defaultHtml}/* var/www/html/
            chmod -R 755 var/www/html
            chmod 1777 tmp
          '';

          config = {
            Entrypoint = [ "${nginx}/bin/nginx" ];
            Cmd = [ "-c" "${nginxConf}" "-g" "daemon off;" ];
            ExposedPorts = { "8080/tcp" = { }; };
            User = uid;
            WorkingDir = "/var/www/html";
            Env = [ "PATH=/bin" "NGINX_VERSION=${version}" ];
            Labels = {
              "org.opencontainers.image.title" = "nginx";
              "org.opencontainers.image.version" = version;
              "org.opencontainers.image.description" =
                "Hardened Nginx ${version} (${tier} tier)";
              "org.armorred.tier" = tier;
              "org.armorred.base" = "scratch";
            };
          };
        };

    in {
      packages.${system} = {
        default = self.packages.${system}."${version}-hardened";

        "${version}-hardened" = mkImage {
          tier = "hardened";
          nginx = nginxHardened;
        };
        "${version}-locked" = mkImage {
          tier = "locked";
          nginx = nginxLocked;
        };
      };

      # Metadata for CI/CD
      supportedVersions = [ version ];
      latestVersion = version;
      inherit version;

      devShells.${system}.default = pkgs.mkShell {
        buildInputs = with pkgs; [ skopeo checksec grype ];
        shellHook = ''
          echo "[*] Nginx ${version} version line"
        '';
      };
    };
}
