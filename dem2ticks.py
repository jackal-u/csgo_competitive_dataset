from typing import List, Dict
from demoparser2 import DemoParser
import pandas as pd


class DemoPOVs:
    def __init__(self, demo_path: str):
        self.demo_path = demo_path
        self.demo_parser = DemoParser(self.demo_path)
        self.players: Dict[str, PlayerPOVs] = {}
        self._init_players()

    def _init_players(self):
        """初始化所有玩家的POV数据"""
        player_info = self.demo_parser.parse_player_info()
        for player in player_info.itertuples():
            self.players[str(player.steamid)] = PlayerPOVs(self.demo_parser, player.steamid)

    @staticmethod
    def get_player_alive_ranges(parser: DemoParser, target_steamid: int) -> List[tuple[int, int]]:
        """
        获取玩家在整个比赛中的存活时间范围

        :param parser: DemoParser对象
        :param target_steamid: 目标玩家的Steam ID
        :return: 存活时间范围列表,每个元素为(开始tick, 结束tick)
        """
        # 一次性获取所有tick的数据,提高效率
        ticks_df = parser.parse_ticks(["is_alive", "player_steamid", "game_time"])
        round_end_df = parser.parse_event("round_end")

        # 过滤目标玩家的数据
        player_data = ticks_df[ticks_df['player_steamid'] == target_steamid]

        alive_ranges = []
        start_tick = None
        last_round_end_tick = 0

        for tick, row in player_data.iterrows():
            # 检查回合是否结束
            round_end_ticks = round_end_df[round_end_df.index > last_round_end_tick].index
            if len(round_end_ticks) > 0 and tick > round_end_ticks[0]:
                if start_tick is not None:
                    alive_ranges.append((start_tick, round_end_ticks[0]))
                    start_tick = None
                last_round_end_tick = round_end_ticks[0]

            if row['is_alive'] and start_tick is None:
                start_tick = tick
            elif not row['is_alive'] and start_tick is not None:
                alive_ranges.append((start_tick, tick - 1))
                start_tick = None

        # 处理最后一个回合
        if start_tick is not None:
            last_round_end = round_end_df.index[-1] if not round_end_df.empty else player_data.index[-1]
            alive_ranges.append((start_tick, last_round_end))

        # 过滤掉异常长的范围
        MAX_LEN = 128 * (55 + 60 + 15 + 15 + 45)
        return [(start, end) for start, end in alive_ranges if end - start < MAX_LEN]


class PlayerActionFrame:
    @staticmethod
    def get_player_action(parser: DemoParser, steamid: int, tick: int) -> "PlayerActionFrame":
        """
        获取玩家在特定tick的动作信息

        :param parser: DemoParser对象
        :param steamid: 玩家的Steam ID
        :param tick: 目标tick
        :return: PlayerActionFrame对象
        """
        fields = [
            "player_steamid", "FORWARD", "LEFT", "RIGHT", "BACK",
            "team_num", "WALK", "USE", "INSPECT",
            "usercmd_mouse_dx", "usercmd_mouse_dy",
            "FIRE", "RIGHTCLICK", "RELOAD", "active_weapon",
            "old_jump_pressed", "in_crouch", "ducked", "ducking", "in_duck_jump"
        ]

        # 只获取特定tick和玩家的数据
        tick_data = parser.parse_ticks(fields, players=[steamid], ticks=[tick])

        if tick_data.empty:
            raise ValueError(f"未在tick {tick}找到steamid为{steamid}的玩家数据")

        player_action = tick_data.iloc[0]

        wasd = [
            int(player_action['FORWARD']),
            int(player_action['LEFT']),
            int(player_action['BACK']),
            int(player_action['RIGHT'])
        ]

        # 使用多个字段来判断跳跃和蹲下状态
        jump = int(player_action['old_jump_pressed'] or player_action['in_duck_jump'])
        crouch = int(player_action['in_crouch'] or player_action['ducked'] or player_action['ducking'])

        return PlayerActionFrame(
            wasd=wasd,
            team=player_action['team_num'],
            walk=int(player_action['WALK']),
            use=int(player_action['USE']),
            inspect=int(player_action['INSPECT']),
            dx=player_action['usercmd_mouse_dx'],
            dy=player_action['usercmd_mouse_dy'],
            attack=int(player_action['FIRE']),
            l_attack=int(player_action['RIGHTCLICK']),
            reload=int(player_action['RELOAD']),
            select=player_action['active_weapon'],
            jump=jump,
            crouch=crouch,
            tick=tick
        )

class PlayerInfoFrame:
    """
    player info in one tick
    """
    def __init__(self, tick:int,
                 hp:int, team:int, weapon:int, round:int, time:int,
                 armor:int, money:int, player_name:str, steamid:int,
                 pic_path:str=None):
        self.tick = tick
        self.pic_path = pic_path   # fill after render, default is None
        self.hp = hp
        self.team = team
        self.weapon = weapon
        self.round = round
        self.time = time
        self.armor = armor
        self.money = money
        self.player_name = player_name
        self.steamid = steamid

    @staticmethod
    def get_player_info(parser: DemoParser, steamid: int, tick: int) -> "PlayerInfoFrame":
        """
        获取玩家在特定tick的信息

        :param parser: DemoParser对象
        :param steamid: 玩家的Steam ID
        :param tick: 目标tick
        :return: PlayerInfoFrame对象
        """
        fields = [
            "health", "team_num", "active_weapon", "total_rounds_played",
            "armor_value", "balance", "player_name", "player_steamid",
            "round_start_time", "game_time"
        ]

        # 只获取特定tick和玩家的数据
        tick_data = parser.parse_ticks(fields, players=[steamid], ticks=[tick])

        if tick_data.empty:
            raise ValueError(f"未在tick {tick}找到steamid为{steamid}的玩家数据")

        player_info = tick_data.iloc[0]

        # 计算回合时间
        round_time = player_info['game_time'] - player_info['round_start_time']

        return PlayerInfoFrame(
            tick=tick,
            hp=player_info['health'],
            team=player_info['team_num'],
            weapon=player_info['active_weapon'],
            round=player_info['total_rounds_played'],
            time=int(round_time),
            armor=player_info['armor_value'],
            money=player_info['balance'],
            player_name=player_info['player_name'],
            steamid=player_info['player_steamid']
        )


class PlayerFrame:
    def __init__(self, parser: DemoParser, steamid: int, tick: int):
        self.tick = tick
        self.player_info = PlayerInfoFrame.get_player_info(parser, steamid, tick)
        self.player_action = PlayerActionFrame.get_player_action(parser, steamid, tick)


class PlayerRoundFrames:
    def __init__(self, parser: DemoParser, start_tick: int, end_tick: int, steamid: int):
        self.start_tick = start_tick
        self.end_tick = end_tick
        self.steamid = steamid
        self.player_frames: List[PlayerFrame] = []
        self._build_player_frames(parser)

    def _build_player_frames(self, parser: DemoParser):
        """构建玩家在一个回合内的所有帧数据"""
        for tick in range(self.start_tick, self.end_tick + 1):
            self.player_frames.append(PlayerFrame(parser, self.steamid, tick))


class PlayerPOVs:
    def __init__(self, demo_parser: DemoParser, steamid: int):
        self.demo_parser = demo_parser
        self.steamid = steamid
        self.round_frames: List[PlayerRoundFrames] = []
        self._parse_round_frames()

    def _parse_round_frames(self):
        """解析玩家在每个回合的帧数据"""
        ranges = DemoPOVs.get_player_alive_ranges(self.demo_parser, self.steamid)
        for start, end in ranges:
            self.round_frames.append(PlayerRoundFrames(self.demo_parser, start, end, self.steamid))


if __name__ == "__main__":
    demo_path = "./demo/g161-b-20241003023822567004606_de_mirage.dem"
    povs = DemoPOVs(demo_path)
    print(len(povs.players))