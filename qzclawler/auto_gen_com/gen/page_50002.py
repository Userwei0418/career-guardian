def crawl_page(page):
    try:
        # 定位“下一页”按钮
        next_btn = page.locator('li[title="下一页"]')

        if next_btn.count() == 0:
            print("没有找到下一页按钮")
            return False

        # 判断是否禁用，看类名中是否含有 'ant-pagination-disabled'
        classes = next_btn.get_attribute('class') or ''
        aria_disabled = next_btn.get_attribute('aria-disabled') or 'false'

        if 'ant-pagination-disabled' in classes or aria_disabled == 'true':
            print("下一页按钮已禁用，最后一页")
            return False

        # 按钮可用，点击翻页
        next_btn.click()
        page.wait_for_timeout(1000)  # 等待页面刷新加载
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
