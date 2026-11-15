#!/bin/sh
set -eu
PORT="${PORT:-10000}"
sed "s/listen 10000;/listen ${PORT};/" /etc/nginx/templates/ai-voice.conf.template > /etc/nginx/conf.d/default.conf
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/ai-voice.conf
