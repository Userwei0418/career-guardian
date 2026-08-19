"""
监控命令行工具
提供监控相关的命令行操作
"""

import argparse
import json
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from monitor import CrawlerMonitor, FullScanner, AlertSystem, ReportGenerator

def cmd_report(args):
    """查看报告"""
    monitor = CrawlerMonitor()
    
    if args.date:
        # 查看指定日期的报告
        log_file = f"data/monitor/logs/{args.date}.json"
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"错误: 日志文件不存在 {log_file}")
            return
    else:
        # 查看今日报告
        data = monitor.log_data
    
    if args.company:
        # 查看特定公司
        company_data = data["companies"].get(args.company)
        if company_data:
            print(json.dumps(company_data, ensure_ascii=False, indent=2))
        else:
            print(f"错误: 未找到公司 {args.company}")
    else:
        # 查看汇总
        if args.detail:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(data["summary"], ensure_ascii=False, indent=2))

def cmd_scan(args):
    """全盘扫描"""
    # 根据操作系统选择路径
    import os
    if os.name == "nt":  # Windows
        tmp_base = "D:/code/python/chu/clawler_data/data/tmp"
        ar_base = "D:/code/python/chu/clawler_data/data/ardata"
    else:  # Mac/Linux
        tmp_base = "/Users/your_username/code/python/chu/clawler_data/data/tmp"
        ar_base = "/Users/your_username/code/python/chu/clawler_data/data/ardata"
    
    scanner = FullScanner(tmp_base=tmp_base, ar_base=ar_base)
    
    print("开始全盘扫描...")
    report = scanner.scan_all(days_threshold=args.days)
    
    if args.output:
        # 保存到指定文件
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"报告已保存至: {args.output}")
    elif args.summary:
        # 只显示摘要
        print("\n" + "="*60)
        print("扫描摘要")
        print("="*60)
        stats = report["statistics"]
        print(f"总公司数: {stats['total_companies']}")
        print(f"  活跃: {stats['active_companies']}")
        print(f"  非活跃: {stats['inactive_companies']}")
        print(f"总文件数:")
        print(f"  tmp: {stats['total_tmp_files']}")
        print(f"  model: {stats['total_model_files']}")
        print(f"  expired: {stats['total_expired_files']}")
        print(f"清洗率: {stats['clean_rate']}%")
        
        print(f"\n发现的问题:")
        issues = report["issues"]
        print(f"  未清洗: {len(issues['missing_clean'])}")
        print(f"  孤立文件: {len(issues['orphan_clean'])}")
        print(f"  长期无数据: {len(issues['old_data'])}")
        print(f"  空目录: {len(issues['empty_companies'])}")
    else:
        # 显示完整报告
        print(json.dumps(report, ensure_ascii=False, indent=2))

def cmd_alert(args):
    """检查报警"""
    monitor = CrawlerMonitor()
    alert_system = AlertSystem()
    
    # 加载自定义配置
    if args.config:
        alert_system.load_config(args.config)
    
    alerts = alert_system.check_alerts(monitor.log_data)
    
    if alerts:
        print(f"\n发现 {len(alerts)} 个报警\n")
        
        if args.level:
            # 过滤级别
            alerts = [a for a in alerts if a.get("level") == args.level]
        
        if args.output:
            # 保存到文件
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(alerts, f, ensure_ascii=False, indent=2)
            print(f"报警已保存至: {args.output}")
        else:
            # 打印到屏幕
            for alert in alerts:
                level = alert.get("level", "info").upper()
                company = alert.get("company", "N/A")
                message = alert.get("message", "")
                print(f"[{level}] {company}: {message}")
    else:
        print("未发现报警")

def cmd_daily(args):
    """生成日报"""
    generator = ReportGenerator()
    
    if args.print:
        # 打印摘要
        generator.print_daily_summary(args.date)
    else:
        # 生成JSON报告
        report = generator.generate_daily_report(args.date)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"日报已保存至: {args.output}")
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))

def cmd_weekly(args):
    """生成周报"""
    generator = ReportGenerator()
    report = generator.generate_weekly_report(args.end_date)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"周报已保存至: {args.output}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

def cmd_check(args):
    """快速检查单个公司"""
    import os
    if os.name == "nt":
        tmp_base = "D:/code/python/chu/clawler_data/data/tmp"
        ar_base = "D:/code/python/chu/clawler_data/data/ardata"
    else:
        tmp_base = "/Users/your_username/code/python/chu/clawler_data/data/tmp"
        ar_base = "/Users/your_username/code/python/chu/clawler_data/data/ardata"
    
    scanner = FullScanner(tmp_base=tmp_base, ar_base=ar_base)
    result = scanner.quick_check(args.company)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))

def cmd_missing(args):
    """查看未清洗文件"""
    import os
    if os.name == "nt":
        tmp_base = "D:/code/python/chu/clawler_data/data/tmp"
        ar_base = "D:/code/python/chu/clawler_data/data/ardata"
    else:
        tmp_base = "/Users/your_username/code/python/chu/clawler_data/data/tmp"
        ar_base = "/Users/your_username/code/python/chu/clawler_data/data/ardata"
    
    scanner = FullScanner(tmp_base=tmp_base, ar_base=ar_base)
    missing_list = scanner.get_missing_clean_list(args.company)
    
    if args.count:
        # 只显示数量
        if args.company:
            print(f"{args.company}: {len(missing_list)}")
        else:
            # 按公司统计
            company_count = {}
            for item in missing_list:
                company = item["company"]
                company_count[company] = company_count.get(company, 0) + 1
            
            for company, count in sorted(company_count.items()):
                print(f"{company}: {count}")
    else:
        # 显示详细列表
        print(json.dumps(missing_list, ensure_ascii=False, indent=2))

def main():
    parser = argparse.ArgumentParser(
        description='爬虫监控工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  查看今日报告:
    python monitor_cli.py report
  
  查看特定公司:
    python monitor_cli.py report -c com_00498
  
  全盘扫描:
    python monitor_cli.py scan --summary
  
  检查报警:
    python monitor_cli.py alert
  
  生成日报:
    python monitor_cli.py daily --print
  
  查看未清洗文件:
    python monitor_cli.py missing --count
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='子命令')
    
    # report 命令
    parser_report = subparsers.add_parser('report', help='查看报告')
    parser_report.add_argument('-d', '--date', help='日期（YYYYMMDD）')
    parser_report.add_argument('-c', '--company', help='公司代码')
    parser_report.add_argument('--detail', action='store_true', help='显示详细信息')
    
    # scan 命令
    parser_scan = subparsers.add_parser('scan', help='全盘扫描')
    parser_scan.add_argument('--days', type=int, default=7, 
                            help='多少天无数据算作长期无更新（默认7天）')
    parser_scan.add_argument('-o', '--output', help='输出文件路径')
    parser_scan.add_argument('--summary', action='store_true', help='只显示摘要')
    
    # alert 命令
    parser_alert = subparsers.add_parser('alert', help='检查报警')
    parser_alert.add_argument('--config', help='报警配置文件')
    parser_alert.add_argument('--level', choices=['error', 'warning', 'info'],
                             help='过滤报警级别')
    parser_alert.add_argument('-o', '--output', help='输出文件路径')
    
    # daily 命令
    parser_daily = subparsers.add_parser('daily', help='生成日报')
    parser_daily.add_argument('-d', '--date', help='日期（YYYYMMDD）')
    parser_daily.add_argument('-o', '--output', help='输出文件路径')
    parser_daily.add_argument('--print', action='store_true', help='打印摘要')
    
    # weekly 命令
    parser_weekly = subparsers.add_parser('weekly', help='生成周报')
    parser_weekly.add_argument('-e', '--end-date', help='结束日期（YYYYMMDD）')
    parser_weekly.add_argument('-o', '--output', help='输出文件路径')
    
    # check 命令
    parser_check = subparsers.add_parser('check', help='快速检查单个公司')
    parser_check.add_argument('company', help='公司代码（如com_00498）')
    
    # missing 命令
    parser_missing = subparsers.add_parser('missing', help='查看未清洗文件')
    parser_missing.add_argument('-c', '--company', help='公司代码')
    parser_missing.add_argument('--count', action='store_true', 
                               help='只显示数量统计')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 执行对应命令
    commands = {
        'report': cmd_report,
        'scan': cmd_scan,
        'alert': cmd_alert,
        'daily': cmd_daily,
        'weekly': cmd_weekly,
        'check': cmd_check,
        'missing': cmd_missing
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()