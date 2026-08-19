def crawl_page(page):
    try:
        ul = page.query_selector('#page ul') or page.query_selector('ul')
        if not ul:
            print("未找到分页 ul")
            return False

        lis = ul.query_selector_all('li')

        cur_index = -1
        cur_page = None
        for i, li in enumerate(lis):
            if 'xl-active' in (li.get_attribute('class') or ''):
                cur_index = i
                cur_page = li.inner_text().strip()
                break

        if cur_index == -1:
            print("未找到当前页")
            return False

        next_li = None
        for li in lis[cur_index + 1:]:
            if li.inner_text().strip().isdigit():
                next_li = li
                break

        if not next_li:
            print(f"已到最后一页（当前页 {cur_page}）")
            return False

        print(f"当前页 {cur_page} → 翻页")

        next_li.click()
        page.wait_for_timeout(500)  # 足够稳定

        return True

    except Exception as e:
        print(f"翻页失败: {e}")
        return False
