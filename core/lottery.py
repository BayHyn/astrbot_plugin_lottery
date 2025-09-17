import random
from datetime import datetime
from typing import Dict, Optional, Tuple
from enum import Enum
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from .data import LotteryPersistence


class PrizeLevel(Enum):
    """奖项等级枚举"""

    SPECIAL = "特等奖"
    FIRST = "一等奖"
    SECOND = "二等奖"
    THIRD = "三等奖"
    NONE = "未中奖"

    @property
    def emoji(self) -> str:
        return {
            PrizeLevel.SPECIAL: "🎊",
            PrizeLevel.FIRST: "🥇",
            PrizeLevel.SECOND: "🥈",
            PrizeLevel.THIRD: "🥉",
            PrizeLevel.NONE: "😢",
        }[self]

class LotteryActivity:
    """抽奖活动类"""

    def __init__(self, group_id: str, template: dict[PrizeLevel, dict]):
        self.group_id = group_id
        self.is_active = False
        self.created_at = datetime.now().isoformat()
        self.participants = set()  # 已参与用户ID集合
        self.winners = {}  # {user_id: prize_level}
        # 复制模板（含名称）
        self.prize_config = {
            lvl: {
                "probability": cfg["probability"],
                "count": cfg["count"],
                "remaining": cfg["count"],
                "name": cfg["name"],
            }
            for lvl, cfg in template.items()
        }

    def add_participant(self, user_id: str) -> bool:
        """添加参与者"""
        if user_id not in self.participants:
            self.participants.add(user_id)
            return True
        return False

    def has_participated(self, user_id: str) -> bool:
        """检查用户是否已参与"""
        return user_id in self.participants

    def add_winner(self, user_id: str, prize_level: PrizeLevel):
        """记录中奖者"""
        self.winners[user_id] = prize_level.value

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "group_id": self.group_id,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "participants": list(self.participants),
            "winners": self.winners,
            "prize_config": {lvl.name: cfg for lvl, cfg in self.prize_config.items()},
        }

    @classmethod
    def from_dict(
        cls, data: dict, template: dict[PrizeLevel, dict]
    ) -> "LotteryActivity":
        """从字典创建实例"""
        activity = cls(data["group_id"], template)
        activity.is_active = data["is_active"]
        activity.created_at = data["created_at"]
        activity.participants = set(data["participants"])
        activity.winners = data["winners"]
        return activity


class LotteryManager:
    """抽奖管理类"""

    def __init__(self, persistence: LotteryPersistence, config: AstrBotConfig):
        self.activities: Dict[str, LotteryActivity] = {}
        prize_config = config["default_prize_config"]
        self.template = {PrizeLevel[k.upper()]: v for k, v in prize_config.items()}
        # 数据持久化对象
        self.persistence = persistence
        self.persistence.load(self)

    def set_prize_config(
        self, group_id: str, prize_level: PrizeLevel, probability: float, count: int
    ) -> bool:
        """设置奖项配置"""
        activity = self.activities.get(group_id)
        if not activity or not activity.is_active:
            return False
        activity.prize_config[prize_level] = {
            "probability": probability,
            "count": count,
            "remaining": count,
            "name": activity.prize_config[prize_level]["name"],  # 保留原名
        }
        self.persistence.save(self)
        return True

    def start_activity(self, group_id: str) -> Tuple[bool, str]:
        """开启抽奖活动"""
        if self.activities.get(group_id) and self.activities[group_id].is_active:
            return False, "该群已有进行中的抽奖活动"
        self.activities[group_id] = LotteryActivity(group_id, self.template)
        self.activities[group_id].is_active = True
        logger.debug(f"[Lottery] 群 {group_id} 抽奖活动已创建，初始模板：{self.template}")
        self.persistence.save(self)
        return True, "本群的抽奖活动已开启"

    def draw_lottery(
        self, group_id: str, user_id: str
    ) -> Tuple[str, Optional[PrizeLevel]]:
        """抽奖"""
        # 检查活动是否存在且激活
        if group_id not in self.activities:
            logger.debug(f"[Lottery] 群 {group_id} 无活动，拒绝抽奖")
            return "该群没有抽奖活动", None

        activity = self.activities[group_id]
        if not activity.is_active:
            return "抽奖活动未开启", None

        # 检查用户是否已参与
        if activity.has_participated(user_id):
            logger.debug(f"[Lottery] 用户 {user_id} 已参与过，拒绝重复抽奖")
            return "您已经参与过本次抽奖", None

        # 执行抽奖
        prize_level = self._draw_prize(activity)
        activity.add_participant(user_id)

        if prize_level != PrizeLevel.NONE:
            activity.add_winner(user_id, prize_level)
            logger.debug(
                f"[Lottery] 用户 {user_id} 中奖 {prize_level.value}（{activity.prize_config[prize_level]['name']}）"
            )
            self.persistence.save(self)
            return f"恭喜您中了{prize_level.value}！", prize_level
        else:
            self.persistence.save(self)
            logger.debug(f"[Lottery] 用户 {user_id} 未中奖")
            return "很遗憾，您未中奖", PrizeLevel.NONE

    def _draw_prize(self, activity: LotteryActivity) -> PrizeLevel:
        """执行抽奖逻辑"""
        rand = random.random()
        cum = 0.0
        for lvl, cfg in sorted(
            activity.prize_config.items(), key=lambda x: x[1]["probability"]
        ):
            if cfg["remaining"] > 0:
                cum += cfg["probability"]
                if rand <= cum:
                    cfg["remaining"] -= 1
                    return lvl
        return PrizeLevel.NONE

    def stop_activity(self, group_id: str) -> Tuple[bool, str]:
        """停止抽奖活动"""
        if group_id not in self.activities:
            return False, "该群没有抽奖活动"

        activity = self.activities[group_id]
        if not activity.is_active:
            return False, "抽奖活动已经停止"

        activity.is_active = False
        logger.debug(
            f"[Lottery] 群 {group_id} 活动已停止，中奖记录：{activity.winners}"
        )
        self.persistence.save(self)
        return True, "抽奖活动已停止"

    def get_status_and_winners(self, group_id: str) -> Optional[dict]:
        activity = self.activities.get(group_id)
        if not activity:
            return None

        # 1. 概览
        overview = {
            "active": activity.is_active,
            "participants": len(activity.participants),
            "winners": len(activity.winners),
        }

        # 2. 奖品剩余
        prize_left = [
            {
                "level": lvl.value,
                "name": cfg["name"],
                "remaining": cfg["remaining"],
                "total": cfg["count"],
            }
            for lvl, cfg in activity.prize_config.items()
        ]

        # 3. 中奖名单
        winners_by_lvl = {}
        for uid, lvl_name in activity.winners.items():
            winners_by_lvl.setdefault(lvl_name, []).append(uid)

        return {
            "overview": overview,
            "prize_left": prize_left,
            "winners_by_lvl": winners_by_lvl,
        }
