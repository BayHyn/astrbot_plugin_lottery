
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


async def get_nickname(event: AstrMessageEvent, user_id:str) -> str:
    """获取指定群友的群昵称或Q名"""
    if event.get_platform_name() == "aiocqhttp" and user_id.isdigit():
        assert isinstance(event, AiocqhttpMessageEvent)
        all_info = await event.bot.get_group_member_info(
            group_id=int(event.get_group_id()), user_id=int(user_id)
        )
        return all_info.get("card") or all_info.get("nickname")
    return user_id









