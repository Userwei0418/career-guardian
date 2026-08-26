import hashlib
import os
import subprocess
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from mysql_test_support import MYSQL_TEST_DATABASE_URL, mysql_test


class OfflineMigrationTest(unittest.TestCase):
    backend_dir = Path(__file__).resolve().parents[1]

    def _offline_environment(self):
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": "mysql+pymysql://offline:offline@127.0.0.1:1/offline",
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )
        return environment

    def test_decision_guardian_migrations_render_full_round_trip(self):
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260819_0021:20260820_0024",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=self._offline_environment(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(upgrade.returncode, 0, upgrade.stdout + upgrade.stderr)
        self.assertLess(upgrade.stdout.index("CREATE TABLE offer_revisions"), upgrade.stdout.index("CREATE TABLE offer_decision_contexts"))
        self.assertLess(upgrade.stdout.index("CREATE TABLE offer_decision_contexts"), upgrade.stdout.index("CREATE TABLE offer_analysis_snapshots"))

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260820_0024:20260819_0021",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=self._offline_environment(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(downgrade.returncode, 0, downgrade.stdout + downgrade.stderr)
        self.assertLess(downgrade.stdout.index("DROP TABLE offer_analysis_snapshots"), downgrade.stdout.index("DROP TABLE offer_decision_contexts"))
        self.assertLess(downgrade.stdout.index("DROP TABLE offer_decision_contexts"), downgrade.stdout.index("DROP TABLE offer_revisions"))
        self.assertLess(
            downgrade.stdout.index("DROP FOREIGN KEY fk_decision_analysis_snapshot"),
            downgrade.stdout.index("DROP INDEX ix_decision_records_analysis_snapshot_id"),
        )
        self.assertLess(
            downgrade.stdout.index(
                "DROP FOREIGN KEY fk_decision_records_offer_revision_id_offer_revisions"
            ),
            downgrade.stdout.index("DROP INDEX ix_decision_records_offer_revision_id"),
        )

    def test_cashflow_guardian_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260821_0028:20260822_0029",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE financial_categories", output)
        self.assertIn("CREATE TABLE financial_transactions", output)
        self.assertIn("uq_financial_transaction_source_key", output)
        self.assertLess(
            output.index("CREATE TABLE financial_categories"),
            output.index("CREATE TABLE financial_transactions"),
        )

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260822_0029:20260821_0028",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(
            output.index("DROP TABLE financial_transactions"),
            output.index("DROP TABLE financial_categories"),
        )

    def test_growth_work_loop_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260825_0057:20260825_0058",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        expected_tables = [
            "growth_work_intakes",
            "growth_work_items",
            "growth_emotion_notes",
            "growth_work_events",
            "growth_weekly_reports",
            "growth_audit_events",
        ]
        for table in expected_tables:
            self.assertIn(f"CREATE TABLE {table}", output)
        self.assertLess(output.index("CREATE TABLE growth_work_intakes"), output.index("CREATE TABLE growth_work_items"))
        self.assertLess(output.index("CREATE TABLE growth_work_items"), output.index("CREATE TABLE growth_work_events"))

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260825_0058:20260825_0057",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(output.index("DROP TABLE growth_work_events"), output.index("DROP TABLE growth_work_items"))
        self.assertLess(output.index("DROP TABLE growth_work_items"), output.index("DROP TABLE growth_work_intakes"))

    def test_growth_assets_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260825_0058:20260825_0059",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        expected_tables = [
            "growth_portfolio_items",
            "growth_evidence_items",
            "growth_skill_assessments",
            "growth_skill_evidence_links",
            "growth_reflections",
        ]
        for table in expected_tables:
            self.assertIn(f"CREATE TABLE {table}", output)
        self.assertIn("uq_growth_portfolio_owner_request", output)
        self.assertIn("uq_growth_evidence_owner_request", output)
        self.assertIn("uq_growth_reflection_owner_event", output)
        self.assertLess(output.index("CREATE TABLE growth_portfolio_items"), output.index("CREATE TABLE growth_evidence_items"))
        self.assertLess(output.index("CREATE TABLE growth_skill_assessments"), output.index("CREATE TABLE growth_skill_evidence_links"))

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260825_0059:20260825_0058",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(output.index("DROP TABLE growth_reflections"), output.index("DROP TABLE growth_evidence_items"))
        self.assertLess(output.index("DROP TABLE growth_skill_evidence_links"), output.index("DROP TABLE growth_skill_assessments"))
        self.assertLess(output.index("DROP TABLE growth_evidence_items"), output.index("DROP TABLE growth_portfolio_items"))

    def test_growth_direction_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260825_0059:20260825_0060", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        for table in ("growth_future_targets", "growth_market_signals", "growth_gap_snapshots", "growth_milestones"):
            self.assertIn(f"CREATE TABLE {table}", output)
        self.assertIn("uq_growth_target_owner_key_version", output)
        self.assertIn("uq_growth_market_signal_batch_key", output)
        self.assertIn("uq_growth_gap_target_version", output)
        self.assertIn("uq_growth_milestone_owner_key_version", output)
        self.assertLess(output.index("CREATE TABLE growth_future_targets"), output.index("CREATE TABLE growth_market_signals"))
        self.assertLess(output.index("CREATE TABLE growth_gap_snapshots"), output.index("CREATE TABLE growth_milestones"))

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260825_0060:20260825_0059", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(output.index("DROP TABLE growth_milestones"), output.index("DROP TABLE growth_gap_snapshots"))
        self.assertLess(output.index("DROP TABLE growth_market_signals"), output.index("DROP TABLE growth_future_targets"))

    def test_growth_integration_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260825_0060:20260825_0061", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE growth_communication_drafts", output)
        self.assertIn("CREATE TABLE growth_handoffs", output)
        self.assertIn("CREATE TABLE growth_inquiries", output)
        self.assertIn("uq_growth_communication_owner_key_version", output)
        self.assertIn("ix_growth_handoff_target_inbox", output)
        self.assertIn("ck_growth_handoffs_status", output)

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260825_0061:20260825_0060", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(output.index("DROP TABLE growth_inquiries"), output.index("DROP TABLE growth_handoffs"))
        self.assertLess(output.index("DROP TABLE growth_handoffs"), output.index("DROP TABLE growth_communication_drafts"))

    def test_growth_market_temperature_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260825_0061:20260825_0062", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN recent_count", output)
        self.assertIn("ADD COLUMN share_delta", output)
        self.assertIn("ADD COLUMN previous_window_end", output)

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260825_0062:20260825_0061", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN previous_window_end", output)
        self.assertIn("DROP COLUMN recent_count", output)

    def test_growth_work_coaching_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260825_0062:20260825_0063", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN progress_summary", output)
        self.assertIn("ADD COLUMN blocker_note", output)
        self.assertIn("ADD COLUMN next_action", output)

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260825_0063:20260825_0062", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN next_action", output)
        self.assertIn("DROP COLUMN progress_summary", output)

    def test_growth_work_updates_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260825_0063:20260825_0064", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE growth_work_updates", output)
        self.assertIn("uq_growth_work_update_owner_request", output)
        self.assertIn("ck_growth_work_updates_kind", output)
        self.assertIn("ix_growth_work_updates_owner_item_created", output)
        self.assertGreaterEqual(output.count("ON DELETE CASCADE"), 2)

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260825_0064:20260825_0063", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP TABLE growth_work_updates", output)

    def test_growth_work_nodes_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260825_0064:20260825_0065", "--sql"],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("MODIFY content MEDIUMTEXT", output)
        self.assertIn("ADD COLUMN resource_links JSON", output)
        self.assertIn("ADD COLUMN node_suggestions JSON", output)
        self.assertIn("CREATE TABLE growth_work_nodes", output)
        self.assertIn("CREATE TABLE growth_work_node_evidence", output)
        self.assertIn("uq_growth_work_node_owner_request", output)
        self.assertIn("uq_growth_work_node_evidence_relation", output)
        self.assertIn("ck_growth_work_node_evidence_status", output)
        self.assertLess(
            output.index("CREATE TABLE growth_work_nodes"),
            output.index("CREATE TABLE growth_work_node_evidence"),
        )

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260825_0065:20260825_0064", "--sql"],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(
            output.index("DROP TABLE growth_work_node_evidence"),
            output.index("DROP TABLE growth_work_nodes"),
        )
        self.assertIn("DROP COLUMN node_suggestions", output)
        self.assertIn("MODIFY content TEXT", output)

    def test_growth_work_materials_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260825_0065:20260825_0066", "--sql"],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        for table in (
            "growth_work_materials",
            "growth_work_material_requests",
            "growth_work_material_statements",
            "growth_work_material_links",
            "growth_work_material_relations",
            "growth_work_placement_events",
        ):
            self.assertIn(f"CREATE TABLE {table}", output)
        self.assertIn("ADD COLUMN priority_axis", output)
        self.assertIn("uq_growth_work_material_owner_hash", output)
        self.assertIn("occurred_at_precision", output)
        self.assertIn("ck_growth_work_materials_occurred_precision", output)
        self.assertIn("ck_growth_work_material_links_target_consistency", output)
        self.assertIn("ck_growth_work_placement_quadrant", output)
        self.assertLess(
            output.index("CREATE TABLE growth_work_materials"),
            output.index("CREATE TABLE growth_work_material_statements"),
        )
        self.assertLess(
            output.index("CREATE TABLE growth_work_material_links"),
            output.index("CREATE TABLE growth_work_placement_events"),
        )

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260825_0066:20260825_0065", "--sql"],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(
            output.index("DROP TABLE growth_work_placement_events"),
            output.index("DROP TABLE growth_work_materials"),
        )
        self.assertIn("DROP COLUMN priority_axis", output)

    def test_cashflow_import_candidate_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260822_0029:20260822_0030",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE financial_import_batches", output)
        self.assertIn("CREATE TABLE financial_transaction_candidates", output)
        self.assertIn("CREATE TABLE personal_attachment_cleanup_jobs", output)
        self.assertIn("ADD COLUMN business_data_epoch", output)
        self.assertIn("uq_fin_import_batch_source_hash_parser", output)
        self.assertIn("uq_fin_tx_candidate_batch_row", output)
        self.assertIn("fk_fin_tx_candidate_batch_owner", output)
        self.assertIn("ON DELETE CASCADE", output)
        self.assertIn("ON DELETE SET NULL", output)
        self.assertLess(
            output.index("CREATE TABLE financial_import_batches"),
            output.index("CREATE TABLE financial_transaction_candidates"),
        )

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260822_0030:20260822_0029",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN business_data_epoch", output)
        self.assertIn("DROP TABLE personal_attachment_cleanup_jobs", output)
        self.assertLess(
            output.index("DROP TABLE financial_transaction_candidates"),
            output.index("DROP TABLE financial_import_batches"),
        )

    def test_cashflow_recognition_artifact_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260822_0030:20260823_0031",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE financial_recognition_artifacts", output)
        self.assertIn("MEDIUMTEXT", output)
        self.assertIn("uq_personal_attachment_id_owner", output)
        self.assertIn("fk_fin_recognition_artifact_batch_owner", output)
        self.assertIn("fk_fin_recognition_artifact_attachment_owner", output)
        self.assertIn("ON DELETE CASCADE", output)
        self.assertIn("ON DELETE RESTRICT", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0031:20260822_0030",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(
            output.index("DROP TABLE financial_recognition_artifacts"),
            output.index("DROP INDEX uq_personal_attachment_id_owner"),
        )

    def test_payslip_recognition_fields_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0031:20260823_0032",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN pay_date DATE", output)
        self.assertIn("ADD COLUMN custom_items JSON", output)
        self.assertIn("ck_payslips_source_type", output)
        self.assertIn("ix_payslips_case_pay_month", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0032:20260823_0031",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN pay_date", output)
        self.assertIn("DROP CHECK ck_payslips_source_type", output)

    def test_payslip_material_link_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0032:20260823_0033",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE payslip_material_links", output)
        self.assertIn("ck_payslip_material_exactly_one", output)
        self.assertIn("uq_payslip_material_offer", output)
        self.assertIn("uq_payslip_material_contract", output)
        self.assertIn("INSERT INTO payslip_material_links", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0033:20260823_0032",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP TABLE payslip_material_links", output)

    def test_payslip_arrival_link_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0033:20260823_0034",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE payslip_arrival_links", output)
        self.assertIn("uq_payslip_arrival_transaction", output)
        self.assertIn("financial_transactions", output)
        self.assertIn("confirmed_by_user_id", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0034:20260823_0033",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP TABLE payslip_arrival_links", output)

    def test_payslip_agreed_pay_date_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0034:20260823_0035",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN agreed_pay_date DATE", output)
        self.assertIn("ix_payslips_agreed_pay_date", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0035:20260823_0034",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN agreed_pay_date", output)

    def test_payslip_arrival_fact_migration_renders_backfill_and_revision_history(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0045:20260823_0046",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN economic_fact_id INTEGER", output)
        self.assertIn("ADD COLUMN ledger_revision INTEGER", output)
        self.assertIn("JOIN economic_facts", output)
        self.assertIn("uq_payslip_arrival_fact", output)
        self.assertIn("CREATE TABLE payslip_arrival_link_revisions", output)
        self.assertIn("uq_payslip_arrival_link_revision_number", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0046:20260823_0045",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP TABLE payslip_arrival_link_revisions", output)
        self.assertIn("uq_payslip_arrival_transaction", output)
        self.assertIn("DROP COLUMN economic_fact_id", output)
        self.assertLess(
            output.index("DROP FOREIGN KEY fk_payslip_arrival_links_economic_fact_id"),
            output.index("DROP INDEX ix_payslip_arrival_fact"),
        )

    def test_payslip_recognition_draft_migration_renders_resumable_candidate_table(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0046:20260823_0047",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE payslip_recognition_candidate_drafts", output)
        self.assertIn("fk_payslip_recognition_draft_batch_owner", output)
        self.assertIn("uq_payslip_recognition_draft_row", output)
        self.assertIn("ck_payslip_recognition_draft_status", output)
        self.assertIn("ON DELETE CASCADE", output)
        self.assertIn("ON DELETE SET NULL", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0047:20260823_0046",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP TABLE payslip_recognition_candidate_drafts", output)

    def test_payslip_material_preference_migration_renders_explicit_user_choice_fields(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0047:20260823_0048",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN application_status", output)
        self.assertIn("ADD COLUMN priority_rank", output)
        self.assertIn("ADD COLUMN user_note", output)
        self.assertIn("ck_payslip_material_application_status", output)
        self.assertIn("ck_payslip_material_priority_rank", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0048:20260823_0047",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN user_note", output)
        self.assertIn("DROP COLUMN application_status", output)

    def test_payslip_pay_date_provenance_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0048:20260823_0049",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN agreed_pay_date_source_type", output)
        self.assertIn("ADD COLUMN agreed_pay_date_source_contract_id", output)
        self.assertIn("fk_payslips_agreed_date_source_contract", output)
        self.assertIn("ck_payslip_agreed_date_adjustment", output)
        self.assertIn("agreed_pay_date_source_type = 'manual'", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0049:20260823_0048",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP FOREIGN KEY fk_payslips_agreed_date_source_contract", output)
        self.assertIn("DROP COLUMN agreed_pay_date_calendar_version", output)
        self.assertIn("DROP COLUMN agreed_pay_date_source_type", output)
        self.assertLess(
            output.index("DROP FOREIGN KEY fk_payslips_agreed_date_source_contract"),
            output.index("DROP INDEX ix_payslip_agreed_date_source_contract"),
        )

    def test_cashflow_knowledge_citation_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0049:20260823_0050",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN applicable_issues JSON", output)
        self.assertIn("ADD COLUMN source_title VARCHAR(255)", output)
        self.assertIn("ADD COLUMN knowledge_references JSON", output)
        self.assertIn("JSON_ARRAY('全国通用')", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0050:20260823_0049",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN knowledge_references", output)
        self.assertIn("DROP COLUMN applicable_issues", output)

    def test_recurring_subscription_schedule_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0050:20260823_0051",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN renewal_cycle VARCHAR(20)", output)
        self.assertIn("ADD COLUMN next_charge_date DATE", output)
        self.assertIn("ADD COLUMN auto_renewal BOOL", output)
        self.assertIn("ck_financial_recurring_reminder_days", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0051:20260823_0050",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP CHECK ck_financial_recurring_reminder_days", output)
        self.assertIn("DROP COLUMN renewal_cycle", output)

    def test_cashflow_communication_category_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0051:20260824_0052",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("INSERT INTO financial_categories", output)
        self.assertIn("通讯", output)
        self.assertIn("2026-08-24 00:52:00", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260824_0052:20260823_0051",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DELETE FROM financial_categories", output)
        self.assertIn("created_at = '2026-08-24 00:52:00'", output)

    def test_cashflow_knowledge_articles_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260824_0052:20260824_0053",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("INSERT INTO knowledge_articles", output)
        self.assertIn("cashflow-internal-transfer", output)
        self.assertIn("cashflow-confirmed-budget", output)
        self.assertEqual(6, output.count("WHERE NOT EXISTS"))
        self.assertIn("2026-08-24 00:53:00", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260824_0053:20260824_0052",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DELETE FROM knowledge_articles", output)
        self.assertIn("cashflow-refund-reimbursement", output)
        self.assertIn("created_at = '2026-08-24 00:53:00'", output)

    def test_cashflow_knowledge_user_guides_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260824_0053:20260825_0054",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertEqual(6, output.count("UPDATE knowledge_articles"))
        self.assertIn("cashflow-internal-transfer", output)
        self.assertIn("工资通常每月集中到账", output)
        self.assertIn("第一份预算", output)
        self.assertIn("2026.8.1", output)
        self.assertNotIn("INSERT INTO knowledge_articles", output)
        self.assertNotIn("DELETE FROM knowledge_articles", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260825_0054:20260824_0053",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertEqual(6, output.count("UPDATE knowledge_articles"))
        self.assertIn("cashflow-refund-reimbursement", output)
        self.assertIn("系统怎样处理", output)
        self.assertNotIn("INSERT INTO knowledge_articles", output)
        self.assertNotIn("DELETE FROM knowledge_articles", output)

    def test_cashflow_user_finance_guides_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260825_0054:20260825_0055",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertEqual(6, output.count("INSERT INTO knowledge_articles"))
        self.assertEqual(2, output.count("UPDATE knowledge_articles"))
        self.assertIn("is_published=false", output)
        self.assertIn("cashflow-spending-spike-review", output)
        self.assertIn("cashflow-emergency-fund-plan", output)
        self.assertIn("cashflow-paycheck-drop-check", output)
        self.assertIn("攒钱先回答", output)
        self.assertEqual(6, output.count("WHERE NOT EXISTS"))
        self.assertIn("2026-08-25 00:55:00", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260825_0055:20260825_0054",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertEqual(1, output.count("DELETE FROM knowledge_articles"))
        self.assertEqual(2, output.count("UPDATE knowledge_articles"))
        self.assertIn("cashflow-month-end-review", output)
        self.assertIn("created_at = '2026-08-25 00:55:00'", output)
        self.assertIn("is_published=true", output)
        self.assertIn("攒钱的核心不是省钱", output)

    def test_cashflow_saving_guide_title_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260825_0055:20260825_0056",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertEqual(1, output.count("UPDATE knowledge_articles"))
        self.assertIn("title = '从目标倒推：一份能坚持的攒钱计划'", output)
        self.assertIn('tags = \'["目标储蓄", "发薪分配", "储蓄计划", "现金流"]\'', output)
        self.assertNotIn("INSERT INTO knowledge_articles", output)
        self.assertNotIn("DELETE FROM knowledge_articles", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260825_0056:20260825_0055",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertEqual(1, output.count("UPDATE knowledge_articles"))
        self.assertIn("title = '攒钱计划'", output)
        self.assertIn('tags = \'["攒钱", "储蓄", "理财", "预算"]\'', output)
        self.assertNotIn("INSERT INTO knowledge_articles", output)
        self.assertNotIn("DELETE FROM knowledge_articles", output)

    def test_cashflow_chat_idempotency_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260825_0056:20260825_0057",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN request_id VARCHAR(80)", output)
        self.assertIn("ADD COLUMN request_fingerprint VARCHAR(64)", output)
        self.assertIn("uq_cashflow_conversation_turn_owner_request", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260825_0057:20260825_0056",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP INDEX uq_cashflow_conversation_turn_owner_request", output)
        self.assertIn("DROP COLUMN request_fingerprint", output)
        self.assertIn("DROP COLUMN request_id", output)

    def test_economic_fact_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0035:20260823_0036",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE economic_facts", output)
        self.assertIn("CREATE TABLE economic_fact_allocations", output)
        self.assertIn("CREATE TABLE economic_fact_relations", output)
        self.assertIn("INSERT INTO economic_facts", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0036:20260823_0035",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(output.index("DROP TABLE economic_fact_relations"), output.index("DROP TABLE economic_facts"))

    def test_economic_fact_component_fields_render_mysql_safe_downgrade_order(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0044:20260823_0045",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN category_id INTEGER", output)
        self.assertIn("fk_economic_facts_category_id", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0045:20260823_0044",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(
            output.index("DROP FOREIGN KEY fk_economic_facts_category_id"),
            output.index("DROP INDEX ix_economic_facts_category_id"),
        )

    def test_economic_fact_revision_table_renders_mysql_safe_downgrade(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0043:20260823_0044",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE economic_fact_revisions", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0044:20260823_0043",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP TABLE economic_fact_revisions", output)
        self.assertNotIn("DROP INDEX ix_economic_fact_revisions_owner_created", output)

    def test_payslip_lifecycle_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0036:20260823_0037",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN supersedes_payslip_id INTEGER", output)
        self.assertIn("ADD COLUMN record_status VARCHAR(20)", output)
        self.assertIn("fk_payslips_supersedes_payslip_id", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0037:20260823_0036",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN supersedes_payslip_id", output)

    def test_cashflow_budget_ledger_revision_month_close_relation_and_chat_migrations_render_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260823_0037:20260823_0043",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE financial_recurring_decisions", output)
        self.assertIn("CREATE TABLE financial_budgets", output)
        self.assertIn("ADD COLUMN financial_ledger_revision INTEGER", output)
        self.assertIn("CREATE TABLE financial_ledger_revision_events", output)
        self.assertIn("CREATE TABLE financial_transaction_revisions", output)
        self.assertIn("CREATE TABLE financial_month_closes", output)
        self.assertIn("CREATE TABLE economic_fact_relation_revisions", output)
        self.assertIn("CREATE TABLE cashflow_conversations", output)
        self.assertIn("CREATE TABLE cashflow_conversation_turns", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0043:20260823_0037",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP TABLE financial_transaction_revisions", output)
        self.assertIn("DROP TABLE financial_month_closes", output)
        self.assertIn("DROP TABLE economic_fact_relation_revisions", output)
        self.assertIn("DROP TABLE cashflow_conversation_turns", output)
        self.assertIn("DROP TABLE cashflow_conversations", output)
        self.assertIn("DROP TABLE financial_ledger_revision_events", output)
        self.assertIn("DROP TABLE financial_budgets", output)
        self.assertIn("DROP TABLE financial_recurring_decisions", output)

    def test_offer_fact_migration_renders_without_database_connection(self):
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": "mysql+pymysql://offline:offline@127.0.0.1:1/offline",
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260819_0021:20260820_0022",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("CREATE TABLE offer_revisions", output)
        self.assertIn("CREATE TABLE offer_fact_assertions", output)
        self.assertIn("ALTER TABLE decision_records", output)
        self.assertIn("20260820_0022", output)

    def test_offer_decision_context_migration_renders_without_database_connection(self):
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": "mysql+pymysql://offline:offline@127.0.0.1:1/offline",
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260820_0022:20260820_0023",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("CREATE TABLE offer_decision_contexts", output)
        self.assertIn("uq_offer_decision_contexts_offer_id", output)
        self.assertIn("20260820_0023", output)

    def test_offer_analysis_snapshot_migration_renders_without_database_connection(self):
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": "mysql+pymysql://offline:offline@127.0.0.1:1/offline",
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260820_0023:20260820_0024",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("CREATE TABLE offer_analysis_snapshots", output)
        self.assertIn("ADD COLUMN analysis_snapshot_id", output)
        self.assertIn("fk_decision_analysis_snapshot", output)
        self.assertNotIn(
            "fk_decision_records_analysis_snapshot_id_offer_analysis_snapshots",
            output,
        )
        self.assertIn("20260820_0024", output)

    def test_labor_contract_review_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260820_0024:20260820_0025",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE contract_review_snapshots", output)
        self.assertIn("source_attachment_id", output)
        self.assertIn("fk_contract_source_attachment", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260820_0025:20260820_0024",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP TABLE contract_review_snapshots", output)
        self.assertLess(
            output.index("DROP FOREIGN KEY fk_contract_source_attachment"),
            output.index("DROP INDEX ix_contracts_source_attachment_id"),
        )

    def test_contract_ai_review_metadata_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260820_0025:20260821_0026",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("clause_segments", output)
        self.assertIn("prompt_version", output)
        self.assertIn("redaction_version", output)
        self.assertIn("ai_status", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260821_0026:20260820_0025",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN clause_segments", output)

    def test_contract_document_quality_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260821_0026:20260821_0027", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("LONGTEXT", output.upper())
        self.assertIn("parse_quality", output)
        self.assertIn("ai_batch_count", output)
        self.assertIn("coverage_report", output)

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260821_0027:20260821_0026", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN coverage_report", output)
        self.assertIn("DROP COLUMN parse_quality", output)

    def test_contract_follow_up_history_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260821_0027:20260821_0028", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE contract_follow_up_turns", output)
        self.assertIn("review_snapshot_id", output)
        self.assertIn("ON DELETE CASCADE", output)

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260821_0028:20260821_0027", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP TABLE contract_follow_up_turns", output)

    def test_growth_project_progress_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260825_0066:20260826_0067", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("ADD COLUMN account_name", output)
        self.assertIn("ADD COLUMN objective", output)
        self.assertIn("ADD COLUMN stale_after_days", output)
        self.assertIn("JSON_ARRAY()", output)
        self.assertIn("CREATE TABLE growth_work_progress_events", output)
        self.assertIn("uq_growth_work_progress_material_item_rule", output)
        self.assertIn("ix_growth_work_progress_owner_item_status", output)

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260826_0067:20260825_0066", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(
            output.index("DROP TABLE growth_work_progress_events"),
            output.index("DROP COLUMN stale_after_days"),
        )
        self.assertIn("DROP COLUMN account_name", output)

    def test_growth_project_goal_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260826_0067:20260826_0068", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE growth_project_profiles", output)
        self.assertIn("CREATE TABLE growth_project_progress_events", output)
        self.assertIn("ADD COLUMN project_id", output)
        self.assertIn("objective, success_criteria", output)
        self.assertIn("NULL, JSON_ARRAY()", output)
        self.assertIn("confirmed_at", output)
        self.assertIn("base_confirmed_event_id", output)
        self.assertIn("fk_growth_work_materials_project_id", output)

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260826_0068:20260826_0067", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(
            output.index("DROP TABLE growth_project_progress_events"),
            output.index("DROP TABLE growth_project_profiles"),
        )
        self.assertIn("DROP COLUMN project_id", output)


@mysql_test
class MigrationTest(unittest.TestCase):
    backend_dir = Path(__file__).resolve().parents[1]

    def setUp(self):
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": MYSQL_TEST_DATABASE_URL,
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )
        self._reset_test_schema()

    def tearDown(self):
        self._reset_test_schema()

    def _reset_test_schema(self):
        engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            table_names = inspect(engine).get_table_names()
            preparer = engine.dialect.identifier_preparer
            with engine.begin() as connection:
                connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
                for table_name in table_names:
                    connection.execute(
                        text(f"DROP TABLE IF EXISTS {preparer.quote(table_name)}")
                    )
                connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        finally:
            engine.dispose()

    def _alembic(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=self.backend_dir,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_growth_project_progress_round_trip_from_0066(self):
        before = self._alembic("upgrade", "20260825_0066")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)
        upgraded = self._alembic("upgrade", "20260826_0067")
        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertIn("growth_work_progress_events", inspector.get_table_names())
            item_columns = {column["name"] for column in inspector.get_columns("growth_work_items")}
            material_columns = {column["name"] for column in inspector.get_columns("growth_work_materials")}
            self.assertTrue({"account_name", "objective", "success_criteria", "strategy_summary", "key_constraints", "next_follow_up_at", "stale_after_days"}.issubset(item_columns))
            self.assertTrue({"account_name", "next_follow_up_at"}.issubset(material_columns))
        finally:
            migration_engine.dispose()

        downgraded = self._alembic("downgrade", "20260825_0066")
        self.assertEqual(downgraded.returncode, 0, downgraded.stdout + downgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertNotIn("growth_work_progress_events", inspector.get_table_names())
            item_columns = {column["name"] for column in inspector.get_columns("growth_work_items")}
            material_columns = {column["name"] for column in inspector.get_columns("growth_work_materials")}
            self.assertNotIn("stale_after_days", item_columns)
            self.assertNotIn("account_name", material_columns)
        finally:
            migration_engine.dispose()

        restored = self._alembic("upgrade", "20260826_0067")
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)

    def test_growth_project_goal_round_trip_from_0067_with_data(self):
        before = self._alembic("upgrade", "20260826_0067")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)

        def insert_user(connection, username: str) -> int:
            result = connection.execute(
                text(
                    """
                    INSERT INTO users (username, password_hash, is_demo, is_active)
                    VALUES (:username, :password_hash, 0, 1)
                    """
                ),
                {
                    "username": username,
                    "password_hash": "migration-test-password-hash",
                },
            )
            return int(result.lastrowid)

        def insert_intake(connection, user_id: int, request_id: str) -> int:
            result = connection.execute(
                text(
                    """
                    INSERT INTO growth_work_intakes
                        (user_id, request_id, input_fingerprint, candidate_payload,
                         parser_version, analysis_mode, provider_name, model, status)
                    VALUES
                        (:user_id, :request_id, :fingerprint, :candidate_payload,
                         'migration-fixture-v1', 'rules', NULL, NULL, 'confirmed')
                    """
                ),
                {
                    "user_id": user_id,
                    "request_id": request_id,
                    "fingerprint": hashlib.sha256(request_id.encode("utf-8")).hexdigest(),
                    "candidate_payload": "[]",
                },
            )
            return int(result.lastrowid)

        def insert_item(
            connection,
            *,
            user_id: int,
            intake_id: int,
            candidate_key: str,
            title: str,
            account_name,
            objective=None,
        ) -> int:
            result = connection.execute(
                text(
                    """
                    INSERT INTO growth_work_items
                        (user_id, intake_id, candidate_key, title, account_name,
                         objective, success_criteria, strategy_summary, key_constraints,
                         description, fact_excerpt, impact_level, energy_level,
                         priority_order, selection_reason, resource_links, open_questions,
                         tracking_rule, status, due_at, next_follow_up_at,
                         stale_after_days, progress_summary, blocker_note, next_action,
                         result_summary, reportable, version)
                    VALUES
                        (:user_id, :intake_id, :candidate_key, :title, :account_name,
                         :objective, :success_criteria, :strategy_summary, :key_constraints,
                         :description, :fact_excerpt, 'high', 'medium',
                         17, :selection_reason, :resource_links, :open_questions,
                         :tracking_rule, 'in_progress', '2026-09-01 09:00:00',
                         '2026-08-28 10:30:00', 21, :progress_summary,
                         :blocker_note, :next_action, :result_summary, 1, 4)
                    """
                ),
                {
                    "user_id": user_id,
                    "intake_id": intake_id,
                    "candidate_key": candidate_key,
                    "title": title,
                    "account_name": account_name,
                    "objective": objective,
                    "success_criteria": '["\u5b8c\u6210\u53ef\u9a8c\u6536\u8bd5\u70b9"]',
                    "strategy_summary": "\u5148\u9a8c\u8bc1\u94fe\u8def\uff0c\u518d\u6269\u5927\u8303\u56f4",
                    "key_constraints": '["\u7535\u8bdd\u7ebf\u8def", "\u6570\u636e\u8fb9\u754c"]',
                    "description": "\u8fc1\u79fb\u524d\u5de5\u4f5c\u7ebf\u63cf\u8ff0",
                    "fact_excerpt": "\u5df2\u786e\u8ba4\u7684\u539f\u59cb\u4e8b\u5b9e",
                    "selection_reason": "\u5f71\u54cd\u5ba2\u6237\u4ea4\u4ed8\u8282\u594f",
                    "resource_links": '["https://example.invalid/source"]',
                    "open_questions": '["\u8c01\u63d0\u4f9b\u7ebf\u8def\u53c2\u6570\uff1f"]',
                    "tracking_rule": "\u6bcf\u5468\u6838\u5bf9\u4e00\u6b21\u5ba2\u6237\u8fdb\u5c55",
                    "progress_summary": "\u5df2\u5b8c\u6210\u521d\u6b65\u8c03\u7814",
                    "blocker_note": "\u7ebf\u8def\u578b\u53f7\u5f85\u786e\u8ba4",
                    "next_action": "\u7ec4\u7ec7\u6280\u672f\u52d8\u5bdf",
                    "result_summary": "\u4fdd\u7559\u7684\u5386\u53f2\u7ed3\u679c",
                },
            )
            return int(result.lastrowid)

        def insert_material(
            connection,
            *,
            user_id: int,
            account_name,
            title: str,
            content: str,
            suffix: str,
            ai_metadata: bool = False,
        ) -> int:
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            result = connection.execute(
                text(
                    """
                    INSERT INTO growth_work_materials
                        (user_id, material_type, title, account_name, content,
                         content_hash, occurred_at, occurred_at_precision,
                         next_follow_up_at, source_document_id, source_url,
                         analysis_mode, analysis_rule_version, ai_requested,
                         external_processing_used, provider_name, model,
                         fallback_reason, version)
                    VALUES
                        (:user_id, 'meeting_minutes', :title, :account_name, :content,
                         :content_hash, :occurred_at, 'datetime', :next_follow_up_at,
                         :source_document_id, :source_url, :analysis_mode,
                         :analysis_rule_version, :ai_requested,
                         :external_processing_used, :provider_name, :model,
                         :fallback_reason, :version)
                    """
                ),
                {
                    "user_id": user_id,
                    "title": title,
                    "account_name": account_name,
                    "content": content,
                    "content_hash": content_hash,
                    "occurred_at": "2026-08-19 17:32:00",
                    "next_follow_up_at": "2026-08-29 09:15:00",
                    "source_document_id": f"migration-source-{suffix}",
                    "source_url": f"https://example.invalid/material/{suffix}",
                    "analysis_mode": "ai" if ai_metadata else "rules",
                    "analysis_rule_version": f"migration-analysis-{suffix}",
                    "ai_requested": 1 if ai_metadata else 0,
                    "external_processing_used": 1 if ai_metadata else 0,
                    "provider_name": "SenseAudio" if ai_metadata else None,
                    "model": "qwen3.8-27b" if ai_metadata else None,
                    "fallback_reason": None if ai_metadata else "ai_not_requested",
                    "version": 5 if ai_metadata else 2,
                },
            )
            return int(result.lastrowid)

        try:
            with migration_engine.begin() as connection:
                alice_id = insert_user(connection, "migration-0068-alice")
                bob_id = insert_user(connection, "migration-0068-bob")
                alice_intake_id = insert_intake(connection, alice_id, "migration-0068-alice-intake")
                bob_intake_id = insert_intake(connection, bob_id, "migration-0068-bob-intake")

                alice_item_id = insert_item(
                    connection,
                    user_id=alice_id,
                    intake_id=alice_intake_id,
                    candidate_key="people-daily-main",
                    title="\u4eba\u6c11\u65e5\u62a5\u5728\u7ebf\u8bed\u97f3\u5ba2\u670d\u8bd5\u70b9",
                    account_name="\u4eba\u6c11\u65e5\u62a5",
                    objective="\u5de5\u4f5c\u7ebf\u539f\u76ee\u6807\u4e0d\u5e94\u88ab\u9879\u76ee\u8fc1\u79fb\u8986\u76d6",
                )
                alice_blank_item_id = insert_item(
                    connection,
                    user_id=alice_id,
                    intake_id=alice_intake_id,
                    candidate_key="blank-account",
                    title="\u7a7a\u767d\u5ba2\u6237\u5de5\u4f5c\u7ebf",
                    account_name="   ",
                )
                bob_item_id = insert_item(
                    connection,
                    user_id=bob_id,
                    intake_id=bob_intake_id,
                    candidate_key="people-daily-other-user",
                    title="\u53e6\u4e00\u7528\u6237\u7684\u4eba\u6c11\u65e5\u62a5\u9879\u76ee",
                    account_name="\u4eba\u6c11\u65e5\u62a5",
                )

                alice_material_one_id = insert_material(
                    connection,
                    user_id=alice_id,
                    account_name="\u4eba\u6c11\u65e5\u62a5",
                    title="\u4eba\u6c11\u65e5\u62a5\u7ebf\u8def\u4f1a\u8bae",
                    content="\u8fd9\u662f\u9700\u8981\u5b8c\u6574\u4fdd\u7559\u7684\u7b2c\u4e00\u4efd\u4f1a\u8bae\u7eaa\u8981\u5168\u6587\u3002\n\u5305\u542b\u7535\u8bdd\u7ebf\u8def\u3001\u8f6c\u4eba\u5de5\u548c\u7559\u75d5\u95ed\u73af\u3002",
                    suffix="alice-people-1",
                    ai_metadata=True,
                )
                alice_material_two_id = insert_material(
                    connection,
                    user_id=alice_id,
                    account_name="\u4eba\u6c11\u65e5\u62a5",
                    title="\u4eba\u6c11\u65e5\u62a5\u65b9\u6848\u4f1a\u8bae",
                    content="\u7b2c\u4e8c\u4efd\u4f1a\u8bae\u7eaa\u8981\u9700\u8981\u5b8c\u6574\u4fdd\u7559\uff1a\u5148\u6570\u5b57\u5316\u63a5\u5165\uff0c\u518d\u5f15\u5165 AI \u524d\u7f6e\u63a5\u542c\u3002",
                    suffix="alice-people-2",
                )
                material_only_id = insert_material(
                    connection,
                    user_id=alice_id,
                    account_name="\u4ec5\u6750\u6599\u5ba2\u6237",
                    title="\u5c1a\u672a\u62c6\u6210\u5de5\u4f5c\u7ebf\u7684\u6750\u6599",
                    content="\u8fd9\u4e2a\u5ba2\u6237\u53ea\u6709\u4e00\u4efd\u6750\u6599\uff0c\u4e5f\u5e94\u751f\u6210\u5f85\u786e\u8ba4\u9879\u76ee\u6863\u6848\u3002",
                    suffix="alice-material-only",
                )
                null_account_material_id = insert_material(
                    connection,
                    user_id=alice_id,
                    account_name=None,
                    title="\u672a\u5f52\u4f4d\u6750\u6599",
                    content="\u6ca1\u6709\u5ba2\u6237\u65f6\u53ea\u4fdd\u7559\u6750\u6599\uff0c\u4e0d\u5e94\u731c\u6d4b\u9879\u76ee\u3002",
                    suffix="alice-null-account",
                )
                blank_account_material_id = insert_material(
                    connection,
                    user_id=alice_id,
                    account_name="",
                    title="\u7a7a\u5b57\u7b26\u5ba2\u6237\u6750\u6599",
                    content="\u7a7a\u5b57\u7b26\u5ba2\u6237\u4e0d\u80fd\u751f\u6210\u4e34\u65f6\u9879\u76ee\u3002",
                    suffix="alice-blank-account",
                )
                bob_material_id = insert_material(
                    connection,
                    user_id=bob_id,
                    account_name="\u4eba\u6c11\u65e5\u62a5",
                    title="\u53e6\u4e00\u7528\u6237\u7684\u540c\u540d\u5ba2\u6237\u6750\u6599",
                    content="\u4e0d\u540c\u7528\u6237\u7684\u540c\u540d\u5ba2\u6237\u5fc5\u987b\u4fdd\u6301\u79df\u6237\u9694\u79bb\u3002",
                    suffix="bob-people",
                )

            item_snapshot_columns = """
                id, user_id, intake_id, career_event_id, candidate_key, title,
                account_name, objective, success_criteria, strategy_summary,
                key_constraints, description, fact_excerpt, impact_level,
                energy_level, priority_order, selection_reason, resource_links,
                open_questions, tracking_rule, status, due_at, next_follow_up_at,
                stale_after_days, progress_summary, blocker_note, next_action,
                result_summary, reportable, priority_axis, progress_health,
                quadrant, placement_rule_version, placement_updated_at, version,
                confirmed_at, completed_at, deleted_at, created_at, updated_at
            """
            material_snapshot_columns = """
                id, user_id, material_type, title, account_name, content,
                content_hash, occurred_at, occurred_at_precision,
                next_follow_up_at, source_document_id, source_url, analysis_mode,
                analysis_rule_version, ai_requested, external_processing_used,
                provider_name, model, fallback_reason, version, created_at, updated_at
            """

            def read_baseline(connection):
                items = [
                    dict(row)
                    for row in connection.execute(
                        text(f"SELECT {item_snapshot_columns} FROM growth_work_items ORDER BY id")
                    ).mappings()
                ]
                materials = [
                    dict(row)
                    for row in connection.execute(
                        text(
                            f"SELECT {material_snapshot_columns} "
                            "FROM growth_work_materials ORDER BY id"
                        )
                    ).mappings()
                ]
                return items, materials

            with migration_engine.connect() as connection:
                original_items, original_materials = read_baseline(connection)

            def assert_upgraded_state():
                inspector = inspect(migration_engine)
                self.assertIn("growth_project_profiles", inspector.get_table_names())
                self.assertIn("growth_project_progress_events", inspector.get_table_names())
                self.assertIn(
                    "project_id",
                    {column["name"] for column in inspector.get_columns("growth_work_items")},
                )
                self.assertIn(
                    "project_id",
                    {column["name"] for column in inspector.get_columns("growth_work_materials")},
                )
                for table_name in ("growth_work_items", "growth_work_materials"):
                    project_foreign_keys = [
                        foreign_key
                        for foreign_key in inspector.get_foreign_keys(table_name)
                        if foreign_key["constrained_columns"] == ["project_id"]
                    ]
                    self.assertEqual(1, len(project_foreign_keys))
                    self.assertEqual(
                        "growth_project_profiles",
                        project_foreign_keys[0]["referred_table"],
                    )
                    self.assertEqual(
                        "SET NULL",
                        str(project_foreign_keys[0].get("options", {}).get("ondelete", "")).upper(),
                    )

                with migration_engine.connect() as connection:
                    self.assertEqual(
                        "20260826_0068",
                        connection.scalar(text("SELECT version_num FROM alembic_version")),
                    )
                    current_items, current_materials = read_baseline(connection)
                    self.assertEqual(original_items, current_items)
                    self.assertEqual(original_materials, current_materials)

                    profiles = connection.execute(
                        text(
                            """
                            SELECT id, user_id, account_name, project_name
                            FROM growth_project_profiles
                            ORDER BY user_id, account_name, project_name
                            """
                        )
                    ).mappings().all()
                    self.assertEqual(3, len(profiles))
                    profile_by_owner_account = {
                        (row["user_id"], row["account_name"]): row["id"] for row in profiles
                    }
                    alice_people_project = profile_by_owner_account[(alice_id, "\u4eba\u6c11\u65e5\u62a5")]
                    bob_people_project = profile_by_owner_account[(bob_id, "\u4eba\u6c11\u65e5\u62a5")]
                    material_only_project = profile_by_owner_account[(alice_id, "\u4ec5\u6750\u6599\u5ba2\u6237")]
                    self.assertNotEqual(alice_people_project, bob_people_project)

                    invalid_profile_count = connection.scalar(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM growth_project_profiles
                            WHERE objective IS NOT NULL
                               OR confirmed_at IS NOT NULL
                               OR project_name <> account_name
                               OR JSON_LENGTH(success_criteria) <> 0
                               OR JSON_LENGTH(key_constraints) <> 0
                               OR stale_after_days <> 14
                               OR version <> 1
                            """
                        )
                    )
                    self.assertEqual(0, invalid_profile_count)

                    def project_id_for(table_name: str, row_id: int):
                        return connection.scalar(
                            text(f"SELECT project_id FROM {table_name} WHERE id = :row_id"),
                            {"row_id": row_id},
                        )

                    self.assertEqual(
                        alice_people_project,
                        project_id_for("growth_work_items", alice_item_id),
                    )
                    self.assertEqual(
                        alice_people_project,
                        project_id_for("growth_work_materials", alice_material_one_id),
                    )
                    self.assertEqual(
                        alice_people_project,
                        project_id_for("growth_work_materials", alice_material_two_id),
                    )
                    self.assertEqual(
                        material_only_project,
                        project_id_for("growth_work_materials", material_only_id),
                    )
                    self.assertEqual(
                        bob_people_project,
                        project_id_for("growth_work_items", bob_item_id),
                    )
                    self.assertEqual(
                        bob_people_project,
                        project_id_for("growth_work_materials", bob_material_id),
                    )
                    self.assertIsNone(project_id_for("growth_work_items", alice_blank_item_id))
                    self.assertIsNone(
                        project_id_for("growth_work_materials", null_account_material_id)
                    )
                    self.assertIsNone(
                        project_id_for("growth_work_materials", blank_account_material_id)
                    )

                    self.assertEqual(
                        0,
                        connection.scalar(
                            text(
                                """
                                SELECT COUNT(*)
                                FROM growth_work_items AS item
                                LEFT JOIN growth_project_profiles AS project
                                  ON project.id = item.project_id
                                WHERE item.account_name IS NOT NULL
                                  AND TRIM(item.account_name) <> ''
                                  AND project.id IS NULL
                                """
                            )
                        ),
                    )
                    self.assertEqual(
                        0,
                        connection.scalar(
                            text(
                                """
                                SELECT COUNT(*)
                                FROM growth_work_materials AS material
                                LEFT JOIN growth_project_profiles AS project
                                  ON project.id = material.project_id
                                WHERE material.account_name IS NOT NULL
                                  AND TRIM(material.account_name) <> ''
                                  AND project.id IS NULL
                                """
                            )
                        ),
                    )
                    self.assertEqual(
                        0,
                        connection.scalar(
                            text(
                                """
                                SELECT COUNT(*)
                                FROM growth_work_items AS item
                                JOIN growth_project_profiles AS project
                                  ON project.id = item.project_id
                                WHERE item.user_id <> project.user_id
                                """
                            )
                        ),
                    )
                    self.assertEqual(
                        0,
                        connection.scalar(
                            text(
                                """
                                SELECT COUNT(*)
                                FROM growth_work_materials AS material
                                JOIN growth_project_profiles AS project
                                  ON project.id = material.project_id
                                WHERE material.user_id <> project.user_id
                                """
                            )
                        ),
                    )
                    self.assertEqual(
                        0,
                        connection.scalar(text("SELECT COUNT(*) FROM growth_project_progress_events")),
                    )

            upgraded = self._alembic("upgrade", "20260826_0068")
            self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
            assert_upgraded_state()

            downgraded = self._alembic("downgrade", "20260826_0067")
            self.assertEqual(downgraded.returncode, 0, downgraded.stdout + downgraded.stderr)
            inspector = inspect(migration_engine)
            self.assertNotIn("growth_project_profiles", inspector.get_table_names())
            self.assertNotIn("growth_project_progress_events", inspector.get_table_names())
            self.assertNotIn(
                "project_id",
                {column["name"] for column in inspector.get_columns("growth_work_items")},
            )
            self.assertNotIn(
                "project_id",
                {column["name"] for column in inspector.get_columns("growth_work_materials")},
            )
            with migration_engine.connect() as connection:
                self.assertEqual(
                    "20260826_0067",
                    connection.scalar(text("SELECT version_num FROM alembic_version")),
                )
                downgraded_items, downgraded_materials = read_baseline(connection)
                self.assertEqual(original_items, downgraded_items)
                self.assertEqual(original_materials, downgraded_materials)

            restored = self._alembic("upgrade", "20260826_0068")
            self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
            assert_upgraded_state()
        finally:
            migration_engine.dispose()

    def test_empty_database_upgrades_to_head(self):
        result = self._alembic("upgrade", "head")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            tables = set(inspector.get_table_names())
            self.assertIn("offer_revisions", tables)
            self.assertIn("offer_fact_assertions", tables)
            self.assertIn("offer_decision_contexts", tables)
            self.assertIn("offer_analysis_snapshots", tables)
            self.assertIn("contract_review_snapshots", tables)
            offer_columns = {
                column["name"] for column in inspector.get_columns("offers")
            }
            contract_columns = {
                column["name"] for column in inspector.get_columns("contracts")
            }
            contract_review_columns = {
                column["name"]
                for column in inspector.get_columns("contract_review_snapshots")
            }
            raw_text_type = next(column["type"] for column in inspector.get_columns("contracts") if column["name"] == "raw_text")
            decision_columns = {
                column["name"] for column in inspector.get_columns("decision_records")
            }
            self.assertTrue({"offer_revision_id", "preflight_snapshot", "acknowledged_unknowns"}.issubset(decision_columns))
            self.assertIn("analysis_snapshot_id", decision_columns)
            target_columns = {
                column["name"] for column in inspector.get_columns("job_targets")
            }
            draft_columns = {
                column["name"]
                for column in inspector.get_columns("resume_tailoring_drafts")
            }
            analysis_columns = {
                column["name"]
                for column in inspector.get_columns("opportunity_analyses")
            }
            invocation_columns = {
                column["name"]
                for column in inspector.get_columns("ai_invocation_logs")
            }
            provider_columns = {
                column["name"]
                for column in inspector.get_columns("ai_provider_settings")
            }
            import_batch_columns = {
                column["name"]
                for column in inspector.get_columns("financial_import_batches")
            }
            import_candidate_columns = {
                column["name"]
                for column in inspector.get_columns("financial_transaction_candidates")
            }
            recognition_artifact_columns = {
                column["name"]
                for column in inspector.get_columns("financial_recognition_artifacts")
            }
            import_batch_unique_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("financial_import_batches")
            }
            import_candidate_unique_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("financial_transaction_candidates")
            }
            user_columns = {
                column["name"] for column in inspector.get_columns("users")
            }
            knowledge_columns = {
                column["name"] for column in inspector.get_columns("knowledge_articles")
            }
            cashflow_turn_columns = {
                column["name"] for column in inspector.get_columns("cashflow_conversation_turns")
            }
            cashflow_turn_unique_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("cashflow_conversation_turns")
            }
            recurring_decision_columns = {
                column["name"] for column in inspector.get_columns("financial_recurring_decisions")
            }
            with migration_engine.connect() as connection:
                article_count = connection.scalar(
                    text("SELECT COUNT(*) FROM knowledge_articles")
                )
                category_count = connection.scalar(
                    text("SELECT COUNT(DISTINCT category) FROM knowledge_articles")
                )
                financial_category_count = connection.scalar(
                    text("SELECT COUNT(*) FROM financial_categories WHERE is_system = 1")
                )
        finally:
            migration_engine.dispose()

        self.assertTrue(
            {
                "alembic_version",
                "users",
                "career_cases",
                "offers",
                "career_events",
                "evidence",
                "guardian_findings",
                "action_items",
                "decision_records",
                "outcomes",
                "knowledge_articles",
                "resume_versions",
                "opportunity_analyses",
                "ai_provider_settings",
                "ai_invocation_logs",
                "ai_configuration_audits",
                "personal_attachment_versions",
                "job_targets",
                "resume_tailoring_drafts",
                "career_image_generations",
                "financial_categories",
                "financial_transactions",
                "financial_recurring_decisions",
                "financial_budgets",
                "financial_month_closes",
                "financial_ledger_revision_events",
                "financial_transaction_revisions",
                "economic_fact_relation_revisions",
                "cashflow_conversations",
                "cashflow_conversation_turns",
                "financial_import_batches",
                "financial_transaction_candidates",
                "financial_recognition_artifacts",
                "personal_attachment_cleanup_jobs",
            }.issubset(tables)
        )
        self.assertIn("business_data_epoch", user_columns)
        self.assertIn("financial_ledger_revision", user_columns)
        self.assertTrue({"applicable_issues", "applicable_regions", "source_title", "content_version", "effective_from", "effective_to"}.issubset(knowledge_columns))
        self.assertTrue({"knowledge_references", "request_id", "request_fingerprint"}.issubset(cashflow_turn_columns))
        self.assertIn("uq_cashflow_conversation_turn_owner_request", cashflow_turn_unique_constraints)
        self.assertTrue({"renewal_cycle", "next_charge_date", "auto_renewal", "reminder_days_before"}.issubset(recurring_decision_columns))
        self.assertTrue(
            {
                "clause_segments",
                "provider_name",
                "model_name",
                "prompt_version",
                "redaction_version",
                "ai_status",
                "ai_input_clause_count",
                "redaction_report",
                "ai_batch_count",
                "ai_completed_batch_count",
                "coverage_report",
            }.issubset(contract_review_columns)
        )
        self.assertIn("LONGTEXT", str(raw_text_type).upper())
        self.assertIn("career_event_id", offer_columns)
        self.assertTrue(
            {
                "source_attachment_id",
                "display_name",
                "document_kind",
                "status",
                "parse_status",
                "parse_mode",
                "parse_notice",
                "page_count",
                "text_page_count",
                "ocr_page_count",
                "parse_error_code",
                "parse_quality",
                "archived_at",
            }.issubset(contract_columns)
        )
        self.assertTrue(
            {
                "job_target_id",
                "source_attachment_id",
                "offer_kind",
                "decision_status",
                "response_deadline",
                "facts_confirmed_at",
                "employment_type",
                "department",
                "job_level",
                "work_mode",
            }.issubset(offer_columns)
        )
        self.assertTrue(
            {
                "plan_status",
                "plan_error",
                "plan_started_at",
                "advice_kind",
                "advice_summary",
                "advice_source_analysis_id",
                "advice_updated_at",
            }.issubset(target_columns)
        )
        self.assertTrue(
            {"error_message", "generation_started_at", "generation_completed_at"}.issubset(
                draft_columns
            )
        )
        self.assertTrue(
            {"scoring_version", "score_breakdown"}.issubset(analysis_columns)
        )
        self.assertTrue(
            {"estimated_cost_microunits", "cost_currency"}.issubset(
                invocation_columns
            )
        )
        self.assertTrue(
            {
                "image_enabled",
                "image_model",
                "image_api_key_encrypted",
                "image_api_key_suffix",
                "image_style_prompt",
                "image_landscape_prompt",
                "image_square_prompt",
            }.issubset(provider_columns)
        )
        self.assertTrue(
            {
                "origin_type",
                "source_type",
                "attachment_version_id",
                "content_hash",
                "parser_version",
                "column_mapping",
                "exact_duplicate_count",
                "possible_duplicate_count",
                "version",
            }.issubset(import_batch_columns)
        )
        self.assertTrue(
            {
                "batch_id",
                "user_id",
                "category_name",
                "external_key",
                "fingerprint",
                "duplicate_transaction_id",
                "transaction_id",
                "validation_errors",
                "warnings",
                "version",
            }.issubset(import_candidate_columns)
        )
        self.assertTrue(
            {
                "batch_id",
                "user_id",
                "artifact_type",
                "sequence_number",
                "status",
                "content_text",
                "content_json",
                "attachment_version_id",
                "content_hash",
                "byte_size",
                "source_locator",
                "artifact_metadata",
            }.issubset(recognition_artifact_columns)
        )
        self.assertIn("uq_fin_import_batch_source_hash_parser", import_batch_unique_constraints)
        self.assertIn("uq_fin_tx_candidate_batch_row", import_candidate_unique_constraints)
        self.assertEqual(43, article_count)
        self.assertEqual(8, category_count)
        self.assertEqual(21, financial_category_count)

    def test_cashflow_import_candidate_round_trip_from_0029(self):
        before = self._alembic("upgrade", "20260822_0029")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

        upgraded = self._alembic("upgrade", "20260822_0030")
        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertIn("financial_import_batches", inspector.get_table_names())
            self.assertIn("financial_transaction_candidates", inspector.get_table_names())
            self.assertIn("personal_attachment_cleanup_jobs", inspector.get_table_names())
            self.assertIn(
                "business_data_epoch",
                {column["name"] for column in inspector.get_columns("users")},
            )
        finally:
            migration_engine.dispose()

        downgraded = self._alembic("downgrade", "20260822_0029")
        self.assertEqual(downgraded.returncode, 0, downgraded.stdout + downgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertNotIn("financial_import_batches", inspector.get_table_names())
            self.assertNotIn("financial_transaction_candidates", inspector.get_table_names())
            self.assertNotIn("personal_attachment_cleanup_jobs", inspector.get_table_names())
            self.assertNotIn(
                "business_data_epoch",
                {column["name"] for column in inspector.get_columns("users")},
            )
        finally:
            migration_engine.dispose()

        restored = self._alembic("upgrade", "20260822_0030")
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)

    def test_cashflow_recognition_artifact_round_trip_from_0030(self):
        before = self._alembic("upgrade", "20260822_0030")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

        upgraded = self._alembic("upgrade", "20260823_0031")
        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertIn("financial_recognition_artifacts", inspector.get_table_names())
            artifact_columns = {
                column["name"]
                for column in inspector.get_columns("financial_recognition_artifacts")
            }
            self.assertTrue(
                {
                    "batch_id",
                    "user_id",
                    "artifact_type",
                    "sequence_number",
                    "content_text",
                    "content_json",
                    "content_hash",
                }.issubset(artifact_columns)
            )
            attachment_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints(
                    "personal_attachment_versions"
                )
            }
            self.assertIn(
                "uq_personal_attachment_id_owner",
                attachment_constraints,
            )
        finally:
            migration_engine.dispose()

        downgraded = self._alembic("downgrade", "20260822_0030")
        self.assertEqual(downgraded.returncode, 0, downgraded.stdout + downgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertNotIn("financial_recognition_artifacts", inspector.get_table_names())
            attachment_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints(
                    "personal_attachment_versions"
                )
            }
            self.assertNotIn(
                "uq_personal_attachment_id_owner",
                attachment_constraints,
            )
        finally:
            migration_engine.dispose()

        restored = self._alembic("upgrade", "20260823_0031")
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)

    def test_existing_offer_case_is_backfilled_to_decision_event(self):
        before = self._alembic("upgrade", "a31f5740d0c5")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            with migration_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users (username, password_hash, is_active) "
                        "VALUES ('legacy-user', 'not-used', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO career_cases "
                        "(user_id, type, title, status, current_step) "
                        "VALUES (1, 'offer_analysis', '历史 Offer', 'in_progress', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO offers "
                        "(case_id, company_name, salary_months, probation_months, "
                        "probation_salary_rate) "
                        "VALUES (1, '历史公司', 12, 0, 0.8)"
                    )
                )
        finally:
            migration_engine.dispose()

        after = self._alembic("upgrade", "head")
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)

        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            with migration_engine.connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT ce.event_type, ce.legacy_case_id, o.career_event_id "
                        "FROM career_events ce "
                        "JOIN offers o ON o.career_event_id = ce.id"
                    )
                ).one()
        finally:
            migration_engine.dispose()
        self.assertEqual(tuple(row), ("decision", 1, 1))

    def test_labor_contract_review_round_trip_from_0024(self):
        before = self._alembic("upgrade", "20260820_0024")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            with migration_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users (username, password_hash, is_active) "
                        "VALUES ('legacy-contract-user', 'not-used', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO career_cases "
                        "(user_id, type, title, status, current_step) "
                        "VALUES (1, 'contract_review', '历史劳动合同', 'in_progress', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO contracts (case_id, employer, raw_text) "
                        "VALUES (1, '历史公司', '历史劳动合同文本')"
                    )
                )
        finally:
            migration_engine.dispose()

        upgraded = self._alembic("upgrade", "20260820_0025")
        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertIn("contract_review_snapshots", inspector.get_table_names())
            columns = {column["name"] for column in inspector.get_columns("contracts")}
            self.assertIn("source_attachment_id", columns)
            with migration_engine.connect() as connection:
                row = connection.execute(
                    text("SELECT document_kind, status, parse_status FROM contracts WHERE id = 1")
                ).one()
            self.assertEqual(tuple(row), ("labor_contract", "active", "ready"))
        finally:
            migration_engine.dispose()

        downgraded = self._alembic("downgrade", "20260820_0024")
        self.assertEqual(downgraded.returncode, 0, downgraded.stdout + downgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertNotIn("contract_review_snapshots", inspector.get_table_names())
            columns = {column["name"] for column in inspector.get_columns("contracts")}
            self.assertNotIn("source_attachment_id", columns)
        finally:
            migration_engine.dispose()

    def test_contract_document_quality_round_trip_from_0026(self):
        before = self._alembic("upgrade", "20260821_0026")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

        upgraded = self._alembic("upgrade", "20260821_0027")
        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            contract_columns = {column["name"]: column for column in inspector.get_columns("contracts")}
            snapshot_columns = {column["name"] for column in inspector.get_columns("contract_review_snapshots")}
            self.assertIn("LONGTEXT", str(contract_columns["raw_text"]["type"]).upper())
            self.assertTrue({"parse_error_code", "text_page_count", "ocr_page_count", "parse_quality"}.issubset(contract_columns))
            self.assertTrue({"ai_batch_count", "ai_completed_batch_count", "coverage_report"}.issubset(snapshot_columns))
        finally:
            migration_engine.dispose()

        downgraded = self._alembic("downgrade", "20260821_0026")
        self.assertEqual(downgraded.returncode, 0, downgraded.stdout + downgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            contract_columns = {column["name"]: column for column in inspector.get_columns("contracts")}
            snapshot_columns = {column["name"] for column in inspector.get_columns("contract_review_snapshots")}
            self.assertNotIn("parse_quality", contract_columns)
            self.assertNotIn("coverage_report", snapshot_columns)
            self.assertNotIn("LONGTEXT", str(contract_columns["raw_text"]["type"]).upper())
        finally:
            migration_engine.dispose()

        restored = self._alembic("upgrade", "20260821_0027")
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)


if __name__ == "__main__":
    unittest.main()
