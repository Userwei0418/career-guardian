def crawl_page(page):
    try:
        # 用文字内容定位“下一页”
        next_btn = page.locator('a.page_btn', has_text="下一页").first

        if not next_btn or not next_btn.is_visible():
            print("没有找到下一页按钮")
            return False

        # 判断按钮是否不可点击（比如被隐藏或禁用）
        classes = next_btn.get_attribute('class') or ''
        if 'disabled' in classes:  # 如果有禁用标记
            print("下一页按钮已禁用，最后一页")
            return False

        # 点击按钮并等待页面刷新
        next_btn.click()
        page.wait_for_load_state("networkidle")  # 等待网络空闲，确保新页面加载完成
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
