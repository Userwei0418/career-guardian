import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    def get_text_safe(tag):
        """安全获取文本，如果 tag 为 None 则返回空字符串"""
        return tag.text.strip() if tag else ""

    def get_all_div_text_safe(divs, index):
        """安全获取指定索引的 div 文本，如果不存在则返回空字符串"""
        try:
            return divs[index].text.strip()
        except IndexError:
            return ""

    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = get_text_safe(job.find('span', class_='title-u2qk9xX9Ie'))
        link_tag = job.find('a')
        link = link_tag['href'] if link_tag and link_tag.has_attr('href') else ""

        publish_time = get_text_safe(job.find('span', class_='operation-K6n6FDy7Dx'))  # 如果没有就为空
        hd_dept = ""  # 可以保留默认值，也可改为空
        divs = job.find_all('div', class_='sd-foundation-body-secondary-1Z7H-')
        hd_loc = get_all_div_text_safe(divs, 2)
        hd_job_num = ""  # 没有就空
        hd_job_category = get_all_div_text_safe(divs, 1)

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

    # 保存为 JSON
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
