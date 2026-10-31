#!/usr/bin/env bash
set -Eeuo pipefail

# Idempotent Let's Encrypt provisioner. Initial issuance uses a temporary Nginx
# ACME listener; renewals use the long-running production Nginx webroot and a
# graceful config reload, so certificate replacement does not drop connections.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${PAPERPLANE_DOMAIN:-}"
EMAIL="${PAPERPLANE_CERTBOT_EMAIL:-${CERTBOT_EMAIL:-}}"
CERT_DIR="$ROOT_DIR/deploy/certs"
WEBROOT="$ROOT_DIR/deploy/acme"
LETSENCRYPT_DIR="$CERT_DIR/letsencrypt"
TEMP_CONTAINER="paperplane-acme-nginx"
TEMP_CONFIG=""
NGINX_STOPPED=0
COMPOSE=(docker compose)

log() { printf '[ssl] %s\n' "$*"; }
die() { printf '[ssl] ERROR: %s\n' "$*" >&2; exit 1; }

cleanup() {
  if [[ -n "$TEMP_CONFIG" ]]; then
    docker rm -f "$TEMP_CONTAINER" >/dev/null 2>&1 || true
    rm -f "$TEMP_CONFIG"
  fi
  if [[ "$NGINX_STOPPED" == "1" ]]; then
    "${COMPOSE[@]}" up -d nginx >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

load_env() {
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    . "$ROOT_DIR/.env"
    set +a
    DOMAIN="${PAPERPLANE_DOMAIN:-$DOMAIN}"
    EMAIL="${PAPERPLANE_CERTBOT_EMAIL:-${CERTBOT_EMAIL:-$EMAIL}}"
  fi
}

require_tools() {
  command -v docker >/dev/null 2>&1 || die "docker is required"
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required"
  command -v getent >/dev/null 2>&1 || command -v dig >/dev/null 2>&1 || die "getent or dig is required for DNS validation"
  command -v curl >/dev/null 2>&1 || die "curl is required for ACME listener validation"
  [[ -n "$EMAIL" ]] || die "Set PAPERPLANE_CERTBOT_EMAIL or CERTBOT_EMAIL"
}

validate_domain() {
  [[ -n "$DOMAIN" ]] || die "Set PAPERPLANE_DOMAIN"
  [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || die "PAPERPLANE_DOMAIN contains invalid characters"
  [[ "$DOMAIN" != "localhost" && "$DOMAIN" != "127.0.0.1" && "$DOMAIN" != "yourdomain.com" ]] || die "A public domain is required for Let's Encrypt"
}

validate_dns() {
  local addresses
  if command -v dig >/dev/null 2>&1; then
    addresses="$(dig +short A "$DOMAIN" | awk 'NF {print $1}')"
  else
    addresses="$(getent ahostsv4 "$DOMAIN" | awk '{print $1}' | sort -u)"
  fi
  [[ -n "$addresses" ]] || die "No DNS A record resolves for $DOMAIN"
  while read -r address; do
    [[ -n "$address" ]] || continue
    if [[ "$address" =~ ^(10\.|127\.|169\.254\.|192\.168\.|0\.) ]]; then
      die "DNS A record $address is not publicly reachable"
    fi
    if [[ "$address" =~ ^172\.([1][6-9]|2[0-9]|3[0-1])\. ]]; then
      die "DNS A record $address is a private address"
    fi
  done <<< "$addresses"
  log "DNS A record validated for $DOMAIN: $(tr '\n' ' ' <<< "$addresses")"
}

install_cron() {
  command -v crontab >/dev/null 2>&1 || die "crontab is required to install automatic renewal"
  local line="0 3 1 * * cd '$ROOT_DIR' && bash '$ROOT_DIR/scripts/provision_ssl.sh' --renew-only >> '$ROOT_DIR/deploy/ssl-renew.log' 2>&1"
  (crontab -l 2>/dev/null | grep -vF "$ROOT_DIR/scripts/provision_ssl.sh --renew-only" || true; printf '%s\n' "$line") | crontab -
  log "Installed monthly renewal cron at 03:00 on the first day of each month"
}

copy_certificates() {
  local live_dir="$LETSENCRYPT_DIR/live/$DOMAIN"
  [[ -s "$live_dir/fullchain.pem" && -s "$live_dir/privkey.pem" ]] || die "Certbot did not produce certificates in $live_dir"
  install -d -m 700 "$CERT_DIR"
  install -m 644 "$live_dir/fullchain.pem" "$CERT_DIR/fullchain.pem"
  install -m 600 "$live_dir/privkey.pem" "$CERT_DIR/privkey.pem"
  log "Installed fullchain.pem and privkey.pem into deploy/certs"
}

reload_nginx() {
  if "${COMPOSE[@]}" ps -q nginx 2>/dev/null | grep -q .; then
    "${COMPOSE[@]}" exec -T nginx nginx -s reload
  else
    "${COMPOSE[@]}" up -d nginx
  fi
}

renew() {
  log "Running zero-downtime Certbot renewal"
  docker run --rm --network host \
    -v "$WEBROOT:/var/www/certbot" \
    -v "$LETSENCRYPT_DIR:/etc/letsencrypt" \
    certbot/certbot:latest renew --webroot --webroot-path /var/www/certbot --quiet
  copy_certificates
  reload_nginx
  install_cron
}

initial_issue() {
  install -d -m 755 "$WEBROOT" "$LETSENCRYPT_DIR" "$CERT_DIR"
  install -d -m 755 "$WEBROOT/.well-known/acme-challenge"
  local challenge="paperplane-$(date +%s)"
  printf '%s\n' "$challenge" > "$WEBROOT/.well-known/acme-challenge/$challenge"
  printf '%s\n' "$challenge" > "$WEBROOT/$challenge"
  TEMP_CONFIG="$(mktemp)"
  cat > "$TEMP_CONFIG" <<EOF
events {}
http {
  server {
    listen 80 default_server;
    server_name $DOMAIN 127.0.0.1 localhost;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
  }
}
EOF

  # Stop only the production Nginx container if it currently owns port 80.
  if "${COMPOSE[@]}" ps -q nginx 2>/dev/null | grep -q .; then
    "${COMPOSE[@]}" stop nginx >/dev/null 2>&1 || true
    NGINX_STOPPED=1
  fi
  docker run -d --rm --name "$TEMP_CONTAINER" -p 80:80 \
    -v "$WEBROOT:/var/www/certbot:ro" \
    -v "$TEMP_CONFIG:/etc/nginx/nginx.conf:ro" \
    nginx:1.27-alpine >/dev/null
  sleep 2
  curl --fail --silent "http://127.0.0.1/.well-known/acme-challenge/$challenge" | grep -q "$challenge" || die "Temporary ACME Nginx listener failed"

  log "Requesting Let's Encrypt certificate for $DOMAIN"
  docker run --rm --network host \
    -v "$WEBROOT:/var/www/certbot:ro" \
    -v "$LETSENCRYPT_DIR:/etc/letsencrypt" \
    certbot/certbot:latest certonly --webroot --webroot-path /var/www/certbot \
    --config-dir /etc/letsencrypt --work-dir /var/lib/letsencrypt --logs-dir /var/log/letsencrypt \
    --domain "$DOMAIN" --email "$EMAIL" --agree-tos --no-eff-email --non-interactive
  copy_certificates
  "${COMPOSE[@]}" up -d nginx
  NGINX_STOPPED=0
  install_cron
}

main() {
  load_env
  require_tools
  validate_domain
  validate_dns
  if [[ "${1:-}" == "--renew-only" ]]; then
    renew
  elif [[ -s "$CERT_DIR/fullchain.pem" && -s "$CERT_DIR/privkey.pem" && "${1:-}" != "--force" ]]; then
    log "Certificates already exist; using idempotent renewal path"
    renew
  else
    initial_issue
  fi
}

main "$@"
