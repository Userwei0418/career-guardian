import os
import configparser
import json
import requests
from urllib.parse import urlparse
import time

# ---------------- 配置区 ----------------
# 你的本地数据目录
DATA_DIR = r'D:\code\python\chu\qzclawler\data'

# 目标系统
TARGET_SYSTEMS = ["zhiye.com", "hotjob.cn", "app.mokahr.com"]

# YouSearch API Key
YOU_API_KEY = "ydc-sk-2566a57ea92185ee-uvodZ5wp3Ba5RHubiTsXeI1GqHErxNIL-040a0520"
# ----------------------------------------

def get_existing_domains(source_dir):
    """从本地 ini 文件中提取所有已知的域名集合"""
    existing_domains = set()
    if not os.path.exists(source_dir):
        print(f"找不到目录: {source_dir}")
        return existing_domains

    for file_name in os.listdir(source_dir):
        if not file_name.endswith('.ini'):
            continue
            
        file_path = os.path.join(source_dir, file_name)
        config = configparser.ConfigParser(interpolation=None)
        
        try:
            config.read(file_path, encoding='utf-8')
        except:
            config.read(file_path, encoding='gbk')

        if 'Company' not in config.sections():
            continue

        for key in config['Company']:
            try:
                data = json.loads(config['Company'][key])[0]
                for url_field in ['json_domain', 'pre_open_url']:
                    url = data.get(url_field, "")
                    if url:
                        domain = urlparse(url).netloc
                        if domain:
                            existing_domains.add(domain)
            except:
                continue
                
    return existing_domains

def fetch_search_results_you(query):
    """
    调用 You.com V1 API，并自动翻页获取最大允许的结果数 (最多 100 条)
    """
    found_domains = set()
    url = "https://ydc-index.io/v1/search"
    headers = {
        "X-API-KEY": YOU_API_KEY,
        "Accept": "application/json"
    }
    proxies = {
        "http": "http://127.0.0.1:7897",
        "https": "http://127.0.0.1:7897"
    }
    
    # You.com 官方文档说明 offset 范围是 0 到 9
    for offset in range(10):
        params = {
            "query": query,
            "count": 10,
            "offset": offset
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, proxies=proxies, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                web_results = data.get('results', {}).get('web', [])
                
                # 如果这一页没有结果了，说明到底了，提前结束循环
                if not web_results:
                    break
                    
                for item in web_results:
                    link = item.get('url', '')
                    if link:
                        domain = urlparse(link).netloc
                        if domain:
                            found_domains.add(domain)
            else:
                print(f"   [!] 第 {offset+1} 页请求失败: {response.status_code}")
                break
                
        except Exception as e:
            print(f"   [!] 请求发生异常: {e}")
            break
            
        # 翻页间隙暂停 1.5 秒，防止触发 API 限流 (429 Too Many Requests)
        time.sleep(1.5)
        
    return found_domains

def main():
    print("1. 正在提取本地已知站点...")
    existing_domains = get_existing_domains(DATA_DIR)
    print(f"-> 本地共发现 {len(existing_domains)} 个已知站点。\n")

    new_discoveries = {}

    print("2. 开始通过 YouSearch API (v1) 查询新站点...")
    for system in TARGET_SYSTEMS:
        query = f"site:{system}"
        print(f"-> 正在搜索: {query}")
        
        searched_domains = fetch_search_results_you(query)
        
        # 求差集 (搜索到的 - 本地已知的)
        new_domains = searched_domains - existing_domains
        
        # 过滤掉非目标域名的垃圾结果（比如新闻报道页面）
        clean_new_domains = {d for d in new_domains if system in d.lower()}
        
        new_discoveries[system] = list(clean_new_domains)
        
        print(f"   找到相关域名 {len(searched_domains)} 个，其中新增有效站点 {len(clean_new_domains)} 个。")
        
        # 暂停一下，防止并发过快
        time.sleep(2)

    print("\n3. 拓展比对结果：")
    for system, domains in new_discoveries.items():
        print(f"\n【{system}】新发现站点:")
        if not domains:
            print("  (无新增站点)")
        for d in domains:
            print(f"  - {d}")

if __name__ == "__main__":
    main()