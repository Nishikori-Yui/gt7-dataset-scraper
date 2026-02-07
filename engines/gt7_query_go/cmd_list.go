package main

import (
	"database/sql"
	"flag"
	"fmt"
	"sort"

	_ "modernc.org/sqlite"
)

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
		listBySpecSort(db, *locale, *sortBy, *limit)
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

func listBySpecSort(db *sql.DB, locale string, sortBy string, limit int) {
	rows, err := db.Query(`SELECT c.id, COALESCE(ct.name,c.name) AS name, s.spec_value
		FROM cars c
		LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=?
		LEFT JOIN car_specs s ON s.car_id=c.id AND s.locale='gb' AND s.spec_key=?`, locale, sortBy)
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
	if sortBy == "max_power" {
		sort.SliceStable(out, func(i, j int) bool {
			a, b := out[i].Value, out[j].Value
			aNil, bNil := a == nil, b == nil
			if aNil != bNil {
				return aNil && !bNil
			}
			if aNil && bNil {
				return false
			}
			return *a > *b
		})
	} else {
		sort.SliceStable(out, func(i, j int) bool {
			a, b := out[i].Value, out[j].Value
			aNil, bNil := a == nil, b == nil
			if aNil != bNil {
				return !aNil && bNil
			}
			if aNil && bNil {
				return false
			}
			return *a < *b
		})
	}
	var payload []idName
	for _, r := range out {
		payload = append(payload, idName{ID: r.ID, Name: r.Name})
	}
	if limit > 0 && limit < len(payload) {
		payload = payload[:limit]
	}
	writeJSON(payload)
}
