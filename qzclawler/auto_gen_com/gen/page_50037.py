def crawl_page(page):
    try:
        # 找到 li 节点
        next_page_button = page.locator('li[title="下一页"]').first
        if not next_page_button:
            print("没有找到下一页按钮")
            return False

        # 判断禁用状态
        classes = next_page_button.get_attribute('class') or ''
        aria_disabled = next_page_button.get_attribute('aria-disabled') or 'false'

        if 'ant-pagination-disabled' in classes or aria_disabled == 'true':
            print("下一页按钮不可用，翻页结束")
            return False

        # 找 li 里面的 <a> 节点去点击
        clickable = next_page_button.locator('a')
        if clickable.is_visible():
            clickable.click()
            print("点击下一页成功")
            return True
        else:
            print("下一页按钮不可见")
            return False

    except Exception as e:
        print(f"翻页时出现错误: {e}")
    return False
