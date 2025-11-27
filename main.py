from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot import logger
from astrbot.core.star.filter.permission import PermissionType
from astrbot.core.star.star_tools import StarTools
import aiohttp
import asyncio
from pathlib import Path


@register("avatar_uploader", "YourName", "头像上传插件", "1.0.0")
class AvatarUploaderPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        # 存储等待头像上传的用户会话状态
        self.waiting_for_avatar = {}
        self.avatar_dir = StarTools.get_data_dir("avatar_uploader") / "avatars"
        self.avatar_dir.mkdir(parents=True, exist_ok=True)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("上传头像")
    async def upload_avatar(self, event: AiocqhttpMessageEvent):
        """开始头像上传流程"""
        session_id = event.session_id
        
        # 设置该会话为等待头像状态
        self.waiting_for_avatar[session_id] = True
        
        yield event.plain_result("请发送您要设置为头像的图片~")
        
        # 设置超时清理（30秒后自动清除等待状态）
        asyncio.create_task(self._clear_waiting_status(session_id))

    async def _clear_waiting_status(self, session_id: str, delay: int = 30):
        """清理等待状态"""
        await asyncio.sleep(delay)
        if session_id in self.waiting_for_avatar:
            del self.waiting_for_avatar[session_id]

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_image_message(self, event: AiocqhttpMessageEvent):
        """处理所有消息，检查是否有等待头像上传的会话"""
        session_id = event.session_id
        
        # 如果这个会话不在等待头像状态，直接返回
        if session_id not in self.waiting_for_avatar:
            return
        
        # 检查消息中是否包含图片
        chain = event.get_messages()
        img_url = None
        
        for seg in chain:
            if isinstance(seg, Comp.Image):
                img_url = seg.url
                break
        
        if not img_url:
            # 如果用户发送的不是图片，提醒并保持等待状态
            yield event.plain_result("请发送图片哦~ 如需取消，请等待30秒或发送其他指令")
            return
        
        # 清除等待状态
        del self.waiting_for_avatar[session_id]
        
        try:
            # 下载并设置头像
            await self._download_and_set_avatar(event, img_url)
            yield event.plain_result("头像设置成功！")
            
        except Exception as e:
            logger.error(f"设置头像失败: {e}")
            yield event.plain_result("头像设置失败，请稍后重试")

    async def _download_and_set_avatar(self, event: AiocqhttpMessageEvent, img_url: str):
        """下载图片并设置为头像"""
        # 下载图片到临时文件
        temp_path = self.avatar_dir / f"temp_avatar_{event.session_id}.jpg"
        
        try:
            # 下载图片
            async with aiohttp.ClientSession() as session:
                async with session.get(img_url) as response:
                    if response.status == 200:
                        with open(temp_path, 'wb') as f:
                            f.write(await response.read())
                    else:
                        raise Exception(f"下载图片失败，状态码: {response.status}")
            
            # 设置QQ头像
            await event.bot.set_qq_avatar(file=str(temp_path))
            
            logger.info(f"头像设置成功，会话: {event.session_id}")
            
        finally:
            # 清理临时文件
            if temp_path.exists():
                temp_path.unlink()

    async def terminate(self):
        """插件卸载时清理资源"""
        self.waiting_for_avatar.clear()