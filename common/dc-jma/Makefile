# Makefile for dc-jma Docker image build
#
# Invoked from debian/rules via:  $(MAKE) -C common/dc-jma all
#
# All decision logic lives here — the caller just runs "make all" and
# this Makefile decides what to do.  The cascade:
#
#   1. SKIP_DC_JMA_BUILD=1                             → skip entirely
#   2. .gz already present in this directory            → done
#   3. Pre-built .gz at DC_JMA_ARCHIVE_PATH            → copy it
#   4. Clone repo + docker build from source            → build it
#   5. None of the above                                → fail
#
# When a dedicated dc-jma nightly pipeline is set up, it publishes
# archives to DC_JMA_ARCHIVE_PATH and step 3 kicks in automatically.

# ── Pre-built archive location ──────────────────────────────────────
# Directory where the nightly pipeline (or a developer) drops
# docker-sonic-dc-jma.gz and docker-sonic-dc-jma-dbg.gz.
DC_JMA_ARCHIVE_PATH ?= /volume/path/to/latest/archive

# ── Git repository (source-build fallback) ──────────────────────────
DC_JMA_GIT_REPO   := git@eng-gitlab.juniper.net:aide-jcloud/sonic/jma.git
DC_JMA_GIT_BRANCH := jcloud-develop
DC_JMA_SRC_DIR    := sonic-dc-jma

# ── Docker image ────────────────────────────────────────────────────
DOCKER_DC_JMA_STEM := docker-sonic-dc-jma
DOCKER_DC_JMA      := $(DOCKER_DC_JMA_STEM).gz
DOCKER_DC_JMA_DBG  := $(DOCKER_DC_JMA_STEM)-dbg.gz

JMA_TARGET     ?= evo_x86_64
DOCKER_USERTAG ?= latest

# Optional overrides for reproducible image metadata.
DC_JMA_VERSION         ?=
DC_JMA_SOURCE_REVISION ?=

# Set SKIP_DC_JMA_BUILD=1 to skip entirely (no image in .deb)
SKIP_DC_JMA_BUILD ?= 0

.PHONY: all clean

# ── all: single entry point with full cascade logic ─────────────────
all:
	@# ── Step 1: skip? ──────────────────────────────────────────────
	@if [ "$(SKIP_DC_JMA_BUILD)" = "1" ]; then \
		echo "[dc-jma] SKIP_DC_JMA_BUILD=1, skipping"; \
		exit 0; \
	fi; \
	\
	# ── Step 2: already built? ──────────────────────────────────────
	if [ -f "$(DOCKER_DC_JMA)" ]; then \
		echo "[dc-jma] $(DOCKER_DC_JMA) already present, nothing to do"; \
		exit 0; \
	fi; \
	\
	# ── Step 3: copy from archive path? ─────────────────────────────
	if [ -f "$(DC_JMA_ARCHIVE_PATH)/$(DOCKER_DC_JMA)" ]; then \
		echo "[dc-jma] Copying pre-built image from $(DC_JMA_ARCHIVE_PATH)/"; \
		cp "$(DC_JMA_ARCHIVE_PATH)/$(DOCKER_DC_JMA)" "$(DOCKER_DC_JMA)"; \
		if [ "$(ENABLE_DEBUG_SYMBOLS)" = "y" ]; then \
			if [ -f "$(DC_JMA_ARCHIVE_PATH)/$(DOCKER_DC_JMA_DBG)" ]; then \
				echo "[dc-jma] Copying $(DOCKER_DC_JMA_DBG) (ENABLE_DEBUG_SYMBOLS=y)"; \
				cp "$(DC_JMA_ARCHIVE_PATH)/$(DOCKER_DC_JMA_DBG)" "$(DOCKER_DC_JMA_DBG)"; \
			else \
				echo "[dc-jma] WARNING: $(DOCKER_DC_JMA_DBG) not at archive path"; \
			fi; \
		else \
			echo "[dc-jma] Skipping $(DOCKER_DC_JMA_DBG) (ENABLE_DEBUG_SYMBOLS != y)"; \
		fi; \
		exit 0; \
	fi; \
	\
	# ── Step 4: build from source ───────────────────────────────────
	echo "[dc-jma] No pre-built archives at $(DC_JMA_ARCHIVE_PATH), building from source"; \
	\
	# Ensure Docker daemon is available, with proxy configured for
	# image pulls.  The SONiC build system normally does this in the
	# slave.mk docker-start target, but dc-jma builds earlier (during
	# dpkg-buildpackage of the platform .deb), so we must handle it here.
	#
	# BuildKit (DOCKER_BUILDKIT=1) resolves FROM base images via the
	# daemon, and the daemon must have proxy in its *process* environment
	# — --build-arg and ~/.docker/config.json do NOT apply to image
	# metadata resolution.  We inject proxy into /etc/default/docker
	# and (re)start the daemon so dockerd inherits it.
	_need_restart=0; \
	if [ -n "$$http_proxy" ] || [ -n "$$https_proxy" ]; then \
		if ! grep -q "^export http_proxy=" /etc/default/docker 2>/dev/null; then \
			echo "[dc-jma] Injecting proxy into /etc/default/docker"; \
			sudo sed -i -e '/^export http_proxy=/d' -e '/^export https_proxy=/d' -e '/^export no_proxy=/d' /etc/default/docker; \
			sudo bash -c "{ \
				echo \"export http_proxy=$$http_proxy\"; \
				echo \"export https_proxy=$$https_proxy\"; \
				echo \"export no_proxy=$$no_proxy\"; \
			} >> /etc/default/docker"; \
			_need_restart=1; \
		fi; \
	fi; \
	if ! docker info >/dev/null 2>&1; then \
		echo "[dc-jma] Docker daemon not running, starting..."; \
		_need_restart=1; \
	fi; \
	if [ "$$_need_restart" = "1" ]; then \
		sudo service docker stop 2>/dev/null || true; \
		echo "[dc-jma] Aligning DinD storage-driver with slave.mk docker-start ($${SONIC_SLAVE_DOCKER_DRIVER:-overlay2})"; \
		sudo sed -i "s/--storage-driver=vfs/--storage-driver=$${SONIC_SLAVE_DOCKER_DRIVER:-overlay2}/" /etc/default/docker; \
		sudo service docker start 2>/dev/null || true; \
		for i in $$(seq 1 30); do \
			docker info >/dev/null 2>&1 && break; \
			sleep 1; \
		done; \
		if ! docker info >/dev/null 2>&1; then \
			echo "[dc-jma] ERROR: Cannot start Docker daemon"; \
			exit 1; \
		fi; \
		echo "[dc-jma] Docker daemon running"; \
	fi; \
	\
	# Ensure the GitLab host key is in known_hosts (the sonic-slave
	# container forwards SSH_AUTH_SOCK but does not mount ~/.ssh).
	mkdir -p $$HOME/.ssh; \
	if ! grep -q eng-gitlab.juniper.net $$HOME/.ssh/known_hosts 2>/dev/null; then \
		echo "[dc-jma] Adding eng-gitlab.juniper.net to known_hosts"; \
		ssh-keyscan -T 10 eng-gitlab.juniper.net >> $$HOME/.ssh/known_hosts 2>/dev/null; \
	fi; \
	\
	# Clone if needed — remove stale/broken dir first (e.g. leftover .gitkeep
	# or partial clone with broken HEAD from a previous failed SSH auth attempt)
	if [ ! -d "$(DC_JMA_SRC_DIR)/.git" ] || [ ! -f "$(DC_JMA_SRC_DIR)/Dockerfile" ]; then \
		rm -rf "$(DC_JMA_SRC_DIR)"; \
		echo "[dc-jma] Cloning $(DC_JMA_GIT_BRANCH) from $(DC_JMA_GIT_REPO)..."; \
		if git clone -b $(DC_JMA_GIT_BRANCH) --single-branch $(DC_JMA_GIT_REPO) $(DC_JMA_SRC_DIR); then \
			echo "[dc-jma] Clone successful"; \
		else \
			echo "[dc-jma] ERROR: git clone failed"; \
			echo "[dc-jma] To fix:"; \
			echo "[dc-jma]   - Ensure SSH_AUTH_SOCK is forwarded into the build container"; \
			echo "[dc-jma]   - Or place pre-built archives in $(DC_JMA_ARCHIVE_PATH)/"; \
			echo "[dc-jma]   - Or set SKIP_DC_JMA_BUILD=1 to skip (no dc-jma in image)"; \
			exit 1; \
		fi; \
	fi; \
	\
	# Validate source tree
	if [ ! -f "$(DC_JMA_SRC_DIR)/Dockerfile" ]; then \
		echo "[dc-jma] ERROR: No Dockerfile in $(DC_JMA_SRC_DIR)"; \
		exit 1; \
	fi; \
	JMA_SOURCE_REVISION="$(DC_JMA_SOURCE_REVISION)"; \
	if [ -z "$$JMA_SOURCE_REVISION" ]; then \
		JMA_SOURCE_REVISION=$$(git -C "$(DC_JMA_SRC_DIR)" rev-parse HEAD) || exit 1; \
	fi; \
	JMA_VERSION="$(DC_JMA_VERSION)"; \
	if [ -z "$$JMA_VERSION" ] && [ -f "$(DC_JMA_SRC_DIR)/tools/version.py" ]; then \
		JMA_VERSION=$$(cd "$(DC_JMA_SRC_DIR)" && python3 tools/version.py --path . 2>/dev/null | tr '/' '_'); \
	fi; \
	if [ -z "$$JMA_VERSION" ] && [ -n "$$JMA_SOURCE_REVISION" ]; then \
		JMA_VERSION=$$(echo "$(DC_JMA_GIT_BRANCH)" | tr '/' '_')_0_$$(git -C "$(DC_JMA_SRC_DIR)" rev-parse --short=8 HEAD)_$$(date -u +%Y%m%d%H%M); \
	fi; \
	JMA_BUILD_TIME=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	if [ -z "$$JMA_VERSION" ] || [ -z "$$JMA_SOURCE_REVISION" ] || [ -z "$$JMA_BUILD_TIME" ]; then \
		echo "[dc-jma] ERROR: Could not determine image metadata"; \
		exit 1; \
	fi; \
	echo "[dc-jma] DOCKER_BUILDKIT=1 docker build --ssh default"; \
	DOCKER_BUILDKIT=1 docker build \
		--no-cache \
		--network host \
		--ssh default \
		--build-arg HTTP_PROXY=$${HTTP_PROXY} \
		--build-arg HTTPS_PROXY=$${HTTPS_PROXY} \
		--build-arg http_proxy=$${HTTP_PROXY} \
		--build-arg https_proxy=$${HTTPS_PROXY} \
		--build-arg NO_PROXY=$${NO_PROXY} \
		--build-arg no_proxy=$${NO_PROXY} \
		--build-arg TARGET=$(JMA_TARGET) \
		--build-arg VERSION="$$JMA_VERSION" \
		--build-arg SOURCE_REVISION="$$JMA_SOURCE_REVISION" \
		--build-arg BUILD_TIME="$$JMA_BUILD_TIME" \
		--label com.azure.sonic.manifest="$$(cat $(DC_JMA_SRC_DIR)/manifest.json)" \
		--label Tag="$(DOCKER_USERTAG)" \
		-t $(DOCKER_DC_JMA_STEM):$(DOCKER_USERTAG) \
		-t $(DOCKER_DC_JMA_STEM):latest \
		-f "$(DC_JMA_SRC_DIR)/Dockerfile" \
		"$(DC_JMA_SRC_DIR)" || exit 1; \
	\
	# Save production image to .gz \
	echo "[dc-jma] Saving $(DOCKER_DC_JMA_STEM):latest → $(DOCKER_DC_JMA)"; \
	docker save $(DOCKER_DC_JMA_STEM):latest | gzip -c > $(DOCKER_DC_JMA); \
	ls -lh $(DOCKER_DC_JMA); \
	if [ "$(ENABLE_DEBUG_SYMBOLS)" = "y" ]; then \
		echo "[dc-jma] Building debug image (ENABLE_DEBUG_SYMBOLS=y)"; \
		DOCKER_BUILDKIT=1 docker build \
			--network host \
			--ssh default \
			--build-arg HTTP_PROXY=$${HTTP_PROXY} \
			--build-arg HTTPS_PROXY=$${HTTPS_PROXY} \
			--build-arg http_proxy=$${HTTP_PROXY} \
			--build-arg https_proxy=$${HTTPS_PROXY} \
			--build-arg NO_PROXY=$${NO_PROXY} \
			--build-arg no_proxy=$${NO_PROXY} \
			--build-arg TARGET=$(JMA_TARGET) \
			--build-arg VERSION="$$JMA_VERSION" \
			--build-arg SOURCE_REVISION="$$JMA_SOURCE_REVISION" \
			--build-arg BUILD_TIME="$$JMA_BUILD_TIME" \
			--build-arg INSTALL_DEBUG_TOOLS=y \
			--label com.azure.sonic.manifest="$$(cat $(DC_JMA_SRC_DIR)/manifest.json)" \
			--label Tag="$(DOCKER_USERTAG)-dbg" \
			-t $(DOCKER_DC_JMA_STEM)-dbg:$(DOCKER_USERTAG) \
			-t $(DOCKER_DC_JMA_STEM)-dbg:latest \
			-f "$(DC_JMA_SRC_DIR)/Dockerfile" \
			"$(DC_JMA_SRC_DIR)"; \
		echo "[dc-jma] Saving $(DOCKER_DC_JMA_STEM)-dbg:latest → $(DOCKER_DC_JMA_DBG)"; \
		docker save $(DOCKER_DC_JMA_STEM)-dbg:latest | gzip -c > $(DOCKER_DC_JMA_DBG); \
		ls -lh $(DOCKER_DC_JMA_DBG); \
	else \
		echo "[dc-jma] Skipping debug image build (ENABLE_DEBUG_SYMBOLS != y)"; \
	fi

# ── Clean ───────────────────────────────────────────────────────────
clean:
	rm -rf $(DC_JMA_SRC_DIR)
	rm -f $(DOCKER_DC_JMA) $(DOCKER_DC_JMA_DBG)
	docker rmi $(DOCKER_DC_JMA_STEM):$(DOCKER_USERTAG) 2>/dev/null || true
	docker rmi $(DOCKER_DC_JMA_STEM):latest 2>/dev/null || true
	docker rmi $(DOCKER_DC_JMA_STEM)-dbg:$(DOCKER_USERTAG) 2>/dev/null || true
	docker rmi $(DOCKER_DC_JMA_STEM)-dbg:latest 2>/dev/null || true
