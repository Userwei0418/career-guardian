def crawl_page(page):
    try:
        # 1. 精准定位下一页：根据 title 和 class 适配你的 HTML
        next_btn = page.locator('a.next.fanye_xyy[title="下一页"]')

        # 2. 是否存在按钮
        if next_btn.count() == 0:
            print("未找到下一页按钮，可能已经是最后一页")
            return False

        # 3. 检查 href 是否为空或 JS 不可点（可能是最后一页）
        href = next_btn.get_attribute("href") or ""
        if href.strip() in ["", "#", "javascript:void(0)"]:
            print("下一页按钮不可点击，已到最后一页")
            return False

        # 4. 点击前记录当前 URL，用于判断是否真正翻页
        old_url = page.url

        next_btn.click()
        page.wait_for_timeout(800)

        # 5. 判断 URL 是否变化，确保真正翻页成功
        if page.url == old_url:
            print("点击后 URL 未变化，说明已经是最后一页")
            return False

        print("成功翻到下一页:", page.url)
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
