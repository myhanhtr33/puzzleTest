# UI Contracts

This document is the authoring guide for customer-pack UI contracts. Use it when drawing or updating a pack diagram: the diagram describes how to find and validate UI objects, and (for purchase flows) the relationship between a buy product and its rewards. Keep pack data isolated by Unity project; each project/bundle pair has one strict Draw.io source and one generated JSON manifest:

```text
locator generator/<ProjectName>/IAP_<BundleName>.drawio
locator generator/<ProjectName>/IAP_<BundleName>.json
tests/ui_fakes/<project_name>/<bundle_name>.py
```

The Draw.io file is the source of truth. Create each testable node as a Draw.io `<object>` and put the contract attributes in **Edit Data**. The generated JSON manifest is derived output; do not edit it by hand. Shared parser and purchase-flow code should consume the selected project's manifest rather than duplicate the framework. The pre-existing flat `locator generator/IAP_SmallBundle.drawio` and `.json` files are retained as BusRush compatibility files; do not use those paths for another Unity project.

## Node fields

These fields describe how the test runner locates a UI object and what it asserts about that object:

- `testId`: Required, unique ID for this node. Other nodes refer to it through `base` and `amountTextRef`.
- `base`: The `testId` whose resolved Poco object is the search scope. Leave empty only on the root node.
- `pathMode`: How to resolve `path`: `name_chain` starts from the Poco root and follows the listed names; `offspring` searches descendants under `base`; `same` selects the `base` object itself and requires an empty `path`.
- `path`: Object name, slash-separated names, or a JSON array of names. `name_chain` and `offspring` need at least one name; `same` needs none. Prefer a JSON array when names or paths could be ambiguous.
- `exist`: `true` requires the selector to find the object; `false` asserts that it is absent.
- `checks`: JSON array of assertions run on the resolved node. Supported built-ins are `texture`, `texture_image_match`, `clickable`, `component_exists`, `child_count`, and `text`. See **Check fields** below.
- `cardinality`: Number of matches allowed/required: `unique` means exactly one; `one_or_more` means at least one; `any` imposes no count requirement. Defaults to `unique`.
- `childCount` (optional): Shorthand for adding a `child_count` check to this node. Counts immediate Poco children only. Prefer `checks` when defining the check explicitly.
- `contractType` (optional, defaults to `ui`): Semantic role for pack purchase flow nodes: `ui`, `reward`, or `button`. It does not change how the node is located or its UI checks; it enables extra reward/button metadata and purchase-flow validation.
- `label` (optional): Human-readable label copied to the manifest; useful for identifying a node in reports/diagram tooling.

Edges are visual scope hints only. The `base` attribute is the executable scope.

### Check fields

Each check is a JSON object with a `type`. Its target is the node itself unless a `target` is supplied. A target can be a slash-separated path/name array, or an object such as `{"type":"offspring","names":["T_Price"]}` resolved relative to the node.

- `texture`: `expected` is the expected sprite/texture identity; optional `target` selects a child instead of the node.
- `texture_image_match`: `image` is a reference image path; optional `threshold` is a match threshold from `0` to `1`. It must be paired with exactly one `texture` check on the same node.
- `clickable`: optional boolean `expected` (defaults to requiring clickability).
- `component_exists`: required `component` name and optional boolean `expected` (defaults to requiring it).
- `child_count`: required non-negative integer `expected`; optional `target` selects which object’s immediate children to count.
- `text`: optional `target`; `format` is `literal`, `price`, `gold_amount`, `booster_amount`, or `life_duration`. `literal` uses `expected`. `price` uses numeric `amount`, non-empty `currencies`, and optional `currency_position` (`any`, `prefix`, `suffix`). `gold_amount` and `booster_amount` use `amount`. `life_duration` uses `seconds` and optional `rounding` (`exact`, `floor`, `ceil`, `nearest`).

## Pack purchase metadata

Use these fields on the diagram nodes to describe a purchasable pack and its displayed rewards. These semantic fields supplement the UI selectors/checks above; the reward nodes are also independently checked as UI contracts.

| Field | Put it on | Meaning and authoring rule |
|---|---|---|
| `contractType` | Any testable node | `ui` for ordinary UI; `button` for an actionable pack button; `reward` for a reward displayed in the pack. `ui` is the default. |
| `buttonType` | `contractType=button` | Button role: `buy`, `ads`, or `claim`. A `buy` button must have `productId` and at least one `grants` entry. |
| `productId` | Buy button | Store/IAP product identifier used to start and observe the purchase. Must match the product configured in the game/store. |
| `price` | Button | Human-readable/descriptive price metadata. It is not the executable price assertion; put the actual assertion in the button’s `checks` using a `text` check with `format=price`. |
| `grants` | Buy button | JSON string array of `rewardId` values that this product is expected to grant. This is the link from the purchased product to its reward nodes. It contains IDs, not amounts. Every ID must match a `rewardId` on a `contractType=reward` node. |
| `rewardId` | Reward node | Stable ID identifying a reward type (for example, `gold` or `booster_sort`). Keep IDs unambiguous across reward nodes and reference them from the relevant button’s `grants`. |
| `amount` | Reward node | Expected quantity/value granted. Must be a number; current units require integer values. The purchase flow uses it to compare the pre-purchase and post-purchase storage snapshots. |
| `amountUnit` | Reward node | Meaning of `amount`: `count` for item/currency quantities, or `seconds` for durations such as unlimited lives. Defaults to `count` if omitted. Must match the reward registry’s unit. |
| `amountTextRef` | Reward node (optional) | `testId` of a separate node whose text check validates the shared amount label. Use when several displayed rewards share one amount text (e.g. “x1” for all boosters). The referenced node must exist and have a `text` check; rewards sharing it must use the same amount and unit. |

### How the purchase flow uses the pack metadata

The purchase flow selects the unique node with `contractType=button` and `buttonType=buy`, uses its `productId` to initiate/watch the purchase, and reads `grants` to select applicable reward definitions. For each listed ID, it looks up a `contractType=reward` node and takes that node’s `amount` and `amountUnit` as the expected storage delta. Thus `grants` says **which rewards belong to this product**; reward-node fields say **how much of each reward is expected**. Reward nodes not listed by the buy button are still UI-checked but are not included in that product’s storage comparison.

For every pack diagram:

1. Add one root node representing the pack panel.
2. Add UI nodes for the pack title, reward containers, reward icons/text, and buy button. Give each a unique `testId`, correct `base`/`pathMode`/`path`, and checks for the visible details that matter.
3. Mark each reward whose grant must be verified with `contractType=reward`, a stable `rewardId`, `amount`, and `amountUnit`. Add the appropriate UI checks to the same node (or use `amountTextRef` when amount text is shared).
4. Mark the purchase button with `contractType=button`, `buttonType=buy`, the exact `productId`, and a `grants` JSON array containing exactly the reward IDs included in that purchase.
5. Put the price assertion in the button’s `checks`; do not rely on the descriptive `price` field for validation.
6. Ensure every ID in `grants` resolves to a reward node. Regenerate the JSON and run the bundle’s offline and real-device tests.

Example semantic metadata for a pack granting gold and one booster:

```text
Buy button: contractType=button, buttonType=buy, productId=bus_flow_inapp_8
             grants=["gold", "booster_sort"]
Gold reward: contractType=reward, rewardId=gold, amount=5000, amountUnit=count
Booster node: contractType=reward, rewardId=booster_sort, amount=1, amountUnit=count
```

The nodes still need their normal selector metadata (`testId`, `base`, `pathMode`, `path`, `exist`) and UI checks. The snippet shows only the purchase/reward fields.

The sample root uses `UIPack_SmallBundle`, matching the existing Windows Unity Editor Poco fixture and the editor-side pack rename. The prefab asset is named `UIPack_Bundle_SmallBundle` before that rename.

Convert a diagram to JSON with:

```text
python "locator generator/drawio_to_manifest.py" "locator generator/Goose/IAP_MegaBundle.drawio" -o "locator generator/Goose/IAP_MegaBundle.json"
```

Keep shared parser/checker tests in `tests/test_ui_contracts.py`. Each bundle test owns its source path, generated manifest path, fake Poco tree, offline contract checks, and real-device test.

## Editing a bundle contract

Edit the `.drawio` file first; it is the source of truth. Select a node and open **Edit Data** to add or change its metadata attributes. The metadata drives parsing and runtime checks. The shape's displayed label is separate: edit it by double-clicking the node text. To display a metadata value in the label, enable **Placeholders** in Edit Data and use `%attributeName%`, for example `childCount: %childCount%`.

Every contract-node label must be a readable mirror of the values that affect locating or checking that node. Keep these visible fields synchronized with **Edit Data**:

- All nodes: `testId`, `base`, `pathMode`, `path`, `exist`, `cardinality`, and a readable summary of every executable check and its expected value/target. Show `checks: none` when there are no checks.
- Buy button: additionally show `contractType`, `buttonType`, `productId`, descriptive `price`, the complete `grants` reward-ID list, and each check in `checks` (including clickability, components, texture, and price target/amount/currencies/position).
- Reward node: additionally show `contractType`, `rewardId`, `amount`, `amountUnit`, `amountTextRef` when set, plus all UI checks including their targets and expected values.
- For `pathMode=same`, display `path: (base object)`; an empty root `base` should display `base: (root)`. Do not display unsupported placeholder values such as `parent` as if they were the executable selector path.
- For `texture_image_match`, show the reference image filename in the diagram label; retain the complete path in metadata.

The label is documentation for diagram readers, not executable input. Runtime checks use the metadata fields in **Edit Data**. When updating those fields, update the label in the same edit. Increase the shape size or rearrange nodes when needed so no important label text is clipped. Decorative or explanatory shapes should be marked `testIgnore=true` and styled/labeled as notes so they cannot be mistaken for test nodes.

Update existing checks in the node's `checks` JSON array. For example, a literal text check can expect a renamed UI label:

```json
[{"type":"text","format":"literal","expected":"Car Bundle"}]
```

A price check stores its expected price in `amount`:

```json
{"type":"text","format":"price","target":{"type":"offspring","names":["I_Inside","T_Price"]},"amount":"7.99","currencies":["$"],"currency_position":"any"}
```

The `price` metadata on a buy button is descriptive; the executable price assertion is configured in `checks`. The `price` text check validates both the numeric amount and one listed currency. Use `currency_position: "suffix"` for text such as `7.99$`.

The `childCount` metadata attribute adds a `child_count` check for the node. It compares the node's immediate Poco children (`len(node.children())`) to a non-negative integer. For example, set `childCount` to `3` to require exactly three direct children; grandchildren are not counted. Other arbitrary metadata attributes do not automatically become checks: use an existing supported check type in `checks`, or implement and register a new checker as described below.

To add a testable node, create a shape or duplicate a similar one, then set its object metadata in Edit Data:

- Give it a unique `testId`.
- Set `base` to the `testId` of the node whose Poco object is the scope. Use an empty value only for the root.
- Set `pathMode` and `path` to resolve the UI object. For a named descendant, use `pathMode=offspring` and a path such as `/RewardIcon`; for a root, use `name_chain`.
- Set `exist`, `checks`, and `cardinality` as required.

An edge to another shape is only a visual scope hint; it does not replace the `base` metadata. Update the displayed label separately if it should show the node's new data.

After editing the diagram, regenerate the JSON manifest from the repository root. Do not edit the generated JSON by hand:

```text
python "locator generator/drawio_to_manifest.py" "locator generator/Goose/IAP_SmallBundle.drawio" -o "locator generator/Goose/IAP_SmallBundle.json"
```

Run the bundle's offline tests to check diagram parsing, generated-manifest parity, and fake-Poco behavior. If the diagram's testable-node count changes, update the corresponding expected count in `tests/test_iap_<bundle_name>_contract.py`. Then run the real-device test against Unity/Poco to verify the selectors and check expectations against the current UI.

When pytest-html export is enabled, calls to `run_contract` are automatically included in the report's assertion table. `texture_image_match` checks also capture and attach debug images; no per-bundle report code is needed.

## Adding a check type

Built-in runtime checks live in `utils/ui_contract_checks/`, grouped by concern:

- `texture.py`: texture identity and screenshot/template matching
- `interaction.py`: clickability and component presence
- `text.py`: literal, price, gold, booster, and duration text formats

To add a new check, implement a function in the appropriate module with the signature
`check_<name>(runner, node, check, contract) -> str | None`. Return `None` on success
or a readable failure message. Register it in that module's `CHECKERS` dictionary;
`utils.ui_contract_checks.DEFAULT_CHECKERS` assembles those dictionaries for the runner.
The manifest uses `{"type": "<name>", ...}`. Add schema validation in
`utils/ui_contracts.py::_validate_checks` when the check has required fields or constrained
values, and add offline coverage in `tests/test_ui_contracts.py`. Custom checkers can
still be passed to `run_contract(..., checkers={"<name>": function})`.

Use the existing session-scoped `poco` and `dev` fixtures from `tests/conftest.py` in a real-device integration test:

```python
from pathlib import Path

import pytest

from utils.ui_contracts import assert_contract, load_manifest


@pytest.mark.real_device
def test_iap_small_bundle_contract(poco, dev):
    path = Path(__file__).parents[1] / "locator generator" / "Goose" / "IAP_MegaBundle.json"
    assert_contract(poco, load_manifest(path))
```

For the current small bundle, run the bundle-specific offline tests with:

```text
python -m pytest tests/test_iap_small_bundle_contract.py::TestUIContractOffline -v
```

Run shared framework tests with:

```text
python -m pytest tests/test_ui_contracts.py -v
```

Run the small-bundle real-device contract with:

```text
python -m pytest tests/test_iap_small_bundle_contract.py::TestUIContractRealDevice -m real_device -v
```
