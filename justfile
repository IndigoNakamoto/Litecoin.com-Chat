# Litecoin Knowledge Hub operator surface.
# Daily work on the build machine: `just up dev`
# Do not run `just up prod` here — that claims production tunnels.

set dotenv-load := false

default:
    @just --list

preflight target="dev":
    ./scripts/preflight.sh {{target}}

up target="dev":
    #!/usr/bin/env bash
    set -euo pipefail
    ./scripts/preflight.sh {{target}}
    case "{{target}}" in
      dev) ./scripts/run-dev.sh ;;
      prod-local) ./scripts/run-prod-local.sh ;;
      prod)
        echo "Refusing just up prod on the build machine (claims Cloudflare tunnels)."
        echo "Use just up prod-local here, or run-prod.sh only on the Mini."
        exit 1
        ;;
      *)
        echo "Unknown target {{target}} (dev|prod-local)"
        exit 1
        ;;
    esac

down target="dev":
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{target}}" in
      dev) docker compose -f docker-compose.dev.yml down ;;
      prod-local) docker compose -f docker-compose.prod-local.yml down ;;
      prod) ./scripts/down-prod.sh ;;
      *) echo "Unknown target {{target}}"; exit 1 ;;
    esac

rebuild service="backend":
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{service}}" in
      backend) ./scripts/rebuild-backend.sh ;;
      frontend) ./scripts/rebuild-frontend.sh ;;
      admin) ./scripts/rebuild-admin-frontend.sh ;;
      *) echo "Unknown service {{service}} (backend|frontend|admin)"; exit 1 ;;
    esac

diagnose:
    ./scripts/diagnose-prod.sh

backup:
    ./scripts/backup-mongodb.sh

reindex:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "${ADMIN_TOKEN:-}" ]; then
      echo "Set ADMIN_TOKEN to enqueue reindex"
      exit 1
    fi
    curl -sf -X POST http://localhost:8000/api/v1/admin/jobs/reindex \
      -H "Authorization: Bearer $ADMIN_TOKEN"
    echo
