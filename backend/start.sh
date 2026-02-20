#!/bin/bash

# Ensure data directory exists
mkdir -p /app/backend/data

# Check if data directory is empty (hidden files included)
if [ -z "$(ls -A /app/backend/data)" ]; then
    echo "Data directory is empty. Initializing from seed data..."
    if [ -d "/app/backend/data_seed" ]; then
        cp -r /app/backend/data_seed/* /app/backend/data/
        echo "Data initialization complete."
    else
        echo "Warning: Seed data directory not found!"
    fi
else
    echo "Data directory is not empty. Skipping initialization."
fi

# Ensure permissions (in case volume mount messed them up)
# Note: This might fail if the user doesn't have permission to chmod the mount, 
# but usually in this container we run as 'user' (1000) so we hope the volume is compatible.
# We skip chmod here to avoid fatal errors if we can't change perms on a mount.

# Start the application
exec uvicorn main:app --host 0.0.0.0 --port 7860
