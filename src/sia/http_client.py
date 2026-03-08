from __future__ import annotations

import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


logger = logging.getLogger("trading_signal_notifier")


def parse_http_error_payload(exc: urllib.error.HTTPError) -> dict[str, Any] | None:
    try:
        body = exc.read().decode("utf-8", errors="ignore")
    except Exception:
        return None
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout: int = 20,
    max_retries: int = 2,
    backoff_seconds: float = 0.5,
) -> dict[str, Any]:
    method = method.upper()
    request_headers = dict(headers or {})
    if method == "GET":
        if payload is not None:
            delimiter = "&" if "?" in url else "?"
            url = f"{url}{delimiter}{urllib.parse.urlencode(payload)}"
        data = None
    elif method == "POST":
        request_headers.setdefault("Content-Type", "application/json")
        data = json.dumps(payload or {}).encode("utf-8")
    else:
        raise ValueError(f"지원되지 않는 HTTP 메서드: {method}")

    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)

    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="ignore")
            if not body.strip():
                return {}
            return json.loads(body)
        except urllib.error.HTTPError as exc:
            error_payload = parse_http_error_payload(exc)
            if error_payload is not None:
                return error_payload
            if attempt >= max_retries:
                raise RuntimeError(f"{method} 요청 실패: {url}") from exc
            logger.warning("HTTP 재시도 (%d/%d) 요청=%s: %s", attempt + 1, max_retries, url, exc)
            time.sleep(backoff_seconds * (2**attempt))
        except (urllib.error.URLError, socket.timeout, TimeoutError, json.JSONDecodeError) as exc:
            if attempt >= max_retries:
                raise RuntimeError(f"{method} 요청 실패: {url}") from exc
            logger.warning("HTTP 재시도 (%d/%d) 요청=%s: %s", attempt + 1, max_retries, url, exc)
            time.sleep(backoff_seconds * (2**attempt))
    return {}


def http_get_json(
    url: str,
    params: dict[str, str] | None = None,
    timeout: int = 20,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    if params:
        return json_request(url, payload=params, method="GET", timeout=timeout, headers=headers)
    return json_request(url, method="GET", timeout=timeout, headers=headers)


def http_get_text(
    url: str,
    params: dict[str, str] | None = None,
    *,
    timeout: int = 20,
    max_retries: int = 2,
    backoff_seconds: float = 0.5,
    headers: dict[str, str] | None = None,
) -> str:
    if params is not None:
        delimiter = "&" if "?" in url else "?"
        url = f"{url}{delimiter}{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="ignore")
        except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            if attempt >= max_retries:
                raise RuntimeError(f"GET 요청 실패: {url}") from exc
            logger.warning("HTTP 텍스트 요청 재시도 (%d/%d) (%s): %s", attempt + 1, max_retries, url, exc)
            time.sleep(backoff_seconds * (2**attempt))
    return ""


def http_post_json(
    url: str,
    payload: dict[str, Any],
    timeout: int = 8,
    max_retries: int = 1,
) -> dict[str, Any]:
    return json_request(
        url,
        payload=payload,
        method="POST",
        timeout=timeout,
        max_retries=max_retries,
    )
