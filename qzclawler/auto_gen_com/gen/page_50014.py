from playwright.sync_api import Page, TimeoutError


def crawl_page(page: Page) -> bool:
    """
    翻页函数，返回 True 表示翻到下一页成功，
    False 表示已经是最后一页或出错
    """
    try:
        # 尝试查找“下一页”按钮，排除禁用状态
        next_button = page.query_selector(
            'a.layui-laypage-next:not(.layui-disabled), button.sd-Pagination-forward-3z80f:not([disabled])')

        if next_button:
            # 点击下一页
            next_button.click()

            # 等待页面加载完成（可根据实际情况调整）
            page.wait_for_timeout(1500)  # 1.5秒

            print("成功点击下一页按钮")
            return True
        else:
            print("没有可用的下一页按钮，已经是最后一页")
            return False

    except TimeoutError:
        print("等待页面超时，翻页失败")
        return False
    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
