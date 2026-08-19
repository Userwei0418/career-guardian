
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []
    items = soup.find_all('div', class_='style__STListItem-editor__sc-10r1nhd-0 hjqbak')
    for item in items:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        # 公告名称(announcement_name)
        title_section = item.find('div', class_='style__STTitleSection-editor__sc-10r1nhd-2 bhsAAi')
        if title_section:
            job_title_div = title_section.find('div', class_='style__STJobTitle-editor__sc-10r1nhd-4 kMriaU')
            if job_title_div and job_title_div.span:
                announcement_name = job_title_div.span.get_text(strip=True)

        # 发布时间(publish_time)
        other_section = item.find('div', class_='style__STOtherSection-editor__sc-10r1nhd-10 emrrHN')
        if other_section:
            time_div = other_section.find('div', class_='style__STJobTime-editor__sc-10r1nhd-16 eKeZsF')
            if time_div:
                publish_time = time_div.get_text(strip=True).replace(' 发布', '')

        # 链接(link) - 页面中无明显链接，赋空字符串
        link = ""

        # 所属部门或机构(hd_dept) - 页面中无明显字段，赋空字符串
        hd_dept = ""

        # 工作地点(hd_loc)
        hd_loc = ""
        if other_section:
            label_section = other_section.find('div', class_='style__STLabelSection-editor__sc-10r1nhd-11 kDWFRA')
            if label_section:
                label_texts = label_section.find_all('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK')
                # 位置一般是第三个label_text
                if len(label_texts) >= 3:
                    hd_loc = label_texts[2].get_text(strip=True)

        # 招聘人数(hd_job_num) - 页面中无明显字段，赋空字符串
        hd_job_num = ""

        # 职位类别(hd_job_category) - 页面中无明显字段，赋空字符串
        hd_job_category = ""

        results.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
`