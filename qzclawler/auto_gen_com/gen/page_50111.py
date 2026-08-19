def crawl_page(page):
    try:
        next_btn = page.query_selector('a[aria-label="Next"]')
        if not next_btn:
            print("没有找到下一页")
            return False

        # 判断是否被禁用（Bootstrap 常见写法）
        parent_li = next_btn.evaluate_handle("n => n.parentElement")
        cls = parent_li.get_attribute("class") or ""
        if "disabled" in cls:
            print("已经是最后一页")
            return False

        print("准备翻页 → 下一页")
        next_btn.click()
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
