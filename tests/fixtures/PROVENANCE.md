# Herkunft der Fixtures

**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**

Aufgezeichnet am **2026-08-28**.

Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht
mehr zu unterscheiden — die Datei sieht gleich aus.

## Die Anfragen baut der Produktivcode

Das Skript ruft `ElComSparqlClient` und `DashboardClient` auf und faengt
die Antwort ueber einen httpx-Transport ab, statt die SPARQL-Abfragen
daneben noch einmal zu tippen. Eine Fixture, die eine leicht andere Frage
beantwortet als der Server stellt, belegt die falsche Antwort — und zwar
unauffaellig, weil sie plausibel aussieht. Bei 40 Zeilen SPARQL ist
«leicht anders» der Normalfall, nicht die Ausnahme.

Die vollstaendige Abfrage steht deshalb in der `url` jeder Datei unten.

**Es sind Ausschnitte, keine Vollabzuege.** Wo eine Suche gekuerzt ist,
bleibt `count` auf dem echten Wert: Er sagt, wie viel **nicht** in der
Datei steht.

**Feste Gemeinde:** BFS 261 (Zürich). Eine Auswahl, die vom Ort
oder Tag des Laufs abhaengt, erzeugt bei jedem Aufzeichnen einen anderen
Diff und laesst sich nicht mehr nachvollziehen.

## `lindas_tariffs_municipality.json`

- **Quelle:** `https://lindas.admin.ch/query?query=%0APREFIX+schema%3A+%3Chttp%3A%2F%2Fschema.org%2F%3E%0APREFIX+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E%0ASELECT+%3Fperiod+%3FcategoryCode+%3FproductLabel+%3Foperator+%3FoperatorLabel%0A+++++++%3Ftotal+%3Fenergy+%3Fgridusage+%3Fcharge+%3Faidfee%0A+++++++%3FenergyName+%3FgridusageName+%3FmunLabel%0AWHERE+%7B%0A++%3Fobs+%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fperiod%3E+%3Fperiod+%3B%0A+++++++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fmunicipality%3E+%3Chttps%3A%2F%2Fld.admin.ch%2Fmunicipality%2F261%3E+%3B%0A+++++++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fcategory%3E+%3Fcategory+%3B%0A+++++++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Foperator%3E+%3Foperator+%3B%0A+++++++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fproduct%3E+%3Fproduct+%3B%0A+++++++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Ftotal%3E+%3Ftotal+.%0A++OPTIONAL+%7B+%3Fobs+%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fenergy%3E+%3Fenergy+%7D%0A++OPTIONAL+%7B+%3Fobs+%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fgridusage%3E+%3Fgridusage+%7D%0A++OPTIONAL+%7B+%3Fobs+%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fcharge%3E+%3Fcharge+%7D%0A++OPTIONAL+%7B+%3Fobs+%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Faidfee%3E+%3Faidfee+%7D%0A++OPTIONAL+%7B+%3Fobs+%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fenergyname%3E+%3FenergyName+%7D%0A++OPTIONAL+%7B+%3Fobs+%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fgridusagename%3E+%3FgridusageName+%7D%0A++BIND%28REPLACE%28STR%28%3Fcategory%29%2C+%22.%2A%2F%22%2C+%22%22%29+AS+%3FcategoryCode%29%0A++BIND%28REPLACE%28STR%28%3Fproduct%29%2C+%22.%2A%2F%22%2C+%22%22%29+AS+%3FproductLabel%29%0A++OPTIONAL+%7B+%3Chttps%3A%2F%2Fld.admin.ch%2Fmunicipality%2F261%3E+schema%3Aname+%3FmunLabel+%7D%0A++OPTIONAL+%7B+%3Foperator+schema%3Aname+%3FoperatorLabel+%7D%0A++%0A++FILTER%28xsd%3Ainteger%28REPLACE%28STR%28%3Fperiod%29%2C+%22%5E%28-%3F%5B0-9%5D%2B%29.%2A%24%22%2C+%22%241%22%29%29+%3E%3D+2019%29+%0A%7D%0AORDER+BY+DESC%28%3Fperiod%29+%3FcategoryCode%0ALIMIT+5%0A`
- **Aufgezeichnet:** 2026-08-28
- **Auswahl:** Tarife der Gemeinde Zürich (BFS 261) ab 2019, 5 Zeilen bei LIMIT 5. Die SPARQL-Abfrage stammt aus `get_tariffs_by_municipality` und ist nicht daneben nachgebaut
- **Groesse:** 8822 B
- **SHA-256:** `418ebcc7d750066b91c98e36b895210347081c833b91b97fd25196180e781afc`

## `lindas_median_swiss.json`

- **Quelle:** `https://lindas.admin.ch/query?query=%0APREFIX+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E%0ASELECT+%3Fperiod+%3FcategoryCode+%3Ftotal%0AWHERE+%7B%0A++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice-swiss%3E+%3Chttps%3A%2F%2Fcube.link%2FobservationSet%3E+%3Fset+.%0A++%3Fset+%3Chttps%3A%2F%2Fcube.link%2Fobservation%3E+%3Fobs+.%0A++%3Fobs+%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fperiod%3E+%3Fperiod+%3B%0A+++++++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fcategory%3E+%3Fcategory+%3B%0A+++++++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Ftotal%3E+%3Ftotal+.%0A++BIND%28REPLACE%28STR%28%3Fcategory%29%2C+%22.%2A%2F%22%2C+%22%22%29+AS+%3FcategoryCode%29%0A++%0A++FILTER%28xsd%3Ainteger%28REPLACE%28STR%28%3Fperiod%29%2C+%22%5E%28-%3F%5B0-9%5D%2B%29.%2A%24%22%2C+%22%241%22%29%29+%3E%3D+2019%29+%0A%7D%0AORDER+BY+DESC%28%3Fperiod%29+%3FcategoryCode%0ALIMIT+5%0A`
- **Aufgezeichnet:** 2026-08-28
- **Auswahl:** Schweizer Medianpreise ab 2019, 5 Zeilen bei LIMIT 5; Abfrage aus `get_median_swiss`
- **Groesse:** 2180 B
- **SHA-256:** `0cdc99561cfc8ec222373b003834982443ca23c2be65b9f3c6809191e85c8a8e`

## `lindas_median_canton.json`

- **Quelle:** `https://lindas.admin.ch/query?query=%0APREFIX+schema%3A+%3Chttp%3A%2F%2Fschema.org%2F%3E%0APREFIX+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E%0ASELECT+%3Fperiod+%3FcategoryCode+%3Ftotal+%3FcantonLabel%0AWHERE+%7B%0A++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice-canton%3E+%3Chttps%3A%2F%2Fcube.link%2FobservationSet%3E+%3Fset+.%0A++%3Fset+%3Chttps%3A%2F%2Fcube.link%2Fobservation%3E+%3Fobs+.%0A++%3Fobs+%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fperiod%3E+%3Fperiod+%3B%0A+++++++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fcanton%3E+%3FcantonURI+%3B%0A+++++++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Fcategory%3E+%3Fcategory+%3B%0A+++++++%3Chttps%3A%2F%2Fenergy.ld.admin.ch%2Felcom%2Felectricityprice%2Fdimension%2Ftotal%3E+%3Ftotal+.%0A++%3FcantonURI+schema%3Aname+%3FcantonLabel+.%0A++FILTER%28STR%28%3FcantonLabel%29+%3D+%22Luzern%22%29%0A++BIND%28REPLACE%28STR%28%3Fcategory%29%2C+%22.%2A%2F%22%2C+%22%22%29+AS+%3FcategoryCode%29%0A++%0A++FILTER%28xsd%3Ainteger%28REPLACE%28STR%28%3Fperiod%29%2C+%22%5E%28-%3F%5B0-9%5D%2B%29.%2A%24%22%2C+%22%241%22%29%29+%3E%3D+2019%29+%0A%7D%0AORDER+BY+DESC%28%3Fperiod%29+%3FcategoryCode%0ALIMIT+5%0A`
- **Aufgezeichnet:** 2026-08-28
- **Auswahl:** Medianpreise des Kantons Luzern ab 2019, 5 Zeilen bei LIMIT 5; Abfrage aus `get_median_canton`
- **Groesse:** 2805 B
- **SHA-256:** `3a89de8e71b6427b053e5d14e5b5e25e8533b02a20c9b48401292e2187177740`

## `dashboard_production_mix.json`

- **Quelle:** `https://www.energiedashboard.admin.ch/api/strom/strom-produktionsmix`
- **Aufgezeichnet:** 2026-08-28
- **Auswahl:** Objekt mit den Schluesseln ['2022', '2023', '2024', '2025', '2026', 'date', 'isUpToDate'] — vollstaendig, wie die Quelle sie liefert
- **Groesse:** 2180 B
- **SHA-256:** `89e6ff25c71f0b5d5305e7a8c9ee48b5c723e04467a12e11d437aeda98c9879b`

## `dashboard_consumption_forecast.json`

- **Quelle:** `https://www.energiedashboard.admin.ch/api/strom/v2/strom-verbrauch/landesverbrauch-mit-prognose`
- **Aufgezeichnet:** 2026-08-28
- **Auswahl:** Objekt mit den Schluesseln ['currentEntry', 'entries', 'isUpToDate'] — Zeitreihen gekuerzt (`entries` von 378 auf 15: die letzten 12 mit `landesverbrauch` plus 3 der 253 Zeilen ohne). Die Zeilen ohne Messung bleiben absichtlich drin: Der Produktivcode schneidet mit `entries[-limit_weeks:]`, und ohne sie liesse sich nicht pruefen, dass er sie ueberspringt
- **Groesse:** 5210 B
- **SHA-256:** `d2196f436d85b1af288eb45e77b8601205e186b6f14fb97ff0422313b80835fe`

## `dashboard_storage_lakes.json`

- **Quelle:** `https://www.energiedashboard.admin.ch/api/strom/v2/fuellungsgrad-speicherseen`
- **Aufgezeichnet:** 2026-08-28
- **Auswahl:** Objekt mit den Schluesseln ['graubuenden', 'tessin', 'totalCH', 'uebrigCH', 'wallis'] — Zeitreihen gekuerzt (`totalCH.entries` von 455 auf 15: die letzten 12 mit `speicherstandProzent` plus 3 der 94 Zeilen ohne; `uebrigCH.entries` von 455 auf 15: die letzten 12 mit `speicherstandProzent` plus 3 der 94 Zeilen ohne; `graubuenden.entries` von 455 auf 15: die letzten 12 mit `speicherstandProzent` plus 3 der 94 Zeilen ohne; `wallis.entries` von 455 auf 15: die letzten 12 mit `speicherstandProzent` plus 3 der 94 Zeilen ohne; `tessin.entries` von 455 auf 15: die letzten 12 mit `speicherstandProzent` plus 3 der 94 Zeilen ohne). Die Zeilen ohne Messung bleiben absichtlich drin: Der Produktivcode schneidet mit `entries[-limit_weeks:]`, und ohne sie liesse sich nicht pruefen, dass er sie ueberspringt
- **Groesse:** 33469 B
- **SHA-256:** `f7af7ba04d9390b4824b7f03985f3004332c298455440b7290aab1179d99ebd8`

## `dashboard_consumer_price_index.json`

- **Quelle:** `https://www.energiedashboard.admin.ch/api/preise/strom-endverbrauch`
- **Aufgezeichnet:** 2026-08-28
- **Auswahl:** Liste mit 79 Eintraegen — vollstaendig, wie die Quelle sie liefert
- **Groesse:** 8717 B
- **SHA-256:** `9c8e19f9c08175d0e1d1fe2dcd7b6ad78d105165dde99b7587c1989e8819dce7`

## `ckan_opendata_swiss_search.json`

- **Quelle:** `https://opendata.swiss/api/3/action/package_search?q=strom&rows=3&start=0`
- **Aufgezeichnet:** 2026-08-28
- **Auswahl:** Suche «strom» mit explizitem rows=3; `count` ist der echte Gesamtbestand (75), `results` sind 3
- **Groesse:** 39264 B
- **SHA-256:** `f8d4af0a88008aa6c2af23c521eba24936e4032d059b308e75efa3f03c12ce4b`

## `ckan_zurich_search.json`

- **Quelle:** `https://data.stadt-zuerich.ch/api/3/action/package_search?q=strom&rows=3&start=0`
- **Aufgezeichnet:** 2026-08-28
- **Auswahl:** Suche «strom» mit explizitem rows=3; `count` ist der echte Gesamtbestand (27), `results` sind 3
- **Groesse:** 34519 B
- **SHA-256:** `13cd28dccb3037f98a22929b1d8559a93b632086d99d0c08b97567f632b268e3`
