from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from market_data.errors import SourcePolicyError


REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
NETWORK_POLICY_MODES = {"direct", "proxy", "session", "proxy_and_session"}
NETWORK_POLICY_KEYS = {"mode", "proxy_pool_id", "session_profile_id"}


def _environment_suffix(reference: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", reference).upper()


def validate_network_policy(value: object) -> dict[str, str]:
    """Validate an opaque network/session reference without accepting secrets.

    Recruitment channel rows may select an administrator-managed pool or
    session profile, but never persist proxy URLs, credentials, Cookie values,
    or browser storage state.
    """

    if value in (None, {}):
        return {"mode": "direct"}
    if not isinstance(value, dict):
        raise ValueError("network_policy 必须是对象")
    unknown = sorted(set(value) - NETWORK_POLICY_KEYS)
    if unknown:
        raise ValueError(
            f"network_policy 只能保存受控引用，包含不允许的字段: {', '.join(unknown)}"
        )
    mode = str(value.get("mode") or "direct").strip().lower()
    if mode not in NETWORK_POLICY_MODES:
        raise ValueError("network_policy.mode 必须是 direct/proxy/session/proxy_and_session")
    result = {"mode": mode}
    for key in ("proxy_pool_id", "session_profile_id"):
        reference = str(value.get(key) or "").strip()
        if reference:
            if not REFERENCE_PATTERN.fullmatch(reference):
                raise ValueError(f"network_policy.{key} 不是有效的受控引用")
            result[key] = reference
    if mode in {"proxy", "proxy_and_session"} and "proxy_pool_id" not in result:
        raise ValueError("选择代理模式时必须配置 proxy_pool_id")
    if mode in {"session", "proxy_and_session"} and "session_profile_id" not in result:
        raise ValueError("选择会话模式时必须配置 session_profile_id")
    return result


@dataclass(frozen=True)
class ResolvedNetworkAccess:
    launch_options: dict
    context_options: dict
    summary: dict[str, str]


class EnvironmentNetworkAccessResolver:
    """Resolve opaque IDs from server-only environment configuration.

    Proxy pool JSON is read from ``MARKET_PROXY_POOL_<ID>`` and Playwright
    storage state path from ``MARKET_SESSION_PROFILE_<ID>``. These resolved
    values are deliberately never returned by management APIs or task logs.
    """

    def resolve(self, value: object) -> ResolvedNetworkAccess:
        policy = validate_network_policy(value)
        mode = policy["mode"]
        launch_options: dict = {}
        context_options: dict = {}
        summary = {"mode": mode}

        proxy_id = policy.get("proxy_pool_id")
        if proxy_id:
            env_name = f"MARKET_PROXY_POOL_{_environment_suffix(proxy_id)}"
            raw = os.getenv(env_name, "").strip()
            if not raw:
                raise SourcePolicyError(f"代理池 {proxy_id} 尚未在服务端配置")
            try:
                proxy = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SourcePolicyError(f"代理池 {proxy_id} 的服务端配置无效") from exc
            if not isinstance(proxy, dict) or not str(proxy.get("server") or "").strip():
                raise SourcePolicyError(f"代理池 {proxy_id} 缺少 server")
            launch_options["proxy"] = {
                key: str(proxy[key])
                for key in ("server", "bypass", "username", "password")
                if proxy.get(key) not in (None, "")
            }
            summary["proxy_pool_id"] = proxy_id

        session_id = policy.get("session_profile_id")
        if session_id:
            env_name = f"MARKET_SESSION_PROFILE_{_environment_suffix(session_id)}"
            state_path = os.getenv(env_name, "").strip()
            if not state_path:
                raise SourcePolicyError(f"会话配置 {session_id} 尚未在服务端配置")
            path = Path(state_path).expanduser().resolve()
            if not path.is_file():
                raise SourcePolicyError(f"会话配置 {session_id} 的服务端文件不存在")
            context_options["storage_state"] = str(path)
            summary["session_profile_id"] = session_id

        return ResolvedNetworkAccess(
            launch_options=launch_options,
            context_options=context_options,
            summary=summary,
        )


def resolve_network_access(value: object) -> ResolvedNetworkAccess:
    return EnvironmentNetworkAccessResolver().resolve(value)
