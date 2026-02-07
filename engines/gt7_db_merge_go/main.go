package main

import (
	"database/sql"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"

	_ "modernc.org/sqlite"
)

func must(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func parseLocales(raw string) []string {
	if strings.TrimSpace(raw) == "" {
		return nil
	}
	seen := map[string]bool{}
	var out []string
	for _, item := range strings.Split(raw, ",") {
		locale := strings.TrimSpace(item)
		if locale == "" || seen[locale] {
			continue
		}
		seen[locale] = true
		out = append(out, locale)
	}
	return out
}

func discoverLocales(outDir string) ([]string, error) {
	entries, err := os.ReadDir(outDir)
	if err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	var out []string
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || !strings.HasPrefix(name, "gt7.") || !strings.HasSuffix(name, ".db") || name == "gt7.db" {
			continue
		}
		locale := strings.TrimSuffix(strings.TrimPrefix(name, "gt7."), ".db")
		if locale == "" || seen[locale] {
			continue
		}
		seen[locale] = true
		out = append(out, locale)
	}
	slices.Sort(out)
	return out, nil
}

func normalizeLocaleOrder(locales []string, base string) []string {
	seen := map[string]bool{}
	out := []string{base}
	seen[base] = true
	for _, locale := range locales {
		if locale == "" || seen[locale] {
			continue
		}
		out = append(out, locale)
		seen[locale] = true
	}
	return out
}

func tableExists(db *sql.DB, schema, table string) (bool, error) {
	query := fmt.Sprintf("SELECT 1 FROM %s.sqlite_master WHERE type='table' AND name=? LIMIT 1", schema)
	var row int
	err := db.QueryRow(query, table).Scan(&row)
	if errors.Is(err, sql.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

func exec(db *sql.DB, query string, args ...any) error {
	_, err := db.Exec(query, args...)
	return err
}

func mergeLocale(db *sql.DB, locale, srcPath string, includeFetchLog bool) error {
	if err := exec(db, "ATTACH ? AS src", srcPath); err != nil {
		return err
	}
	defer func() {
		_ = exec(db, "DETACH src")
	}()

	if err := exec(db, "BEGIN"); err != nil {
		return err
	}
	rollback := func(err error) error {
		_ = exec(db, "ROLLBACK")
		return err
	}

	if err := exec(db, "INSERT OR IGNORE INTO manufacturers(id, name, logo_path, country_id) SELECT id, name, logo_path, country_id FROM src.manufacturers"); err != nil {
		return rollback(err)
	}
	if err := exec(db, "INSERT OR IGNORE INTO manufacturer_i18n(id, locale, name) SELECT id, locale, name FROM src.manufacturer_i18n"); err != nil {
		return rollback(err)
	}
	if err := exec(db, "INSERT OR IGNORE INTO aspiration_codes(code, default_name) SELECT code, default_name FROM src.aspiration_codes"); err != nil {
		return rollback(err)
	}
	if err := exec(db, "INSERT OR IGNORE INTO drivetrain_codes(code, default_name) SELECT code, default_name FROM src.drivetrain_codes"); err != nil {
		return rollback(err)
	}
	if err := exec(db,
		"INSERT OR IGNORE INTO cars(id, name, manufacturer_id, aspiration_code, drivetrain_code, intro, detail, car_class, pp, year, raw_json) "+
			"SELECT id, name, manufacturer_id, aspiration_code, drivetrain_code, intro, detail, car_class, pp, year, raw_json FROM src.cars"); err != nil {
		return rollback(err)
	}

	if err := exec(db, "DELETE FROM aspiration_i18n WHERE locale=?", locale); err != nil {
		return rollback(err)
	}
	if err := exec(db, "INSERT INTO aspiration_i18n(code, locale, label) SELECT code, locale, label FROM src.aspiration_i18n WHERE locale=?", locale); err != nil {
		return rollback(err)
	}
	if err := exec(db, "DELETE FROM drivetrain_i18n WHERE locale=?", locale); err != nil {
		return rollback(err)
	}
	if err := exec(db, "INSERT INTO drivetrain_i18n(code, locale, label) SELECT code, locale, label FROM src.drivetrain_i18n WHERE locale=?", locale); err != nil {
		return rollback(err)
	}
	if err := exec(db, "DELETE FROM spec_code_i18n WHERE locale=?", locale); err != nil {
		return rollback(err)
	}
	if err := exec(db, "INSERT INTO spec_code_i18n(code, locale, label) SELECT code, locale, label FROM src.spec_code_i18n WHERE locale=?", locale); err != nil {
		return rollback(err)
	}
	if err := exec(db, "DELETE FROM car_texts WHERE locale=?", locale); err != nil {
		return rollback(err)
	}
	if err := exec(db, "INSERT INTO car_texts(car_id, locale, name, intro, detail) SELECT car_id, locale, name, intro, detail FROM src.car_texts WHERE locale=?", locale); err != nil {
		return rollback(err)
	}
	if err := exec(db, "DELETE FROM car_specs WHERE locale=?", locale); err != nil {
		return rollback(err)
	}
	if err := exec(db, "INSERT INTO car_specs(car_id, locale, spec_key, spec_value, spec_unit, spec_raw, sort_order) SELECT car_id, locale, spec_key, spec_value, spec_unit, spec_raw, sort_order FROM src.car_specs WHERE locale=?", locale); err != nil {
		return rollback(err)
	}

	if includeFetchLog {
		if err := exec(db, "DELETE FROM fetch_log WHERE locale=?", locale); err != nil {
			return rollback(err)
		}
		if err := exec(db, "INSERT INTO fetch_log(car_id, locale, status, message, updated_at) SELECT car_id, locale, status, message, updated_at FROM src.fetch_log WHERE locale=?", locale); err != nil {
			return rollback(err)
		}
	}

	targetHasImages, err := tableExists(db, "main", "car_images")
	if err != nil {
		return rollback(err)
	}
	sourceHasImages, err := tableExists(db, "src", "car_images")
	if err != nil {
		return rollback(err)
	}
	if targetHasImages && sourceHasImages {
		if err := exec(db,
			"INSERT INTO car_images(car_id, image_path, sort_order, image_type) "+
				"SELECT s.car_id, s.image_path, s.sort_order, s.image_type "+
				"FROM src.car_images s WHERE NOT EXISTS ("+
				"SELECT 1 FROM car_images d WHERE d.car_id=s.car_id AND d.image_path=s.image_path "+
				"AND COALESCE(d.image_type,'')=COALESCE(s.image_type,''))"); err != nil {
			return rollback(err)
		}
	}

	return exec(db, "COMMIT")
}

func copyFile(src, dst string) error {
	input, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, input, 0o644)
}

func main() {
	var outDir string
	var baseLocale string
	var localesRaw string
	var combinedDB string
	var includeFetchLog bool
	var checkpoint bool

	flag.StringVar(&outDir, "out-dir", "./output", "Directory containing per-locale DB files")
	flag.StringVar(&baseLocale, "base-locale", "gb", "Base locale DB used as merge template")
	flag.StringVar(&localesRaw, "locales", "", "Comma-separated locales to merge (empty=auto-discover)")
	flag.StringVar(&combinedDB, "combined-db", "", "Output combined DB path (empty=<out-dir>/gt7.db)")
	flag.BoolVar(&includeFetchLog, "include-fetch-log", true, "Include fetch_log rows")
	flag.BoolVar(&checkpoint, "checkpoint", true, "Run WAL checkpoint at end")
	flag.Parse()

	if combinedDB == "" {
		combinedDB = filepath.Join(outDir, "gt7.db")
	}
	locales := parseLocales(localesRaw)
	if len(locales) == 0 {
		discovered, err := discoverLocales(outDir)
		must(err)
		locales = discovered
	}
	if len(locales) == 0 {
		must(errors.New("no locale dbs found"))
	}
	if !slices.Contains(locales, baseLocale) {
		must(fmt.Errorf("base locale %q not in locales %v", baseLocale, locales))
	}
	ordered := normalizeLocaleOrder(locales, baseLocale)
	baseDB := filepath.Join(outDir, fmt.Sprintf("gt7.%s.db", baseLocale))
	if _, err := os.Stat(baseDB); err != nil {
		must(fmt.Errorf("base db missing: %s", baseDB))
	}
	if err := copyFile(baseDB, combinedDB); err != nil {
		must(err)
	}

	db, err := sql.Open("sqlite", combinedDB)
	must(err)
	defer db.Close()
	must(exec(db, "PRAGMA journal_mode=WAL"))
	must(exec(db, "PRAGMA synchronous=NORMAL"))

	for _, locale := range ordered {
		if locale == baseLocale {
			continue
		}
		srcDB := filepath.Join(outDir, fmt.Sprintf("gt7.%s.db", locale))
		if _, err := os.Stat(srcDB); err != nil {
			must(fmt.Errorf("locale db missing: %s", srcDB))
		}
		must(mergeLocale(db, locale, srcDB, includeFetchLog))
	}

	must(exec(db,
		"INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
		"build_base_locale",
		baseLocale,
	))
	must(exec(db,
		"INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
		"build_locales",
		`["`+strings.Join(ordered, `","`)+`"]`,
	))
	if checkpoint {
		must(exec(db, "PRAGMA wal_checkpoint(TRUNCATE)"))
		must(exec(db, "PRAGMA journal_mode=DELETE"))
	}

	fmt.Printf("merged locales=%s base=%s into %s\n", strings.Join(ordered, ","), baseLocale, combinedDB)
}
