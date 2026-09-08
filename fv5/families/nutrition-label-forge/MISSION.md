# nutrition-label-forge — what this sells and to whom

**Sells:** one Nutrition Facts panel, as files, for one named product. $49, paid
once. The buyer gets a private web page carrying the same calculator that sits
free on the public page, with the DRAFT stamp off, plus downloads of the panel
as true vector SVG in the vertical, tabular and linear formats and a JSON copy
of the recipe and the ingredient and allergen text they typed. Delivered within
15 minutes of payment.

**Buyer:** a small US food maker putting a first product on a shelf — cottage
food, farmers' market, a first retail SKU. They have a recipe in grams and a
serving size, and they need a panel plus some confidence about where each number
came from.

**Free, and staying free:** the recipe calculator and the exemption reader on the
family page, 15 pages of reference amounts from the tables in 21 CFR 101.12(b),
and 18 pages that quote the rules in 101.9 and 101.4. The free calculator draws a
complete, correct panel; the only thing $49 removes is the DRAFT stamp and the
only thing it adds is the vector files.

**Guardrails applied, and why each one is there:**

* **No verdicts.** The exemption reader prints the paragraphs of 101.9(j) an
  answer touches and stops. Nothing on any page, free or paid, says whether an
  exemption covers the buyer or whether a panel passes. `selftest.py` enforces
  this as a substring test over everything we wrote.
* **Added sugars is typed, never inferred.** Not one of the 8,156 USDA rows read
  carries an added-sugars figure, so there is nothing honest to derive it from.
* **The ingredient statement and the allergen line are never generated.** There
  is no code here that writes either. A generated allergen line that misses an
  allergen hurts somebody.
* **Database, not laboratory.** Every page says the values come from USDA
  FoodData Central and that 21 CFR 101.9(g) describes a 12-unit lab composite,
  which this is not.
* **Branded FoodData Central rows are excluded.** Those are label data submitted
  by other manufacturers; building a label off them copies someone else's label.
* **The price lives in `catalog.json` only.** No page types it.
