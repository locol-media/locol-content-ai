# Claude Code Hooks

This directory contains hooks that automatically execute during Claude Code operations.

## post-tool-use.sh

**Purpose**: Automatically updates the cache buster in `FrontEnd/src/index.html` when JavaScript or CSS files in the FrontEnd directory are modified.

**How it works**:
1. Runs after any tool use (Edit, Write, etc.)
2. Checks if any `.js`, `.css`, `.ts`, or `.tsx` files in `FrontEnd/src/includes` or `FrontEnd/src/components` were modified in the last 5 seconds
3. If recent changes detected, generates a new Unix timestamp
4. Updates all `?v=XXXXXXXX` cache busters in `FrontEnd/src/index.html` to the new timestamp
5. Outputs a message confirming the update

**Benefits**:
- No need to manually update cache busters
- Ensures browser always loads latest JavaScript/CSS changes
- Only updates when actual source files change (not on every edit)

**Configuration**:
- Modify the 5-second window in line 24 if needed: `if [ "$TIME_DIFF" -le 5 ]; then`
- Add more directories to watch by updating line 16

**Testing**:
To test the hook, edit any file in `FrontEnd/src/includes/` and check if the cache buster in `FrontEnd/src/index.html` updates.

**Note**: This hook only updates `FrontEnd/src/index.html`. The `BackEnd/www/index.html` file should be updated separately when needed (it's typically a build artifact).
