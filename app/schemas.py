SCHEMA_REGISTRY: dict[str, dict] = {
    "invoice_basic": {
        "description": "Grundlegende Rechnungsfelder.",
        "fields": {
            "vendor": "string",
            "invoice_number": "string",
            "invoice_date": "string",
            "due_date": "string",
            "total": "string",
            "currency": "string",
        },
    },
    "receipt_basic": {
        "description": "Grundlegende Belegfelder.",
        "fields": {
            "merchant": "string",
            "date": "string",
            "total": "string",
            "tax": "string",
            "currency": "string",
        },
    },
    "table_basic": {
        "description": "Tabellenextraktion mit Kopfzeile und Zeilenwerten.",
        "fields": {
            "title": "string",
            "columns": "array<string>",
            "rows": "array<array<string>>",
            "notes": "string",
        },
    },
    "business_card_basic": {
        "description": "Wichtige Felder einer Visitenkarte.",
        "fields": {
            "full_name": "string",
            "role_title": "string",
            "company": "string",
            "email": "string",
            "phone": "string",
            "website": "string",
            "address": "string",
        },
    },
}
