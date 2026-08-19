import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def extract_table_from_html(htmlcontext, tempfile):
    # 基础 URL，用于拼接完整链接
    base_url = "https://app.mokahr.com/campus-recruitment/nestlezgc/91899"

    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    containers = soup.find_all('div', class_='container-aOp138AX_X')
    for container in containers:
        job_data = {}

        # 拼接完整的链接
        link_tag = container.find('a', class_='link-txmgVOCVz9')
        if link_tag and link_tag.has_attr('href'):
            job_data['link'] = urljoin(base_url, link_tag['href'].strip())
        else:
            job_data['link'] = ""

        # 其他字段解析保持原逻辑
        title_tag = container.find('span', class_='title-u2qk9xX9Ie')
        job_data['announcement_name'] = title_tag.text.strip() if title_tag else ""

        publish_tag = container.find('span', class_='published-at-PQ5IBWmbJV')
        job_data['publish_time'] = publish_tag.text.strip() if publish_tag else ""

        hd_dept_tag = container.find('div', class_='sd-Ellipsis-hiddenContent-1Skwh')
        job_data['hd_dept'] = hd_dept_tag.text.strip() if hd_dept_tag else ""

        # html中没有明确提供这些信息，暂时留空
        job_data['hd_loc'] = ""
        job_data['hd_job_num'] = ""
        job_data['hd_job_category'] = ""
        if "实习" in job_data['announcement_name']:
            job_data['hd_hopeworktype'] = "实习"
        else:
            job_data['hd_hopeworktype'] = ""
        job_list.append(job_data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=2)
