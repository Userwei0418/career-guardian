def crawl_page(page):
    """
    尝试点击下一页按钮。
    返回:
        True - 点击成功（成功翻页）
        False - 未找到或按钮被禁用
    """
    try:
        # 使用 aria-label 而不是 title
        next_button = page.locator('button[aria-label^="下一页"]')

        # 确认按钮是否存在
        if next_button.count() == 0:
            print("未找到下一页按钮")
            return False

        # 获取元素属性
        aria_disabled = next_button.get_attribute('aria-disabled')

        # 判断是否禁用
        if aria_disabled == 'true':
            print("下一页按钮被禁用，已到最后一页")
            return False

        # 检查是否可见且可点击
        if next_button.is_visible() and next_button.is_enabled():
            next_button.click()
            page.wait_for_load_state("networkidle")  # 等待页面加载稳定
            print("成功翻到下一页")
            return True
        else:
            print("下一页按钮不可点击")
            return False

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
