#!/usr/bin/env bash
# Daily collection job for the prospective pilot (discover + capture + follow-up + public export).
# Collection only happens when this script actually runs. Example cron entry (America/New_York, 07:15 daily):
#   CRON_TZ=America/New_York
#   15 7 * * * /path/to/DunklikeVC/personal_vc_research/prospective/run_daily.sh >> /path/to/prospective_cron.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
: "${SEC_USER_AGENT:?set SEC_USER_AGENT='project-name your.email@example.com' (SEC fair-access policy)}"
python3 -m prospective run
# Weekly report on Mondays (local time)
if [ "$(date +%u)" = "1" ]; then python3 -m prospective report-weekly; fi
# Monthly coverage report on the 1st
if [ "$(date +%d)" = "01" ]; then python3 -m prospective report-monthly; fi
