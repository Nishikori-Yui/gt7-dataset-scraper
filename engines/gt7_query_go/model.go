package main

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

type manufacturerPayload struct {
	ID   *string `json:"id"`
	Name *string `json:"name"`
}

type countryPayload struct {
	CountryID *string `json:"country_id"`
	ISO3      *string `json:"iso3"`
	Name      *string `json:"name"`
}

type codeLabelPayload struct {
	Code  *string `json:"code"`
	Label *string `json:"label"`
}

type specPayload struct {
	SpecKey   *string `json:"spec_key"`
	SpecLabel *string `json:"spec_label"`
	SpecValue *string `json:"spec_value"`
	SpecUnit  *string `json:"spec_unit"`
	SpecRaw   *string `json:"spec_raw"`
	SortOrder *int64  `json:"sort_order"`
}

type imagePayload struct {
	ImageType *string `json:"image_type"`
	ImagePath *string `json:"image_path"`
	SortOrder *int64  `json:"sort_order"`
}

type carPayload struct {
	ID           string              `json:"id"`
	Name         string              `json:"name"`
	Manufacturer manufacturerPayload `json:"manufacturer"`
	Country      countryPayload      `json:"country"`
	Drivetrain   codeLabelPayload    `json:"drivetrain"`
	Aspiration   codeLabelPayload    `json:"aspiration"`
	Intro        *string             `json:"intro"`
	Detail       *string             `json:"detail"`
	Specs        []specPayload       `json:"specs"`
	Images       []imagePayload      `json:"images"`
}
