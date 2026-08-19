def extract_table_from_html(htmlcontext, tempfile):
    import json
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []

    container = soup.find('div', class_='listItems__fca8c0') or soup
    for a in container.find_all('a', attrs={'data-id': True}):
        try:
            title = (a.select_one('.positionItem-title-text') or a.select_one('.title__fca8c0')).get_text(strip=True)
        except Exception:
            title = ""

        sub = a.select_one('.positionItem-subTitle')
        hd_loc, hd_job_category = "", ""
        if sub:
            try:
                # 第一个 span 通常是地点
                first_span = sub.find('span')
                if first_span:
                    hd_loc = first_span.get_text(strip=True)
            except Exception:
                pass
            try:
                # 第一个 infoText 通常是职位类别
                cat_spans = sub.select('span.infoText__fca8c0')
                if cat_spans:
                    hd_job_category = cat_spans[0].get_text(strip=True)
            except Exception:
                pass

        link = a.get('href', "") or ""

        results.append({
            "announcement_name": title,
            "publish_time": "",
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category": hd_job_category
        })

    try:
        with open(tempfile, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return results
