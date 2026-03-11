#!/usr/bin/env bash
set -euo pipefail

collect_api_status() {
  local log_file="$1"
  local line
  local -a notes=()

  if [[ ! -f "$log_file" ]]; then
    echo "NONE"
    return 0
  fi

  if grep -qiE "finnhub.*candle.*(failed|denied|blocked|403|401|429|error)|FINNHUB_CANDLE_ACCESS_DENIED|candle endpoint blocked|stock/candle" "$log_file"; then
    line="$(grep -iE "finnhub.*candle.*(failed|denied|blocked|403|401|429|error)|FINNHUB_CANDLE_ACCESS_DENIED|candle endpoint blocked|stock/candle" "$log_file" | head -n 1 | sed -E 's/[[:space:]]+/ /g')"
    if echo "$line" | grep -qiE "FINNHUB_CANDLE_ACCESS_DENIED|access denied|권한|요금제|403|don't have access|access to this resource"; then
      notes+=("FALLBACK|FINNHUB: 차트 조회 권한/요금제 제한으로 대체 경로 사용(권장: 업그레이드 확인). 예시: ${line:0:170}")
    else
      notes+=("FALLBACK|FINNHUB: 캔들 데이터 실패(차트 폴백). 예시: ${line:0:170}")
    fi
  fi

  if grep -qiE "MARKETAUX_API_KEY.*(placeholder|dummy|missing)|MARKETAUX.*(disabled|not configured|no key|access denied)|news fetch disabled|marketaux.*failed|marketaux.*error" "$log_file"; then
    line="$(grep -iE "MARKETAUX_API_KEY.*(placeholder|dummy|missing)|MARKETAUX.*(disabled|not configured|no key|access denied)|news fetch disabled|marketaux.*failed|marketaux.*error" "$log_file" | head -n 1 | sed -E 's/[[:space:]]+/ /g')"
    notes+=("FALLBACK|MARKETAUX: 뉴스 기반 분석이 비활성/실패 상태입니다(폴백). 예시: ${line:0:180}")
  fi

  if grep -qiE "telegram.*(failed|error|request failed|send failed|send skipped|timeout|forbidden|bad request|unauthorized|not modified|retry after|TELEGRAM_API|api request)" "$log_file"; then
    line="$(grep -iE "telegram.*(failed|error|request failed|send failed|send skipped|timeout|forbidden|bad request|unauthorized|not modified|retry after|TELEGRAM_API|api request)" "$log_file" | head -n 1 | sed -E 's/[[:space:]]+/ /g')"
    notes+=("BLOCKER|TELEGRAM: 발송 API 호출 오류/재전송 필요(운영 영향 큼). 예시: ${line:0:180}")
  fi

  if grep -qiE "ollama.*(failed|error|timeout|connection refused|unavailable|service not running|not found)|OLLAMA.*error|ollama service unavailable" "$log_file"; then
    line="$(grep -iE "ollama.*(failed|error|timeout|connection refused|unavailable|service not running|not found)|OLLAMA.*error|ollama service unavailable" "$log_file" | head -n 1 | sed -E 's/[[:space:]]+/ /g')"
    notes+=("FALLBACK|OLLAMA: LLM 호출 실패(현재 폴백 규칙 사용). 예시: ${line:0:180}")
  fi

  if grep -qiE "failing|failure|exception|traceback|stacktrace" "$log_file"; then
    line="$(grep -iE "failing|failure|exception|traceback|stacktrace" "$log_file" | head -n 1 | sed -E 's/[[:space:]]+/ /g')"
    notes+=("BLOCKER|GENERAL: 런타임 예외/에러 감지. 예시: ${line:0:180}")
  fi

  if (( ${#notes[@]} == 0 )); then
    echo "NONE"
    return 0
  fi

  printf '%s\n' "${notes[@]}"
}

parse_api_status() {
  local api_notes="$1"
  local blocker_count fallback_count
  blocker_count=0
  fallback_count=0
  API_STATUS_BLOCKER_LIST=()
  API_STATUS_FALLBACK_LIST=()
  API_STATUS_UNKNOWN_LIST=()

  if [[ "$api_notes" == "NONE" ]]; then
    API_GRADE="OK"
    return 0
  fi

  while IFS='|' read -r severity msg; do
    if [[ "$severity" == "BLOCKER" ]]; then
      API_STATUS_BLOCKER_LIST+=("$msg")
      blocker_count=$((blocker_count + 1))
    elif [[ "$severity" == "FALLBACK" ]]; then
      API_STATUS_FALLBACK_LIST+=("$msg")
      fallback_count=$((fallback_count + 1))
    else
      API_STATUS_UNKNOWN_LIST+=("${severity}|${msg}")
    fi
  done <<< "$api_notes"

  if (( blocker_count > 0 )); then
    API_GRADE="BLOCKER"
  elif (( fallback_count > 0 )); then
    API_GRADE="FALLBACK"
  else
    API_GRADE="OK"
  fi
}
