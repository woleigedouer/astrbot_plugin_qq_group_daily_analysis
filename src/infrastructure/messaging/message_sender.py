"""
消息发送器 - 基础设施层
提供高层消息发送接口，支持跨平台智能路由。
"""

from ...utils.logger import logger


class MessageSender:
    """
    消息发送器
    封装了 PlatformAdapter 的底层调用，提供更高层的发送接口
    """

    def __init__(self, bot_manager, config_manager):
        self.bot_manager = bot_manager
        self.config_manager = config_manager

    async def send_text(
        self, group_id: str, text: str, platform_id: str | None = None
    ) -> bool:
        """发送文本消息"""
        adapter = self.bot_manager.get_adapter(platform_id)
        if not adapter:
            logger.error(f"[MessageSender] 未找到平台 {platform_id} 的适配器")
            return False
        return await adapter.send_text(group_id, text)

    async def send_image_smart(
        self,
        group_id: str,
        image_url: str,
        caption: str = "",
        platform_id: str | None = None,
    ) -> bool:
        """智能发送图片，支持自动选择适配器"""
        adapter = self.bot_manager.get_adapter(platform_id)
        if not adapter:
            logger.error(f"[MessageSender] 未找到平台 {platform_id} 的适配器")
            return False
        return await adapter.send_image(group_id, image_url, caption)

    async def send_file(
        self,
        group_id: str,
        file_path: str,
        caption: str = "",
        platform_id: str | None = None,
        filename: str | None = None,
    ) -> bool:
        """发送文件（HTML/PDF/其它文件）。支持可选 caption。"""
        adapter = self.bot_manager.get_adapter(platform_id)
        if not adapter:
            logger.error(f"[MessageSender] 未找到平台 {platform_id} 的适配器")
            return False

        # 尝试将 caption 合并到文件消息中（适配器支持时）
        send_kwargs = {}
        if filename:
            send_kwargs["filename"] = filename
        if caption and hasattr(adapter.send_file, "__code__") and "caption" in adapter.send_file.__code__.co_varnames:
            send_kwargs["caption"] = caption
            file_sent = await adapter.send_file(group_id, file_path, **send_kwargs)
            return file_sent if file_sent else False

        # 回退：分开发送文件和 caption
        file_sent = await adapter.send_file(group_id, file_path, **send_kwargs)

        if not file_sent:
            return False

        if caption:
            try:
                await adapter.send_text(group_id, f"{caption}")
            except Exception as e:
                logger.warning(f"[MessageSender] 文件已发送，但 caption 发送异常: {e}")

        return True

    def _get_available_platforms(self, group_id: str):
        """获取可用的平台列表 (Helper for Dispatcher)"""
        # 简单实现：返回所有已加载的平台
        return [(pid, None) for pid in self.bot_manager.get_platform_ids()]
