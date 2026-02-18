#!/bin/bash

# Get script directory and move to project root
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
cd "$SCRIPT_DIR/.."

# Force use of the hyphenated version since V1 is installed
DOCKER_CMD="docker-compose"

ACTION=$1

if [ "$ACTION" == "up" ]; then
    echo "Starting containers using: $DOCKER_CMD"
    $DOCKER_CMD up -d
    echo "Containers are up."

elif [ "$ACTION" == "down" ]; then
    echo "Stopping containers..."
    $DOCKER_CMD down
    echo "Containers are down."

else
    echo "Usage: ./scripts/docker-manage.sh [up|down]"
fi