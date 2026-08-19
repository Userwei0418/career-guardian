def crawl_page(page):
    try:
        # 当前页（href="javascript:;"）
        current = page.query_selector('a[href="javascript:;"]')
        if not current:
            print("找不到当前页标签")
            return False

        # 直接用 CSS 找当前页后面的第一个页码
        next_tag = current.query_selector('xpath=following-sibling::a[contains(@href,"job_p")]')

        if not next_tag:
            print("已经是最后一页，无下一页链接")
            return False

        # 点击
        href = next_tag.get_attribute("href")
        print(f"准备翻页 → {href}")
        next_tag.click()

        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
