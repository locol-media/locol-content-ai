#!/bin/bash

# Hook to automatically update cache buster when FrontEnd files change
# This runs after any tool use (Edit, Write, etc.)

# Path to the index.html file
INDEX_FILE="FrontEnd/src/index.html"

# Check if we're in the project root
if [ ! -f "$INDEX_FILE" ]; then
    exit 0
fi

# Check if any files in FrontEnd (excluding index.html itself) were modified in last 5 seconds
# This indicates a recent change that might need cache busting
RECENT_CHANGES=$(find FrontEnd/src/includes FrontEnd/src/components -type f -name "*.js" -o -name "*.css" -o -name "*.ts" -o -name "*.tsx" 2>/dev/null | xargs ls -t 2>/dev/null | head -1)

if [ -n "$RECENT_CHANGES" ]; then
    # Check if file was modified in last 5 seconds
    FILE_TIME=$(stat -c %Y "$RECENT_CHANGES" 2>/dev/null || stat -f %m "$RECENT_CHANGES" 2>/dev/null)
    CURRENT_TIME=$(date +%s)
    TIME_DIFF=$((CURRENT_TIME - FILE_TIME))

    if [ "$TIME_DIFF" -le 5 ]; then
        # Generate new timestamp
        NEW_TIMESTAMP=$(date +%s)

        # Find current cache buster version
        CURRENT_VERSION=$(grep -oP '\?v=\K[0-9]+' "$INDEX_FILE" 2>/dev/null | head -1)

        if [ -n "$CURRENT_VERSION" ] && [ "$CURRENT_VERSION" != "$NEW_TIMESTAMP" ]; then
            # Update cache buster
            if [[ "$OSTYPE" == "darwin"* ]]; then
                # macOS
                sed -i '' "s/?v=$CURRENT_VERSION/?v=$NEW_TIMESTAMP/g" "$INDEX_FILE"
            else
                # Linux
                sed -i "s/?v=$CURRENT_VERSION/?v=$NEW_TIMESTAMP/g" "$INDEX_FILE"
            fi
            echo "[Cache Buster Hook] Updated from ?v=$CURRENT_VERSION to ?v=$NEW_TIMESTAMP in $INDEX_FILE"
        fi
    fi
fi
