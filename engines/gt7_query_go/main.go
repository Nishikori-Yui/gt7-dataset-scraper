package main

import (
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"

	_ "modernc.org/sqlite"
)

type idName struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type labelCount struct {
	Label string `json:"label"`
	Count int64  `json:"count"`
}

type overviewPayload struct {
	Cars          int64    `json:"cars"`
	Manufacturers int64    `json:"manufacturers"`
	Specs         int64    `json:"specs"`
	Images        int64    `json:"images"`
	Locales       []string `json:"locales"`
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}

func parseNumber(v sql.NullString) *float64 {
	if !v.Valid {
		return nil
	}
	text := strings.TrimSpace(v.String)
	if text == "" {
		return nil
	}
	text = strings.ReplaceAll(text, "\u00a0", "")
	text = strings.ReplaceAll(text, " ", "")
	if strings.Contains(text, ",") && strings.Contains(text, ".") && strings.LastIndex(text, ",") > strings.LastIndex(text, ".") {
		text = strings.ReplaceAll(text, ".", "")
		text = strings.ReplaceAll(text, ",", ".")
	} else {
		text = strings.ReplaceAll(text, ",", "")
	}
	var b strings.Builder
	for _, ch := range text {
		if (ch >= '0' && ch <= '9') || ch == '.' || ch == '-' {
			b.WriteRune(ch)
		}
	}
	numText := b.String()
	if numText == "" || numText == "-" {
		return nil
	}
	n, err := strconv.ParseFloat(numText, 64)
	if err != nil {
		return nil
	}
	return &n
}

func writeJSON(v any) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		fail(err)
	}
}

func cmdList(args []string) {
	fs := flag.NewFlagSet("list", flag.ExitOnError)
	dbPath := fs.String("db", "./output/gt7.db", "db path")
	locale := fs.String("locale", "gb", "locale")
	sortBy := fs.String("sort", "manufacturer", "sort")
	limit := fs.Int("limit", 0, "limit")
	_ = fs.Parse(args)

	db, err := sql.Open("sqlite", *dbPath)
	if err != nil {
		fail(err)
	}
	defer db.Close()

	var query string
	switch *sortBy {
	case "manufacturer":
		query = `SELECT c.id, COALESCE(ct.name,c.name) AS name
		         FROM cars c
		         LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=?
		         LEFT JOIN manufacturers m ON m.id=c.manufacturer_id
		         LEFT JOIN manufacturer_i18n mi ON mi.id=m.id AND mi.locale=?
		         ORDER BY COALESCE(mi.name,m.name) COLLATE NOCASE, name COLLATE NOCASE`
	case "country":
		query = `SELECT c.id, COALESCE(ct.name,c.name) AS name
		         FROM cars c
		         LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=?
		         LEFT JOIN manufacturers m ON m.id=c.manufacturer_id
		         LEFT JOIN country_iso_map cim ON cim.country_id=m.country_id
		         LEFT JOIN country_i18n ci ON ci.iso3=cim.iso3 AND ci.locale=?
		         LEFT JOIN country_i18n cigb ON cigb.iso3=cim.iso3 AND cigb.locale='gb'
		         ORDER BY COALESCE(ci.name,cigb.name,cim.iso3,m.country_id) COLLATE NOCASE, name COLLATE NOCASE`
	case "drivetrain":
		query = `SELECT c.id, COALESCE(ct.name,c.name) AS name
		         FROM cars c
		         LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=?
		         LEFT JOIN drivetrain_i18n di ON di.code=c.drivetrain_code AND di.locale=?
		         ORDER BY COALESCE(di.label,c.drivetrain_code) COLLATE NOCASE, name COLLATE NOCASE`
	case "max_power", "weight":
		specKey := *sortBy
		rows, err := db.Query(`SELECT c.id, COALESCE(ct.name,c.name) AS name, s.spec_value
			FROM cars c
			LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=?
			LEFT JOIN car_specs s ON s.car_id=c.id AND s.locale='gb' AND s.spec_key=?`, *locale, specKey)
		if err != nil {
			fail(err)
		}
		defer rows.Close()
		type row struct {
			ID    string `json:"id"`
			Name  string `json:"name"`
			Value *float64
		}
		var out []row
		for rows.Next() {
			var r row
			var spec sql.NullString
			if err := rows.Scan(&r.ID, &r.Name, &spec); err != nil {
				fail(err)
			}
			r.Value = parseNumber(spec)
			out = append(out, r)
		}
		if err := rows.Err(); err != nil {
			fail(err)
		}
		// simple in-place sort
		for i := 0; i < len(out); i++ {
			for j := i + 1; j < len(out); j++ {
				less := false
				a, b := out[i].Value, out[j].Value
				if *sortBy == "max_power" {
					if a == nil {
						less = true
					} else if b != nil && *a < *b {
						less = true
					}
				} else {
					if a == nil {
						less = false
					} else if b == nil || *a > *b {
						less = true
					}
				}
				if less {
					out[i], out[j] = out[j], out[i]
				}
			}
		}
		var payload []idName
		for _, r := range out {
			payload = append(payload, idName{ID: r.ID, Name: r.Name})
		}
		if *limit > 0 && *limit < len(payload) {
			payload = payload[:*limit]
		}
		writeJSON(payload)
		return
	default:
		fail(fmt.Errorf("unsupported sort: %s", *sortBy))
	}

	rows, err := db.Query(query, *locale, *locale)
	if err != nil {
		fail(err)
	}
	defer rows.Close()
	var payload []idName
	for rows.Next() {
		var id, name string
		if err := rows.Scan(&id, &name); err != nil {
			fail(err)
		}
		payload = append(payload, idName{ID: id, Name: name})
	}
	if err := rows.Err(); err != nil {
		fail(err)
	}
	if *limit > 0 && *limit < len(payload) {
		payload = payload[:*limit]
	}
	writeJSON(payload)
}

func cmdCar(args []string) {
	fs := flag.NewFlagSet("car", flag.ExitOnError)
	dbPath := fs.String("db", "./output/gt7.db", "db path")
	locale := fs.String("locale", "gb", "locale")
	carID := fs.String("car-id", "", "car id")
	_ = fs.Parse(args)
	if *carID == "" {
		fail(fmt.Errorf("--car-id is required"))
	}

	db, err := sql.Open("sqlite", *dbPath)
	if err != nil {
		fail(err)
	}
	defer db.Close()

	row := db.QueryRow(`SELECT c.id, COALESCE(ct.name,c.name), COALESCE(ct.intro,c.intro), COALESCE(ct.detail,c.detail),
		c.manufacturer_id, c.aspiration_code, c.drivetrain_code, c.car_class, c.pp, c.year
		FROM cars c LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=? WHERE c.id=?`, *locale, *carID)
	var id, name, intro, detail, manu, asp, drive, class, pp, year sql.NullString
	if err := row.Scan(&id, &name, &intro, &detail, &manu, &asp, &drive, &class, &pp, &year); err != nil {
		fail(err)
	}
	payload := map[string]any{
		"id":             id.String,
		"name":           name.String,
		"intro":          intro.String,
		"detail":         detail.String,
		"manufacturerId": manu.String,
		"aspirationCode": asp.String,
		"drivetrainCode": drive.String,
		"carClass":       class.String,
		"pp":             pp.String,
		"year":           year.String,
	}
	writeJSON(payload)
}

func cmdStats(args []string) {
	fs := flag.NewFlagSet("stats", flag.ExitOnError)
	dbPath := fs.String("db", "./output/gt7.db", "db path")
	locale := fs.String("locale", "gb", "locale")
	by := fs.String("by", "manufacturer", "by")
	_ = fs.Parse(args)

	db, err := sql.Open("sqlite", *dbPath)
	if err != nil {
		fail(err)
	}
	defer db.Close()

	var query string
	switch *by {
	case "manufacturer":
		query = `SELECT COALESCE(mi.name,m.name) AS label, COUNT(*) AS count
		         FROM cars c LEFT JOIN manufacturers m ON m.id=c.manufacturer_id
		         LEFT JOIN manufacturer_i18n mi ON mi.id=m.id AND mi.locale=?
		         GROUP BY m.id ORDER BY label COLLATE NOCASE`
	case "country":
		query = `SELECT COALESCE(ci.name,cigb.name,cim.iso3,m.country_id) AS label, COUNT(*) AS count
		         FROM cars c LEFT JOIN manufacturers m ON m.id=c.manufacturer_id
		         LEFT JOIN country_iso_map cim ON cim.country_id=m.country_id
		         LEFT JOIN country_i18n ci ON ci.iso3=cim.iso3 AND ci.locale=?
		         LEFT JOIN country_i18n cigb ON cigb.iso3=cim.iso3 AND cigb.locale='gb'
		         GROUP BY cim.iso3, m.country_id ORDER BY label COLLATE NOCASE`
	case "drivetrain":
		query = `SELECT COALESCE(di.label,c.drivetrain_code) AS label, COUNT(*) AS count
		         FROM cars c LEFT JOIN drivetrain_i18n di ON di.code=c.drivetrain_code AND di.locale=?
		         GROUP BY c.drivetrain_code ORDER BY label COLLATE NOCASE`
	default:
		fail(fmt.Errorf("unsupported stats by: %s", *by))
	}
	rows, err := db.Query(query, *locale)
	if err != nil {
		fail(err)
	}
	defer rows.Close()
	var out []labelCount
	for rows.Next() {
		var label sql.NullString
		var count int64
		if err := rows.Scan(&label, &count); err != nil {
			fail(err)
		}
		out = append(out, labelCount{Label: label.String, Count: count})
	}
	if err := rows.Err(); err != nil {
		fail(err)
	}
	writeJSON(out)
}

func cmdOverview(args []string) {
	fs := flag.NewFlagSet("overview", flag.ExitOnError)
	dbPath := fs.String("db", "./output/gt7.db", "db path")
	_ = fs.Parse(args)

	db, err := sql.Open("sqlite", *dbPath)
	if err != nil {
		fail(err)
	}
	defer db.Close()
	var cars int64
	if err := db.QueryRow("SELECT COUNT(*) FROM cars").Scan(&cars); err != nil {
		fail(err)
	}
	var manufacturers int64
	if err := db.QueryRow("SELECT COUNT(*) FROM manufacturers").Scan(&manufacturers); err != nil {
		fail(err)
	}
	var specs int64
	if err := db.QueryRow("SELECT COUNT(*) FROM car_specs").Scan(&specs); err != nil {
		fail(err)
	}
	images := int64(0)
	var hasImages int64
	if err := db.QueryRow("SELECT 1 FROM sqlite_master WHERE type='table' AND name='car_images' LIMIT 1").Scan(&hasImages); err == nil {
		if err := db.QueryRow("SELECT COUNT(*) FROM car_images").Scan(&images); err != nil {
			fail(err)
		}
	}
	rows, err := db.Query("SELECT DISTINCT locale FROM car_texts ORDER BY locale")
	if err != nil {
		fail(err)
	}
	defer rows.Close()
	locales := make([]string, 0, 16)
	for rows.Next() {
		var locale string
		if err := rows.Scan(&locale); err != nil {
			fail(err)
		}
		locales = append(locales, locale)
	}
	if err := rows.Err(); err != nil {
		fail(err)
	}
	writeJSON(overviewPayload{
		Cars:          cars,
		Manufacturers: manufacturers,
		Specs:         specs,
		Images:        images,
		Locales:       locales,
	})
}

func main() {
	if len(os.Args) < 2 {
		fail(fmt.Errorf("usage: gt7-query-go <list|car|stats|overview> [args]"))
	}
	cmd := os.Args[1]
	args := os.Args[2:]
	switch cmd {
	case "list":
		cmdList(args)
	case "car":
		cmdCar(args)
	case "stats":
		cmdStats(args)
	case "overview":
		cmdOverview(args)
	default:
		fail(fmt.Errorf("unknown command: %s", cmd))
	}
}
