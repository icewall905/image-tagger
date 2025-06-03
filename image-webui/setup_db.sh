#!/bin/bash
set -e

# Create versions directory if it doesn't exist
mkdir -p migrations/versions

# Generate initial migration
alembic revision --autogenerate -m "Initial database setup"

# Apply the migration
alembic upgrade head

echo "Database migrations have been applied successfully."
