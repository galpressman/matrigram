#!/usr/bin/env bash

set -e
set -x

CONFIG_FILE="config.json"
TOKEN="314662038:AAGyo7vcZpS89xoe59gd075MEioBRHEc5wQ"

cp -f config.json.example $CONFIG_FILE
sed -i -- "s/my_telegram_token_here/""${TOKEN}""/g" $CONFIG_FILE
