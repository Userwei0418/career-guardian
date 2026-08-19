import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    """
    从HTML文本中提取招聘信息，转换为指定格式的列表并写入JSON文件
    
    参数:
        htmlcontext (str): 包含招聘信息的HTML文本
        tempfile (str): 要写入的JSON文件路径
    """
    # 初始化结果列表
    result_list = []
    
    # 使用BeautifulSoup解析HTML
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    
    # 查找所有包含招聘信息的news类div元素
    news_items = soup.find_all('div', class_='news')
    
    for item in news_items:
        # 提取公告名称（new_title类的文本）
        announcement_name_elem = item.find('div', class_='new_title')
        announcement_name = announcement_name_elem.get_text(strip=True) if announcement_name_elem else ''
        
        # 提取发布时间（new_date类的文本）
        publish_time_elem = item.find('div', class_='new_date')
        publish_time = publish_time_elem.get_text(strip=True) if publish_time_elem else ''
        
        # 提取公司名称（从公告名称中截取，去掉末尾的"招聘信息"）
        hd_company = ''#announcement_name.replace('招聘信息', '').strip() if announcement_name else ''
        
        # 链接字段：HTML中未提供具体链接，暂设为空字符串
        link = ''
        
        # 构造单条数据字典
        item_dict = {
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link,
            'hd_company': hd_company
        }
        
        result_list.append(item_dict)
    
    # 将结果列表写入JSON文件
    try:
        with open(tempfile, 'w', encoding='utf-8') as f:
            # ensure_ascii=False保证中文正常显示，indent=4让JSON格式更易读
            json.dump(result_list, f, ensure_ascii=False, indent=4)
    except Exception as e:
        raise Exception(f"写入JSON文件失败: {str(e)}")