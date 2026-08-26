-- ============================================================
-- 职护历史市场库兼容测试夹具
-- 数据库: zhaogebanshang
-- 字符集: utf8mb4 / 引擎: InnoDB
-- 仅供测试解析；如需手工复现：mysql -u root -p < legacy_market_schema.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS `zhaogebanshang`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE `zhaogebanshang`;

-- ============================================================
-- 1. companies - 公司主表
-- ============================================================
DROP TABLE IF EXISTS `companies`;
CREATE TABLE `companies` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL COMMENT '公司全称',
  `alias_name` varchar(255) DEFAULT NULL COMMENT '公司别名',
  `short_name` varchar(100) DEFAULT NULL COMMENT '公司简称',
  `logo_url` varchar(500) DEFAULT NULL COMMENT '公司logo',
  `website_url` varchar(500) DEFAULT NULL COMMENT '公司官网',
  `career_page_url` varchar(500) DEFAULT NULL COMMENT '招聘页面',
  `industry` varchar(100) DEFAULT NULL COMMENT '行业',
  `company_type` varchar(100) DEFAULT NULL COMMENT '公司类型',
  `size_range` varchar(100) DEFAULT NULL COMMENT '公司规模',
  `headquarters` varchar(255) DEFAULT NULL COMMENT '总部',
  `description` text COMMENT '公司简介',
  `tags` json DEFAULT NULL COMMENT '标签',
  `status` tinyint NOT NULL DEFAULT '1' COMMENT '1有效 0无效',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_name` (`name`),
  KEY `idx_industry` (`industry`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 2. crawl_companies - 爬虫目标公司配置
-- ============================================================
DROP TABLE IF EXISTS `crawl_companies`;
CREATE TABLE `crawl_companies` (
  `id` int NOT NULL AUTO_INCREMENT,
  `com_id` varchar(50) NOT NULL COMMENT '爬虫业务ID',
  `com_name` varchar(255) NOT NULL COMMENT '公司名称',
  `com_webname` varchar(255) DEFAULT NULL,
  `com_logo` varchar(500) DEFAULT NULL,
  `career_url` varchar(500) DEFAULT NULL COMMENT '招聘列表URL',
  `json_config` json NOT NULL COMMENT 'CSS选择器配置',
  `is_active` tinyint DEFAULT '1',
  `crawl_count` int DEFAULT '0',
  `last_crawl_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `com_id` (`com_id`),
  KEY `idx_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 3. crawl_jobs - 抓取→解析→入库 流水线
-- ============================================================
DROP TABLE IF EXISTS `crawl_jobs`;
CREATE TABLE `crawl_jobs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `crawl_job_id` varchar(64) NOT NULL COMMENT 'UUID',
  `com_id` varchar(50) NOT NULL,
  `job_title` varchar(255) DEFAULT NULL,
  `job_type` varchar(50) DEFAULT NULL COMMENT 'sheozhao/xiaozhao/shixi',
  `source_url` text,
  `raw_html` mediumtext,
  `raw_json` json DEFAULT NULL COMMENT '爬虫原始JSON',
  `model_json` json DEFAULT NULL COMMENT 'LLM解析结果(cjob+other)',
  `model_json_path` varchar(500) DEFAULT NULL,
  `status` enum('crawled','parsed','ingested','failed') NOT NULL DEFAULT 'crawled',
  `error_message` text,
  `crawled_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `parsed_at` datetime DEFAULT NULL,
  `ingested_at` datetime DEFAULT NULL,
  `job_id` bigint DEFAULT NULL COMMENT '入库后 jobs.id',
  PRIMARY KEY (`id`),
  UNIQUE KEY `crawl_job_id` (`crawl_job_id`),
  KEY `idx_com_status` (`com_id`,`status`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 4. jobs - 清洗后职位主表
-- ============================================================
DROP TABLE IF EXISTS `jobs`;
CREATE TABLE `jobs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `company_id` bigint NOT NULL COMMENT '关联 companies.id',
  `title` varchar(255) NOT NULL COMMENT '职位名称',
  `normalized_title` varchar(255) DEFAULT NULL COMMENT '标准化名称',
  `department` varchar(255) DEFAULT NULL COMMENT '部门',
  `job_category` varchar(100) DEFAULT NULL COMMENT '职位类别',
  `employment_type` varchar(50) DEFAULT NULL COMMENT '全职/兼职/实习',
  `is_campus` tinyint NOT NULL DEFAULT '0' COMMENT '是否校招',
  `is_intern` tinyint NOT NULL DEFAULT '0' COMMENT '是否实习',
  `location_text` text COMMENT '工作地点原始',
  `city` varchar(100) DEFAULT NULL COMMENT '标准化城市',
  `province` varchar(100) DEFAULT NULL COMMENT '省份',
  `district` varchar(255) DEFAULT NULL COMMENT '行政区',
  `address` varchar(500) DEFAULT NULL COMMENT '详细地址',
  `location_list` json DEFAULT NULL COMMENT '多地点列表',
  `education_requirement` varchar(255) DEFAULT NULL COMMENT '学历要求原始',
  `education_level` varchar(50) DEFAULT NULL COMMENT '标准化学历',
  `experience_requirement` varchar(255) DEFAULT NULL COMMENT '经验要求原始',
  `experience_min_months` int DEFAULT NULL COMMENT '最低经验月数',
  `experience_max_months` int DEFAULT NULL COMMENT '最高经验月数',
  `salary_text` varchar(255) DEFAULT NULL COMMENT '薪资原始文本',
  `salary_min` int DEFAULT NULL COMMENT '最低薪资(折算月薪)',
  `salary_max` int DEFAULT NULL COMMENT '最高薪资(折算月薪)',
  `salary_unit` varchar(50) DEFAULT NULL COMMENT 'day/week/month/hour',
  `salary_months` int DEFAULT NULL COMMENT '年薪月数',
  `salary_currency` varchar(20) DEFAULT 'CNY',
  `job_description` mediumtext COMMENT '职位描述/JD',
  `job_requirements` mediumtext COMMENT '任职要求',
  `job_responsibilities` mediumtext COMMENT '岗位职责',
  `benefits` text COMMENT '福利待遇',
  `skill_tags` json DEFAULT NULL COMMENT '技能标签JSON',
  `major_requirement` varchar(255) DEFAULT NULL COMMENT '专业要求',
  `language_requirement` varchar(255) DEFAULT NULL COMMENT '语言要求',
  `certificate_requirement` text COMMENT '证书要求',
  `work_time` varchar(100) DEFAULT NULL COMMENT '工作时间',
  `salary_payment` varchar(100) DEFAULT NULL COMMENT '发放方式',
  `industry_requirement` text COMMENT '行业要求',
  `job_level` varchar(100) DEFAULT NULL COMMENT '职级L1-L5',
  `apply_url` text COMMENT '投递链接',
  `detail_url` text COMMENT '详情链接',
  `source_site` varchar(100) DEFAULT NULL COMMENT '来源站点com_id',
  `source_job_id` varchar(255) DEFAULT NULL COMMENT '来源职位ID',
  `published_at` datetime DEFAULT NULL COMMENT '发布时间',
  `deadline_at` datetime DEFAULT NULL COMMENT '截止时间',
  `first_seen_at` datetime DEFAULT NULL COMMENT '首次抓取',
  `last_seen_at` datetime DEFAULT NULL COMMENT '最后抓取',
  `status` varchar(50) NOT NULL DEFAULT 'open' COMMENT 'open/closed/expired',
  `is_active` tinyint NOT NULL DEFAULT '1' COMMENT '是否展示',
  `quality_score` int DEFAULT NULL COMMENT '数据质量评分0-100',
  `dedupe_key` varchar(255) DEFAULT NULL COMMENT '去重键',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_ai_related` tinyint DEFAULT '0' COMMENT 'AI相关标记',
  PRIMARY KEY (`id`),
  KEY `idx_company_id` (`company_id`),
  KEY `idx_title` (`title`),
  KEY `idx_city` (`city`),
  KEY `idx_is_intern` (`is_intern`),
  KEY `idx_is_campus` (`is_campus`),
  KEY `idx_employment_type` (`employment_type`),
  KEY `idx_status` (`status`),
  KEY `idx_published_at` (`published_at`),
  KEY `idx_is_ai_related` (`is_ai_related`),
  KEY `idx_dedupe_key` (`dedupe_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 5. job_sources - 职位来源表
-- ============================================================
DROP TABLE IF EXISTS `job_sources`;
CREATE TABLE `job_sources` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `job_id` bigint NOT NULL COMMENT '关联 jobs.id',
  `source_site` varchar(100) NOT NULL COMMENT '来源站点',
  `source_type` varchar(50) DEFAULT NULL COMMENT '爬虫/招聘站/公众号',
  `source_job_id` varchar(255) DEFAULT NULL,
  `source_url` text COMMENT '来源页面URL',
  `apply_url` text COMMENT '投递链接',
  `is_official` tinyint NOT NULL DEFAULT '0',
  `is_primary_source` tinyint NOT NULL DEFAULT '0',
  `published_at` datetime DEFAULT NULL,
  `first_seen_at` datetime DEFAULT NULL,
  `last_seen_at` datetime DEFAULT NULL,
  `status` varchar(50) NOT NULL DEFAULT 'active',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_job_id` (`job_id`),
  KEY `idx_source_site` (`source_site`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 6. crawl_tasks - 任务执行日志
-- ============================================================
DROP TABLE IF EXISTS `crawl_tasks`;
CREATE TABLE `crawl_tasks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` varchar(50) NOT NULL COMMENT 'UUID',
  `task_type` enum('crawl','process','ingest','full') NOT NULL,
  `status` enum('pending','running','completed','failed','stopped') DEFAULT 'pending',
  `total_items` int DEFAULT '0',
  `processed_items` int DEFAULT '0',
  `failed_items` int DEFAULT '0',
  `started_at` datetime DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  `error_message` text,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `task_id` (`task_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 7. raw_job_records - 原始抓取记录
-- ============================================================
DROP TABLE IF EXISTS `raw_job_records`;
CREATE TABLE `raw_job_records` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `source_site` varchar(100) NOT NULL,
  `source_type` varchar(50) DEFAULT NULL,
  `source_url` text,
  `source_job_id` varchar(255) DEFAULT NULL,
  `fetch_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `http_status` int DEFAULT NULL,
  `raw_title` varchar(500) DEFAULT NULL,
  `raw_text` mediumtext,
  `raw_html` mediumtext,
  `raw_json` json DEFAULT NULL,
  `content_hash` varchar(255) DEFAULT NULL,
  `parse_status` varchar(50) NOT NULL DEFAULT 'pending',
  `parse_error` text,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_source_site` (`source_site`),
  KEY `idx_parse_status` (`parse_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 8. company_lists - 企业榜单目录
-- ============================================================
DROP TABLE IF EXISTS `company_lists`;
CREATE TABLE `company_lists` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(200) NOT NULL,
  `short_name` varchar(100) DEFAULT NULL,
  `category` varchar(50) NOT NULL,
  `source_url` varchar(1000) DEFAULT NULL,
  `source_year` varchar(20) DEFAULT NULL,
  `is_active` tinyint DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 9. company_list_entries - 企业榜单条目
-- ============================================================
DROP TABLE IF EXISTS `company_list_entries`;
CREATE TABLE `company_list_entries` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `list_id` int NOT NULL COMMENT '关联 company_lists.id',
  `company_name` varchar(300) NOT NULL,
  `company_name_normalized` varchar(300) DEFAULT NULL,
  `rank_num` int DEFAULT NULL,
  `stock_code` varchar(50) DEFAULT NULL,
  `province` varchar(100) DEFAULT NULL,
  `extra_data` json DEFAULT NULL,
  `matched_company_id` bigint DEFAULT NULL,
  `match_score` decimal(3,2) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_list_id` (`list_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 10. vector_index_metadata - 向量索引元数据
-- ============================================================
DROP TABLE IF EXISTS `vector_index_metadata`;
CREATE TABLE `vector_index_metadata` (
  `id` int NOT NULL AUTO_INCREMENT,
  `index_type` varchar(50) NOT NULL,
  `model_name` varchar(200) NOT NULL,
  `dimension` int NOT NULL,
  `total_jobs` int NOT NULL,
  `index_file_path` varchar(500) DEFAULT NULL,
  `build_config` json DEFAULT NULL,
  `status` varchar(50) DEFAULT 'active',
  `error_message` text,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 11. resume_match_history - 简历匹配历史
-- ============================================================
DROP TABLE IF EXISTS `resume_match_history`;
CREATE TABLE `resume_match_history` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `resume_text_hash` varchar(64) DEFAULT NULL,
  `match_params` json DEFAULT NULL,
  `results` json DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 12-14. 技能统计缓存
-- ============================================================
DROP TABLE IF EXISTS `skill_stats_cache`;
CREATE TABLE `skill_stats_cache` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `skill_name` varchar(100) NOT NULL,
  `stats_data` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_skill` (`skill_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `skill_combination_cache`;
CREATE TABLE `skill_combination_cache` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `combo_key` varchar(200) NOT NULL,
  `data` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_combo` (`combo_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

DROP TABLE IF EXISTS `v_match_performance_stats`;
CREATE TABLE `v_match_performance_stats` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` varchar(64) DEFAULT NULL,
  `stats` json DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
