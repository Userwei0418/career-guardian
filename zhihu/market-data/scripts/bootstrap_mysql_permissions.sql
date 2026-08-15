-- FP-02 MySQL 8 logical/permission isolation. This file creates no users and stores no passwords.
CREATE DATABASE IF NOT EXISTS `pin_legacy_staging` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS `market_raw` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE ROLE IF NOT EXISTS `career_guardian_staging_importer`;
CREATE ROLE IF NOT EXISTS `career_guardian_staging_auditor`;
CREATE ROLE IF NOT EXISTS `career_guardian_raw_worker`;
CREATE ROLE IF NOT EXISTS `career_guardian_core_transformer`;
CREATE ROLE IF NOT EXISTS `career_guardian_market_reader`;

GRANT ALL PRIVILEGES ON `pin_legacy_staging`.* TO `career_guardian_staging_importer`;
GRANT SELECT ON `pin_legacy_staging`.* TO `career_guardian_staging_auditor`;
GRANT SELECT, INSERT, UPDATE ON `market_raw`.* TO `career_guardian_raw_worker`;
GRANT SELECT ON `market_raw`.* TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_job_families` TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_cities` TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_skills` TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_recruitment_types` TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_companies` TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_jobs` TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_job_sources` TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_job_skills` TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_core_promotion_batches` TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_rejected_legacy_jobs` TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_quality_gate_policies` TO `career_guardian_core_transformer`;
GRANT SELECT, INSERT, UPDATE, DELETE ON `zhihu`.`market_insight_snapshots` TO `career_guardian_core_transformer`;

GRANT SELECT ON `zhihu`.`market_job_families` TO `career_guardian_market_reader`;
GRANT SELECT ON `zhihu`.`market_cities` TO `career_guardian_market_reader`;
GRANT SELECT ON `zhihu`.`market_skills` TO `career_guardian_market_reader`;
GRANT SELECT ON `zhihu`.`market_recruitment_types` TO `career_guardian_market_reader`;
GRANT SELECT ON `zhihu`.`market_companies` TO `career_guardian_market_reader`;
GRANT SELECT ON `zhihu`.`market_jobs` TO `career_guardian_market_reader`;
GRANT SELECT ON `zhihu`.`market_job_sources` TO `career_guardian_market_reader`;
GRANT SELECT ON `zhihu`.`market_job_skills` TO `career_guardian_market_reader`;
GRANT SELECT ON `zhihu`.`market_insight_snapshots` TO `career_guardian_market_reader`;

-- Deliberately absent: Guardian API and market reader receive no staging/raw grant.
