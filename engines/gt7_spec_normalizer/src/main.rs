use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha1::{Digest, Sha1};
use std::collections::{HashMap, HashSet};
use std::env;
use std::fs;
use std::io::{self, Read};
use std::path::PathBuf;

#[derive(Deserialize)]
struct SpecInputPayload {
    locale: String,
    specs: Vec<(String, String)>,
}

#[derive(Deserialize)]
struct CodesInputPayload {
    locale: String,
    aspiration: Option<String>,
    aspiration_short: Option<String>,
    drivetrain: Option<String>,
}

#[derive(Serialize)]
struct SpecRow {
    spec_key: String,
    spec_label: String,
    spec_value: String,
    spec_unit: String,
    spec_raw: String,
    locale: String,
    sort_order: usize,
}

#[derive(Serialize)]
struct CodesOutput {
    aspiration_code: Option<String>,
    aspiration_label: Option<String>,
    drivetrain_code: Option<String>,
    drivetrain_label: Option<String>,
}

fn normalize_unit_text(text: &str) -> String {
    text.to_lowercase().replace(' ', "")
}

fn infer_spec_code(raw_value: &str, dim_index: usize) -> (Option<String>, usize) {
    let value = raw_value.trim();
    let norm = normalize_unit_text(value);
    let drivetrain_codes: HashSet<&str> =
        ["FR", "FF", "MR", "RR", "4WD", "AWD"].into_iter().collect();
    if drivetrain_codes.contains(value) {
        return (Some("drivetrain".to_string()), dim_index);
    }
    let asp_re = Regex::new(r"^[A-Z]{1,3}").expect("invalid regex");
    if asp_re.is_match(value) {
        if ["NA", "TC", "SC", "EV", "HV"]
            .iter()
            .any(|prefix| value.starts_with(prefix))
        {
            return (Some("aspiration".to_string()), dim_index);
        }
    }
    let displacement_units = ["cc", "cm³", "cm3", "立方厘米", "см³"];
    if displacement_units.iter().any(|u| norm.contains(u)) {
        return (Some("displacement".to_string()), dim_index);
    }
    let rpm_tokens = [
        "rpm",
        "r/min",
        "u/min",
        "tr/min",
        "g/min",
        "ob/min",
        "об/мин",
        "ot/min",
        "转每分",
        "轉每分",
        "รอบ/นาที",
        "รอบต่อนาที",
        "دورة في الدقيقة",
    ];
    let power_units = [
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
    ];
    let torque_units = [
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
        "公斤力米",
    ];
    if value.contains('/') && rpm_tokens.iter().any(|t| norm.contains(t)) {
        let left = value.split('/').next().unwrap_or("").trim();
        let left_norm = normalize_unit_text(left);
        if power_units.iter().any(|u| left_norm.contains(u)) {
            return (Some("max_power".to_string()), dim_index);
        }
        if torque_units.iter().any(|u| left_norm.contains(u)) {
            return (Some("max_torque".to_string()), dim_index);
        }
    }
    if power_units.iter().any(|u| norm.contains(u)) {
        return (Some("max_power".to_string()), dim_index);
    }
    if torque_units.iter().any(|u| norm.contains(u)) {
        return (Some("max_torque".to_string()), dim_index);
    }
    let weight_units = ["kg", "公斤", "lbs", "lb", "кг"];
    if weight_units.iter().any(|u| norm.contains(u))
        && !torque_units.iter().any(|u| norm.contains(u))
    {
        return (Some("weight".to_string()), dim_index);
    }
    let length_units = [
        "mm", "㎜", "мм", "公釐", "毫米", "in", "inch", "in.", "มม", "مم",
    ];
    if length_units.iter().any(|u| norm.contains(u)) {
        let dims = ["length", "width", "height"];
        if dim_index < dims.len() {
            return (Some(dims[dim_index].to_string()), dim_index + 1);
        }
        return (Some("dimension".to_string()), dim_index);
    }
    (None, dim_index)
}

fn parse_spec_value(raw: &str) -> (String, String) {
    (raw.trim().to_string(), "".to_string())
}

fn is_rpm_expression(text: &str) -> bool {
    let lowered = text.to_lowercase();
    [
        "rpm",
        "r/min",
        "u/min",
        "tr/min",
        "g/min",
        "ob/min",
        "об/мин",
        "ot/min",
        "转每分",
        "轉每分",
        "รอบ/นาที",
        "รอบต่อนาที",
        "دورة في الدقيقة",
    ]
    .iter()
    .any(|token| lowered.contains(token))
}

fn load_mapping(mappings_dir: &PathBuf, locale: &str) -> HashMap<String, String> {
    let path = mappings_dir.join(format!("{locale}.json"));
    let mut out = HashMap::new();
    let Ok(content) = fs::read_to_string(path) else {
        return out;
    };
    let Ok(value) = serde_json::from_str::<Value>(&content) else {
        return out;
    };
    let Some(obj) = value.as_object() else {
        return out;
    };
    for (k, v) in obj {
        if let Some(code) = v.as_str() {
            out.insert(k.to_string(), code.to_string());
        }
    }
    out
}

fn map_spec_label(
    mapping: &HashMap<String, String>,
    locale: &str,
    label: &str,
    raw_value: &str,
    dim_index: usize,
) -> (String, String, usize) {
    let trimmed = label.trim();
    if let Some(code) = mapping.get(trimmed) {
        return (code.to_string(), trimmed.to_string(), dim_index);
    }
    let (inferred, next_dim) = infer_spec_code(raw_value, dim_index);
    if let Some(code) = inferred {
        return (code, trimmed.to_string(), next_dim);
    }
    let mut hasher = Sha1::new();
    hasher.update(format!("{locale}:{trimmed}").as_bytes());
    let digest = format!("{:x}", hasher.finalize());
    let code = format!("raw_{}", &digest[..10]);
    (code, trimmed.to_string(), dim_index)
}

fn normalize_specs(payload: &SpecInputPayload, mappings_dir: &PathBuf) -> Vec<SpecRow> {
    let mapping = load_mapping(mappings_dir, &payload.locale);
    let mut rows: Vec<SpecRow> = Vec::new();
    let mut order: usize = 1;
    let mut dim_index: usize = 0;
    for (label, raw_value) in &payload.specs {
        let raw_text = raw_value.trim().to_string();
        let (spec_code, spec_label, next_dim) =
            map_spec_label(&mapping, &payload.locale, label, raw_value, dim_index);
        dim_index = next_dim;
        if (spec_code == "max_power" || spec_code == "max_torque")
            && raw_text.contains('/')
            && is_rpm_expression(&raw_text)
        {
            let mut parts = raw_text.splitn(2, '/');
            let left = parts.next().unwrap_or("").trim().to_string();
            let right = parts.next().unwrap_or("").trim().to_string();
            let (value_num, value_unit) = parse_spec_value(&left);
            let (rpm_num, rpm_unit) = parse_spec_value(&right);
            rows.push(SpecRow {
                spec_key: spec_code.clone(),
                spec_label: spec_label.clone(),
                spec_value: value_num,
                spec_unit: value_unit,
                spec_raw: left,
                locale: payload.locale.clone(),
                sort_order: order,
            });
            order += 1;
            rows.push(SpecRow {
                spec_key: format!("{spec_code}_rpm"),
                spec_label: format!("{spec_label} RPM"),
                spec_value: rpm_num,
                spec_unit: rpm_unit,
                spec_raw: right,
                locale: payload.locale.clone(),
                sort_order: order,
            });
            order += 1;
            continue;
        }
        let (value, unit) = parse_spec_value(raw_value);
        rows.push(SpecRow {
            spec_key: spec_code,
            spec_label,
            spec_value: value,
            spec_unit: unit,
            spec_raw: raw_text,
            locale: payload.locale.clone(),
            sort_order: order,
        });
        order += 1;
    }
    rows
}

fn extract_aspiration_label(raw_value: Option<&str>) -> Option<String> {
    let text = raw_value?.trim();
    if text.is_empty() {
        return None;
    }
    let re = Regex::new(r"[（(]\s*([^）)]+)\s*[）)]").ok()?;
    if let Some(captures) = re.captures(text) {
        if let Some(group) = captures.get(1) {
            let label = group.as_str().trim();
            if !label.is_empty() {
                return Some(label.to_string());
            }
        }
    }
    Some(text.to_string())
}

fn normalize_aspiration_code(raw_value: Option<&str>, short_code: Option<&str>) -> Option<String> {
    let raw = short_code.filter(|v| !v.trim().is_empty()).or(raw_value)?;
    let text = raw.trim();
    if text.is_empty() || text == "---" {
        return None;
    }
    let text_clean = text.replace(' ', "").replace('＋', "+").to_uppercase();
    if text_clean.starts_with("TC+SC") {
        return Some("TC+SC".to_string());
    }
    if Regex::new(r"^T(\b|\+)").ok()?.is_match(&text_clean) {
        return Some("TC".to_string());
    }
    for code in ["NA", "TC", "SC", "EV", "HV"] {
        if text_clean.starts_with(code) {
            return Some(code.to_string());
        }
    }

    let lower = text.to_lowercase();
    let na_tokens = [
        "自然",
        "naturally",
        "n/a",
        "na",
        "atmosfér",
        "atmosfer",
        "doğal",
        "dogal",
        "emişli",
        "ατμοσφαιρ",
        "سحب طبيعي",
        "ไม่ใช้ระบบอัดอากาศ",
    ];
    if na_tokens.iter().any(|t| lower.contains(t)) {
        return Some("NA".to_string());
    }
    let tc_tokens = ["涡轮", "渦輪", "turbo", "ターボ", "터보", "турбо"];
    if tc_tokens.iter().any(|t| lower.contains(t)) {
        return Some("TC".to_string());
    }
    let sc_tokens = [
        "机械",
        "機械",
        "supercharger",
        "スーパーチャージャ",
        "슈퍼차저",
        "kompresor",
        "kompresör",
    ];
    if sc_tokens.iter().any(|t| lower.contains(t)) {
        return Some("SC".to_string());
    }
    let ev_tokens = ["电", "電", "electric", "電気", "전기"];
    if ev_tokens.iter().any(|t| lower.contains(t)) {
        return Some("EV".to_string());
    }
    None
}

fn normalize_drivetrain_code(raw_value: Option<&str>) -> Option<String> {
    let text = raw_value?.trim();
    if text.is_empty() || text == "---" {
        return None;
    }
    let upper = text.to_uppercase().replace(' ', "");
    for code in ["FR", "FF", "MR", "RR", "4WD", "AWD"] {
        if upper == code {
            return Some(code.to_string());
        }
    }
    let cn_map = HashMap::from([
        ("前置后驱", "FR"),
        ("前置前驱", "FF"),
        ("中置后驱", "MR"),
        ("后置后驱", "RR"),
        ("四驱", "4WD"),
    ]);
    if let Some(mapped) = cn_map.get(text) {
        return Some((*mapped).to_string());
    }
    None
}

fn normalize_codes(payload: &CodesInputPayload) -> CodesOutput {
    let aspiration_code = normalize_aspiration_code(
        payload.aspiration.as_deref(),
        payload.aspiration_short.as_deref(),
    );
    let aspiration_label = extract_aspiration_label(
        payload
            .aspiration
            .as_deref()
            .or(payload.aspiration_short.as_deref()),
    );
    let drivetrain_code = normalize_drivetrain_code(payload.drivetrain.as_deref());
    let drivetrain_label = payload
        .drivetrain
        .as_ref()
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty());

    CodesOutput {
        aspiration_code,
        aspiration_label,
        drivetrain_code,
        drivetrain_label,
    }
}

fn parse_args() -> (PathBuf, String) {
    let args: Vec<String> = env::args().collect();
    let mut mappings = PathBuf::from("./gt7_scraper/mappings/spec_labels");
    let mut mode = "specs".to_string();
    let mut idx = 0usize;
    while idx < args.len() {
        if args[idx] == "--mappings-dir" && idx + 1 < args.len() {
            mappings = PathBuf::from(args[idx + 1].clone());
            idx += 1;
        } else if args[idx] == "--mode" && idx + 1 < args.len() {
            mode = args[idx + 1].clone();
            idx += 1;
        }
        idx += 1;
    }
    (mappings, mode)
}

fn main() {
    let (mappings_dir, mode) = parse_args();
    let mut input = String::new();
    if let Err(err) = io::stdin().read_to_string(&mut input) {
        eprintln!("{err}");
        std::process::exit(2);
    }

    if mode == "codes" {
        let payload: CodesInputPayload = match serde_json::from_str(&input) {
            Ok(value) => value,
            Err(err) => {
                eprintln!("{err}");
                std::process::exit(2);
            }
        };
        let output = normalize_codes(&payload);
        match serde_json::to_string(&output) {
            Ok(text) => println!("{text}"),
            Err(err) => {
                eprintln!("{err}");
                std::process::exit(2);
            }
        }
        return;
    }

    let payload: SpecInputPayload = match serde_json::from_str(&input) {
        Ok(value) => value,
        Err(err) => {
            eprintln!("{err}");
            std::process::exit(2);
        }
    };
    let rows = normalize_specs(&payload, &mappings_dir);
    match serde_json::to_string(&rows) {
        Ok(text) => println!("{text}"),
        Err(err) => {
            eprintln!("{err}");
            std::process::exit(2);
        }
    }
}
