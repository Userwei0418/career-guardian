def crawl_page(page):
    try:
        # —— 3. 获取按钮（使用 locator 以提高稳定性） ——
        next_btn = page.locator('button.btn-next')

        if next_btn.count() == 0:
            print("未找到下一页按钮")
            return False

        # —— 4. 判断按钮是否 disabled ——
        disabled = next_btn.first.get_attribute("disabled")
        if disabled is not None:
            print("下一页按钮被禁用，停止翻页")
            return False

        # —— 5. 按钮可用，点击翻页 ——
        next_btn.first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)
        return True

    except Exception as e:
        print(f"翻页时出错: {e}")

    return False
