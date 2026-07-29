# Shared base image for frontend/Dockerfile and Dockerfile.self-hosted's
# frontend-builder stage. Rebuilt weekly by .github/workflows/base-images.yml
# so OS-package security patches land on a predictable cadence instead of
# only whenever Docker Hub happens to rebuild node:24-slim.
FROM node:24-slim

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Also update the bundled npm CLI itself - its own vendored dependencies
# (tar, undici, brace-expansion, ...) get Trivy findings independently of
# anything in this image's OS packages, and a newer npm release often
# carries the fix. This is the one place to do it now that frontend/
# Dockerfile and Dockerfile.self-hosted both build FROM this image, instead
# of each repeating (and, historically, sometimes getting wrong) the same
# fix. Not a cure-all: some npm-bundled CVEs have no fixed npm release yet
# (see .trivyignore for CVE-2026-14257) - this just keeps npm itself
# current so anything that *is* fixed upstream gets picked up weekly.
#
# `npm install -g npm@latest` alone verified NOT to work here - node:24-slim's
# bundled npm 11.16.0 stayed at 11.16.0 (still tar@7.5.15/undici@6.26.0/
# brace-expansion@5.0.6) after running it, a known npm self-update quirk.
# Replacing the npm module directory from `npm pack npm@latest`'s tarball
# was tried next and *also* didn't take effect in this build environment
# (this image's actual CI build still reported the same stale versions) -
# most likely this environment's registry mirror/proxy caches the "latest"
# dist-tag separately from concrete version lookups. Pin an explicit,
# already-verified-good version instead of relying on "latest" resolving
# consistently, and assert the fix actually landed so a future regression
# fails this build immediately instead of silently shipping stale versions
# that only surface in a downstream Trivy scan.
WORKDIR /tmp
RUN npm pack npm@12.0.1 && \
    rm -rf /usr/local/lib/node_modules/npm && \
    tar -xzf npm-*.tgz -C /usr/local/lib/node_modules && \
    mv /usr/local/lib/node_modules/package /usr/local/lib/node_modules/npm && \
    rm -f /tmp/npm-*.tgz && \
    installed_tar_version=$(node -p "require('/usr/local/lib/node_modules/npm/node_modules/tar/package.json').version") && \
    echo "Bundled npm tar version after replace: $installed_tar_version" && \
    [ "$installed_tar_version" = "7.5.19" ] || \
      (echo "ERROR: expected npm-bundled tar@7.5.19, got $installed_tar_version - the npm replace step did not take effect" && exit 1)
