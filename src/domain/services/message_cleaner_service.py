"""
消息清理服务 - 领域层
负责过滤掉机器人消息、指令、技术性内容（如原始表情代码）及敏感内容。
"""

import re
from dataclasses import replace

from ..value_objects.unified_message import (
    MessageContent,
    MessageContentType,
    UnifiedMessage,
)


class MessageCleanerService:
    """消息清理服务"""

    # Discord 自定义表情正则 <:name:id> 或 <a:name:id>
    DISCORD_CUSTOM_EMOJI_PATTERN = re.compile(r"<a?:.+?:\d+>")

    # 指令匹配正则：匹配以 / 开头，或者以 @某人 / 开头的消息
    # 比如: "/group_analysis", "@bot /help", " /test"
    COMMAND_PATTERN = re.compile(r"^\s*(?:<@\d+>\s+)?/")

    # 触发词匹配：@某人 + 插件指令关键词
    TRIGGER_PATTERN = re.compile(
        r"@\S+\s*(群分析|群总结|group_analysis)", re.IGNORECASE
    )

    # 垃圾消息混淆字符：广告常在关键词间插入这些字符来绕过过滤
    SPAM_OBFUSCATION_CHARS = re.compile(
        r"[\s\-·~～•‧∙⋅★☆❤♥♡✦✧●○◆◇■□▪▫※×†‡"
        r"​‌‍﻿"  # 零宽字符
        r"()（）\[\]【】{}｛｝<>《》〈〉「」『』"
        r".,，。、;；:：!！?？/\\|｜#＃@＠$＄%％^＾&＆*＊+＋=＝`''\"\"\"_＿]"
    )

    def clean_messages(
        self,
        messages: list[UnifiedMessage],
        bot_self_ids: list[str] = None,
        filter_commands: bool = True,
        extra_spam_keywords: list[str] | None = None,
    ) -> list[UnifiedMessage]:
        """
        清理并过滤消息列表。

        Args:
            messages: 原始统一格式消息列表
            bot_self_ids: 机器人自身的 ID 列表
            filter_commands: 是否过滤指令消息

        Returns:
            清理后的消息列表
        """
        bot_ids = set(bot_self_ids or [])
        cleaned_list = []

        # 构建垃圾消息过滤正则（仅当有关键词时启用）
        spam_pattern = None
        spam_pattern_normalized = None
        if extra_spam_keywords:
            valid_keywords = [re.escape(k) for k in extra_spam_keywords if k.strip()]
            if valid_keywords:
                spam_pattern = re.compile("|".join(valid_keywords), re.IGNORECASE)
                # 归一化版本：关键词去除混淆字符后匹配，带最小长度保护
                normalized_keywords = []
                for k in extra_spam_keywords:
                    if not k.strip():
                        continue
                    nk = self.SPAM_OBFUSCATION_CHARS.sub("", k)
                    if not nk:
                        continue
                    # 防止短关键词归一化后误杀：中文至少2字符，纯ASCII至少3字符
                    if nk.isascii() and len(nk) < 3:
                        continue
                    if not nk.isascii() and len(nk) < 2:
                        continue
                    normalized_keywords.append(re.escape(nk))
                if normalized_keywords:
                    spam_pattern_normalized = re.compile(
                        "|".join(normalized_keywords), re.IGNORECASE
                    )

        for msg in messages:
            # 1. 过滤机器人发送的消息
            if msg.sender_id in bot_ids:
                continue

            # 2. 预检指令消息（首个内容块通常是文本）
            is_command = False
            first_text = msg.text_content
            if (
                filter_commands
                and first_text
                and (self.COMMAND_PATTERN.match(first_text) or self.TRIGGER_PATTERN.search(first_text))
            ):
                is_command = True

            if is_command:
                continue

            # 3. 过滤广告/垃圾消息（检测正文 + 发送者名称）
            if spam_pattern:
                spam_targets = [t for t in (first_text, msg.sender_name, msg.sender_card) if t]
                is_spam = False
                for target in spam_targets:
                    if spam_pattern.search(target):
                        is_spam = True
                        break
                    if spam_pattern_normalized:
                        normalized = self.SPAM_OBFUSCATION_CHARS.sub("", target)
                        if spam_pattern_normalized.search(normalized):
                            is_spam = True
                            break
                if is_spam:
                    continue

            # 3. 清理消息内容中的技术性噪音
            cleaned_contents = []
            has_meaningful_content = False

            for content in msg.contents:
                if content.type == MessageContentType.TEXT:
                    text = content.text or ""

                    # 移除 Discord 原始表情代码
                    text = self.DISCORD_CUSTOM_EMOJI_PATTERN.sub("", text)

                    # 移除 @mentions 文本 (e.g. <@123456>)
                    text = re.sub(r"<@\d+>", "", text)

                    # 清理多余空格
                    text = text.strip()

                    if text:
                        cleaned_contents.append(
                            MessageContent(type=MessageContentType.TEXT, text=text)
                        )
                        has_meaningful_content = True
                else:
                    # 其他类型（图片、回复等）暂时保留，但由后续分析器决定是否使用
                    cleaned_contents.append(content)
                    if content.type != MessageContentType.REPLY:
                        has_meaningful_content = True

            # 4. 如果清理后仍有内容，则保留消息
            if has_meaningful_content:
                # 重新合成 text_content 用于 LLM 分析
                new_text_content = "".join(
                    [
                        c.text
                        for c in cleaned_contents
                        if c.type == MessageContentType.TEXT
                    ]
                ).strip()

                # 使用 replace 创建新实例（Frozen dataclass 必须如此）
                new_msg = replace(
                    msg, contents=tuple(cleaned_contents), text_content=new_text_content
                )
                cleaned_list.append(new_msg)

        return cleaned_list
