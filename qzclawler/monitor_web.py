"""
监控系统Web服务
提供可视化的监控面板
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
import os
import json
from pathlib import Path
import configparser

from monitor import CrawlerMonitor, FullScanner, AlertSystem, ReportGenerator

app = Flask(__name__)

# 配置路径（根据操作系统）
if os.name == "nt":  # Windows
    TMP_BASE = "D:/code/python/chu/clawler_data/data/tmp"
    AR_BASE = "D:/code/python/chu/clawler_data/data/ardata"
else:  # Mac/Linux
    TMP_BASE = "/Users/your_username/code/python/chu/clawler_data/data/tmp"
    AR_BASE = "/Users/your_username/code/python/chu/clawler_data/data/ardata"

# 初始化组件
monitor = CrawlerMonitor()
scanner = FullScanner(tmp_base=TMP_BASE, ar_base=AR_BASE)
alert_system = AlertSystem()
report_gen = ReportGenerator()

def load_company_config(company_key):
    """加载公司配置信息"""
    # 从company_key提取配置文件编号（如com_00501 -> 文件可能在52.ini中）
    # 这里需要遍历所有配置文件查找
    config = configparser.ConfigParser()
    
    # 遍历所有可能的配置文件
    for i in range(1, 100):
        config_file = f"data/setting_com_{i}.ini"
        if os.path.exists(config_file):
            config.read(config_file, encoding="utf-8")
            
            if config.has_option("Company", company_key):
                value = config.get("Company", company_key)
                company_info = json.loads(value)
                
                if isinstance(company_info, list) and len(company_info) > 0:
                    return company_info[0]  # 返回第一个配置
    
    return None

@app.route('/')
def index():
    """首页 - 总览"""
    return render_template('index.html')

@app.route('/companies')
def companies():
    """公司列表页面"""
    return render_template('companies.html')

@app.route('/detail/<company_key>')
def company_detail(company_key):
    """公司详情页面"""
    return render_template('detail.html', company_key=company_key)

# ==================== API接口 ====================

@app.route('/api/overview')
def api_overview():
    """总览数据API"""
    try:
        # 获取今日数据
        today_summary = monitor.get_today_summary()
        
        # 获取最近7天数据
        weekly_data = []
        for i in range(6, -1, -1):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            log_file = f"data/monitor/logs/{date}.json"
            
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    weekly_data.append({
                        'date': date,
                        'crawled': data['summary'].get('total_crawled', 0),
                        'cleaned': data['summary'].get('total_cleaned', 0),
                        'errors': data['summary']['errors'].get('crawl_errors', 0) + 
                                 data['summary']['errors'].get('clean_errors', 0)
                    })
            else:
                weekly_data.append({
                    'date': date,
                    'crawled': 0,
                    'cleaned': 0,
                    'errors': 0
                })
        
        # 检查报警
        alerts = alert_system.check_alerts(monitor.log_data)
        
        return jsonify({
            'success': True,
            'data': {
                'today': today_summary,
                'weekly': weekly_data,
                'alerts': alerts[:5]  # 最多显示5条报警
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/companies')
def api_companies():
    """公司列表API - 优化版"""
    try:
        # 获取分页参数
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        status_filter = request.args.get('status', 'all')  # all/active/inactive/empty
        search = request.args.get('search', '')
        
        # 执行快速扫描 - 只扫描必要的信息
        tmp_companies = scanner._get_company_dirs(TMP_BASE)
        ar_companies = scanner._get_company_dirs(AR_BASE)
        all_companies = set(tmp_companies.keys()) | set(ar_companies.keys())
        
        companies_data = []
        for company_key in sorted(all_companies):
            # 快速统计文件数量，不做详细扫描
            tmp_dir = tmp_companies.get(company_key)
            ar_dir = ar_companies.get(company_key)
            
            tmp_count = 0
            model_count = 0
            last_tmp_time = None
            last_model_time = None
            days_since_crawl = None
            days_since_clean = None
            
            # 统计tmp文件
            if tmp_dir and os.path.exists(tmp_dir):
                try:
                    files = [f for f in os.listdir(tmp_dir) 
                            if f.startswith("detail_") and f.endswith(".json")]
                    tmp_count = len(files)
                    
                    if files:
                        # 获取最新文件的时间
                        latest_file = max([os.path.join(tmp_dir, f) for f in files], 
                                        key=os.path.getmtime)
                        latest_time = os.path.getmtime(latest_file)
                        last_tmp_time = datetime.fromtimestamp(latest_time).strftime("%Y-%m-%d %H:%M:%S")
                        days_since_crawl = (datetime.now() - datetime.fromtimestamp(latest_time)).days
                except Exception as e:
                    print(f"读取tmp目录失败 {tmp_dir}: {e}")
            
            # 统计model文件
            if ar_dir and os.path.exists(ar_dir):
                try:
                    files = [f for f in os.listdir(ar_dir) 
                            if f.endswith(".model.json")]
                    model_count = len(files)
                    
                    if files:
                        # 获取最新文件的时间
                        latest_file = max([os.path.join(ar_dir, f) for f in files], 
                                        key=os.path.getmtime)
                        latest_time = os.path.getmtime(latest_file)
                        last_model_time = datetime.fromtimestamp(latest_time).strftime("%Y-%m-%d %H:%M:%S")
                        days_since_clean = (datetime.now() - datetime.fromtimestamp(latest_time)).days
                except Exception as e:
                    print(f"读取ar目录失败 {ar_dir}: {e}")
            
            # 判断状态
            if tmp_count == 0 and model_count == 0:
                status = 'empty'
            elif days_since_crawl is not None and days_since_crawl > 7:
                status = 'inactive'
            else:
                status = 'active'
            
            # 获取公司名称（从今日监控数据）
            today_data = monitor.log_data.get('companies', {}).get(company_key, {})
            company_name = today_data.get('company_name', '')
            
            company_info = {
                'key': company_key,
                'name': company_name,
                'status': status,
                'tmp_count': tmp_count,
                'model_count': model_count,
                'missing_clean': tmp_count - model_count if tmp_count > model_count else 0,
                'last_crawl_time': last_tmp_time,
                'last_clean_time': last_model_time,
                'days_since_crawl': days_since_crawl,
                'days_since_clean': days_since_clean
            }
            
            # 过滤
            if status_filter != 'all' and status != status_filter:
                continue
            if search and search.lower() not in company_key.lower() and search.lower() not in company_name.lower():
                continue
            
            companies_data.append(company_info)
        
        # 分页
        total = len(companies_data)
        start = (page - 1) * per_page
        end = start + per_page
        
        return jsonify({
            'success': True,
            'data': {
                'companies': companies_data[start:end],
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': (total + per_page - 1) // per_page
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/company/<company_key>')
def api_company_detail(company_key):
    """公司详情API"""
    try:
        # 获取扫描数据
        tmp_dir = os.path.join(TMP_BASE, company_key)
        ar_dir = os.path.join(AR_BASE, company_key)
        scan_data = scanner._scan_company(company_key, tmp_dir, ar_dir, 7)
        
        # 获取今日监控数据
        today_data = monitor.get_company_status(company_key)
        
        # 加载配置信息（只在详情页加载）
        config_info = load_company_config(company_key)
        
        # 获取历史数据（最近7天）
        history = []
        for i in range(6, -1, -1):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            log_file = f"data/monitor/logs/{date}.json"
            
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    company_data = data.get('companies', {}).get(company_key)
                    
                    if company_data:
                        history.append({
                            'date': date,
                            'crawled': company_data['crawl']['success'],
                            'cleaned': company_data['clean']['success'],
                            'failed': company_data['crawl']['failed'] + company_data['clean']['failed']
                        })
        
        return jsonify({
            'success': True,
            'data': {
                'scan': scan_data,
                'today': today_data,
                'history': history,
                'config': {
                    'name': config_info.get('com_name', '') if config_info else '',
                    'website': config_info.get('pre_open_url', '') if config_info else '',
                    'logo': config_info.get('com_logo', '') if config_info else '',
                    'tmp_path': tmp_dir,
                    'ar_path': ar_dir
                }
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/missing_clean')
def api_missing_clean():
    """未清洗文件列表API"""
    try:
        company_key = request.args.get('company')
        missing_list = scanner.get_missing_clean_list(company_key)
        
        return jsonify({
            'success': True,
            'data': missing_list
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/alerts')
def api_alerts():
    """报警列表API"""
    try:
        alerts = alert_system.check_alerts(monitor.log_data)
        
        return jsonify({
            'success': True,
            'data': alerts
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/scan')
def api_full_scan():
    """触发全盘扫描API"""
    try:
        report = scanner.scan_all(save_report=True)
        
        return jsonify({
            'success': True,
            'data': report
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

if __name__ == '__main__':
    # 创建必要的目录
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    # 启动服务
    print("=" * 60)
    print("爬虫监控面板启动成功！")
    print("访问地址: http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)