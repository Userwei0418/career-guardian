"""
全盘扫描模块
对比tmp和ardata目录，发现数据完整性问题
"""

import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict

class FullScanner:
    """全盘扫描分析器"""
    
    def __init__(self, 
                 tmp_base: str,
                 ar_base: str,
                 monitor_base: str = "data/monitor"):
        """
        初始化扫描器
        
        Args:
            tmp_base: tmp目录路径
            ar_base: ardata目录路径
            monitor_base: 监控数据目录
        """
        self.tmp_base = tmp_base
        self.ar_base = ar_base
        self.monitor_base = monitor_base
        self.report_dir = os.path.join(monitor_base, "reports")
        os.makedirs(self.report_dir, exist_ok=True)
    
    def scan_all(self, 
                 days_threshold: int = 7,
                 save_report: bool = True) -> Dict[str, Any]:
        """
        全盘扫描
        
        Args:
            days_threshold: 多少天无数据算作长期无更新
            save_report: 是否保存报告
            
        Returns:
            扫描报告字典
        """
        report = {
            "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "config": {
                "tmp_base": self.tmp_base,
                "ar_base": self.ar_base,
                "days_threshold": days_threshold
            },
            "companies": {},
            "issues": {
                "missing_clean": [],      # 已抓取但未清洗
                "orphan_clean": [],       # 有清洗但无原始文件
                "old_data": [],           # 长期无更新
                "empty_companies": [],    # 空公司目录
                "expired_files": []       # 过期文件
            },
            "statistics": {
                "total_companies": 0,
                "total_tmp_files": 0,
                "total_model_files": 0,
                "total_expired_files": 0,
                "clean_rate": 0,
                "active_companies": 0,
                "inactive_companies": 0
            }
        }
        
        print("开始全盘扫描...")
        
        # 扫描所有公司目录
        tmp_companies = self._get_company_dirs(self.tmp_base)
        ar_companies = self._get_company_dirs(self.ar_base)
        all_companies = set(tmp_companies.keys()) | set(ar_companies.keys())
        
        print(f"发现 {len(all_companies)} 个公司目录")
        
        for i, company_key in enumerate(all_companies, 1):
            print(f"扫描进度: {i}/{len(all_companies)} - {company_key}")
            
            company_report = self._scan_company(
                company_key,
                tmp_companies.get(company_key),
                ar_companies.get(company_key),
                days_threshold
            )
            report["companies"][company_key] = company_report
            
            # 收集问题
            self._collect_issues(company_key, company_report, report["issues"])
        
        # 计算统计数据
        self._calculate_statistics(report)
        
        # 保存报告
        if save_report:
            report_file = os.path.join(
                self.report_dir,
                f"full_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"报告已保存至: {report_file}")
        
        return report
    
    def _get_company_dirs(self, base_path: str) -> Dict[str, str]:
        """
        获取所有公司目录
        
        Args:
            base_path: 基础路径
            
        Returns:
            {公司key: 目录路径}
        """
        companies = {}
        if not os.path.exists(base_path):
            return companies
        
        try:
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                if os.path.isdir(item_path) and item.startswith("com_"):
                    companies[item] = item_path
        except Exception as e:
            print(f"扫描目录 {base_path} 失败: {e}")
        
        return companies
    
    def _scan_company(self,
                     company_key: str,
                     tmp_dir: str,
                     ar_dir: str,
                     days_threshold: int) -> Dict[str, Any]:
        """
        扫描单个公司
        
        Args:
            company_key: 公司key
            tmp_dir: tmp目录
            ar_dir: ardata目录
            days_threshold: 天数阈值
            
        Returns:
            公司扫描报告
        """
        report = {
            "tmp_count": 0,
            "model_count": 0,
            "expired_count": 0,
            "missing_clean": [],
            "orphan_clean": [],
            "last_tmp_time": None,
            "last_model_time": None,
            "days_since_last_crawl": None,
            "days_since_last_clean": None,
            "status": "unknown"  # active/inactive/empty
        }
        
        # 扫描tmp目录
        tmp_files = {}
        if tmp_dir and os.path.exists(tmp_dir):
            for file in os.listdir(tmp_dir):
                if file.startswith("detail_") and file.endswith(".json"):
                    file_path = os.path.join(tmp_dir, file)
                    try:
                        tmp_files[file] = os.path.getmtime(file_path)
                        report["tmp_count"] += 1
                    except Exception as e:
                        print(f"读取文件 {file_path} 失败: {e}")
            
            if tmp_files:
                latest_time = max(tmp_files.values())
                report["last_tmp_time"] = datetime.fromtimestamp(
                    latest_time
                ).strftime("%Y-%m-%d %H:%M:%S")
                report["days_since_last_crawl"] = (
                    datetime.now() - datetime.fromtimestamp(latest_time)
                ).days
        
        # 扫描ardata目录
        model_files = {}
        expired_files = {}
        
        if ar_dir and os.path.exists(ar_dir):
            for file in os.listdir(ar_dir):
                file_path = os.path.join(ar_dir, file)
                try:
                    if file.endswith(".model.json"):
                        model_files[file] = os.path.getmtime(file_path)
                        report["model_count"] += 1
                    elif file.endswith(".json.expired"):
                        expired_files[file] = os.path.getmtime(file_path)
                        report["expired_count"] += 1
                except Exception as e:
                    print(f"读取文件 {file_path} 失败: {e}")
            
            if model_files:
                latest_time = max(model_files.values())
                report["last_model_time"] = datetime.fromtimestamp(
                    latest_time
                ).strftime("%Y-%m-%d %H:%M:%S")
                report["days_since_last_clean"] = (
                    datetime.now() - datetime.fromtimestamp(latest_time)
                ).days
        
        # 对比找出问题
        for tmp_file in tmp_files:
            model_file = tmp_file.replace(".json", ".model.json")
            expired_file = tmp_file.replace(".json", ".json.expired")
            
            # 检查是否有对应的model或expired文件
            if model_file not in model_files and expired_file not in expired_files:
                report["missing_clean"].append({
                    "file": tmp_file,
                    "mtime": datetime.fromtimestamp(
                        tmp_files[tmp_file]
                    ).strftime("%Y-%m-%d %H:%M:%S")
                })
        
        for model_file in model_files:
            source_file = model_file.replace(".model.json", ".json")
            if source_file not in tmp_files:
                report["orphan_clean"].append({
                    "file": model_file,
                    "mtime": datetime.fromtimestamp(
                        model_files[model_file]
                    ).strftime("%Y-%m-%d %H:%M:%S")
                })
        
        # 判断公司状态
        if report["tmp_count"] == 0 and report["model_count"] == 0:
            report["status"] = "empty"
        elif (report["days_since_last_crawl"] is not None and 
              report["days_since_last_crawl"] > days_threshold):
            report["status"] = "inactive"
        else:
            report["status"] = "active"
        
        return report
    
    def _collect_issues(self,
                       company_key: str,
                       company_report: Dict[str, Any],
                       issues: Dict[str, List]):
        """
        收集问题到总问题列表
        
        Args:
            company_key: 公司key
            company_report: 公司报告
            issues: 总问题字典
        """
        # 未清洗的文件
        for item in company_report["missing_clean"]:
            issues["missing_clean"].append({
                "company": company_key,
                "file": item["file"],
                "mtime": item["mtime"]
            })
        
        # 孤立的清洗文件
        for item in company_report["orphan_clean"]:
            issues["orphan_clean"].append({
                "company": company_key,
                "file": item["file"],
                "mtime": item["mtime"]
            })
        
        # 长期无数据
        if (company_report["days_since_last_crawl"] is not None and
            company_report["status"] == "inactive"):
            issues["old_data"].append({
                "company": company_key,
                "days": company_report["days_since_last_crawl"],
                "last_time": company_report["last_tmp_time"]
            })
        
        # 空目录
        if company_report["status"] == "empty":
            issues["empty_companies"].append(company_key)
        
        # 过期文件
        if company_report["expired_count"] > 0:
            issues["expired_files"].append({
                "company": company_key,
                "count": company_report["expired_count"]
            })
    
    def _calculate_statistics(self, report: Dict[str, Any]):
        """
        计算统计数据
        
        Args:
            report: 报告字典
        """
        stats = report["statistics"]
        
        stats["total_companies"] = len(report["companies"])
        stats["total_tmp_files"] = sum(
            c["tmp_count"] for c in report["companies"].values()
        )
        stats["total_model_files"] = sum(
            c["model_count"] for c in report["companies"].values()
        )
        stats["total_expired_files"] = sum(
            c["expired_count"] for c in report["companies"].values()
        )
        
        # 计算清洗率
        if stats["total_tmp_files"] > 0:
            stats["clean_rate"] = round(
                (stats["total_model_files"] + stats["total_expired_files"]) / 
                stats["total_tmp_files"] * 100, 2
            )
        
        # 统计活跃/非活跃公司
        stats["active_companies"] = sum(
            1 for c in report["companies"].values() 
            if c["status"] == "active"
        )
        stats["inactive_companies"] = sum(
            1 for c in report["companies"].values() 
            if c["status"] == "inactive"
        )
    
    def quick_check(self, company_key: str) -> Dict[str, Any]:
        """
        快速检查单个公司
        
        Args:
            company_key: 公司key
            
        Returns:
            公司状态报告
        """
        tmp_dir = os.path.join(self.tmp_base, company_key)
        ar_dir = os.path.join(self.ar_base, company_key)
        
        return self._scan_company(company_key, tmp_dir, ar_dir, 7)
    
    def get_missing_clean_list(self, company_key: str = None) -> List[Dict]:
        """
        获取未清洗文件列表
        
        Args:
            company_key: 公司key，None表示所有公司
            
        Returns:
            未清洗文件列表
        """
        result = []
        
        if company_key:
            companies = {company_key: None}
        else:
            companies = self._get_company_dirs(self.tmp_base)
        
        for key in companies:
            tmp_dir = os.path.join(self.tmp_base, key)
            ar_dir = os.path.join(self.ar_base, key)
            
            if not os.path.exists(tmp_dir):
                continue
            
            for file in os.listdir(tmp_dir):
                if not (file.startswith("detail_") and file.endswith(".json")):
                    continue
                
                model_file = os.path.join(
                    ar_dir, 
                    file.replace(".json", ".model.json")
                )
                expired_file = os.path.join(
                    ar_dir,
                    file.replace(".json", ".json.expired")
                )
                
                if not os.path.exists(model_file) and not os.path.exists(expired_file):
                    result.append({
                        "company": key,
                        "file": file,
                        "path": os.path.join(tmp_dir, file)
                    })
        
        return result