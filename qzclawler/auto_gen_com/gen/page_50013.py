def crawl_page(page) -> bool:
    """
    翻页函数，返回 True 表示翻到下一页成功，
    False 表示已经是最后一页或出错
    """
    try:
        # 定位“下一页”按钮
        next_btn = page.query_selector('li.ant-pagination-next')
        if not next_btn:
            print("没有找到下一页按钮")
            return False

        # 判断按钮是否被禁用
        classes = next_btn.get_attribute('class') or ''
        aria_disabled = next_btn.get_attribute('aria-disabled') or 'false'

        if 'ant-pagination-disabled' in classes or aria_disabled == 'true':
            print("下一页按钮已禁用，已经是最后一页")
            return False

        # 点击按钮翻页
        next_btn.click()
        page.wait_for_timeout(1000)  # 等待页面刷新
        print("成功点击下一页")
        return True

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
