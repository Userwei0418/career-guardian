"""
报告生成器模块
生成各类统计报告
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from pathlib import Path

class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, monitor_base: str = "data/monitor"):
        """
        初始化报告生成器
        
        Args:
            monitor_base: 监控数据目录
        """
        self.monitor_base = monitor_base
        self.log_dir = os.path.join(monitor_base, "logs")
        self.report_dir = os.path.join(monitor_base, "reports")
        os.makedirs(self.report_dir, exist_ok=True)
    
    def generate_daily_report(self, date: str = None) -> Dict[str, Any]:
        """
        生成日报
        
        Args:
            date: 日期（YYYYMMDD），None表示今天
            
        Returns:
            日报字典
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        
        log_file = os.path.join(self.log_dir, f"{date}.json")
        
        if not os.path.exists(log_file):
            return {"error": f"日志文件不存在: {log_file}"}
        
        with open(log_file, 'r', encoding='utf-8') as f:
            log_data = json.load(f)
        
        report = {
            "report_type": "daily",
            "date": date,
            "generate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "summary": log_data.get("summary", {}),
            "performance": log_data.get("performance", {}),
            "top_companies": self._get_top_companies(log_data),
            "problem_companies": self._get_problem_companies(log_data),
            "hourly_stats": self._analyze_hourly_stats(log_data)
        }
        
        # 保存报告
        report_file = os.path.join(
            self.report_dir,
            f"daily_{date}.json"
        )
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return report
    
    def generate_weekly_report(self, end_date: str = None) -> Dict[str, Any]:
        """
        生成周报（最近7天）
        
        Args:
            end_date: 结束日期（YYYYMMDD），None表示今天
            
        Returns:
            周报字典
        """
        if end_date is None:
            end_dt = datetime.now()
        else:
            end_dt = datetime.strptime(end_date, "%Y%m%d")
        
        # 收集最近7天的数据
        daily_data = []
        for i in range(7):
            date_dt = end_dt - timedelta(days=i)
            date_str = date_dt.strftime("%Y%m%d")
            log_file = os.path.join(self.log_dir, f"{date_str}.json")
            
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    daily_data.append({
                        "date": date_str,
                        "data": json.load(f)
                    })
        
        if not daily_data:
            return {"error": "没有找到最近7天的数据"}
        
        report = {
            "report_type": "weekly",
            "period": {
                "start": daily_data[-1]["date"],
                "end": daily_data[0]["date"]
            },
            "generate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_summary": self._aggregate_summary(daily_data),
            "daily_trend": self._analyze_daily_trend(daily_data),
            "company_ranking": self._rank_companies(daily_data),
            "performance_trend": self._analyze_performance_trend(daily_data)
        }
        
        # 保存报告
        report_file = os.path.join(
            self.report_dir,
            f"weekly_{end_dt.strftime('%Y%m%d')}.json"
        )
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return report
    
    def _get_top_companies(self, 
                          log_data: Dict[str, Any],
                          top_n: int = 10) -> List[Dict[str, Any]]:
        """获取爬取量最多的公司"""
        companies = []
        
        for key, company in log_data.get("companies", {}).items():
            companies.append({
                "key": key,
                "name": company.get("company_name", ""),
                "crawled": company["crawl"]["success"],
                "cleaned": company["clean"]["success"]
            })
        
        # 按爬取量排序
        companies.sort(key=lambda x: x["crawled"], reverse=True)
        
        return companies[:top_n]
    
    def _get_problem_companies(self, log_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取有问题的公司"""
        problems = []
        
        for key, company in log_data.get("companies", {}).items():
            issues = []
            
            # 检查清洗率
            if company["crawl"]["success"] > 0:
                clean_rate = (company["clean"]["success"] / 
                            company["crawl"]["success"] * 100)
                if clean_rate < 80:
                    issues.append(f"清洗率低: {clean_rate:.1f}%")
            
            # 检查错误率
            total_ops = company["crawl"]["total"] + company["clean"]["total"]
            if total_ops > 0:
                errors = company["crawl"]["failed"] + company["clean"]["failed"]
                error_rate = errors / total_ops * 100
                if error_rate > 10:
                    issues.append(f"错误率高: {error_rate:.1f}%")
            
            # 检查待清洗
            if company["clean"].get("pending", 0) > 20:
                issues.append(f"待清洗: {company['clean']['pending']}个")
            
            if issues:
                problems.append({
                    "key": key,
                    "name": company.get("company_name", ""),
                    "issues": issues
                })
        
        return problems
    
    def _analyze_hourly_stats(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析每小时统计"""
        hourly = {}
        
        for company in log_data.get("companies", {}).values():
            # 分析爬取时间分布
            for detail in company["crawl"]["details"]:
                time_str = detail.get("time", "")
                if time_str:
                    hour = time_str.split()[1].split(":")[0]
                    if hour not in hourly:
                        hourly[hour] = {"crawl": 0, "clean": 0}
                    hourly[hour]["crawl"] += 1
            
            # 分析清洗时间分布
            for detail in company["clean"]["details"]:
                time_str = detail.get("time", "")
                if time_str:
                    hour = time_str.split()[1].split(":")[0]
                    if hour not in hourly:
                        hourly[hour] = {"crawl": 0, "clean": 0}
                    hourly[hour]["clean"] += 1
        
        return hourly
    
    def _aggregate_summary(self, daily_data: List[Dict]) -> Dict[str, Any]:
        """汇总多日数据"""
        total = {
            "total_crawled": 0,
            "total_cleaned": 0,
            "total_errors": 0,
            "active_companies": set()
        }
        
        for item in daily_data:
            data = item["data"]
            summary = data.get("summary", {})
            
            total["total_crawled"] += summary.get("total_crawled", 0)
            total["total_cleaned"] += summary.get("total_cleaned", 0)
            total["total_errors"] += summary.get("errors", {}).get("crawl_errors", 0)
            total["total_errors"] += summary.get("errors", {}).get("clean_errors", 0)
            
            # 统计活跃公司
            for key, company in data.get("companies", {}).items():
                if company["crawl"]["success"] > 0:
                    total["active_companies"].add(key)
        
        total["active_companies"] = len(total["active_companies"])
        
        return total
    
    def _analyze_daily_trend(self, daily_data: List[Dict]) -> List[Dict[str, Any]]:
        """分析每日趋势"""
        trend = []
        
        for item in sorted(daily_data, key=lambda x: x["date"]):
            data = item["data"]
            summary = data.get("summary", {})
            
            trend.append({
                "date": item["date"],
                "crawled": summary.get("total_crawled", 0),
                "cleaned": summary.get("total_cleaned", 0),
                "errors": (summary.get("errors", {}).get("crawl_errors", 0) +
                          summary.get("errors", {}).get("clean_errors", 0)),
                "active_companies": summary.get("active_companies", 0)
            })
        
        return trend
    
    def _rank_companies(self, daily_data: List[Dict]) -> List[Dict[str, Any]]:
        """公司排名"""
        company_stats = {}
        
        for item in daily_data:
            for key, company in item["data"].get("companies", {}).items():
                if key not in company_stats:
                    company_stats[key] = {
                        "key": key,
                        "name": company.get("company_name", ""),
                        "total_crawled": 0,
                        "total_cleaned": 0
                    }
                
                company_stats[key]["total_crawled"] += company["crawl"]["success"]
                company_stats[key]["total_cleaned"] += company["clean"]["success"]
        
        # 排序
        ranking = sorted(
            company_stats.values(),
            key=lambda x: x["total_crawled"],
            reverse=True
        )
        
        return ranking[:20]  # 返回前20名
    
    def _analyze_performance_trend(self, daily_data: List[Dict]) -> Dict[str, Any]:
        """分析性能趋势"""
        trend = {
            "daily_avg_crawl_time": [],
            "daily_avg_clean_time": []
        }
        
        for item in sorted(daily_data, key=lambda x: x["date"]):
            data = item["data"]
            perf = data.get("performance", {})
            
            trend["daily_avg_crawl_time"].append({
                "date": item["date"],
                "value": perf.get("avg_crawl_time", 0)
            })
            
            trend["daily_avg_clean_time"].append({
                "date": item["date"],
                "value": perf.get("avg_clean_time", 0)
            })
        
        return trend
    
    def print_daily_summary(self, date: str = None):
        """打印日报摘要"""
        report = self.generate_daily_report(date)
        
        if "error" in report:
            print(report["error"])
            return
        
        print(f"\n{'='*60}")
        print(f"日报 - {report['date']}")
        print(f"{'='*60}\n")
        
        summary = report["summary"]
        print(f"总体统计:")
        print(f"  爬取: {summary.get('total_crawled', 0)} 条")
        print(f"  清洗: {summary.get('total_cleaned', 0)} 条")
        print(f"  待清洗: {summary.get('pending_clean', 0)} 条")
        print(f"  活跃公司: {summary.get('active_companies', 0)} / {summary.get('total_companies', 0)}")
        
        errors = summary.get('errors', {})
        print(f"  爬取错误: {errors.get('crawl_errors', 0)} 次")
        print(f"  清洗错误: {errors.get('clean_errors', 0)} 次")
        
        perf = report.get("performance", {})
        print(f"\n性能统计:")
        print(f"  平均爬取耗时: {perf.get('avg_crawl_time', 0):.2f}秒")
        print(f"  平均清洗耗时: {perf.get('avg_clean_time', 0):.2f}秒")
        
        print(f"\nTop 5 公司:")
        for i, company in enumerate(report.get("top_companies", [])[:5], 1):
            print(f"  {i}. {company['name']} - "
                  f"爬取:{company['crawled']} 清洗:{company['cleaned']}")
        
        problems = report.get("problem_companies", [])
        if problems:
            print(f"\n问题公司 ({len(problems)}):")
            for company in problems[:5]:
                print(f"  • {company['name']}: {', '.join(company['issues'])}")
        
        print(f"\n{'='*60}\n")