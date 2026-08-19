import json
import re
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    """
    从HTML内容中提取公告信息并写入JSON文件
    
    参数:
    htmlcontext (str): HTML内容字符串
    tempfile (str): 输出的JSON文件路径
    """
    # 初始化结果列表
    result_list = []
    
    # 使用BeautifulSoup解析HTML
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    
    # 查找所有的cms-content-item列表项
    item_list = soup.find_all('li', class_='cms-content-item')
    
    # 遍历每个列表项提取信息
    for item in item_list:
        # 提取公告名称
        name_elem = item.find('div', class_='cms-content-item-left')
        announcement_name = name_elem.get_text(strip=True) if name_elem else ''
        
        # 提取发布时间
        time_elem = item.find('div', class_='cms-content-item-right')
        publish_time = time_elem.get_text(strip=True) if time_elem else ''
        
        # 提取onclick属性中的链接ID（构造链接）
        onclick_attr = item.get('onclick', '')
        link_id = ''
        # 使用正则表达式匹配ID
        id_match = re.search(r'goDetailPolicy\(\'(\d+)\'', onclick_attr)
        if id_match:
            link_id = id_match.group(1)
        # 构造链接（根据实际情况调整链接格式）
        link = f'https://rst.hebei.gov.cn/ggzp/pages/website/job/cmsDetail.html?id={link_id}' if link_id else ''
        
        # 提取公司/机构名称（从公告名称中提取）
        # 简单处理：取公告名称开头到第一个“202”/“关于”等关键词前的部分
        hd_company = ''        
        # 构造字典
        item_dict = {
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link,
            'hd_company': hd_company
        }
        
        result_list.append(item_dict)
    
    # 将结果写入JSON文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result_list, f, ensure_ascii=False, indent=4)