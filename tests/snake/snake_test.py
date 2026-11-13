from tests.snake.snake_helper_function import get_color_name, get_user_data, add_user_data
from snake.InGame import *
from utils.helper_functions import wait_for_element

def set_timescale(poco, timescale):
    poco.invoke("set_timescale", timeScale=timescale)
    print(f"Set timescale to {timescale}")
def is_open_box(box):
    return box['runtimeData'] is not None
def box_color(box):
    return box['runtimeData']['color']
def get_blockers(block_by, snake_id):
    return block_by.get(snake_id,[])
def layer_of(snake_map, snake_id):
    return snake_map[snake_id]['layer']
def pos_of(snake_map, snake_id):
    return snake_map[snake_id]['pos']
def get_ingame_grid_data(poco):
    result = poco.invoke("get_ingame_grid")
    return {
        'layerData': result['layerData'],
        'block_by': result['blockedBy'],
        'block_by2': result['blockedBy_2']
    }
def get_snake_map(poco):
    # snake_map = {
    #   "snake_1": {"pos": [x, y], "color": "red", "layer": 1},
    #   ...
    # }
    result = poco.invoke("get_snake_colors")
    snake_colors = result['snakeColors']
    snake_layers = get_ingame_grid_data(poco)['layerData']
    snake_map = {}
    frozen_game = poco.freeze()("[Game]")
    for snake in snake_layers.keys():
        layer = snake_layers[snake]
        color = snake_colors.get(snake, "unknown")
        poco_snake_head = frozen_game.child(snake).child("snake_head")
        pos = poco_snake_head.get_position()
        snake_map[snake] = {"pos": pos, "color": color, "layer": layer}
    return snake_map
def get_match_boxes(poco):
    result = poco.invoke("get_match_boxes")
    boxes = result.get('matchBoxes', [])
    return boxes[::-1]
def get_waiting_bars(poco):
    result = poco.invoke("get_waitingbar_data")
    return result['waitingBars']
def get_available_waiting_bar_count(poco):
    count=0
    waiting_bars = get_waiting_bars(poco)
    for bar in waiting_bars:
        if bar['snakeId'] is  None:
            count+=1
    return count
def get_tempt_bars(poco):
    result = poco.invoke("get_tempbar_data")
    return result['temptBars']
def get_locked_match_box_count(match_boxes):
    count=0
    for box in match_boxes:
        if not is_open_box(box):
            count+=1
    return count

def open_match_box(match_boxes,poco):
    box=None
    for idx,box in enumerate(match_boxes):
        if not is_open_box(box):
            if idx==2:
                box= poco("btnBooster_4")
            elif idx==3:
                box= poco("btnBooster_5")
            else:
                raise ValueError(f"Unexpected box index {idx} for locked box")
            print(f"clicking locked box[{idx}]")
            box.click(sleep_interval=0.5)
            popup_buy_booster= PopupBuyBooster(poco)
            if not wait_for_element(popup_buy_booster.root, timeout=5):
                raise RuntimeError("PopupBuyBooster not found after clicking locked box")
            current_gold=get_user_data("gold", poco)
            if current_gold<popup_buy_booster.price:
                print(f"Not enough gold to open box, current gold: {current_gold}, booster price: {popup_buy_booster.price}")
                add_user_data("gold", 1000, poco)
                print(f"Added 1000 gold, new gold amount: {get_user_data('gold', poco)}")
            popup_buy_booster.btn_buy.click()
            if not wait_for_element(popup_buy_booster.root, timeout=5, interval=0.5, condition="disappear"):
                raise RuntimeError("PopupBuyBooster still exists after clicking Buy button, purchase may have failed")
            return True
    print("no locked box found to open")
    return False

def compute_plan_and_cost(target_snake_id, block_by, snake_map):
    visited_stack= set()
    moved=set()
    plan=[]
    def dfs(snake_id):
        if snake_id in moved:
            return
        if snake_id in visited_stack:
            return
        visited_stack.add(snake_id)
        blockers = get_blockers(block_by, snake_id)
        # print(f"snake {snake_id} is blocked by {blockers}")
        #if len(blockers)=0, sorted_blockers will be empty list, for loop will be skipped
        sorted_blockers = sorted(blockers, key=lambda b: layer_of(snake_map, b))
        # print(f"sorted blockers of {snake_id} by layer: {[(b, layer_of(snake_map, b)) for b in sorted_blockers]}")

        for b in sorted_blockers:
            dfs(b)
        visited_stack.remove(snake_id)
        if snake_id not in moved:
            plan.append(snake_id)
            moved.add(snake_id)
            # print(f"add {snake_id} to plan, moved: {moved}")
    dfs(target_snake_id)
    return plan, len(moved)
def find_optimal_move(block_by, snake_map, match_boxes, block_by2):
    best= None
    for box_index, box in enumerate(match_boxes):
        if not is_open_box(box):
            continue
        color= box_color(box)
        candidates=[
            sid for sid in snake_map.keys()
            if snake_map[sid]['color']== color
        ]
        if not candidates:
            ####### error, not found reason yet. a open box have to have at least 3 snakes with the same color
            # , but in rare case, we may encounter a box with no candidate snake, which should not happen. log error for debugging
            print(f"No snake found for box color {color}({get_color_name(color)})")
        print(f"box {box_index} with color {color}({get_color_name(color)}) has candidates: {candidates}")
        for sid in candidates:
            plan,cost= compute_plan_and_cost(sid, block_by, snake_map)
            blocking_count=0
            for blocked_snake,blockers in block_by2.items():
                if sid in blockers:
                    blocking_count +=1
            # print(f"{sid} is blocker for {blocking_count} snakes in block_by2")
            blockers_len= len(get_blockers(block_by, sid))
            if best is None or cost < best[3] or (
                    cost == best[3] and blocking_count > best[4]):
                best = (box_index, color, sid, cost, blocking_count, plan)
            # print(f"blockingCount:{best[4]},best so far: {best}")
    if best is None:
        raise RuntimeError("No valid moves found")
    click_position= pos_of(snake_map, best[2])
    # return = {
    #   "box_index":      0,
    #   "box_color":      "red",
    #   "snake_id":       "snake_1",
    #   "total_move":     3,
    #   "blocking_count": 2,
    #   "plan":           ["snake_3", "snake_2", "snake_1"],
    #   "click_position": [x, y]
    # }
    return{
        "box_index": best[0],
        "box_color": best[1],
        "snake_id": best[2],
        "total_move": best[3],
        "blocking_count": best[4],
        "plan": best[5],
        "click_position": click_position
    }



