def crawl_page(page) -> bool:
    """
    翻页函数，适配 Ant Design 的分页组件 (ant-pagination)
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # ✅ 定位下一页 li 元素
        next_li = page.query_selector("li.ant-pagination-next")

        if not next_li:
            print("[翻页] 未找到下一页按钮")
            return False

        # ✅ 判断是否禁用
        aria_disabled = next_li.get_attribute("aria-disabled")
        if aria_disabled == "true":
            print("[翻页] 下一页按钮已禁用，可能是最后一页")
            return False

        # ✅ 获取 <a> 标签
        next_a = next_li.query_selector("a.ant-pagination-item-link")
        if not next_a:
            print("[翻页] 未找到 <a> 标签")
            return False

        # ✅ 点击下一页按钮
        next_a.click()
        page.wait_for_timeout(2000)  # 等待加载新页面内容
        print("[翻页] 成功点击下一页")
        return True

    except Exception as e:
        print(f"[翻页] 出错: {e}")
        return False
