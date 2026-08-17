
import json
from bs4 import BeautifulSoup

def extract_table_from_html(html_content, tempfile):
    soup = BeautifulSoup(html_content, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X')

    for card in job_cards:
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').text.strip()
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').text.replace('发布于 ', '').strip()
        link = card.find('a')['href']
        hd_dept = ""  # Assuming the department is not provided in the HTML
        job_type = ""
        location = ""
        job_category = ""
        job_labels = card.find_all('div', class_='w-full-mRUtzMQLHs')
        # print(job_labels)
        if len(job_labels) >= 1:
            # print("这是调试")
            label_items = job_labels[0].find_all('div', class_='sd-Ellipsis-hiddenContent-1Skwh')
            if len(label_items) >= 3:
                job_type = label_items[0].get_text(strip=True).replace('招聘','') # 第一个标签作为工作类型
                job_category = label_items[1].get_text(strip=True)  # 第二个标签作为职位类别
                location = label_items[2].get_text(strip=True)  # 第三个标签作为地区
        hd_job_num = ""  # Assuming the job number is not provided in the HTML
        hd_job_category = ""  # Assuming the job category is not provided in the HTML

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": location,
            "hd_job_num": hd_job_num,
            "hd_job_category": job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
