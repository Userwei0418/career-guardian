def crawl_page(page):
    try:
        # 找到当前页
        current = page.query_selector(".fenyeon")
        if not current:
            print("找不到当前页标签")
            return False

        # 找下一个兄弟节点
        next_btn = current.evaluate_handle("el => el.nextElementSibling")
        if not next_btn:
            print("已经是最后一页")
            return False

        print("准备翻页 → 下一页")
        next_btn.click()
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
