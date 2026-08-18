import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    # 初始化存储结果的列表
    result_list = []
    # 使用BeautifulSoup解析HTML内容
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    # 定位所有包含招聘信息的dl标签（排除首条交流群信息）
    dl_list = soup.find_all('dl')

    for dl in dl_list:
        # 获取dt标签下的a标签（包含公告名称和链接）
        a_tag = dl.find('dt').find('a')
        if not a_tag:
            continue  # 若没有a标签则跳过当前dl

        # 提取公告名称（优先使用title属性，无则用a标签文本）
        announcement_name = a_tag.get('title', '').strip() or a_tag.get_text(strip=True)
        # 提取链接（处理相对路径，补充基础域名）
        link = a_tag.get('href', '').strip()
        base_url = 'http://www.yinhangzhaopin.com'
        if link and not link.startswith('http'):
            link = base_url + link

        # 提取发布时间（class为list的dd标签）
        publish_time_dd = dl.find('dd', class_='list')
        publish_time = publish_time_dd.get_text(strip=True) if publish_time_dd else ''
        #如果有时间，只要日期
        publish_time = publish_time.split(' ')[0]

        # 提取公司名称（从公告名称中截取，规则：去掉地域前缀和括号内容，取核心机构名）
        # 示例：[广东/安徽]2026年东莞银行秋季校园招聘公告 → 东莞银行
        import re
        # 移除地域前缀（如[广东/安徽]）
        name_clean = re.sub(r'^\[.*?\]', '', announcement_name)
        # 移除年份+“年”（如2026年）
        name_clean = re.sub(r'^\d{4}年', '', name_clean)
        # 提取核心公司名（匹配连续汉字，直到“招聘”“公告”等关键词前）
        company_match = re.search(r'([^\d|^招聘|^公告|^秋季|^春季|^社会|^校园]+)', name_clean)
        hd_company = company_match.group(1).strip() if company_match else ''

        # 将数据整理为字典并添加到结果列表
        result_dict = {
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link,
            'hd_company': hd_company
        }
        result_list.append(result_dict)

    # 将结果列表写入JSON文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result_list, f, ensure_ascii=False, indent=2)