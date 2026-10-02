#!/usr/bin/env bash
set -e
sudo service postgresql start
until pg_isready -h 127.0.0.1 -q; do sleep 0.3; done
echo "postgres ready"
if ! curl -sf -o /dev/null http://localhost:3000/login; then
  sudo -u grafana nohup /usr/share/grafana/bin/grafana server \
    --config=/etc/grafana/grafana.ini \
    --homepath=/usr/share/grafana \
    cfg:default.paths.data=/var/lib/grafana \
    cfg:default.paths.logs=/var/log/grafana \
    cfg:default.paths.plugins=/var/lib/grafana/plugins \
    cfg:default.paths.provisioning=/etc/grafana/provisioning \
    > /tmp/grafana.log 2>&1 &
  until curl -sf -o /dev/null http://localhost:3000/login; do sleep 0.5; done
fi
echo "grafana ready -> http://localhost:3000"
