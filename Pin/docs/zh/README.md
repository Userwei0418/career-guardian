# Pin - 招聘数据聚合平台

## 项目概述

Pin 是一个面向应届生的校招/实习/全职招聘信息聚合与数据分析平台，提供职位检索、数据分析看板、智能简历匹配等核心能力。

## 文档索引

| 文档 | 说明 |
|------|------|
| [项目架构总览](./技术方案/01_架构总览.md) | 系统整体架构、技术选型、服务划分 |
| [爬虫模块](./模块文档/01_爬虫模块.md) | 数据采集、LLM解析、入库流水线 |
| [后端API服务](./模块文档/02_后端API服务.md) | FastAPI 接口设计与路由说明 |
| [前端应用](./模块文档/03_前端应用.md) | Next.js 页面结构与组件设计 |
| [数据库设计](./技术方案/02_数据库设计.md) | 表结构、索引、数据流 |
| [部署指南](./部署运维/01_部署指南.md) | 本地开发、生产部署、服务管理 |
| [变更日志](./部署运维/02_变更日志.md) | 2026-07 重构记录 |

## 服务端口

| 服务 | 地址 | 说明 |
|------|------|------|
| 后端 API | http://localhost:8000 | FastAPI 主服务 |
| 爬虫管理 | http://localhost:8001 | Crawler Management Service |
| 前端 | http://localhost:3000 | Next.js SSR |
| API 文档 | http://localhost:8000/docs | Swagger UI |

## 快速开始

```bash
# 一键启动所有服务
start.bat

# 或手动分步启动
cd backend/api && python main.py         # 后端 API
cd services && python crawler_service.py  # 爬虫管理
cd frontend && npm run dev               # 前端
```