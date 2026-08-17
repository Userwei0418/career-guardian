from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_data.errors import SourcePolicyError
from market_data.services.network_access import (
    EnvironmentNetworkAccessResolver,
    validate_network_policy,
)


class NetworkAccessPolicyTests(unittest.TestCase):
    def test_policy_only_accepts_opaque_references(self) -> None:
        self.assertEqual(
            {
                "mode": "proxy_and_session",
                "proxy_pool_id": "campus-cn-east",
                "session_profile_id": "moka.public",
            },
            validate_network_policy(
                {
                    "mode": "proxy_and_session",
                    "proxy_pool_id": "campus-cn-east",
                    "session_profile_id": "moka.public",
                }
            ),
        )
        for unsafe in (
            {"mode": "proxy", "proxy_url": "http://user:pass@example.test:8080"},
            {"mode": "session", "cookie": "secret=value"},
            {"mode": "proxy", "proxy_pool_id": "http://example.test"},
        ):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                validate_network_policy(unsafe)

    def test_resolver_keeps_secrets_out_of_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps({"cookies": []}), encoding="utf-8")
            environment = {
                "MARKET_PROXY_POOL_CAMPUS_CN_EAST": json.dumps(
                    {
                        "server": "http://proxy.internal:8080",
                        "username": "crawler-user",
                        "password": "crawler-password",
                    }
                ),
                "MARKET_SESSION_PROFILE_MOKA_PUBLIC": str(state_path),
            }
            with patch.dict(os.environ, environment, clear=False):
                resolved = EnvironmentNetworkAccessResolver().resolve(
                    {
                        "mode": "proxy_and_session",
                        "proxy_pool_id": "campus-cn-east",
                        "session_profile_id": "moka.public",
                    }
                )

            self.assertEqual(
                "crawler-password", resolved.launch_options["proxy"]["password"]
            )
            self.assertEqual(
                str(state_path.resolve()), resolved.context_options["storage_state"]
            )
            summary_text = json.dumps(resolved.summary, ensure_ascii=False)
            self.assertNotIn("proxy.internal", summary_text)
            self.assertNotIn("crawler-user", summary_text)
            self.assertNotIn("crawler-password", summary_text)
            self.assertEqual("campus-cn-east", resolved.summary["proxy_pool_id"])

    def test_missing_server_side_reference_is_an_explicit_policy_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SourcePolicyError, "代理池 missing-pool"):
                EnvironmentNetworkAccessResolver().resolve(
                    {"mode": "proxy", "proxy_pool_id": "missing-pool"}
                )


if __name__ == "__main__":
    unittest.main()
