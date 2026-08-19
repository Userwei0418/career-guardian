import requests
import time
import random
import os

def fetch_proxies_infinitely(api_url, params, output_file="proxies.txt"):
    """
    持续无限期请求代理接口，随机休眠10-15s，直到手动按 Ctrl+C 停止。
    发现新代理实时追加到 txt 文件中。
    """
    proxies = set()
    
    # 🌟 亮点：启动前先读取本地已有的文件，确保多次启动脚本也不会有重复 IP
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                # strip() 用于去除换行符和空格
                proxies.add(line.strip())
        print(f"📁 已从本地加载 {len(proxies)} 个历史代理，继续去重抓取...")

    print(f"🚀 开始持续获取代理 (按 Ctrl+C 随时停止)...")
    print(f"💾 新代理将实时追加保存到: {output_file}\n")

    try:
        # 无限循环，直到手动停止
        while True:
            try:
                response = requests.post(api_url, params=params, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == 200:
                        proxy = data.get("data", {}).get("proxy")
                        
                        if proxy:
                            if proxy not in proxies:
                                proxies.add(proxy)
                                # 🌟 重点：发现新IP，立刻用 "a" (追加) 模式写入文件
                                with open(output_file, "a", encoding="utf-8") as f:
                                    f.write(proxy + "\n")
                                print(f"✅ [新增] 成功获取并保存: {proxy} (当前池子总数: {len(proxies)})")
                            else:
                                print(f"⚠️ [重复] 代理已存在，丢弃: {proxy}")
                    else:
                        print(f"❌ [业务错误] 接口返回异常状态: {data}")
                else:
                    print(f"❌ [HTTP错误] 状态码: {response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ [网络异常] 请求失败: {e}")

            # 🎲 随机休眠 10 到 15 秒
            sleep_time = random.randint(10, 15)
            print(f"⏳ 休息 {sleep_time} 秒后继续...\n")
            time.sleep(sleep_time)

    # 🛑 捕获 Ctrl+C 手动中断信号
    except KeyboardInterrupt:
        print(f"\n🛑 检测到手动停止 (Ctrl+C)！")
        print(f"🎉 任务安全结束。当前代理池总计有效 IP 数量: {len(proxies)} 个。")

if __name__ == "__main__":
    # 你的接口配置
    API_URL = 'http://121.36.63.42:6868/getproxy'
    PARAMS = {"channel": 'yupao', "env": 1}
    
    # 开始执行
    fetch_proxies_infinitely(
        api_url=API_URL, 
        params=PARAMS, 
        output_file="proxy_pool.txt"
    )