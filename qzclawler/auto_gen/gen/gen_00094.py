import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    """
    从HTML内容中提取招聘信息表格，转换为列表并写入JSON文件
    
    参数:
    htmlcontext: str - 包含招聘信息的HTML文本内容
    tempfile: str - 输出JSON文件的路径
    """
    # 初始化存储结果的列表
    result_list = []
    
    # 使用BeautifulSoup解析HTML
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    
    # 找到所有的<li>标签（包含招聘信息的列表项）
    li_items = soup.select('ul li')
    
    # 遍历每个列表项，提取所需信息
    for li in li_items:
        # 提取链接和公告名称
        a_tag = li.select_one('h3 a')
        if a_tag:
            link = f"https://www.pfc.edu.cn{a_tag.get('href', '')}"  # 链接
            announcement_name = a_tag.get_text(strip=True)  # 公告名称
        else:
            continue
        
        # 提取发布时间
        span_tag = li.select_one('span')
        publish_time = span_tag.get_text(strip=True) if span_tag else ''
        
        # 提取公司名称（从公告名称中提取，规则：取"招聘启事"前的内容，无则为空）
        hd_company = ''
        
        # 构造单条数据字典
        item = {
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link,
            'hd_company': hd_company
        }
        
        # 添加到结果列表
        result_list.append(item)
    
    # 将结果列表写入JSON文件
    try:
        with open(tempfile, 'w', encoding='utf-8') as f:
            json.dump(result_list, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"写入文件时出错: {e}")
        raise