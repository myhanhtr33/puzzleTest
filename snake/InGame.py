class IngameTopBar:
    def __init__(self,poco):
        self.poco= poco
        self.gold_btn= poco("UI_RsGold").child("btnGetMore")
        self.gold_amount=int(poco("UI_RsGold").child("txtValue").get_text())
        self.achievement_text= poco("UI_Target").child("txtValue").get_text()
        self.level_text= poco("UI_LevelAndPause").child("txtValue").get_text() #Lv.179
        self.pause_btn= poco("UI_LevelAndPause").child("btnGetMore")
class InGameBooster:
    def __init__(self, poco):
        self._poco = poco

    def _btn(self, index):
        return self._poco("[IngameHUD]").offspring(f"btnBooster_{index}")

    def _amount(self, index):
        node = self._btn(index).offspring("txtValue")
        return int(node.get_text()) if node.exists() else None

    def _icon_get_more(self, index):
        node = self._btn(index).offspring("iconGetMore")
        return node if node.exists() else None

    @property
    def magnet_btn(self):          return self._btn(0)
    @property
    def magnet_amount(self):       return self._amount(0)
    @property
    def magnet_icon_get_more(self): return self._icon_get_more(0)

    @property
    def pole_btn(self):            return self._btn(1)
    @property
    def pole_amount(self):         return self._amount(1)
    @property
    def pole_icon_get_more(self):  return self._icon_get_more(1)

    @property
    def broom_btn(self):           return self._btn(2)
    @property
    def broom_amount(self):        return self._amount(2)
    @property
    def broom_icon_get_more(self): return self._icon_get_more(2)

    @property
    def magicwand_btn(self):           return self._btn(3)
    @property
    def magicwand_amount(self):        return self._amount(3)
    @property
    def magicwand_icon_get_more(self): return self._icon_get_more(3)


class PopupBuyBooster:
    def __init__(self,poco):
        self.root= poco("UIPopup_BuyBooster")
        self.title= self.root.child("Viewport").offspring("txtTitle").get_text()
        self.btn_buy= self.root.child("Viewport").offspring("btnBuy")
        self.btn_exit= self.root.child("Viewport").offspring("btnExit")
    @property
    def price(self):
        # extract number from price_text, e.g. "Buy for 100" -> 100
        import re
        price_text= self.btn_buy.child("txtBuy").get_text() #not exclude currency symbol yet
        match = re.search(r'\d+', price_text)
        return int(match.group()) if match else None