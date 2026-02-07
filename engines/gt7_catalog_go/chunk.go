package main

import "fmt"

var carExportNames = []string{"CarList", "CarData", "CarCatalog", "CarInfo"}
var tunerExportNames = []string{"TunerList", "Tuners", "TunerData"}
var idListExportNames = []string{"CarIdList", "CarIds"}

func parseObjectChunk(jsText string, exportNames []string) (map[string]any, error) {
	for _, name := range exportNames {
		if parsed, ok := extractExportedLiteral(jsText, name); ok {
			if data, ok := parsed.(map[string]any); ok {
				return data, nil
			}
		}
	}
	if parsed, ok := findLargestLiteral(jsText, '{'); ok {
		if data, ok := parsed.(map[string]any); ok {
			return data, nil
		}
	}
	return nil, fmt.Errorf("failed to parse object chunk")
}

func parseIDListChunk(jsText string) ([]any, error) {
	for _, name := range idListExportNames {
		if parsed, ok := extractExportedLiteral(jsText, name); ok {
			if data, ok := parsed.([]any); ok {
				return data, nil
			}
		}
	}
	if parsed, ok := findLargestLiteral(jsText, '['); ok {
		if data, ok := parsed.([]any); ok {
			return data, nil
		}
	}
	return nil, fmt.Errorf("failed to parse id list chunk")
}

func parseChunk(jsText string, chunkType string) (any, error) {
	switch chunkType {
	case "car":
		return parseObjectChunk(jsText, carExportNames)
	case "tuner":
		return parseObjectChunk(jsText, tunerExportNames)
	case "id_list":
		return parseIDListChunk(jsText)
	default:
		return nil, fmt.Errorf("unsupported chunk_type: %s", chunkType)
	}
}
