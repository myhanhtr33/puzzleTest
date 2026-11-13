from __future__ import annotations

from tests.ui_fakes.common import FakeNode, FakePoco


def fake_small_bundle_poco(booster_amount_text: str = "x1") -> FakePoco:
    bundle = FakeNode("UIPack_SmallBundle", {"texture": "Shop_normal_pack_bg"})
    bundle.add(FakeNode("T_NamePack", text="Small Bundle"))
    bundle.add(FakeNode("I_Tag", exists=False))

    reward_list = bundle.add(FakeNode("GameObject"))
    gold_box = reward_list.add(FakeNode("G_BoxGold"))
    gold = gold_box.add(FakeNode("UIRewardGold"))
    gold.add(FakeNode("I_Gold", {"texture": "Falcon_Gold_2"}))
    gold.add(FakeNode("T_AmountGold", text="5 000"))

    reward_box = reward_list.add(
        FakeNode("Grid_Reward", {"texture": "Shop_Pack_Panel_bg"})
    )
    for name, texture in (
        ("Sort", "booster_sort"),
        ("Shuffle", "booster_shuffle"),
        ("VIP", "booster_vip"),
        ("Slot", "booster_slot"),
    ):
        reward = reward_box.add(FakeNode(name))
        reward.add(FakeNode("I_Icon", {"texture": texture}))
        reward.add(FakeNode("T_Amount", exists=False))
    reward_box.add(FakeNode("T_BoosterAmount", text=booster_amount_text))

    lives_box = reward_list.add(
        FakeNode("G_Box_Live", {"texture": "Shop_Pack_Panel_bg"})
    )
    lives = lives_box.add(FakeNode("UIReward"))
    lives.add(FakeNode("I_Icon", {"texture": "Icon_Reward_UnlimitedLive"}))
    lives.add(FakeNode("T_Amount", text="1h"))

    bundle_button = bundle.add(
        FakeNode(
            "Button",
            {
                "clickable": True,
                "components": ["Image", "Button"],
                "texture": "Shop_ButtonBuy",
            },
        )
    )
    bundle_button.add(FakeNode("T_Price", text="7.99$"))

    return FakePoco([bundle])
