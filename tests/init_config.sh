#!/usr/bin/env bash
# This test assumes you have $TG_TOKEN evironment variable defined

set -e
set -x

CONFIG_FILE="$HOME/.matrigramconfig"

cp -f config.json.example $CONFIG_FILE
set +x
sed -i -- "s/tg_token/""${TG_TOKEN}""/g" $CONFIG_FILE
