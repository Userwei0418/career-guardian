import json
from bs4 import BeautifulSoup
import re

def extract_table_from_html(htmlcontext, tempfile):
    # 解析HTML内容
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    # 初始化结果列表
    result_list = []
    # 查找所有li标签（排除lm_line类的li）
    li_list = soup.find_all('li', class_=lambda cls: cls not in ['lm_line'])
    
    for li in li_list:
        # 查找a标签
        a_tag = li.find('a', class_='left')
        if not a_tag:
            continue
        
        # 提取公告名称（清理空白字符）
        announcement_name = a_tag.find('span').get_text(strip=True) if a_tag.find('span') else ''
        announcement_name = re.sub(r'\s+', '', announcement_name)  # 去除所有空白字符（包括换行）
        
        # 提取发布时间
        publish_time = li.find('span', class_='date').get_text(strip=True) if li.find('span', class_='date') else ''
        
        # 提取链接
        link = a_tag.get('href', '')
        
        # 提取公司/地区名称（从公告名称中提取市/区名称）
        # 匹配常见的市/区名称模式
        #company_match = re.search(r'([省市县区]+[市县区]|[广德市|黄山市|阜阳市|宿州市|合肥市|亳州市|芜湖市|淮北市|宣城市|马鞍山市|淮南市|安庆市|滁州市|铜陵市|六安市])', announcement_name)
        hd_company = ""#company_match.group(1) if company_match else ''
        
        # 构造字典
        item = {
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link,
            'hd_company': hd_company
        }
        result_list.append(item)
    
    # 将结果写入JSON文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result_list, f, ensure_ascii=False, indent=4)