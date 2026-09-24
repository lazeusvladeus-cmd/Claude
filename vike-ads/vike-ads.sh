#!/usr/bin/env bash
# Convenience launcher: ./vike-ads "give me an ad idea for ..."
cd "$(dirname "$0")" && exec "${PYTHON:-python3}" -m vike_ads "$@"
