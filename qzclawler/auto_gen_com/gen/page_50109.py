def crawl_page(page):
    try:
        # 当前页：class="on"
        current = page.query_selector(".list-page_class a.on")
        if not current:
            print("找不到当前页标签")
            return False

        # 检查右侧下一页按钮
        next_btn = page.query_selector(".list-page_class a.next")

        if not next_btn:
            print("没有找到下一页按钮")
            return False

        # 判断是否是禁用的下一页（最后一页）
        classes = next_btn.get_attribute("class") or ""
        disabled = next_btn.get_attribute("disabled")

        if "disabled" in classes or disabled is not None:
            print("已经是最后一页")
            return False

        print("准备翻页 → 下一页")
        next_btn.click()
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
