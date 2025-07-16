#!/bin/bash
set -euo pipefail
BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$BASE_DIR"

# 1) Make sure certs exist (idempotent).
./generate_ssl.sh

# 2) Launch all executables with PM2
pm2 start dvr_gateway_http_exec/dvr_gateway_http_exec    --name dvr_http
pm2 start dvr_gateway_https_exec/dvr_gateway_https_exec  --name dvr_https
pm2 start fm_gateway_exec/fm_gateway_exec                --name fm_http
pm2 start fm_gateway_https_exec/fm_gateway_https_exec    --name fm_https
pm2 start message_hub_exec/message_hub_exec              --name message_hub
# pm2 start dealer_gui_exec/dealer_gui_exec                --name dealer_gui # OPTIONAL, linux cant load tkinter

pm2 save
echo
pm2 ls
