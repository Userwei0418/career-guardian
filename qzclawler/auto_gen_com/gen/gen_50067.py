import json
import re
from bs4 import BeautifulSoup

def remove_duplicates(text):
    """
    移除文本中的重复部分
    对于连续重复的字符串，只保留一个副本
    """
    if not text:
        return text
    
    # 使用正则表达式查找连续重复的部分
    # 匹配模式: 任意字符序列后跟同样的序列
    pattern = r'^(.*?)\1+$'
    match = re.match(pattern, text)
    if match:
        # 如果找到重复部分，只返回一个副本
        return match.group(1)
    return text

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='container-aOp138AX_X'):
        try:
            announcement_name_elem = job.find('span', class_='title-u2qk9xX9Ie')
            announcement_name = announcement_name_elem.text.strip() if announcement_name_elem else ""
            
            link_elem = job.find('a')
            link = link_elem['href'] if link_elem and link_elem.has_attr('href') else ""

            info_blocks = job.find_all('div', class_='sd-foundation-body-secondary-1Z7H-')
            hd_dept = info_blocks[0].text.strip() if len(info_blocks) > 0 else ""
            hd_job_category = info_blocks[2].text.strip() if len(info_blocks) > 2 else ""
            hd_loc = info_blocks[3].text.strip() if len(info_blocks) > 3 else ""

            # 去除重复内容
            hd_dept = remove_duplicates(hd_dept)
            hd_job_category = remove_duplicates(hd_job_category)
            hd_loc = remove_duplicates(hd_loc)

            hd_job_num = ""  # Placeholder
            publish_time = ""  # Placeholder

            if not announcement_name or not link:
                raise ValueError("缺少必要字段 announcement_name 或 link")

            job_info = {
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            }
            job_list.append(job_info)
        except Exception as e:
            print(f"⚠️ 解析某个职位时出错: {e}")
            continue

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)