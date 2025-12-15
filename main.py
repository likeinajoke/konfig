import sys
import xml.etree.ElementTree as ET
from typing import Any, Dict
from lark import Lark, Transformer, v_args, UnexpectedInput, UnexpectedToken, Token
from xml.dom import minidom


# --- ГРАММАТИКА ---
grammar = r"""
    %import common.WS
    %ignore WS
    %ignore COMMENT

    ?start: statement*

    ?statement: set_decl | dict_entry

    set_decl: "set" IDENT "=" value ";"        -> set_constant
    dict_entry: IDENT ":" value ";"            -> dict_item

    ?value: number
          | array
          | dict
          | constant_ref
          | prefix_expr

    array: "{" (value ("," value)*)? "}"       -> make_array
    dict: "$[" (dict_item_internal ("," dict_item_internal)*)? "]" -> make_dict
    dict_item_internal: IDENT ":" value        -> dict_item_inner

    constant_ref: IDENT                        -> ref_constant

    prefix_expr: "(" OPERATOR value+ ")"       -> eval_prefix

    number: HEX_NUMBER
    HEX_NUMBER: /0[xX][0-9a-fA-F]+/

    OPERATOR: "+" | "-" | "*" | "pow"

    IDENT: /[_a-zA-Z][_a-zA-Z0-9]*/

    COMMENT: /--\[\[[\s\S]*?\]\]/
"""


class ConfigTransformer(Transformer):
    def __init__(self):
        super().__init__()
        self.constants: Dict[str, Any] = {}
        self.errors = []

    def number(self, items):
        return int(items[0], 16)

    def IDENT(self, token: Token):
        return token

    @v_args(inline=True)
    def set_constant(self, name, value):
        self.constants[name.value] = value
        return None

    @v_args(inline=True)
    def dict_item(self, key, value):
        return key.value, value

    @v_args(inline=True)
    def make_array(self, *items):
        return list(items)

    @v_args(inline=True)
    def make_dict(self, *items):
        return dict(items)

    @v_args(inline=True)
    def dict_item_inner(self, key, value):
        return key.value, value

    @v_args(inline=True)
    def ref_constant(self, name):
        if name.value not in self.constants:
            self.errors.append(
                f"Undefined constant '{name.value}' at line {name.line}"
            )
            return None
        return self.constants[name.value]

    @v_args(inline=True)
    def eval_prefix(self, op, *args):
        op = op.value
        nums = list(args)

        if op == "+":
            return sum(nums)
        if op == "-":
            return -nums[0] if len(nums) == 1 else nums[0] - sum(nums[1:])
        if op == "*":
            result = 1
            for n in nums:
                result *= n
            return result
        if op == "pow":
            return pow(nums[0], nums[1])

        self.errors.append(f"Unknown operator '{op}'")
        return None

    def start(self, items):
        result = {}
        for item in items:
            if isinstance(item, tuple):
                key, value = item
                result[key] = value
        return result


class ConfigParser:
    def __init__(self, text: str):
        self.text = text
        self.parser = Lark(grammar, parser="lalr", propagate_positions=True)
        self.transformer = ConfigTransformer()
        self.errors = []

    def parse(self) -> Dict[str, Any]:
        try:
            tree = self.parser.parse(self.text)
            result = self.transformer.transform(tree)
            self.errors = self.transformer.errors
            return result
        except UnexpectedInput as e:
            self.errors.append(str(e))
            return {}


# ---------- XML ----------

def dict_to_xml(data: Any) -> ET.Element:
    root = ET.Element("config")
    _to_xml(data, root)
    return root


def _to_xml(data: Any, parent: ET.Element):
    if isinstance(data, dict):
        for key, value in data.items():
            elem = ET.SubElement(parent, "entry", name=key)
            _to_xml(value, elem)

    elif isinstance(data, list):
        for i, item in enumerate(data):
            elem = ET.SubElement(parent, "array_item", index=str(i))
            _to_xml(item, elem)

    else:
        parent.text = str(data)


# ---------- MAIN ----------

def main():
    if len(sys.argv) != 2:
        print("Usage: python script.py <config_file>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        text = f.read()

    parser = ConfigParser(text)
    result = parser.parse()

    if parser.errors:
        for err in parser.errors:
            print("Error:", err, file=sys.stderr)
        sys.exit(1)

    xml = dict_to_xml(result)

    rough_string = ET.tostring(xml, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ")

    print(pretty_xml)


if __name__ == "__main__":
    main()
