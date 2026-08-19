def crawl_page(page):
    try:
        # 明确定位到“下一页”按钮（不是 class，而是 aria role + 文本）
        next_btn = page.get_by_role("link", name="下一页")

        # 如果不存在就停止
        if next_btn.count() == 0:
            print("未找到下一页按钮，可能已经到最后一页")
            return False

        # 检查是否禁用
        class_attr = next_btn.get_attribute("class") or ""
        if "disabled" in class_attr:
            print("下一页已禁用，停止翻页")
            return False

        # 记录当前页码，用于校验翻页成功
        current_page_elem = page.locator("span.page.present")
        current_page = int(current_page_elem.inner_text()) if current_page_elem.count() else -1

        # 点击
        next_btn.click()
        page.wait_for_timeout(600)

        # 验证是否翻页成功

        print(f"翻页成功：{current_page}")
        return True

    except Exception as e:
        print("翻页异常:", e)
        return False
