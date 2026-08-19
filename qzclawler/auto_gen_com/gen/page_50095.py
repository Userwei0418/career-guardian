def crawl_page(page):
    try:
        # 尝试定位下一页按钮（用 class）
        next_btn = page.query_selector("button.btn-next")
        if not next_btn:
            print("未找到下一页按钮")
            return False

        # 判断按钮是否禁用
        class_attr = next_btn.get_attribute("class") or ""
        if "disabled" in class_attr or "not-active" in class_attr:
            print("已经是最后一页")
            return False

        # 点击翻页
        next_btn.click()
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页出现异常: {e}")
        return False
