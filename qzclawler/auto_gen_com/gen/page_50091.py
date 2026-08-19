def crawl_page(page):
    """
    尝试翻到下一页
    返回 True 表示成功翻页，False 表示没有下一页或不可点击
    """
    try:
        # 定位下一页按钮
        next_btn = page.locator("button.btn-next")

        # 判断按钮是否存在且可点击
        if next_btn and next_btn.is_enabled():
            aria_disabled = next_btn.get_attribute('disabled')
            if aria_disabled != 'true':
                next_btn.click()
                return True
    except Exception as e:
        print(f"翻页时出现错误: {e}")

    return False
