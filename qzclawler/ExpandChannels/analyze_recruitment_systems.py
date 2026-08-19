import os
import configparser
import json
import pandas as pd

def analyze_ini_files():
    # 路径配置
    source_dir = r'D:\code\python\chu\qzclawler\data'
    output_file = r'D:\code\python\chu\qzclawler\recruitment_systems_stats.xlsx'
    
    # 目标域名
    targets = {
        "zhiye.com": [],
        "hotjob.cn": [],
        "app.mokahr.com": []
    }

    # 获取目录下所有 ini 文件
    if not os.path.exists(source_dir):
        print(f"错误: 找不到目录 {source_dir}")
        return

    ini_files = [f for f in os.listdir(source_dir) if f.endswith('.ini')]
    print(f"开始扫描目录，共发现 {len(ini_files)} 个配置文件...")

    for file_name in ini_files:
        file_path = os.path.join(source_dir, file_name)
        
        # 使用 configparser 读取 ini
        # interpolation=None 防止处理带有 % 的 URL 时报错
        config = configparser.ConfigParser(interpolation=None)
        
        try:
            # 尝试以 utf-8 读取，如果失败尝试 gbk
            try:
                config.read(file_path, encoding='utf-8')
            except:
                config.read(file_path, encoding='gbk')

            if 'Company' not in config.sections():
                continue

            # 遍历 [Company] 节下的所有公司
            for key in config['Company']:
                raw_json = config['Company'][key]
                
                try:
                    # 解析 JSON 数据
                    company_data_list = json.loads(raw_json)
                    if not company_data_list:
                        continue
                    
                    company_info = company_data_list[0]
                    com_name = company_info.get("com_name", "未知公司")
                    
                    # 提取所有相关的 URL 文本用于检测
                    urls_dict = company_info.get("urls", {})
                    url_text_blob = str(urls_dict) + \
                                    str(company_info.get("pre_open_url", "")) + \
                                    str(company_info.get("json_domain", ""))
                    
                    # 提取基础信息用于表格
                    row = {
                        "公司ID": key,
                        "公司名称": com_name,
                        "招聘网站名称": company_info.get("com_webname", ""),
                        "主要地址": company_info.get("pre_open_url", ""),
                        "业务域": company_info.get("json_domain", ""),
                        "所在文件": file_name
                    }

                    # 判断属于哪个系统
                    for domain in targets.keys():
                        if domain in url_text_blob.lower():
                            targets[domain].append(row)
                            
                except json.JSONDecodeError:
                    print(f"解析失败: 文件 {file_name} 中的键 {key} JSON 格式有误")
                    
        except Exception as e:
            print(f"处理文件 {file_name} 时出错: {e}")

    # 导出到 Excel
    print("正在生成 Excel 报告...")
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        for domain, data in targets.items():
            # 处理 Sheet 名称（Excel 不允许特殊字符或过长名称，这里直接用域名简写）
            sheet_name = domain.replace("app.", "").split('.')[0]
            df = pd.DataFrame(data)
            
            if not df.empty:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"系统 [{domain}]: 统计到 {len(df)} 家公司")
            else:
                # 如果为空，创建一个空表
                pd.DataFrame(columns=["提示"]).to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"系统 [{domain}]: 未匹配到公司")

    print(f"\n处理完成！结果已保存至: {output_file}")

if __name__ == "__main__":
    analyze_ini_files()