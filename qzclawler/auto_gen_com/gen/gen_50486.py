
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    for li in soup.select('.position_list-list-demo'):
        announcement_name = li.select_one('.position_list-list-demo-title').get_text(strip=True) if li.select_one('.position_list-list-demo-title') else ""
        hd_dept = li.select_one('.position_list-first-row span:nth-of-type(1)').get_text(strip=True) if li.select_one('.position_list-first-row span:nth-of-type(1)') else ""
        hd_job_num = li.select_one('.position_list-first-row span:nth-of-type(2)').get_text(strip=True).replace("招聘", "").replace("人", "").strip() if li.select_one('.position_list-first-row span:nth-of-type(2)') else ""
        hd_loc = li.select_one('.position_list-first-row span:nth-of-type(3)').get_text(strip=True) if li.select_one('.position_list-first-row span:nth-of-type(3)') else ""
        publish_time = li.select_one('.position_list-list-demo-info .cell i').get_text(strip=True) if li.select_one('.position_list-list-demo-info .cell i') else ""
        id = li.find('div', onclick=True)['onclick'].split('(')[1].split(',')[0] if li.find('div', onclick=True) else ""
        link = f"https://sc.hotjob.cn/wt/Essence/mobweb/v8/position/detail?safe=Y&canBack=true&recruitType=12&postIdsAry={id}&postCanApply=0&entityPage.currentPage=1&openid=&brandCode=1&chooseSiteId="
        if "实习" in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": "" , # Assuming this field is not available in the provided HTML
            "hd_hopeworktype":hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
