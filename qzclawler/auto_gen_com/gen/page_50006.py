def crawl_page(page):
    try:
        # 定位“下一页”按钮
        next_btn = page.locator('button.sd-Pagination-item-1cqBB.sd-Pagination-forward-3z80f')

        # 获取按钮的属性判断是否禁用
        classes = next_btn.get_attribute('class') or ''
        if 'disabled' in classes:
            print("下一页按钮已禁用，最后一页")
            return False

        # 点击下一页按钮
        next_btn.click()
        page.wait_for_timeout(1000)  # 等待页面刷新加载
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False