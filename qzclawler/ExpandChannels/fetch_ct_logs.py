import requests
import time

TARGETS = ["zhiye.com", "hotjob.cn"]

def get_subdomains_from_crt(domain):
    """
    通过 crt.sh (证书透明度日志) 获取所有的子域名
    """
    print(f"\n正在查询 {domain} 的全球 SSL 证书记录 (这可能需要十几秒，请耐心等待)...")
    url = f"https://crt.sh/?q=%.{domain}&output=json"
    
    # 同样加上你本地的代理，防止连不上国外的 crt.sh 数据库
    proxies = {
        "http": "http://127.0.0.1:7897",
        "https": "http://127.0.0.1:7897"
    }
    
    try:
        response = requests.get(url, proxies=proxies, timeout=60)
        if response.status_code == 200:
            data = response.json()
            subdomains = set()
            for item in data:
                name_value = item.get('name_value', '')
                # 证书里可能有换行符包含多个域名
                for name in name_value.split('\n'):
                    # 过滤掉通配符证书（*.zhiye.com）并确保是该域名的子域
                    name = name.lower().strip()
                    if name.endswith(domain) and '*' not in name and name != domain:
                        subdomains.add(name)
            return subdomains
        else:
            print(f"查询失败，状态码: {response.status_code}")
            return set()
    except Exception as e:
        print(f"请求发生异常: {e}")
        return set()

def main():
    for domain in TARGETS:
        domains_found = get_subdomains_from_crt(domain)
        print(f"==> 轰炸完成！从 {domain} 的证书库中提取到了 {len(domains_found)} 个独立客户站点！")
        
        # 随便打印前 20 个给你看看效果
        print("预览前 20 个:")
        for d in list(domains_found)[:20]:
            print(f"  - {d}")
        
        # 将结果保存到 txt 文件中
        output_file = f"{domain.split('.')[0]}_all_clients.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            for d in sorted(list(domains_found)):
                f.write(f"{d}\n")
        print(f"==> 全部数据已导出至 {output_file}\n")
        
        time.sleep(2) # 查下一个前缓一缓

if __name__ == "__main__":
    main()