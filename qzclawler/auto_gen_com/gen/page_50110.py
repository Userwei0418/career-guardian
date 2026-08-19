def crawl_page(page):
    try:
        # 当前页：class="hover"
        current = page.query_selector(".news_page a.hover")
        if not current:
            print("找不到当前页")
            return False

        # 当前页后面的兄弟节点 = 下一页
        next_page = current.evaluate_handle(
            "node => node.nextElementSibling"
        )

        if not next_page:
            print("已经是最后一页")
            return False

        print("准备翻页 → 下一页")
        next_page.click()
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
