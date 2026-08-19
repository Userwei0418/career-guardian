"""
实时监控模块
记录爬取和清洗过程的实时日志
"""

import os
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

class CrawlerMonitor:
    """爬虫实时监控器"""
    
    def __init__(self, base_path: str = "data/monitor"):
        """
        初始化监控器
        
        Args:
            base_path: 监控数据基础路径
        """
        self.base_path = base_path
        self.log_dir = os.path.join(base_path, "logs")
        self.report_dir = os.path.join(base_path, "reports")
        self.alert_dir = os.path.join(base_path, "alerts")
        
        # 确保目录存在
        for dir_path in [self.log_dir, self.report_dir, self.alert_dir]:
            os.makedirs(dir_path, exist_ok=True)
        
        self.today = datetime.now().strftime("%Y%m%d")
        self.log_file = os.path.join(self.log_dir, f"{self.today}.json")
        self.log_data = self._load_or_create_log()
        
        # 内存缓存，减少IO
        self._cache_dirty = False
        self._last_save_time = time.time()
        self._save_interval = 10  # 每10秒保存一次
        
    def _load_or_create_log(self) -> Dict[str, Any]:
        """加载或创建今日日志"""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                # 文件损坏，备份并创建新的
                backup_file = f"{self.log_file}.backup_{int(time.time())}"
                os.rename(self.log_file, backup_file)
                return self._create_new_log()
        else:
            return self._create_new_log()
    
    def _create_new_log(self) -> Dict[str, Any]:
        """创建新的日志结构"""
        return {
            "date": self.today,
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": None,
            "companies": {},
            "summary": {
                "total_companies": 0,
                "active_companies": 0,
                "inactive_companies": 0,
                "total_crawled": 0,
                "total_cleaned": 0,
                "pending_clean": 0,
                "errors": {
                    "crawl_errors": 0,
                    "clean_errors": 0
                }
            },
            "performance": {
                "avg_crawl_time": 0,
                "avg_clean_time": 0,
                "max_crawl_time": 0,
                "max_clean_time": 0
            }
        }
    
    def _save_log(self, force: bool = False):
        """
        保存日志（带缓存机制）
        
        Args:
            force: 是否强制保存
        """
        current_time = time.time()
        
        # 如果没有修改或者不是强制保存且未到保存间隔，则跳过
        if not self._cache_dirty:
            return
            
        if not force and (current_time - self._last_save_time) < self._save_interval:
            return
        
        try:
            # 先写入临时文件
            temp_file = f"{self.log_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.log_data, f, ensure_ascii=False, indent=2)
            
            # 再重命名（原子操作）
            os.replace(temp_file, self.log_file)
            
            self._cache_dirty = False
            self._last_save_time = current_time
        except Exception as e:
            print(f"保存日志失败: {e}")
    
    def _get_company_key(self, key: str) -> Dict[str, Any]:
        """
        获取或创建公司数据结构
        
        Args:
            key: 公司key（如com_00001）
            
        Returns:
            公司数据字典
        """
        if key not in self.log_data["companies"]:
            self.log_data["companies"][key] = {
                "company_name": "",
                "config_file": "",
                "crawl": {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "details": []
                },
                "clean": {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "pending": 0,
                    "details": []
                },
                "performance": {
                    "crawl_times": [],
                    "clean_times": []
                },
                "last_crawl_time": None,
                "last_clean_time": None
            }
            self._cache_dirty = True
        return self.log_data["companies"][key]
    
    def log_crawl(self, 
                  key: str,
                  company_name: str,
                  config_file: str,
                  crawl_type: str,
                  url: str,
                  file_hash: str,
                  status: str,
                  error: Optional[str] = None,
                  duration: Optional[float] = None):
        """
        记录爬取操作
        
        Args:
            key: 公司key
            company_name: 公司名称
            config_file: 配置文件编号
            crawl_type: 爬取类型（index/detail）
            url: 爬取的URL
            file_hash: 文件hash
            status: 状态（success/failed）
            error: 错误信息
            duration: 耗时（秒）
        """
        company = self._get_company_key(key)
        company["company_name"] = company_name
        company["config_file"] = config_file
        
        detail = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": crawl_type,
            "url": url,
            "hash": file_hash,
            "status": status,
            "error": error,
            "duration": duration
        }
        
        # 只保留最近100条详情（避免文件过大）
        if len(company["crawl"]["details"]) >= 100:
            company["crawl"]["details"] = company["crawl"]["details"][-99:]
        
        company["crawl"]["details"].append(detail)
        company["crawl"]["total"] += 1
        
        if status == "success":
            company["crawl"]["success"] += 1
            self.log_data["summary"]["total_crawled"] += 1
            
            # 记录性能数据
            if duration:
                company["performance"]["crawl_times"].append(duration)
                # 只保留最近50次
                if len(company["performance"]["crawl_times"]) > 50:
                    company["performance"]["crawl_times"] = \
                        company["performance"]["crawl_times"][-50:]
        else:
            company["crawl"]["failed"] += 1
            self.log_data["summary"]["errors"]["crawl_errors"] += 1
        
        company["last_crawl_time"] = detail["time"]
        self._cache_dirty = True
        self._save_log()
    
    def log_clean(self,
                  key: str,
                  source_file: str,
                  model_file: str,
                  status: str,
                  error: Optional[str] = None,
                  retry_count: int = 0,
                  duration: Optional[float] = None):
        """
        记录清洗操作
        
        Args:
            key: 公司key
            source_file: 源文件名
            model_file: 模型文件名
            status: 状态（success/failed）
            error: 错误信息
            retry_count: 重试次数
            duration: 耗时（秒）
        """
        company = self._get_company_key(key)
        
        detail = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_file": source_file,
            "model_file": model_file,
            "status": status,
            "error": error,
            "retry_count": retry_count,
            "duration": duration
        }
        
        # 只保留最近100条详情
        if len(company["clean"]["details"]) >= 100:
            company["clean"]["details"] = company["clean"]["details"][-99:]
        
        company["clean"]["details"].append(detail)
        company["clean"]["total"] += 1
        
        if status == "success":
            company["clean"]["success"] += 1
            self.log_data["summary"]["total_cleaned"] += 1
            
            # 记录性能数据
            if duration:
                company["performance"]["clean_times"].append(duration)
                if len(company["performance"]["clean_times"]) > 50:
                    company["performance"]["clean_times"] = \
                        company["performance"]["clean_times"][-50:]
        else:
            company["clean"]["failed"] += 1
            self.log_data["summary"]["errors"]["clean_errors"] += 1
        
        company["last_clean_time"] = detail["time"]
        self._cache_dirty = True
        self._save_log()
    
    def update_pending_clean(self, key: str, count: int):
        """
        更新待清洗数量
        
        Args:
            key: 公司key
            count: 待清洗数量
        """
        company = self._get_company_key(key)
        old_count = company["clean"]["pending"]
        company["clean"]["pending"] = count
        
        # 更新总数
        self.log_data["summary"]["pending_clean"] += (count - old_count)
        
        self._cache_dirty = True
        self._save_log()
    
    def finalize_day(self):
        """结束今日任务，生成最终汇总"""
        self.log_data["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 统计活跃公司
        active = sum(1 for c in self.log_data["companies"].values() 
                    if c["crawl"]["success"] > 0)
        total = len(self.log_data["companies"])
        
        self.log_data["summary"]["total_companies"] = total
        self.log_data["summary"]["active_companies"] = active
        self.log_data["summary"]["inactive_companies"] = total - active
        
        # 计算平均性能
        all_crawl_times = []
        all_clean_times = []
        
        for company in self.log_data["companies"].values():
            all_crawl_times.extend(company["performance"]["crawl_times"])
            all_clean_times.extend(company["performance"]["clean_times"])
        
        if all_crawl_times:
            self.log_data["performance"]["avg_crawl_time"] = \
                round(sum(all_crawl_times) / len(all_crawl_times), 2)
            self.log_data["performance"]["max_crawl_time"] = \
                round(max(all_crawl_times), 2)
        
        if all_clean_times:
            self.log_data["performance"]["avg_clean_time"] = \
                round(sum(all_clean_times) / len(all_clean_times), 2)
            self.log_data["performance"]["max_clean_time"] = \
                round(max(all_clean_times), 2)
        
        self._cache_dirty = True
        self._save_log(force=True)
    
    def get_today_summary(self) -> Dict[str, Any]:
        """获取今日汇总"""
        return {
            "date": self.log_data["date"],
            "summary": self.log_data["summary"],
            "performance": self.log_data["performance"],
            "company_count": len(self.log_data["companies"])
        }
    
    def get_company_status(self, key: str) -> Optional[Dict[str, Any]]:
        """
        获取特定公司的状态
        
        Args:
            key: 公司key
            
        Returns:
            公司状态字典，如果不存在返回None
        """
        return self.log_data["companies"].get(key)
    
    def __del__(self):
        """析构时保存"""
        if hasattr(self, '_cache_dirty') and self._cache_dirty:
            self._save_log(force=True)