import hashlib
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import json5

_SPEC_LABEL_CACHE: Dict[str, Dict[str, str]] = {}


def _load_label_map(locale: str) -> Dict[str, str]:
    if locale in _SPEC_LABEL_CACHE:
        return _SPEC_LABEL_CACHE[locale]
    base = Path(__file__).resolve().parent / "mappings" / "spec_labels"
    path = base / f"{locale}.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                _SPEC_LABEL_CACHE[locale] = data
                return data
    _SPEC_LABEL_CACHE[locale] = {}
    return {}


DRIVETRAIN_CODES = {"FR", "FF", "MR", "RR", "4WD", "AWD"}
POWER_UNITS = {
    "hp",
    "ps",
    "bhp",
    "kw",
    "ch",
    "cv",
    "pk",
    "k.s.",
    "ks",
    "к.с",
    "л.с",
    "마력",
    "แรงม้า",
}
TORQUE_UNITS = {
    "nm",
    "n·m",
    "n.m",
    "нм",
    "kgm",
    "kgfm",
    "kgf·m",
    "kgf-m",
    "ft-lb",
    "lb-ft",
    "\u516c\u65a4\u529b\u7c73",
}
WEIGHT_UNITS = {"kg", "\u516c\u65a4", "lbs", "lb", "кг"}
DISPLACEMENT_UNITS = {"cc", "cm³", "cm3", "\u7acb\u65b9\u5398\u7c73", "см³"}
LENGTH_UNITS = {"mm", "㎜", "мм", "\u516c\u91d0", "\u6beb\u7c73", "in", "inch", "in.", "มม", "مم"}


def _normalize_unit_text(text: str) -> str:
    return text.lower().replace(" ", "")


def infer_spec_code(label: str, raw_value: str, dim_index: int) -> Tuple[Optional[str], int]:
    value = str(raw_value).strip()
    norm = _normalize_unit_text(value)

    # drivetrain
    if value in DRIVETRAIN_CODES:
        return "drivetrain", dim_index

    # aspiration
    if re.match(r"^[A-Z]{1,3}", value):
        prefix = re.match(r"^([A-Z]{1,3})", value)
        if prefix and prefix.group(1) in {"NA", "TC", "SC", "EV", "HV"}:
            return "aspiration", dim_index

    # displacement
    if any(unit in norm for unit in DISPLACEMENT_UNITS):
        return "displacement", dim_index

    # power / torque
    if "/" in value and (
        "rpm" in norm
        or "r/min" in norm
        or "u/min" in norm
        or "tr/min" in norm
        or "g/min" in norm
        or "ob/min" in norm
        or "об/мин" in value
        or "\u8f6c\u6bcf\u5206" in value
        or "\u8f49\u6bcf\u5206" in value
        or "รอบ/นาที" in value
    ):
        left = value.split("/", 1)[0]
        left_norm = _normalize_unit_text(left)
        if any(u in left_norm for u in POWER_UNITS):
            return "max_power", dim_index
        if any(u in left_norm for u in TORQUE_UNITS):
            return "max_torque", dim_index

    if any(u in norm for u in POWER_UNITS):
        return "max_power", dim_index
    if any(u in norm for u in TORQUE_UNITS):
        return "max_torque", dim_index

    # weight
    if any(u in norm for u in WEIGHT_UNITS) and not any(u in norm for u in TORQUE_UNITS):
        return "weight", dim_index

    # dimensions
    if any(u in norm for u in LENGTH_UNITS):
        dims = ["length", "width", "height"]
        if dim_index < len(dims):
            code = dims[dim_index]
            return code, dim_index + 1
        return "dimension", dim_index

    return None, dim_index


def map_spec_label(label: str, locale: str, raw_value: Optional[str] = None, dim_index: int = 0) -> Tuple[str, str, int]:
    label = label.strip()
    mapping = _load_label_map(locale)
    if label in mapping:
        return mapping[label], label, dim_index

    if raw_value is not None:
        code, new_dim = infer_spec_code(label, raw_value, dim_index)
        if code:
            return code, label, new_dim

    # fallback to stable hashed code
    digest = hashlib.sha1(f"{locale}:{label}".encode("utf-8")).hexdigest()[:10]
    return f"raw_{digest}", label, dim_index


def extract_exported_var(js_text: str, export_name: str) -> Optional[str]:
    for match in re.finditer(r"export\s*\{([^}]+)\}", js_text):
        body = match.group(1)
        for item in body.split(","):
            part = item.strip()
            if not part:
                continue
            if " as " in part:
                local, export = [p.strip() for p in part.split(" as ", 1)]
            else:
                local = export = part
            if export == export_name:
                return local
    return None


def _extract_balanced(text: str, start: int) -> Tuple[str, int]:
    stack = []
    i = start
    in_string = False
    string_char = ""
    escape = False

    while i < len(text):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == string_char:
                in_string = False
        else:
            if ch in ('"', "'"):
                in_string = True
                string_char = ch
            elif ch in "[{":
                stack.append(ch)
            elif ch in "]}":
                if not stack:
                    break
                opening = stack.pop()
                if opening == "{" and ch != "}":
                    raise ValueError("Mismatched braces")
                if opening == "[" and ch != "]":
                    raise ValueError("Mismatched brackets")
                if not stack:
                    return text[start : i + 1], i + 1
        i += 1
    raise ValueError("Unbalanced literal in JS")


def extract_assigned_literal(js_text: str, var_name: str) -> Optional[str]:
    pattern = re.compile(rf"\b(?:const|let|var)\s+{re.escape(var_name)}\s*=\s*", re.MULTILINE)
    match = pattern.search(js_text)
    if not match:
        return None
    idx = match.end()
    while idx < len(js_text) and js_text[idx].isspace():
        idx += 1
    if idx >= len(js_text) or js_text[idx] not in "[{":
        return None
    literal, _ = _extract_balanced(js_text, idx)
    return literal


def _replace_backtick_strings(literal: str) -> str:
    out = []
    i = 0
    while i < len(literal):
        ch = literal[i]
        if ch == "`":
            i += 1
            start = i
            while i < len(literal) and literal[i] != "`":
                i += 1
            content = literal[start:i]
            out.append(json.dumps(content))
            if i < len(literal) and literal[i] == "`":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_js_literal(literal: str):
    cleaned = _replace_backtick_strings(literal)
    return json5.loads(cleaned)


def extract_exported_literal(js_text: str, export_name: str):
    local = extract_exported_var(js_text, export_name)
    if not local:
        return None
    literal = extract_assigned_literal(js_text, local)
    if not literal:
        return None
    return parse_js_literal(literal)


def find_largest_object(js_text: str):
    candidates = []
    for match in re.finditer(r"\b(?:const|let|var)\s+[A-Za-z0-9_$]+\s*=\s*\{", js_text):
        idx = match.end() - 1
        try:
            literal, end = _extract_balanced(js_text, idx)
            candidates.append((len(literal), literal))
        except ValueError:
            continue
    if not candidates:
        return None
    literal = max(candidates, key=lambda x: x[0])[1]
    return parse_js_literal(literal)


def find_largest_array(js_text: str):
    candidates = []
    for match in re.finditer(r"\b(?:const|let|var)\s+[A-Za-z0-9_$]+\s*=\s*\[", js_text):
        idx = match.end() - 1
        try:
            literal, end = _extract_balanced(js_text, idx)
            candidates.append((len(literal), literal))
        except ValueError:
            continue
    if not candidates:
        return None
    literal = max(candidates, key=lambda x: x[0])[1]
    return parse_js_literal(literal)


def parse_descriptions(js_text: str):
    export_names = ["Descriptions", "Description", "CarDescriptions", "DescriptionsData"]
    for name in export_names:
        data = extract_exported_literal(js_text, name)
        if data is not None:
            return data
    data = find_largest_object(js_text)
    if data is not None:
        return data
    data = find_largest_array(js_text)
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        out = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            car_id = item.get("id") or item.get("carId") or item.get("car_id")
            if car_id:
                out[str(car_id)] = item
        return out
    return {}


def parse_spec_value(raw: str) -> Tuple[str, str]:
    if raw is None:
        return "", ""
    raw = str(raw).strip()
    match = re.match(r"^([0-9][0-9.,\\s]*)\\s*(.*)$", raw)
    if match:
        value = match.group(1).replace(" ", "")
        unit = match.group(2).strip()
        return value, unit
    return raw, ""


def _is_rpm_expression(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in [
            "rpm",
            "r/min",
            "u/min",
            "tr/min",
            "g/min",
            "ob/min",
            "об/мин",
            "ot/min",
            "\u8f6c\u6bcf\u5206",
            "\u8f49\u6bcf\u5206",
            "รอบ/นาที",
            "รอบต่อนาที",
            "دورة في الدقيقة",
        ]
    )


def normalize_specs(specs: Iterable[Tuple[str, str]], locale: str = "us") -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    order = 1
    dim_index = 0
    for label, raw_value in specs:
        raw_text = str(raw_value).strip()
        spec_code, spec_label, dim_index = map_spec_label(str(label), locale, raw_value, dim_index)

        # Special handling for power/torque: "203 HP / 6000 rpm" or localized variants
        if spec_code in {"max_power", "max_torque"} and "/" in raw_text and _is_rpm_expression(raw_text):
            left, right = raw_text.split("/", 1)
            left = left.strip()
            right = right.strip()
            value_num, value_unit = parse_spec_value(left)
            rpm_num, rpm_unit = parse_spec_value(right)
            if value_num or rpm_num:
                out.append(
                    {
                        "spec_key": spec_code,
                        "spec_label": spec_label,
                        "spec_value": value_num,
                        "spec_unit": value_unit,
                        "spec_raw": left,
                        "locale": locale,
                        "sort_order": order,
                    }
                )
                order += 1
                out.append(
                    {
                        "spec_key": f"{spec_code}_rpm",
                        "spec_label": f"{spec_label} RPM",
                        "spec_value": rpm_num,
                        "spec_unit": rpm_unit,
                        "spec_raw": right,
                        "locale": locale,
                        "sort_order": order,
                    }
                )
                order += 1
                continue

        value, unit = parse_spec_value(raw_value)
        out.append(
            {
                "spec_key": spec_code,
                "spec_label": spec_label,
                "spec_value": value,
                "spec_unit": unit,
                "spec_raw": raw_text,
                "locale": locale,
                "sort_order": order,
            }
        )
        order += 1
    return out


def json_dumps(data) -> str:
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"))
