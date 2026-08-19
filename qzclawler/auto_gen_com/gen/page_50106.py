def crawl_page(page):
    try:
        # 找到包含下一页的 a 标签，特点是 href 中带 PageIndex
        next_a = page.query_selector('a[href*="PageIndex="]')
        if not next_a:
            print("未找到下一页按钮，可能已经是最后一页")
            return False

        href = next_a.get_attribute("href")
        if not href or "PageIndex=" not in href:
            print("下一页不可点击")
            return False

        print("准备翻页 →", href)

        # 点击翻页
        next_a.click()
        page.wait_for_load_state("networkidle")

        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
