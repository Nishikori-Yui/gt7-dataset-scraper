package main

import (
	"database/sql"
	"flag"
	"fmt"
)

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
