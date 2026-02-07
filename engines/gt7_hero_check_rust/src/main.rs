use clap::Parser;
use rusqlite::{Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(name = "gt7-hero-check")]
struct Args {
    #[arg(long)]
    manifest: PathBuf,
    #[arg(long, default_value_t = 3)]
    hero_min: i64,
    #[arg(long = "db", required = true)]
    db_paths: Vec<PathBuf>,
}

#[derive(Debug, Serialize, Deserialize)]
struct Manifest {
    #[serde(default)]
    counts: HashMap<String, i64>,
}

#[derive(Debug, Serialize)]
struct DiffRow {
    db: String,
    car_id: String,
    expected: String,
    actual: i64,
    reason: String,
}

#[derive(Debug, Serialize)]
struct Output {
    checked_rows: i64,
    diffs: Vec<DiffRow>,
}

fn load_manifest(path: &PathBuf) -> Result<HashMap<String, i64>, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("failed to read manifest: {e}"))?;
    let parsed: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| format!("invalid manifest json: {e}"))?;
    if let Ok(payload) = serde_json::from_value::<Manifest>(parsed.clone()) {
        if !payload.counts.is_empty() {
            return Ok(payload.counts);
        }
    }
    if let Ok(map) = serde_json::from_value::<HashMap<String, i64>>(parsed) {
        return Ok(map);
    }
    Err("manifest does not contain count map".to_string())
}

fn collect_db_hero_counts(
    db_path: &PathBuf,
) -> Result<(Vec<String>, HashMap<String, i64>), String> {
    let conn = Connection::open(db_path).map_err(|e| format!("open db failed: {e}"))?;
    let mut car_ids = Vec::new();
    {
        let mut stmt = conn
            .prepare("SELECT id FROM cars")
            .map_err(|e| format!("query cars failed: {e}"))?;
        let rows = stmt
            .query_map([], |row| row.get::<_, String>(0))
            .map_err(|e| format!("query cars failed: {e}"))?;
        for row in rows {
            car_ids.push(row.map_err(|e| format!("read car id failed: {e}"))?);
        }
    }

    let has_images: Option<i64> = conn
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='car_images' LIMIT 1",
            [],
            |row| row.get(0),
        )
        .optional()
        .map_err(|e| format!("check table failed: {e}"))?;
    if has_images.is_none() {
        return Ok((car_ids, HashMap::new()));
    }

    let mut hero_map = HashMap::new();
    {
        let mut stmt = conn
            .prepare(
                "SELECT car_id, COUNT(*) FROM car_images WHERE image_type='hero' GROUP BY car_id",
            )
            .map_err(|e| format!("query hero counts failed: {e}"))?;
        let rows = stmt
            .query_map([], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
            })
            .map_err(|e| format!("query hero counts failed: {e}"))?;
        for row in rows {
            let (car_id, count) = row.map_err(|e| format!("read hero row failed: {e}"))?;
            hero_map.insert(car_id, count);
        }
    }

    Ok((car_ids, hero_map))
}

fn main() {
    let args = Args::parse();
    let hero_min = args.hero_min.max(1);
    let expected = match load_manifest(&args.manifest) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1);
        }
    };
    if expected.is_empty() {
        eprintln!("manifest empty");
        std::process::exit(1);
    }

    let mut checked_rows: i64 = 0;
    let mut diffs: Vec<DiffRow> = Vec::new();

    for db_path in &args.db_paths {
        let db_name = db_path
            .file_name()
            .map(|v| v.to_string_lossy().to_string())
            .unwrap_or_else(|| db_path.to_string_lossy().to_string());
        let (car_ids, hero_map) = match collect_db_hero_counts(db_path) {
            Ok(v) => v,
            Err(e) => {
                eprintln!("{}: {}", db_name, e);
                std::process::exit(1);
            }
        };
        checked_rows += car_ids.len() as i64;
        for car_id in car_ids {
            let actual = *hero_map.get(&car_id).unwrap_or(&0);
            if let Some(exp) = expected.get(&car_id) {
                if actual != *exp {
                    diffs.push(DiffRow {
                        db: db_name.clone(),
                        car_id,
                        expected: exp.to_string(),
                        actual,
                        reason: "mismatch_with_reference".to_string(),
                    });
                }
            } else if actual < hero_min {
                diffs.push(DiffRow {
                    db: db_name.clone(),
                    car_id,
                    expected: format!(">={hero_min}"),
                    actual,
                    reason: "below_min_without_reference".to_string(),
                });
            }
        }
    }

    let payload = Output { checked_rows, diffs };
    match serde_json::to_string(&payload) {
        Ok(text) => println!("{text}"),
        Err(e) => {
            eprintln!("failed to serialize output: {e}");
            std::process::exit(1);
        }
    }
}
