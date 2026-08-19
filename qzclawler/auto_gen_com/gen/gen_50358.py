import json
from bs4 import BeautifulSoup

def safe_get_text(parent, tag, cls):
    """安全提取文本：节点不存在返回空"""
    try:
        node = parent.find(tag, class_=cls)
        return node.get_text(strip=True) if node else ""
    except:
        return ""

def safe_get_attr(parent, tag, cls, attr):
    """安全提取属性：节点不存在返回空"""
    try:
        node = parent.find(tag, class_=cls)
        return node.get(attr, "") if node and node.has_attr(attr) else ""
    except:
        return ""

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.find_all('div', class_='announcement-item'):
        announcement = {
            "announcement_name": safe_get_text(item, 'h2', 'announcement-title'),
            "publish_time": safe_get_text(item, 'span', 'publish-time'),
            "link": safe_get_attr(item, 'a', 'announcement-link', 'href'),
            "hd_dept": safe_get_text(item, 'span', 'hd-dept'),
            "hd_loc": safe_get_text(item, 'span', 'hd-loc'),
            "hd_job_num": safe_get_text(item, 'span', 'hd-job-num'),
            "hd_job_category": safe_get_text(item, 'span', 'hd-job-category'),
        }

        announcements.append(announcement)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)
