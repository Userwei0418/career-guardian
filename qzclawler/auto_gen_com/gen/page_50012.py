def crawl_page(page) -> bool:
    """
    翻页函数，返回 True 表示翻到下一页成功，
    False 表示已经是最后一页或出错
    """
    try:
        # 查找下一页按钮，无论是否被禁用
        next_button = page.query_selector('span.pagination-item.next-page-1ksQAFhCzQ')
        
        # 检查按钮是否存在且未被禁用
        if next_button and not next_button.is_visible():
            # 如果按钮不可见，尝试另一种方式检查是否被禁用
            # 通过检查是否有disabled类来判断是否为最后一页
            next_button_classes = next_button.get_attribute('class') or ''
            if 'disabled' in next_button_classes:
                print("下一页按钮已被禁用，当前为最后一页")
                return False
        
        # 检查按钮是否真的可点击（没有disabled类）
        if next_button and 'disabled' not in (next_button.get_attribute('class') or ''):
            next_button.click()
            page.wait_for_timeout(1500)  # 等待页面加载
            print("成功点击下一页按钮")
            return True
        else:
            print("没有可用的下一页按钮，可能已经是最后一页")
            return False

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False