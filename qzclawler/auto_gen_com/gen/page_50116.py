def crawl_page(page):
    try:
        # 当前激活页码
        current_page = page.locator("li.active a").inner_text().strip()

        next_btn = page.locator("li.next a")
        if not next_btn.is_visible():
            print("没有下一页按钮，结束")
            return False

        next_btn.click()

        # 等待分页刷新
        page.wait_for_timeout(800)

        # 点击后的激活页码
        new_page = page.locator("li.active a").inner_text().strip()

        if new_page == current_page:
            print(f"已到最后一页：{current_page}")
            return False

        print(f"翻页成功：{current_page} -> {new_page}")
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
