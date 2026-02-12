# Datei: functions/alerts/alerts_config.py

# Konfiguration der Alerts
# name:            Name der Kategorie in der Datenbank
# label:           Das Label, unter dem die neuen Mails ankommen
# processed_label: Das Label, wohin die Mails verschoben werden (muss in Gmail existieren!)

ALERT_CONFIG = [
    {
        "name": "Carlo Masala",
        "label": "alerts-carlo-masala",
        "processed_label": "alerts-carlo-masala-processed"
    },
    # Hier kannst du später weitere hinzufügen
]

# Links innerhalb der Google-Mail, die wir ignorieren wollen
LINK_BLACKLIST = [
    "google.com/alerts",
    "alerts/remove",
    "alerts/edit",
    "support.google.com",
    "google.com/settings"
]