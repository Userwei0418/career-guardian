"""
报警系统模块
检测异常情况并生成报警
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any

class AlertSystem:
    """报警系统"""
    
    def __init__(self, monitor_base: str = "data/monitor"):
        """
        初始化报警系统
        
        Args:
            monitor_base: 监控数据目录
        """
        self.alert_dir = os.path.join(monitor_base, "alerts")
        os.makedirs(self.alert_dir, exist_ok=True)
        self.config = self._load_default_config()
    
    def _load_default_config(self) -> Dict[str, Any]:
        """加载默认报警配置"""
        return {
            "no_data_days": 3,           # N天无数据报警
            "clean_rate_threshold": 70,  # 清洗率低于70%报警
            "pending_threshold": 50,     # 待清洗超过50条报警
            "error_rate_threshold": 20,  # 错误率超过20%报警
            "crawl_count_threshold": 5,  # 爬取数量少于5条报警
            "clean_time_threshold": 300  # 单次清洗超过5分钟报警
        }
    
    def load_config(self, config_file: str):
        """
        从文件加载配置
        
        Args:
            config_file: 配置文件路径
        """
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                custom_config = json.load(f)
                self.config.update(custom_config)
        except Exception as e:
            print(f"加载配置失败: {e}，使用默认配置")
    
    def check_alerts(self, log_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        检查是否需要报警
        
        Args:
            log_data: 日志数据
            
        Returns:
            报警列表
        """
        alerts = []
        
        for company_key, company in log_data["companies"].items():
            # 检查清洗率
            alerts.extend(
                self._check_clean_rate(company_key, company)
            )
            
            # 检查待清洗数量
            alerts.extend(
                self._check_pending_count(company_key, company)
            )
            
            # 检查错误率
            alerts.extend(
                self._check_error_rate(company_key, company)
            )
            
            # 检查爬取数量
            alerts.extend(
                self._check_crawl_count(company_key, company)
            )
            
            # 检查清洗时间
            alerts.extend(
                self._check_clean_time(company_key, company)
            )
        
        if alerts:
            self._save_alerts(alerts, log_data.get("date", "unknown"))
        
        return alerts
    
    def _check_clean_rate(self, 
                         company_key: str, 
                         company: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检查清洗率"""
        alerts = []
        
        if company["crawl"]["success"] > 0:
            clean_rate = (company["clean"]["success"] / 
                        company["crawl"]["success"] * 100)
            
            if clean_rate < self.config["clean_rate_threshold"]:
                alerts.append({
                    "type": "low_clean_rate",
                    "level": "warning",
                    "company": company_key,
                    "company_name": company.get("company_name", ""),
                    "rate": round(clean_rate, 2),
                    "threshold": self.config["clean_rate_threshold"],
                    "crawled": company["crawl"]["success"],
                    "cleaned": company["clean"]["success"],
                    "message": f"清洗率过低: {clean_rate:.2f}% < {self.config['clean_rate_threshold']}%"
                })
        
        return alerts
    
    def _check_pending_count(self,
                           company_key: str,
                           company: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检查待清洗数量"""
        alerts = []
        
        pending = company["clean"].get("pending", 0)
        if pending > self.config["pending_threshold"]:
            alerts.append({
                "type": "high_pending",
                "level": "warning",
                "company": company_key,
                "company_name": company.get("company_name", ""),
                "pending": pending,
                "threshold": self.config["pending_threshold"],
                "message": f"待清洗数量过多: {pending} > {self.config['pending_threshold']}"
            })
        
        return alerts
    
    def _check_error_rate(self,
                         company_key: str,
                         company: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检查错误率"""
        alerts = []
        
        total_ops = company["crawl"]["total"] + company["clean"]["total"]
        if total_ops > 0:
            errors = company["crawl"]["failed"] + company["clean"]["failed"]
            error_rate = errors / total_ops * 100
            
            if error_rate > self.config["error_rate_threshold"]:
                alerts.append({
                    "type": "high_error_rate",
                    "level": "error",
                    "company": company_key,
                    "company_name": company.get("company_name", ""),
                    "rate": round(error_rate, 2),
                    "threshold": self.config["error_rate_threshold"],
                    "total_errors": errors,
                    "total_ops": total_ops,
                    "message": f"错误率过高: {error_rate:.2f}% > {self.config['error_rate_threshold']}%"
                })
        
        return alerts
    
    def _check_crawl_count(self,
                          company_key: str,
                          company: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检查爬取数量"""
        alerts = []
        
        crawl_count = company["crawl"]["success"]
        if 0 < crawl_count < self.config["crawl_count_threshold"]:
            alerts.append({
                "type": "low_crawl_count",
                "level": "info",
                "company": company_key,
                "company_name": company.get("company_name", ""),
                "count": crawl_count,
                "threshold": self.config["crawl_count_threshold"],
                "message": f"爬取数量较少: {crawl_count} < {self.config['crawl_count_threshold']}"
            })
        
        return alerts
    
    def _check_clean_time(self,
                         company_key: str,
                         company: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检查清洗时间"""
        alerts = []
        
        clean_times = company.get("performance", {}).get("clean_times", [])
        if clean_times:
            max_time = max(clean_times)
            if max_time > self.config["clean_time_threshold"]:
                alerts.append({
                    "type": "long_clean_time",
                    "level": "warning",
                    "company": company_key,
                    "company_name": company.get("company_name", ""),
                    "max_time": round(max_time, 2),
                    "threshold": self.config["clean_time_threshold"],
                    "message": f"清洗耗时过长: {max_time:.2f}s > {self.config['clean_time_threshold']}s"
                })
        
        return alerts
    
    def check_scan_report(self, scan_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        检查扫描报告并生成报警
        
        Args:
            scan_report: 扫描报告
            
        Returns:
            报警列表
        """
        alerts = []
        
        # 检查长期无数据的公司
        for item in scan_report["issues"]["old_data"]:
            if item["days"] > self.config["no_data_days"]:
                alerts.append({
                    "type": "no_data_long_time",
                    "level": "warning",
                    "company": item["company"],
                    "days": item["days"],
                    "last_time": item["last_time"],
                    "threshold": self.config["no_data_days"],
                    "message": f"长期无数据: {item['days']}天 > {self.config['no_data_days']}天"
                })
        
        # 检查未清洗的文件
        missing_clean_count = len(scan_report["issues"]["missing_clean"])
        if missing_clean_count > 0:
            # 按公司分组统计
            company_missing = {}
            for item in scan_report["issues"]["missing_clean"]:
                company = item["company"]
                if company not in company_missing:
                    company_missing[company] = 0
                company_missing[company] += 1
            
            for company, count in company_missing.items():
                if count > 10:  # 超过10个未清洗文件才报警
                    alerts.append({
                        "type": "many_missing_clean",
                        "level": "warning",
                        "company": company,
                        "count": count,
                        "message": f"大量未清洗文件: {count}个"
                    })
        
        # 检查孤立文件
        orphan_count = len(scan_report["issues"]["orphan_clean"])
        if orphan_count > 0:
            alerts.append({
                "type": "orphan_files",
                "level": "info",
                "count": orphan_count,
                "message": f"发现{orphan_count}个孤立清洗文件（有清洗但无原始文件）"
            })
        
        if alerts:
            self._save_alerts(
                alerts, 
                scan_report.get("scan_time", datetime.now().strftime("%Y%m%d_%H%M%S"))
            )
        
        return alerts
    
    def _save_alerts(self, alerts: List[Dict[str, Any]], date_label: str):
        """
        保存报警
        
        Args:
            alerts: 报警列表
            date_label: 日期标签
        """
        alert_file = os.path.join(
            self.alert_dir,
            f"alert_{date_label}_{datetime.now().strftime('%H%M%S')}.json"
        )
        
        try:
            with open(alert_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "count": len(alerts),
                    "alerts": alerts
                }, f, ensure_ascii=False, indent=2)
            
            # 打印报警摘要
            print(f"\n{'='*60}")
            print(f"发现 {len(alerts)} 个报警:")
            print(f"{'='*60}")
            
            for alert in alerts:
                level_icon = {
                    "error": "❌",
                    "warning": "⚠️",
                    "info": "ℹ️"
                }.get(alert.get("level", "info"), "•")
                
                print(f"{level_icon} [{alert.get('level', 'info').upper()}] "
                      f"{alert.get('company', 'N/A')}: {alert.get('message', '')}")
            
            print(f"{'='*60}")
            print(f"详细报警已保存至: {alert_file}\n")
            
        except Exception as e:
            print(f"保存报警失败: {e}")