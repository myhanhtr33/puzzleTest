from __future__ import annotations

import base64
import sys
from types import ModuleType, SimpleNamespace
import zlib
from urllib.parse import quote_from_bytes

import pytest

from tests.ui_fakes.common import FakeNode, FakePoco
from utils.ui_contracts import ManifestError, parse_drawio_xml, run_contract
from utils.ui_contract_checks import texture as texture_checkers


SAMPLE_DRAWIO = b"""<mxGraphModel><root>
<mxCell id='0'/><mxCell id='1' parent='0'/>
<object id='root' metadataRole='ui_object' testId='root' base='' pathMode='name_chain' path='[&quot;Root&quot;]' exist='true' checks='[]' cardinality='unique'>
<mxCell vertex='1' parent='1'/>
</object>
</root></mxGraphModel>"""


class TestUIContractShared:
    def test_typed_reward_and_buy_nodes_round_trip(self):
        source = b"""<mxGraphModel><root>
          <mxCell id='0'/><mxCell id='1' parent='0'/>
          <object id='root_obj' metadataRole='ui_object' testId='root' base='' pathMode='name_chain' path='Root' exist='true' checks='[]'/>
          <object id='reward_obj' metadataRole='ui_object' testId='gold' contractType='reward' rewardId='gold' amount='25' amountUnit='count' base='root' pathMode='offspring' path='Gold' exist='true' checks='[]'/>
          <object id='buy_obj' metadataRole='ui_object' testId='buy' contractType='button' buttonType='buy' productId='sku_1' price='0.99' grants='[&quot;gold&quot;]' base='root' pathMode='offspring' path='Buy' exist='true' checks='[]'/>
          <mxCell id='root_cell' vertex='1' parent='1'/>
          <mxCell id='reward_cell' vertex='1' parent='1'/>
          <mxCell id='buy_cell' vertex='1' parent='1'/>
          </root></mxGraphModel>"""

        manifest = parse_drawio_xml(source)
        objects = {item["testId"]: item for item in manifest["objects"]}

        assert manifest["schemaVersion"] == 2
        assert objects["gold"]["contractType"] == "reward"
        assert objects["gold"]["amount"] == 25
        assert objects["buy"]["buttonType"] == "buy"
        assert objects["buy"]["grants"] == ["gold"]

    def test_buy_button_rejects_unknown_reward_reference(self):
        source = b"""<mxGraphModel><root>
          <mxCell id='0'/><mxCell id='1' parent='0'/>
          <object id='root_obj' testId='root' base='' pathMode='name_chain' path='Root' exist='true' checks='[]'/>
          <object id='buy_obj' testId='buy' contractType='button' buttonType='buy' productId='sku_1' grants='[&quot;missing&quot;]' base='root' pathMode='offspring' path='Buy' exist='true' checks='[]'/>
          </root></mxGraphModel>"""

        with pytest.raises(ManifestError, match="grants references unknown rewardId"):
            parse_drawio_xml(source)

    @staticmethod
    def _text_manifest(text_format: str, **check_fields):
        check = {
            "type": "text",
            "format": text_format,
            "target": {"type": "offspring", "names": ["T_Text"]},
        }
        check.update(check_fields)
        return {
            "schemaVersion": 1,
            "root": "root",
            "objects": [
                {
                    "testId": "root",
                    "base": None,
                    "pathMode": "name_chain",
                    "path": ["Root"],
                    "exist": True,
                    "checks": [check],
                }
            ],
        }

    @classmethod
    def _run_text_check(cls, text_format: str, actual: str, **check_fields):
        root = FakeNode("Root")
        root.add(FakeNode("T_Text", text=actual))
        return run_contract(
            FakePoco([root]),
            cls._text_manifest(text_format, **check_fields),
        )

    @pytest.mark.parametrize("encoding", ["url", "base64"])
    def test_compressed_drawio_page_is_supported(self, encoding):
        page_xml = SAMPLE_DRAWIO.decode("utf-8")
        payload = quote_from_bytes(page_xml.encode("utf-8")).encode("utf-8")
        compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        compressed = compressor.compress(payload) + compressor.flush()

        if encoding == "url":
            encoded = quote_from_bytes(compressed)
        else:
            encoded = base64.b64encode(compressed).decode("ascii")

        wrapped = (
            '<mxfile><diagram name="compressed">'
            + encoded
            + "</diagram></mxfile>"
        )

        manifest = parse_drawio_xml(wrapped.encode("utf-8"))

        assert manifest["root"] == "root"
        assert len(manifest["objects"]) == 1

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [("x1", 1), ("x2", 2), ("x11", 11)],
    )
    def test_booster_amount_accepts_x_number_values(self, actual, expected):
        report = self._run_text_check(
            "booster_amount",
            actual,
            amount=expected,
        )

        assert report.passed, report.format()

    @pytest.mark.parametrize("actual", ["q1", "y1", "x1.5"])
    def test_booster_amount_requires_x_number_format(self, actual):
        report = self._run_text_check(
            "booster_amount",
            actual,
            amount=1,
        )

        assert not report.passed
        assert "xNumber format" in report.format()

    def test_booster_amount_reports_value_mismatch(self):
        report = self._run_text_check(
            "booster_amount",
            "x2",
            amount=1,
        )

        assert not report.passed
        assert "expected booster amount=1, got 2" in report.format()

    def test_runner_collects_failures(self):
        root = FakeNode("Root", {"clickable": True})
        root.add(FakeNode("T_Text", text="$ 7.99"))
        manifest = {
            "schemaVersion": 1,
            "root": "root",
            "objects": [
                {
                    "testId": "root",
                    "base": None,
                    "pathMode": "name_chain",
                    "path": ["Root"],
                    "exist": True,
                    "checks": [
                        {"type": "clickable", "expected": False},
                        {
                            "type": "text",
                            "format": "price",
                            "target": {"type": "offspring", "names": ["T_Text"]},
                            "amount": "8.99",
                            "currencies": ["$"],
                            "currency_position": "any",
                        },
                    ],
                }
            ],
        }

        report = run_contract(FakePoco([root]), manifest)

        assert not report.passed
        assert len(report.failures) == 2
        assert "root" in report.format()

    def test_price_check_validates_amount_and_suffix_currency(self):
        root = FakeNode("Root")
        root.add(FakeNode("T_Price", text="7.99$"))
        manifest = {
            "schemaVersion": 1,
            "root": "root",
            "objects": [{
                "testId": "root",
                "base": None,
                "pathMode": "name_chain",
                "path": ["Root"],
                "exist": True,
                "checks": [{
                    "type": "text",
                    "format": "price",
                    "target": {"type": "offspring", "names": ["T_Price"]},
                    "amount": "7.99",
                    "currencies": ["$"],
                    "currency_position": "suffix",
                }],
            }],
        }

        report = run_contract(FakePoco([root]), manifest)

        assert report.passed, report.format()

    def test_custom_checkers_are_supported(self):
        manifest = {
            "schemaVersion": 1,
            "root": "root",
            "objects": [
                {
                    "testId": "root",
                    "base": None,
                    "pathMode": "name_chain",
                    "path": ["Root"],
                    "exist": True,
                    "checks": [{"type": "custom", "value": "ok"}],
                }
            ],
        }

        report = run_contract(
            FakePoco([FakeNode("Root")]),
            manifest,
            checkers={"custom": lambda runner, node, check, contract: None},
        )

        assert report.passed, report.format()

    @pytest.mark.parametrize(("child_count", "expected", "passed"), [(3, 3, True), (2, 3, False)])
    def test_drawio_child_count_checks_direct_children(self, child_count, expected, passed):
        root = FakeNode("Root")
        for index in range(child_count):
            child = root.add(FakeNode(f"Child{index}"))
            child.add(FakeNode("Grandchild"))

        manifest = {
            "schemaVersion": 1,
            "root": "root",
            "objects": [{
                "testId": "root",
                "base": None,
                "pathMode": "name_chain",
                "path": ["Root"],
                "exist": True,
                "childCount": expected,
            }],
        }

        report = run_contract(FakePoco([root]), manifest)

        assert report.passed is passed, report.format()
        if not passed:
            assert "expected direct child count=3, got 2" in report.format()

    def test_texture_image_match_uses_unique_texture_check_target(self, monkeypatch):
        check = {
            "type": "texture_image_match",
            "image": "missing-reference.png",
        }
        explicit_texture_check = {
            "type": "texture",
            "target": {"type": "offspring", "names": ["I_Icon"]},
            "expected": "booster_sort",
        }
        resolved = []
        monkeypatch.setitem(sys.modules, "cv2", ModuleType("cv2"))
        monkeypatch.setitem(sys.modules, "numpy", ModuleType("numpy"))

        result = texture_checkers.check_texture_image_match(
            SimpleNamespace(resolve_target=lambda node, target: resolved.append(target) or node),
            object(),
            check,
            SimpleNamespace(checks=(explicit_texture_check, check)),
        )

        assert resolved == [explicit_texture_check["target"]]
        assert result is not None
        assert "reference image does not exist" in result

    def test_texture_image_match_requires_texture_check(self, monkeypatch):
        check = {
            "type": "texture_image_match",
            "image": "missing-reference.png",
        }
        monkeypatch.setitem(sys.modules, "cv2", ModuleType("cv2"))
        monkeypatch.setitem(sys.modules, "numpy", ModuleType("numpy"))

        result = texture_checkers.check_texture_image_match(
            SimpleNamespace(),
            object(),
            check,
            SimpleNamespace(checks=(check,)),
        )

        assert result == "texture_image_match requires exactly one texture check, got 0"

    def test_object_rejects_multiple_texture_checks(self):
        manifest = {
            "schemaVersion": 1,
            "root": "root",
            "objects": [{
                "testId": "root",
                "base": None,
                "path": {"mode": "name_chain", "names": ["Root"]},
                "exist": True,
                "checks": [
                    {"type": "texture", "expected": "one"},
                    {"type": "texture", "expected": "two"},
                ],
            }],
        }

        with pytest.raises(ManifestError, match="at most one texture check"):
            run_contract(FakePoco([FakeNode("Root")]), manifest)

    def test_invalid_metadata_is_rejected(self):
        invalid = b"""<mxGraphModel><root>
          <mxCell id='0'/><mxCell id='1' parent='0'/>
          <object id='one' metadataRole='ui_object' testId='same' base='' pathMode='name_chain' path='Root' exist='true' checks='[]'/>
          <object id='two' metadataRole='ui_object' testId='same' base='' pathMode='name_chain' path='Root2' exist='true' checks='[]'/>
        </root></mxGraphModel>"""

        with pytest.raises(ManifestError):
            parse_drawio_xml(invalid)

    def test_manifest_root_must_match_declared_root_object(self):
        manifest = {
            "schemaVersion": 1,
            "root": "wrong",
            "objects": [
                {
                    "testId": "root",
                    "base": None,
                    "pathMode": "name_chain",
                    "path": ["Root"],
                    "exist": True,
                    "checks": [],
                }
            ],
        }

        with pytest.raises(ManifestError):
            run_contract(FakePoco([FakeNode("Root")]), manifest)
