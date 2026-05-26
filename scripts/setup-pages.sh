#!/usr/bin/env bash
set -euo pipefail

GITHUB_REPO_URL="https://github.com/hl9565/paralives-guide.git"
PROJECT_NAME="paralives-guide"
PRODUCTION_BRANCH="main"

usage() {
  cat <<'EOF'
Usage: ./scripts/setup-pages.sh [--apply] [--github-only] [--cloudflare-only] [--skip-push] [--help]

Options:
  --apply            Perform external actions. Without this flag, the script stays in dry-run mode.
  --github-only      Only configure/check the GitHub remote and push main.
  --cloudflare-only  Only create/check the Cloudflare Pages project and deploy it.
  --skip-push        Configure/check the GitHub remote but do not push.
  --help             Show this help message.
EOF
}

status() {
  printf '==> %s\n' "$1"
}

error() {
  printf 'Error: %s\n' "$1" >&2
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    error "Required command not found: $1"
    exit 1
  fi
}

github_only=false
cloudflare_only=false
skip_push=false
apply=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      apply=true
      ;;
    --github-only)
      github_only=true
      ;;
    --cloudflare-only)
      cloudflare_only=true
      ;;
    --skip-push)
      skip_push=true
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      error "Unknown argument: $1"
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if $github_only && $cloudflare_only; then
  error "--github-only and --cloudflare-only cannot be used together."
  exit 1
fi

run_github=true
run_cloudflare=true

if $github_only; then
  run_cloudflare=false
fi

if $cloudflare_only; then
  run_github=false
fi

if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  error "Run this script from inside the project checkout."
  exit 1
fi

current_branch="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD)"
if [[ "$current_branch" != "$PRODUCTION_BRANCH" ]]; then
  error "Current branch is '$current_branch'. Switch to '$PRODUCTION_BRANCH' before running this script."
  exit 1
fi

run_wrangler() {
  npx wrangler --cwd "$repo_root" "$@"
}

manual_steps_notice() {
  cat <<'EOF'
Manual Cloudflare follow-up:
In Cloudflare Pages, add paralivesguide.help as the primary custom domain for project paralives-guide if it is not already attached.
Then attach paralives.help only as a redirect alias to https://paralivesguide.help/; do not make it a second canonical site.
This script does not change DNS automatically. Review any DNS records Cloudflare suggests before making changes.
EOF
}

ensure_no_tracked_secret_files() {
  local tracked_env_files

  tracked_env_files="$(git -C "$repo_root" ls-files '.env' '.env.*' ':!:*.example' || true)"
  if [[ -n "$tracked_env_files" ]]; then
    error "Tracked env files detected. Remove them from git before any push or deploy:"
    printf '%s\n' "$tracked_env_files" >&2
    exit 1
  fi
}

dry_run_notice() {
  status "Dry run only. Re-run with --apply to add remotes, push, create Pages projects, or deploy."
}

ensure_github_remote() {
  status "Checking GitHub CLI"
  require_command gh

  status "Checking GitHub CLI authentication"
  if ! gh auth status >/dev/null 2>&1; then
    error "GitHub CLI is not authenticated. Run: gh auth login"
    exit 1
  fi

  status "Checking git remote 'origin'"
  if git -C "$repo_root" remote get-url origin >/dev/null 2>&1; then
    existing_origin="$(git -C "$repo_root" remote get-url origin)"
    if [[ "$existing_origin" != "$GITHUB_REPO_URL" ]]; then
      error "Existing origin points to '$existing_origin', expected '$GITHUB_REPO_URL'."
      exit 1
    fi
    status "Origin already points to $GITHUB_REPO_URL"
  else
    if ! $apply; then
      status "Would add origin remote: $GITHUB_REPO_URL"
      return
    fi
    status "Adding origin remote"
    git -C "$repo_root" remote add origin "$GITHUB_REPO_URL"
  fi
}

push_main_branch() {
  ensure_no_tracked_secret_files

  if $skip_push; then
    status "Skipping git push because --skip-push was provided"
    return
  fi

  if ! $apply; then
    status "Would push $PRODUCTION_BRANCH to origin"
    return
  fi

  status "Pushing $PRODUCTION_BRANCH to origin"
  git -C "$repo_root" push -u origin "$PRODUCTION_BRANCH"
}

ensure_cloudflare_requirements() {
  status "Checking Node.js and npm"
  require_command node
  require_command npm
  require_command npx

  status "Checking Cloudflare Wrangler authentication"
  if ! run_wrangler whoami --json >/dev/null 2>&1; then
    error "Wrangler is not authenticated. Run: npx wrangler login"
    exit 1
  fi
}

pages_project_exists() {
  local project_json

  if ! project_json="$(run_wrangler pages project list --json 2>/dev/null)"; then
    return 1
  fi

  printf '%s' "$project_json" | node -e '
    const fs = require("fs");
    const data = JSON.parse(fs.readFileSync(0, "utf8"));
    const target = process.argv[1];
    process.exit(Array.isArray(data) && data.some((entry) => entry && entry.name === target) ? 0 : 1);
  ' "$PROJECT_NAME"
}

ensure_pages_project() {
  status "Checking Cloudflare Pages project"
  if pages_project_exists; then
    status "Pages project '$PROJECT_NAME' already exists"
    return
  fi

  if ! $apply; then
    status "Would create Cloudflare Pages project '$PROJECT_NAME' with production branch '$PRODUCTION_BRANCH'"
    return
  fi

  status "Creating Cloudflare Pages project '$PROJECT_NAME'"
  run_wrangler pages project create "$PROJECT_NAME" --production-branch "$PRODUCTION_BRANCH"
}

deploy_pages_project() {
  local deploy_output
  local pages_url

  ensure_no_tracked_secret_files

  if ! $apply; then
    status "Would deploy '$repo_root' to Cloudflare Pages project '$PROJECT_NAME' on branch '$PRODUCTION_BRANCH'"
    manual_steps_notice
    return
  fi

  status "Deploying static site root to Cloudflare Pages"
  deploy_output="$(run_wrangler pages deploy "$repo_root" --project-name "$PROJECT_NAME" --branch "$PRODUCTION_BRANCH" 2>&1)"
  printf '%s\n' "$deploy_output"

  pages_url="$(printf '%s\n' "$deploy_output" | grep -Eo 'https://[[:alnum:]._-]+\.pages\.dev' | head -n 1 || true)"
  if [[ -n "$pages_url" ]]; then
    status "Pages deployment URL: $pages_url"
  else
    status "Pages deployment finished for project '$PROJECT_NAME'"
    status "If Wrangler did not print a deployment URL, check the Cloudflare Pages dashboard for the latest deployment."
  fi

  manual_steps_notice
}

if ! $apply; then
  dry_run_notice
fi

if $run_github; then
  ensure_github_remote
  push_main_branch
fi

if $run_cloudflare; then
  ensure_cloudflare_requirements
  ensure_pages_project
  deploy_pages_project
fi
