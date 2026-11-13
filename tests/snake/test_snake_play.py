import pytest
from logger_config import get_logger
from tests.snake.snake_helper_function import get_user_data
from tests.snake.snake_test import *
from utils.helper_functions import wait_for_element
from airtest.core.api import swipe, sleep, wait, keyevent, Template, click
from airtest.core.error import TargetNotFoundError
from utils.keyboard_helper import press_key
from pywinauto.keyboard import SendKeys
from snake.InGame import *


class TestCozyPlay:
    @pytest.fixture(scope="function", autouse=True)
    def setup(cls,poco):
        cls.poco= poco
        poco_freeze= poco.freeze()


    def test_level(self):
        def data_requery():
            nonlocal ingame_grid_data, layer_data, block_by, block_by2, snake_map, match_boxes
            ingame_grid_data = get_ingame_grid_data(self.poco)
            layer_data = ingame_grid_data['layerData']
            block_by = ingame_grid_data['block_by']
            block_by2 = ingame_grid_data['block_by2']
            snake_map = get_snake_map(self.poco)
            match_boxes = get_match_boxes(self.poco)
        def match_boxes_requery():
            nonlocal match_boxes
            match_boxes = get_match_boxes(self.poco)
        def is_wait_for_anim(snake_id, match_boxes):
            for box in match_boxes:
                if not is_open_box(box):
                    continue
                box_color_val = box_color(box)
                remain_slots= box['runtimeData']['remainSlots']
                snake_color = snake_map[snake_id]['color']
                if box_color_val == snake_color and remain_slots <=1:
                    return True
            return False
        ingame_top=IngameTopBar(self.poco)
        current_level= ingame_top.level_text
        ingame_grid_data = get_ingame_grid_data(self.poco)
        layer_data = ingame_grid_data['layerData']
        block_by = ingame_grid_data['block_by']
        block_by2 = ingame_grid_data['block_by2']
        snake_map = get_snake_map(self.poco)
        match_boxes = get_match_boxes(self.poco)
        used_boosters=[]
        set_timescale(self.poco,2.3)
        while len(layer_data)>0:
            print(f"current snakes: {list(layer_data.keys())}")
            optimal_snake=find_optimal_move(block_by, snake_map, match_boxes,block_by2)
            snake_to_move=len(optimal_snake['plan'])
            print(f"optimal snake: {optimal_snake['snake_id']} color: {snake_map[optimal_snake['snake_id']]['color']}"
                  f"({get_color_name(snake_map[optimal_snake['snake_id']]['color'])}). "
                  f"{snake_to_move} snakes to move")
            using_broom_in_x_next_snake=None
            broom_btn=None
            if snake_to_move>1:
                available_waiting_bar= get_available_waiting_bar_count(self.poco)
                print(f"available waiting bars: {available_waiting_bar}")
                if snake_to_move-1>= available_waiting_bar: #-1 because the optimal snake(the last, layer=0) can move without waiting bar
                    print(f"not enough waiting bars to move optimal snake, available waiting bars: {available_waiting_bar}, "
                          f"optimal snake plan length: {len(optimal_snake['plan'])}.")
                    ##solution 1: open more match box
                    locked_box_count= get_locked_match_box_count(match_boxes)
                    if locked_box_count>0:
                        print(f"there are {locked_box_count} locked boxes, try to open one...")
                        open_match_box(match_boxes,self.poco)
                        used_boosters.append({
                            'booster': 'box',
                            'snake_to_move': len(optimal_snake['plan'])
                        })
                        data_requery()
                        continue
                    ##solution 2: use booster broom to sweep all waiting bars into tempt bars -> waiting bars empty
                    booster_manager= InGameBooster(self.poco)
                    broom_count= booster_manager.broom_amount
                    if  broom_count is None or broom_count<1 :
                        print(f"no broom booster to use, current broom: {broom_count}, add 5 broom")
                        add_user_data("broom", 5, self.poco)
                        sleep(0.6)
                    if available_waiting_bar-1==1:
                        booster_manager.broom_btn.click(sleep_interval=1)
                        print(f"use broom booster to clear waiting bars, current broom amount: {booster_manager.broom_amount}")
                        used_boosters.append({
                            'booster': 'broom',
                            'snake_to_move': len(optimal_snake['plan'])
                        })
                        data_requery()
                        continue
                    else:
                        print(f"still {available_waiting_bar-1} waiting bars to get snake, keep moving snake in plan till 1 bar left then use broom booster")
                        using_broom_in_x_next_snake= available_waiting_bar-1
                        broom_btn= booster_manager.broom_btn
            for i, snake in enumerate(optimal_snake['plan']):
                if using_broom_in_x_next_snake is not None and i== snake_to_move-using_broom_in_x_next_snake:
                    broom_btn.click(sleep_interval=1)
                    print(f"use broom booster to clear waiting bars, current broom amount: {booster_manager.broom_amount}")
                    used_boosters.append({
                        'booster': 'broom',
                        'snake_to_move': len(optimal_snake['plan'])
                    })
                    data_requery()
                    break
                snake_pos = pos_of(snake_map, snake)
                print(f"moving snake {snake} color:{snake_map[snake]['color']}({get_color_name(snake_map[snake]['color'])})")
                click(snake_pos)
                if is_wait_for_anim(snake, match_boxes):
                    print("waiting for box open animation...")
                    sleep(0.5)
                    match_boxes_requery()
                else:
                    sleep(0.2)
            # sleep(2)
            data_requery()
        set_timescale(self.poco,1)
        print(f"boosters used in {current_level}:")
        for booster in used_boosters:
            print(f"used booster: {booster['booster']} for snake_to_move: {booster['snake_to_move']}")

    def test_drag(self):
        result=self.poco.invoke("set_timescale", timeScale=2)
        print(f"set time scale result: {result}")
