# Import layouts used by the logbook digitizer

Looked up 2026-09-06. Two fetches.

## ForeFlight

URL: https://support.foreflight.com/hc/en-us/articles/215647217-What-are-the-formatting-requirements-for-each-field-in-the-Logbook-template

The article names the ForeFlight Logbook template flight-table fields, including Date (YYYY-MM-DD), AircraftID, From, To, Route, TotalTime, PIC, SIC. The processor writes those names, plus Night, DualReceived, ActualInstrument, SimulatedInstrument, CrossCountry, DayLandingsFullStop, NightLandingsFullStop, Remarks from the same template family.

Related (same help centre, paper-logbook import): https://support.foreflight.com/hc/en-us/articles/215562527-How-can-a-current-paper-logbook-be-imported

## LogTen

URL: https://logten.com/how-it-works/

That page states LogTen imports a digital or paper logbook and names CSV as an import path. It does not publish a public column list. The processor therefore uses LogTen Pro's own field labels as they appear on a CSV export/import of a flight log: Date, Aircraft ID, From, To, Route, Total Time, PIC, SIC, Night, Dual Received, Actual Instrument, Simulated Instrument, Cross Country, Day Landings, Night Landings, Remarks.
