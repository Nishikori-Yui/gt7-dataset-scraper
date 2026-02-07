#include <filesystem>
#include <iostream>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <sqlite3.h>

namespace fs = std::filesystem;

struct Config {
  std::string out_dir = "./output";
  std::string base_locale = "gb";
  std::string locales;
  std::string combined_db;
  bool include_fetch_log = true;
  bool checkpoint = true;
};

std::string quote_sql(const std::string& value) {
  std::string out;
  out.reserve(value.size() + 2);
  out.push_back('\'');
  for (char ch : value) {
    if (ch == '\'') {
      out.push_back('\'');
    }
    out.push_back(ch);
  }
  out.push_back('\'');
  return out;
}

std::string json_escape(const std::string& value) {
  std::string out;
  out.reserve(value.size() + 2);
  for (char ch : value) {
    if (ch == '\\' || ch == '"') {
      out.push_back('\\');
      out.push_back(ch);
      continue;
    }
    out.push_back(ch);
  }
  return out;
}

void exec_sql(sqlite3* db, const std::string& sql) {
  char* err = nullptr;
  int rc = sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &err);
  if (rc != SQLITE_OK) {
    std::string msg = err ? err : "sqlite error";
    sqlite3_free(err);
    throw std::runtime_error(msg + " | sql=" + sql);
  }
}

bool table_exists(sqlite3* db, const std::string& schema, const std::string& table) {
  std::string sql = "SELECT 1 FROM " + schema + ".sqlite_master WHERE type='table' AND name=? LIMIT 1";
  sqlite3_stmt* stmt = nullptr;
  int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
  if (rc != SQLITE_OK) {
    if (stmt) sqlite3_finalize(stmt);
    throw std::runtime_error(sqlite3_errmsg(db));
  }
  sqlite3_bind_text(stmt, 1, table.c_str(), -1, SQLITE_TRANSIENT);
  rc = sqlite3_step(stmt);
  bool exists = (rc == SQLITE_ROW);
  sqlite3_finalize(stmt);
  return exists;
}

std::vector<std::string> split_locales(const std::string& raw) {
  std::vector<std::string> out;
  std::set<std::string> seen;
  std::stringstream ss(raw);
  std::string item;
  while (std::getline(ss, item, ',')) {
    if (item.empty()) continue;
    if (!seen.insert(item).second) continue;
    out.push_back(item);
  }
  return out;
}

std::vector<std::string> discover_locales(const fs::path& out_dir) {
  std::vector<std::string> out;
  std::regex pattern(R"(^gt7\.([a-zA-Z0-9_]+)\.db$)");
  std::set<std::string> seen;
  for (const auto& entry : fs::directory_iterator(out_dir)) {
    if (!entry.is_regular_file()) continue;
    std::smatch match;
    const std::string name = entry.path().filename().string();
    if (!std::regex_match(name, match, pattern)) continue;
    if (match.size() < 2) continue;
    std::string locale = match[1].str();
    if (locale.empty()) continue;
    if (!seen.insert(locale).second) continue;
    out.push_back(locale);
  }
  return out;
}

std::vector<std::string> normalize_locale_order(const std::vector<std::string>& locales, const std::string& base) {
  std::vector<std::string> out;
  std::set<std::string> seen;
  if (!base.empty()) {
    out.push_back(base);
    seen.insert(base);
  }
  for (const auto& locale : locales) {
    if (!seen.insert(locale).second) continue;
    out.push_back(locale);
  }
  return out;
}

void merge_locale(sqlite3* db, const std::string& locale, const fs::path& src_db, bool include_fetch_log) {
  sqlite3_stmt* stmt = nullptr;
  std::string attach_sql = "ATTACH ? AS src";
  if (sqlite3_prepare_v2(db, attach_sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) {
    if (stmt) sqlite3_finalize(stmt);
    throw std::runtime_error(sqlite3_errmsg(db));
  }
  sqlite3_bind_text(stmt, 1, src_db.string().c_str(), -1, SQLITE_TRANSIENT);
  int step_rc = sqlite3_step(stmt);
  sqlite3_finalize(stmt);
  if (step_rc != SQLITE_DONE) {
    throw std::runtime_error("attach failed: " + std::string(sqlite3_errmsg(db)));
  }

  try {
    exec_sql(db, "BEGIN");
    exec_sql(db,
             "INSERT OR IGNORE INTO manufacturers(id, name, logo_path, country_id) "
             "SELECT id, name, logo_path, country_id FROM src.manufacturers");
    exec_sql(db,
             "INSERT OR IGNORE INTO manufacturer_i18n(id, locale, name) "
             "SELECT id, locale, name FROM src.manufacturer_i18n");
    exec_sql(db,
             "INSERT OR IGNORE INTO aspiration_codes(code, default_name) "
             "SELECT code, default_name FROM src.aspiration_codes");
    exec_sql(db,
             "INSERT OR IGNORE INTO drivetrain_codes(code, default_name) "
             "SELECT code, default_name FROM src.drivetrain_codes");
    exec_sql(db,
             "INSERT OR IGNORE INTO cars("
             "id, name, manufacturer_id, aspiration_code, drivetrain_code, intro, detail, car_class, pp, year, raw_json"
             ") "
             "SELECT id, name, manufacturer_id, aspiration_code, drivetrain_code, intro, detail, car_class, pp, year, raw_json "
             "FROM src.cars");

    const std::string locale_q = quote_sql(locale);

    exec_sql(db, "DELETE FROM aspiration_i18n WHERE locale=" + locale_q);
    exec_sql(db,
             "INSERT INTO aspiration_i18n(code, locale, label) "
             "SELECT code, locale, label FROM src.aspiration_i18n WHERE locale=" + locale_q);

    exec_sql(db, "DELETE FROM drivetrain_i18n WHERE locale=" + locale_q);
    exec_sql(db,
             "INSERT INTO drivetrain_i18n(code, locale, label) "
             "SELECT code, locale, label FROM src.drivetrain_i18n WHERE locale=" + locale_q);

    exec_sql(db, "DELETE FROM spec_code_i18n WHERE locale=" + locale_q);
    exec_sql(db,
             "INSERT INTO spec_code_i18n(code, locale, label) "
             "SELECT code, locale, label FROM src.spec_code_i18n WHERE locale=" + locale_q);

    exec_sql(db, "DELETE FROM country_i18n WHERE locale=" + locale_q);
    exec_sql(db,
             "INSERT INTO country_i18n(iso3, locale, name) "
             "SELECT iso3, locale, name FROM src.country_i18n WHERE locale=" + locale_q);

    exec_sql(db, "DELETE FROM car_texts WHERE locale=" + locale_q);
    exec_sql(db,
             "INSERT INTO car_texts(car_id, locale, name, intro, detail) "
             "SELECT car_id, locale, name, intro, detail FROM src.car_texts WHERE locale=" + locale_q);

    exec_sql(db, "DELETE FROM car_specs WHERE locale=" + locale_q);
    exec_sql(db,
             "INSERT INTO car_specs(car_id, locale, spec_key, spec_value, spec_unit, spec_raw, sort_order) "
             "SELECT car_id, locale, spec_key, spec_value, spec_unit, spec_raw, sort_order "
             "FROM src.car_specs WHERE locale=" + locale_q);

    if (include_fetch_log) {
      exec_sql(db, "DELETE FROM fetch_log WHERE locale=" + locale_q);
      exec_sql(db,
               "INSERT INTO fetch_log(car_id, locale, status, message, updated_at) "
               "SELECT car_id, locale, status, message, updated_at FROM src.fetch_log WHERE locale=" + locale_q);
    }

    const bool target_has_images = table_exists(db, "main", "car_images");
    const bool source_has_images = table_exists(db, "src", "car_images");
    if (target_has_images && source_has_images) {
      exec_sql(db,
               "INSERT INTO car_images(car_id, image_path, sort_order, image_type) "
               "SELECT s.car_id, s.image_path, s.sort_order, s.image_type "
               "FROM src.car_images s "
               "WHERE NOT EXISTS ("
               "  SELECT 1 FROM car_images d "
               "  WHERE d.car_id=s.car_id "
               "    AND d.image_path=s.image_path "
               "    AND COALESCE(d.image_type,'')=COALESCE(s.image_type,'')"
               ")");
    }

    exec_sql(db, "COMMIT");
  } catch (...) {
    try {
      exec_sql(db, "ROLLBACK");
    } catch (...) {
    }
    try {
      exec_sql(db, "DETACH src");
    } catch (...) {
    }
    throw;
  }
  exec_sql(db, "DETACH src");
}

Config parse_args(int argc, char** argv) {
  Config cfg;
  for (int index = 1; index < argc; ++index) {
    std::string arg = argv[index];
    auto next_value = [&](const std::string& name) -> std::string {
      if (index + 1 >= argc) {
        throw std::runtime_error("missing value for " + name);
      }
      ++index;
      return argv[index];
    };

    if (arg == "--out-dir") {
      cfg.out_dir = next_value(arg);
    } else if (arg == "--base-locale") {
      cfg.base_locale = next_value(arg);
    } else if (arg == "--locales") {
      cfg.locales = next_value(arg);
    } else if (arg == "--combined-db") {
      cfg.combined_db = next_value(arg);
    } else if (arg == "--include-fetch-log") {
      cfg.include_fetch_log = true;
    } else if (arg == "--no-include-fetch-log") {
      cfg.include_fetch_log = false;
    } else if (arg == "--checkpoint") {
      cfg.checkpoint = true;
    } else if (arg == "--no-checkpoint") {
      cfg.checkpoint = false;
    } else if (arg == "-h" || arg == "--help") {
      std::cout
          << "Usage: gt7-db-merge --out-dir <dir> --base-locale <locale> [--locales a,b] [--combined-db path] "
          << "[--include-fetch-log|--no-include-fetch-log] [--checkpoint|--no-checkpoint]\n";
      std::exit(0);
    } else {
      throw std::runtime_error("unknown argument: " + arg);
    }
  }
  return cfg;
}

int main(int argc, char** argv) {
  try {
    Config cfg = parse_args(argc, argv);

    fs::path out_dir(cfg.out_dir);
    if (!fs::exists(out_dir)) {
      throw std::runtime_error("out-dir does not exist: " + out_dir.string());
    }

    std::vector<std::string> locales = cfg.locales.empty() ? discover_locales(out_dir) : split_locales(cfg.locales);
    if (locales.empty()) {
      throw std::runtime_error("no locales to merge");
    }

    bool base_included = false;
    for (const auto& locale : locales) {
      if (locale == cfg.base_locale) {
        base_included = true;
        break;
      }
    }
    if (!base_included) {
      throw std::runtime_error("base locale not included in locales");
    }

    std::vector<std::string> ordered_locales = normalize_locale_order(locales, cfg.base_locale);

    fs::path base_db = out_dir / ("gt7." + cfg.base_locale + ".db");
    if (!fs::exists(base_db)) {
      throw std::runtime_error("base db not found: " + base_db.string());
    }

    fs::path combined_db = cfg.combined_db.empty() ? (out_dir / "gt7.db") : fs::path(cfg.combined_db);
    fs::create_directories(combined_db.parent_path());
    fs::copy_file(base_db, combined_db, fs::copy_options::overwrite_existing);

    sqlite3* db = nullptr;
    if (sqlite3_open(combined_db.string().c_str(), &db) != SQLITE_OK) {
      std::string msg = db ? sqlite3_errmsg(db) : "sqlite3_open failed";
      if (db) sqlite3_close(db);
      throw std::runtime_error(msg);
    }

    try {
      exec_sql(db, "PRAGMA journal_mode=WAL");
      exec_sql(db, "PRAGMA synchronous=NORMAL");

      for (const auto& locale : ordered_locales) {
        if (locale == cfg.base_locale) continue;
        fs::path src_db = out_dir / ("gt7." + locale + ".db");
        if (!fs::exists(src_db)) {
          throw std::runtime_error("locale db not found: " + src_db.string());
        }
        merge_locale(db, locale, src_db, cfg.include_fetch_log);
      }

      std::ostringstream locales_json;
      locales_json << "[";
      for (size_t index = 0; index < ordered_locales.size(); ++index) {
        if (index > 0) locales_json << ",";
        locales_json << "\"" << json_escape(ordered_locales[index]) << "\"";
      }
      locales_json << "]";

      exec_sql(db,
               "INSERT INTO meta(key, value) VALUES('build_base_locale', " + quote_sql(cfg.base_locale) + ") "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value");
      exec_sql(db,
               "INSERT INTO meta(key, value) VALUES('build_locales', " + quote_sql(locales_json.str()) + ") "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value");

      if (cfg.checkpoint) {
        exec_sql(db, "PRAGMA wal_checkpoint(TRUNCATE)");
        exec_sql(db, "PRAGMA journal_mode=DELETE");
      }

      sqlite3_close(db);
    } catch (...) {
      sqlite3_close(db);
      throw;
    }

    std::cout << "merged locales=";
    for (size_t index = 0; index < ordered_locales.size(); ++index) {
      if (index > 0) std::cout << ",";
      std::cout << ordered_locales[index];
    }
    std::cout << " base=" << cfg.base_locale << " into " << combined_db.string() << std::endl;
    return 0;
  } catch (const std::exception& exc) {
    std::cerr << "gt7-db-merge error: " << exc.what() << std::endl;
    return 2;
  }
}
