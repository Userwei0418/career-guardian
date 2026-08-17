import json
from bs4 import BeautifulSoup


def safe_get_text(element, default=''):
    """安全获取文本，如果 element 为 None，则返回默认值"""
    return element.get_text(strip=True) if element else default


def safe_get_list_text(elements, index, default=''):
    """安全从列表中取文本"""
    try:
        return elements[index].get_text(strip=True)
    except (IndexError, AttributeError):
        return default


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_items = soup.find_all('div', class_='style__STListItem-editor__sc-10r1nhd-0')

    for item in job_items:
        title = safe_get_text(item.find('div', class_='style__STJobTitle-editor__sc-10r1nhd-4'))
        publish_time = safe_get_text(item.find('div', class_='style__STJobTime-editor__sc-10r1nhd-16')).replace(' 发布',
                                                                                                                '')
        link = ''  # HTML 中没有提供链接就保持为空
        hd_dept = ''  # HTML 中没有提供部门就保持为空

        labels = item.find_all('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK')
        hd_loc = safe_get_list_text(labels, 2)
        hd_job_num = safe_get_list_text(labels, 3).replace('在招', '').replace('人', '')
        hd_job_category = safe_get_list_text(labels, 5)

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
