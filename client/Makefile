.PHONY: dev stop restart clean build check

# Add cargo to PATH
export PATH := $(HOME)/.cargo/bin:$(PATH)

# Start the Tauri dev server
dev:
	npm run tauri dev

# Stop any running dev servers (Vite + Tauri)
stop:
	-pkill -f "vite" 2>/dev/null || true
	-pkill -f "music-tutor" 2>/dev/null || true
	-lsof -ti:1420 | xargs kill -9 2>/dev/null || true

# Restart the dev server (stop + start)
restart: stop dev

# Alias for restart
bounce: restart

# Clean build artifacts
clean:
	rm -rf dist
	rm -rf src-tauri/target

# Production build
build:
	npm run tauri build

# Type check both Rust and TypeScript
check:
	npx tsc --noEmit
	cd src-tauri && cargo check

# Install dependencies
install:
	npm install
	cd src-tauri && cargo fetch
