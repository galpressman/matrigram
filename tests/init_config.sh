#!/usr/bin/env bash
# This test assumes you have $TG_TOKEN evironment variable defined

set -e
set -x

CONFIG_FILE="config.json"

cp -f config.json.example $CONFIG_FILE
set +x
sed -i -- "s/my_telegram_token_here/""${TG_TOKEN}""/g" $CONFIG_FILE
